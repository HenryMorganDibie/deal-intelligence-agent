"""
Historical (walk-forward) backtest.

Replays the deterministic engine over past dates, using only what was public on
each as-of date, then checks what happened next. It answers the question a buyer
asks first: when the engine flags something, how often does the event follow,
and how much better is that than chance?

For each company and each as-of date (monthly by default):
  1. Sources published in the 30 days before the as-of date: the company's SEC
     filings (with Form 4 insider trades read from the filing XML), its NGX
     disclosures, and news from date-restricted Google News searches.
  2. The rule engine and static calibration turn them into predictions (adaptive
     calibration is off, so later feedback cannot leak into the past). A signal
     type already predicted for the company in the previous 90 days is not
     counted again.
  3. Each prediction is labelled by what followed: a confirming SEC filing,
     exchange disclosure or credible report strictly after the as-of date and
     within 90 days, and the 5/10/30-day price move net of the market.

Reported per signal type and market: precision (official filings only, and all
sources), recall against every confirmed event, base rate (how often a random
company-month is followed by that event) and lift (precision / base rate),
directional hit rate and mean abnormal return. Results are written to
docs/BACKTEST.md and data/historical_backtest.json.

HTTP responses are cached under data/hist_cache, so a rerun resumes cheaply.
"""
from __future__ import annotations

import hashlib
import json
import logging
import statistics
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from src.schemas.models import AgentState, AnalysisRequest, NewsItem, SECFiling, Severity, SignalType
from src.utils.paths import DATA_DIR

log = logging.getLogger(__name__)

CACHE_DIR = DATA_DIR / "hist_cache"
RESULTS_PATH = DATA_DIR / "historical_backtest.json"
REPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "BACKTEST.md"
SUMMARY_PATH = Path(__file__).resolve().parents[2] / "docs" / "backtest_summary.json"
# Judged on the price reaction only: an earnings release or an insider trade is itself the event.
PRICE_ONLY = {"earnings_surprise", "insider_activity"}

LOOKBACK_DAYS = 30
HORIZON_DAYS = 90
SEC_HEADERS = {"User-Agent": "DealIntelligenceAgent research@dealintel.ai"}

# A balanced universe: companies with eventful periods and steady large caps,
# across the US, JSE, NGX and NSE Kenya.
# (company, ticker, SEC CIK when the ticker no longer resolves: acquired or delisted since)
UNIVERSE: list[tuple] = [
    # US
    ("Intel", "INTC"), ("Boeing", "BA"), ("Starbucks", "SBUX"), ("Nike", "NKE"),
    ("Walgreens", "WBA", "0001618921"), ("Paramount Global", "PARA", "0000813828"), ("CVS Health", "CVS"),
    ("Discover Financial", "DFS", "0001393612"), ("Juniper Networks", "JNPR", "0001043604"),
    ("United States Steel", "X", "0001163302"), ("Kellanova", "K", "0000055067"), ("Southwest Airlines", "LUV"),
    ("Peloton", "PTON"), ("Macy's", "M"), ("Wolfspeed", "WOLF"), ("Spirit AeroSystems", "SPR", "0001364885"),
    ("Apple", "AAPL"), ("Microsoft", "MSFT"), ("Coca-Cola", "KO"), ("Procter & Gamble", "PG"),
    ("Walmart", "WMT"), ("McDonald's", "MCD"), ("PepsiCo", "PEP"), ("Visa", "V"),
    # JSE
    ("Naspers", "NPN.JO"), ("Anglo American", "AGL.JO"), ("Sasol", "SOL.JO"), ("MTN Group", "MTN.JO"),
    ("Standard Bank", "SBK.JO"), ("Shoprite", "SHP.JO"), ("Sibanye Stillwater", "SSW.JO"), ("Vodacom", "VOD.JO"),
    # NGX
    ("Dangote Cement", "DANGCEM.LG"), ("MTN Nigeria", "MTNN.LG"), ("Guaranty Trust Holding", "GTCO.LG"),
    ("Zenith Bank", "ZENITHBANK.LG"), ("Access Holdings", "ACCESSCORP.LG"), ("Seplat Energy", "SEPLAT.LG"),
    ("Nestle Nigeria", "NESTLE.LG"), ("Transcorp", "TRANSCORP.LG"), ("First HoldCo", "FIRSTHOLDCO.LG"), ("UBA", "UBA.LG"),
    # NSE Kenya
    ("Safaricom", "SCOM.NR"), ("Equity Group", "EQTY.NR"), ("KCB Group", "KCB.NR"), ("East African Breweries", "EABL.NR"),
]


# ── Cache ─────────────────────────────────────────────────────────────────────

def _cached(key: str, fetch: Callable[[], Any]) -> Any:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / (hashlib.sha256(key.encode()).hexdigest()[:24] + ".json")
    if path.exists():
        try:
            return json.loads(path.read_text())
        except ValueError:
            pass
    value = fetch()
    if value is not None:
        path.write_text(json.dumps(value, default=sorted))
    return value


# ── Sources ───────────────────────────────────────────────────────────────────

class Sources:
    def __init__(self) -> None:
        self.http = httpx.Client(timeout=30, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"})
        self.sec = httpx.Client(timeout=30, follow_redirects=True, headers=SEC_HEADERS)
        self._last_sec = 0.0

    def _sec_get(self, url: str) -> httpx.Response:
        wait = 0.13 - (time.monotonic() - self._last_sec)   # under SEC's 10 requests/second
        if wait > 0:
            time.sleep(wait)
        self._last_sec = time.monotonic()
        return self.sec.get(url)

    def sec_filings(self, ticker: str, since: date, cik: Optional[str] = None) -> list[dict]:
        """All filings since `since` from EDGAR submissions (paging into older files as needed)."""
        def fetch():
            from src.engines.outcome_labeller import _cik_for
            nonlocal cik
            cik = cik or _cik_for(ticker, self.sec)
            if not cik:
                return []
            data = self._sec_get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()
            blocks = [data.get("filings", {}).get("recent", {})]
            for f in data.get("filings", {}).get("files", []):
                if f.get("filingTo", "9999") >= since.isoformat():
                    blocks.append(self._sec_get(f"https://data.sec.gov/submissions/{f['name']}").json())
            rows = []
            for b in blocks:
                for i, form in enumerate(b.get("form", [])):
                    d = b["filingDate"][i]
                    if d < since.isoformat():
                        continue
                    rows.append({"form": form, "date": d, "items": (b.get("items") or [""] * (i + 1))[i],
                                 "accession": b["accessionNumber"][i], "doc": b["primaryDocument"][i],
                                 "cik": cik, "name": data.get("name", "")})
            return rows
        return _cached(f"sec:{ticker}:{since}", fetch) or []

    def form4_summary(self, row: dict) -> Optional[str]:
        import re
        from src.tools.edgar_tool import describe_form4
        url = (f"https://www.sec.gov/Archives/edgar/data/{int(row['cik'])}/"
               f"{row['accession'].replace('-', '')}/{re.sub(r'^xslF345X[0-9]+/', '', row['doc'])}")

        def fetch():
            try:
                return {"summary": describe_form4(self._sec_get(url).text)}
            except Exception:
                return None
        return (_cached(f"f4:{url}", fetch) or {}).get("summary")

    def ngx_disclosures(self, ticker: str, since: date, until: date) -> list[dict]:
        import re
        from src.engines.event_sources import NGX_DISCLOSURES
        code = ticker.upper().rsplit(".", 1)[0]

        def fetch():
            params = {"$select": "CompanySymbol,CompanyName,Type_of_Submission,Modified,URL",
                      "$filter": f"CompanySymbol eq '{code}' and Modified ge datetime'{since}T00:00:00Z' "
                                 f"and Modified le datetime'{until}T23:59:59Z'",
                      "$orderby": "Modified asc", "$top": "1000"}
            r = self.http.get(NGX_DISCLOSURES, params=params, headers={"Accept": "application/json;odata=verbose"})
            r.raise_for_status()
            out = []
            for row in r.json().get("d", {}).get("results", []):
                url = (row.get("URL") or {}).get("Url", "")
                title = " ".join(re.sub(r"^\d+_", "", url.rsplit("/", 1)[-1].rsplit(".", 1)[0]).replace("_", " ").split())
                out.append({"date": (row.get("Modified") or "")[:10], "type": row.get("Type_of_Submission", ""),
                            "title": title, "url": url, "name": row.get("CompanyName", "")})
            return out
        return _cached(f"ngx:{code}:{since}:{until}", fetch) or []

    def news(self, company: str, since: date, until: date, french: bool) -> list[dict]:
        from src.engines.event_sources import historical_news
        return _cached(f"news:{company}:{since}:{until}:{french}",
                       lambda: historical_news(self.http, company, since, until, french)) or []

    def ngx_events(self, ticker: str, company: str, since: date, until: date) -> list[dict]:
        from src.engines.event_sources import NGX_TYPE_EVENTS, _event, classify
        out = []
        for d in self.ngx_disclosures(ticker, since, until):
            kind = d["type"].replace(" ", "").lower()
            types = classify(d["title"]) | NGX_TYPE_EVENTS.get(kind, set())
            if types:
                out.append(_event(d["date"], f"NGX disclosure: {d['title'][:90]}", types))
        return out


# ── Walk-forward run ──────────────────────────────────────────────────────────

@dataclass
class Prediction:
    company: str
    ticker: str
    market: str
    signal_type: str
    severity: str
    as_of: str
    direction: Optional[str]
    source: str
    source_kind: str            # "filing" | "news"
    alpha: Optional[float] = None


def _as_of_dates(start: date, end: date, step_days: int) -> list[date]:
    out, d = [], start
    while d <= end:
        out.append(d)
        d += timedelta(days=step_days)
    return out


def detect(src: Sources, company: str, ticker: str, as_of: date, sec_rows: list[dict],
           cik: Optional[str] = None) -> list[Prediction]:
    """Run the rule engine on what was public in the LOOKBACK_DAYS before as_of."""
    from src.engines.alpha_scorer import alpha_components, signal_direction
    from src.engines.measured import DIRECTION_HYPOTHESIS
    from src.schemas.models import LiquidityTier
    from src.engines.calibration import calibrate
    from src.engines.deterministic_engine import DeterministicSignalEngine
    from src.engines.outcome_labeller import market_for_ticker
    from src.tools.edgar_tool import SIGNAL_FORMS, _describe_8k_items

    since = as_of - timedelta(days=LOOKBACK_DAYS)
    market = market_for_ticker(ticker)
    filings: list[SECFiling] = []
    for r in sec_rows:
        if not (since.isoformat() <= r["date"] <= as_of.isoformat()) or r["form"] not in SIGNAL_FORMS:
            continue
        desc = _describe_8k_items(r["items"]) if r["form"] == "8-K" and r["items"] else ""
        if r["form"] == "4":
            desc = src.form4_summary(r)
            if not desc:
                continue
        filings.append(SECFiling(accession_number=r["accession"], form_type=r["form"], filing_date=r["date"],
                                 company_name=r["name"], cik=r["cik"], document_url=r["doc"], description=desc))
    if ticker.upper().endswith(".LG"):
        for d in src.ngx_disclosures(ticker, since, as_of):
            filings.append(SECFiling(accession_number=f"NGX-{d['url'][-24:]}", form_type="NGX Disclosure",
                                     filing_date=d["date"], company_name=d["name"] or company, cik="NGX",
                                     document_url=d["url"], description=f"{ticker.split('.')[0]}: {d['type']}: {d['title']}"))
    news = [NewsItem(title=n["title"], source=n["publisher"] or "Google News", published_date=n["date"],
                     url=n["url"], snippet="")
            for n in src.news(company, since, as_of, french=market == "africa")]

    cik = cik or (sec_rows[0]["cik"] if sec_rows else None)
    state = AgentState(request=AnalysisRequest(company_name=company, ticker=ticker, cik=cik,
                                               lookback_days=LOOKBACK_DAYS, as_of_date=as_of.isoformat()))
    state.filings, state.news_items = filings, news
    state = DeterministicSignalEngine().run(state)

    best: dict[SignalType, Any] = {}
    for cand in state.signal_candidates:
        if cand.signal_type not in best or cand.raw_score > best[cand.signal_type].raw_score:
            best[cand.signal_type] = cand
    out = []
    for sig_type, cand in best.items():
        severity, _, _ = calibrate(cand)
        # The direction tested is the type's hypothesis, refined by what the text states (a beat, a
        # purchase); measured moves are not used here, so the test does not grade its own answers.
        direction = signal_direction(sig_type, cand.source_text, DIRECTION_HYPOTHESIS[sig_type.value])
        # Alpha as of the replay date. Liquidity is held constant: today's market caps would leak.
        alpha = alpha_components(severity, cand, LiquidityTier.MID_CAP,
                                 now=datetime.combine(as_of, datetime.min.time()))["score"]
        out.append(Prediction(company, ticker, market, sig_type.value, severity.value, as_of.isoformat(),
                              direction, cand.source_text[:160], cand.source_type, alpha))
    return out


def run(
    start: date, end: date, universe: Optional[list[tuple]] = None, step_days: int = 30,
    progress: Callable[[str], None] = lambda m: None,
) -> dict:
    """Walk forward over [start, end]; label each prediction; compute and save metrics."""
    from src.engines.event_sources import news_events
    from src.engines.outcome_labeller import (
        filing_events, ground_truth, label_prediction, market_for_ticker, confirming_events, NEWS_CONFIRMABLE,
        default_price_moves,
    )

    def price_moves(symbol: str, iso: str) -> dict:
        return _cached(f"px:{symbol}:{iso}", lambda: default_price_moves(symbol, iso)) or {}

    universe = universe or UNIVERSE
    src = Sources()
    today = date.today()
    horizon_end = min(end + timedelta(days=HORIZON_DAYS), today)
    dates = _as_of_dates(start, end, step_days)
    predictions: list[dict] = []
    truth: list[dict] = []
    company_months = 0
    base: dict[str, dict[str, int]] = {}

    truth_dates = _as_of_dates(start, horizon_end, step_days)
    for idx, entry in enumerate(universe, 1):
        company, ticker, cik = (tuple(entry) + (None,))[:3]
        progress(f"[{idx}/{len(universe)}] {company} ({ticker})")
        market = market_for_ticker(ticker)
        sec_rows = src.sec_filings(ticker, start - timedelta(days=LOOKBACK_DAYS), cik) if market == "us" else []

        # Ground truth for the whole span: SEC filings, NGX disclosures, and credible news
        # from the same monthly windows the detection step reads (each fetched once).
        events: list[dict] = []
        if market == "us":
            events += filing_events({"filings": {"recent": {
                "form": [r["form"] for r in sec_rows], "filingDate": [r["date"] for r in sec_rows],
                "items": [r["items"] for r in sec_rows]}}})
        if ticker.upper().endswith(".LG"):
            events += src.ngx_events(ticker, company, start, horizon_end)
        for d in truth_dates:
            events += news_events(src.http, company, d - timedelta(days=LOOKBACK_DAYS), d,
                                  headlines=src.news(company, d - timedelta(days=LOOKBACK_DAYS), d,
                                                     french=market == "africa")) or []
        truth += ground_truth(company, events, start, horizon_end)

        last_seen: dict[str, date] = {}
        for as_of in dates:
            company_months += 1
            # Base rate: is this company-month followed by each event type?
            for st in {e["signal_type"] for e in ground_truth(company, events, as_of + timedelta(days=1),
                                                              as_of + timedelta(days=HORIZON_DAYS))}:
                base.setdefault(st, {}).setdefault(market, 0)
                base[st][market] += 1
            for p in detect(src, company, ticker, as_of, sec_rows, cik):
                prev = last_seen.get(p.signal_type)
                last_seen[p.signal_type] = as_of
                if prev and (as_of - prev).days < HORIZON_DAYS:
                    continue                      # same signal still live: not a new prediction
                o = label_prediction(company_name=company, ticker=ticker, signal_type=SignalType(p.signal_type),
                                     severity=p.severity, detection_date=as_of, expected_direction=p.direction,
                                     events=events, today=today, price_moves=price_moves) or {}
                official = None
                if o.get("event_confirmed") is not None:
                    official_events = [e for e in events if not e.get("signal_types")
                                       or e["source"].startswith(("NGX disclosure", "NSE Kenya disclosure"))]
                    hit = [e for e in confirming_events(official_events, SignalType(p.signal_type))
                           if as_of.isoformat() < e["date"] <= (as_of + timedelta(days=HORIZON_DAYS)).isoformat()]
                    official = bool(hit) if (market == "us" or ticker.upper().endswith(".LG")) else None
                predictions.append({**p.__dict__, "event_confirmed": o.get("event_confirmed"),
                                    "confirmed_by_official_filing": official,
                                    "confirmation_source": o.get("confirmation_source"),
                                    "abnormal_return_10d_pct": o.get("abnormal_return_10d_pct"),
                                    "price_change_10d_pct": o.get("price_change_10d_pct"),
                                    "direction_correct": o.get("direction_correct")})

    metrics = compute_metrics(predictions, truth, base, company_months_by_market(universe, len(dates)))
    result = {"start": start.isoformat(), "end": end.isoformat(), "as_of_dates": len(dates),
              "companies": len(universe), "lookback_days": LOOKBACK_DAYS, "horizon_days": HORIZON_DAYS,
              "predictions": predictions, "ground_truth_events": truth, "metrics": metrics,
              "by_severity": by_severity(predictions), "alpha_validation": alpha_validation(predictions)}
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=1, default=str))
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(result))
    write_tables(result)
    SUMMARY_PATH.write_text(json.dumps({k: result[k] for k in ("start", "end", "as_of_dates", "companies",
                                                                "lookback_days", "horizon_days", "metrics",
                                                                "by_severity", "alpha_validation")},
                                       indent=1, default=str))
    return result


def company_months_by_market(universe: list[tuple], n_dates: int) -> dict[str, int]:
    from src.engines.outcome_labeller import market_for_ticker
    out: dict[str, int] = {}
    for entry in universe:
        t = entry[1]
        m = market_for_ticker(t)
        out[m] = out.get(m, 0) + n_dates
    return out


# ── Metrics ───────────────────────────────────────────────────────────────────

def _rate(num: int, den: int) -> Optional[float]:
    return round(num / den, 3) if den else None


def compute_metrics(predictions: list[dict], truth: list[dict], base: dict, months: dict[str, int]) -> dict:
    """Per signal type, per market ('all', 'us', 'africa')."""
    out: dict[str, dict] = {}
    types = sorted({p["signal_type"] for p in predictions} | {e["signal_type"] for e in truth})
    for st in types:
        out[st] = {}
        for mk in ("all", "us", "africa"):
            ps = [p for p in predictions if p["signal_type"] == st and (mk == "all" or p["market"] == mk)]
            price_only = st in PRICE_ONLY
            labelled = [] if price_only else [p for p in ps if p["event_confirmed"] is not None]
            conf = sum(p["event_confirmed"] for p in labelled)
            off = [] if price_only else [p for p in ps if p["confirmed_by_official_filing"] is not None]
            off_conf = sum(p["confirmed_by_official_filing"] for p in off)
            # Recall: confirmed events preceded by a prediction of the same type within the horizon.
            ev = [e for e in truth if e["signal_type"] == st
                  and (mk == "all" or _market_of_company(e["company_name"], predictions, truth) in (mk, None))]
            caught = sum(1 for e in ev if any(
                p["company"] == e["company_name"] and p["signal_type"] == st
                and 0 < (date.fromisoformat(e["date"]) - date.fromisoformat(p["as_of"])).days <= HORIZON_DAYS
                for p in predictions))
            n_months = sum(months.values()) if mk == "all" else months.get(mk, 0)
            base_hits = sum(base.get(st, {}).values()) if mk == "all" else base.get(st, {}).get(mk, 0)
            base_rate = _rate(base_hits, n_months)
            precision = _rate(conf, len(labelled))
            directional = [p["direction_correct"] for p in ps if p["direction_correct"] is not None]
            abn = [p["abnormal_return_10d_pct"] for p in ps if p["abnormal_return_10d_pct"] is not None]
            out[st][mk] = {
                "predictions": len(ps),
                "labelled": len(labelled),
                "precision": precision,
                "precision_official_filings": _rate(off_conf, len(off)),
                "official_labelled": len(off),
                "events": len(ev),
                "recall": _rate(caught, len(ev)),
                "base_rate": base_rate,
                "lift": round(precision / base_rate, 2) if precision is not None and base_rate else None,
                "price_only": price_only,
                "hit_rate": _rate(sum(directional), len(directional)),
                "directional_n": len(directional),
                "mean_abnormal_return_10d_pct": round(statistics.mean(abn), 2) if abn else None,
            }
    return out


def write_tables(result: dict) -> dict:
    """Measured outcome tables (confirmation rates, moves) for live calibration and expected moves."""
    from src.engines import measured
    tables = measured.build(result["predictions"], {"period": f"{result['start']} to {result['end']}",
                                                    "companies": result["companies"]})
    measured.write(tables)
    measured.set_tables(None)
    return tables


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> Optional[float]:
    if len(xs) < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(num / den, 3) if den else None


def alpha_validation(predictions: list[dict]) -> dict:
    """
    Does a higher alpha go with more confirmed events? Confirmable predictions are split into
    alpha terciles; each tercile's precision and mean absolute market-adjusted move are reported,
    with the rank correlation between alpha and confirmation.
    """
    rows = [p for p in predictions if p.get("alpha") is not None and p["signal_type"] not in PRICE_ONLY
            and p.get("event_confirmed") is not None]
    if len(rows) < 9:
        return {"labelled": len(rows), "note": "too few labelled predictions"}
    alphas = sorted(p["alpha"] for p in rows)
    cut1, cut2 = alphas[len(alphas) // 3], alphas[2 * len(alphas) // 3]
    bands = {"low": [p for p in rows if p["alpha"] < cut1],
             "middle": [p for p in rows if cut1 <= p["alpha"] < cut2],
             "high": [p for p in rows if p["alpha"] >= cut2]}
    out = {"labelled": len(rows), "cutoffs": [cut1, cut2], "bands": {}}
    for name, ps in bands.items():
        moves = [abs(p["abnormal_return_10d_pct"]) for p in ps if p.get("abnormal_return_10d_pct") is not None]
        out["bands"][name] = {"n": len(ps), "alpha_range": [min((p["alpha"] for p in ps), default=None),
                                                             max((p["alpha"] for p in ps), default=None)],
                              "precision": _rate(sum(p["event_confirmed"] for p in ps), len(ps)),
                              "mean_abs_move_10d_pct": round(statistics.mean(moves), 2) if moves else None,
                              "moves_n": len(moves)}
    out["spearman_alpha_vs_confirmed"] = spearman([p["alpha"] for p in rows],
                                                  [float(p["event_confirmed"]) for p in rows])
    # Within each signal type with enough labels: the pooled result could be signal-type mix alone.
    out["by_type"] = {}
    for st in sorted({p["signal_type"] for p in rows}):
        sub = [p for p in rows if p["signal_type"] == st]
        if len(sub) < 30:
            continue
        a = sorted(p["alpha"] for p in sub)
        c1, c2 = a[len(a) // 3], a[2 * len(a) // 3]
        thirds = {"low": [p for p in sub if p["alpha"] < c1], "middle": [p for p in sub if c1 <= p["alpha"] < c2],
                  "high": [p for p in sub if p["alpha"] >= c2]}
        out["by_type"][st] = {"labelled": len(sub),
                              "precision": {k: _rate(sum(p["event_confirmed"] for p in v), len(v)) for k, v in thirds.items()},
                              "spearman": spearman([p["alpha"] for p in sub], [float(p["event_confirmed"]) for p in sub])}
    hi, lo = out["bands"]["high"]["precision"], out["bands"]["low"]["precision"]
    out["verdict"] = ("higher alpha went with more confirmations" if hi is not None and lo is not None and hi > lo
                      else "higher alpha did not go with more confirmations")
    return out


def by_severity(predictions: list[dict]) -> dict:
    """Precision for low-severity flags versus medium and above, per signal type (confirmable types only)."""
    out: dict[str, dict] = {}
    for st in sorted({p["signal_type"] for p in predictions} - PRICE_ONLY):
        row = {}
        for band, sevs in (("medium_plus", {"medium", "high", "critical"}), ("low", {"low"})):
            ps = [p for p in predictions if p["signal_type"] == st and p["severity"] in sevs and p["event_confirmed"] is not None]
            row[band] = {"labelled": len(ps), "precision": _rate(sum(p["event_confirmed"] for p in ps), len(ps))}
        out[st] = row
    return out


def _market_of_company(company: str, predictions: list[dict], truth: list[dict]) -> Optional[str]:
    from src.engines.outcome_labeller import market_for_ticker
    for entry in UNIVERSE:
        if entry[0] == company:
            return market_for_ticker(entry[1])
    return None


def _fmt(v, pct=True) -> str:
    if v is None:
        return "–"
    return f"{v:.0%}" if pct else f"{v}"


def render_report(result: dict) -> str:
    m = result["metrics"]
    lines = [
        "# Historical backtest",
        "",
        f"Walk-forward replay over **{result['start']} to {result['end']}**: {result['companies']} companies "
        f"(US, JSE, NGX, NSE Kenya) x {result['as_of_dates']} monthly as-of dates. On each date the engine sees "
        f"only sources published in the previous {result['lookback_days']} days, and each prediction is judged "
        f"on the {result['horizon_days']} days that followed. Generated by "
        "`python main.py backtest --historical`; raw predictions in `data/historical_backtest.json`.",
        "",
        "**Reading the table.** *Precision*: share of labelled predictions followed by a confirming SEC filing, "
        "exchange disclosure or credible report (strictly after the as-of date). *Official*: the same, counting "
        "only SEC filings and exchange disclosures, which rules out follow-up news about the same story. "
        "*Base rate*: share of all company-months followed by that event anyway. *Lift*: precision / base rate, "
        "how much better a flag is than picking a company-month at random. *Recall*: share of confirmed events "
        "a prediction preceded. *Hit rate*: price moved in the predicted direction net of the market "
        "(10 days). Earnings surprises and insider trades are judged on price only.",
        "",
        "| Signal type | Predictions | Precision | Official | Base rate | Lift | Recall | Hit rate | Abn. return 10d |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for st, by in sorted(m.items()):
        a = by["all"]
        lines.append(
            f"| {st.replace('_', ' ')} | {a['predictions']} | {_fmt(a['precision'])} ({a['labelled']}) | "
            f"{_fmt(a['precision_official_filings'])} ({a['official_labelled']}) | {_fmt(a['base_rate'])} | "
            f"{a['lift'] if a['lift'] is not None else '–'}x | {_fmt(a['recall'])} ({a['events']}) | "
            f"{_fmt(a['hit_rate'])} ({a['directional_n']}) | "
            f"{(str(a['mean_abnormal_return_10d_pct']) + '%') if a['mean_abnormal_return_10d_pct'] is not None else '–'} |")
    lines += ["", "Counts in brackets are the sample behind each figure.", ""]
    sev = result.get("by_severity") or by_severity(result.get("predictions", []))
    if sev:
        lines += ["## By severity", "",
                  "Low-severity flags are the noisy tail; medium and above is the operating point for action.", "",
                  "| Signal type | Precision, medium and above | Precision, low |", "|---|---:|---:|"]
        for st, row in sev.items():
            mp, lo = row["medium_plus"], row["low"]
            lines.append(f"| {st.replace('_', ' ')} | {_fmt(mp['precision'])} ({mp['labelled']}) | "
                         f"{_fmt(lo['precision'])} ({lo['labelled']}) |")
        lines.append("")
    av = result.get("alpha_validation") or alpha_validation(result.get("predictions", []))
    if av.get("bands"):
        lines += ["## Does alpha rank signals?", "",
                  "Confirmable predictions split into thirds by alpha (computed as of each replay date, liquidity "
                  "held constant). If the alpha weights are useful, precision should rise from the low to the "
                  "high third.", "",
                  "| Alpha third | Alpha range | Predictions | Precision | Mean absolute 10-day move |",
                  "|---|---|---:|---:|---:|"]
        for name, b in av["bands"].items():
            rng = b["alpha_range"]
            lines.append(f"| {name} | {rng[0]} to {rng[1]} | {b['n']} | {_fmt(b['precision'])} | "
                         f"{(str(b['mean_abs_move_10d_pct']) + '%') if b['mean_abs_move_10d_pct'] is not None else '–'} "
                         f"({b['moves_n']}) |")
        lines += ["", f"Rank correlation between alpha and confirmation: {av['spearman_alpha_vs_confirmed']}. "
                      f"Verdict: {av['verdict']}.", ""]
        if av.get("by_type"):
            lines += ["Within signal types (30 or more labelled predictions), so the result is not just signal-type mix:", "",
                      "| Signal type | Labelled | Low third | Middle third | High third | Rank correlation |",
                      "|---|---:|---:|---:|---:|---:|"]
            for st, r in av["by_type"].items():
                p = r["precision"]
                lines.append(f"| {st.replace('_', ' ')} | {r['labelled']} | {_fmt(p['low'])} | {_fmt(p['middle'])} | "
                             f"{_fmt(p['high'])} | {r['spearman']} |")
            lines.append("")
    lines += ["## By market", ""]
    for mk in ("us", "africa"):
        lines += [f"### {'United States' if mk == 'us' else 'Africa (JSE, NGX, NSE Kenya)'}", "",
                  "| Signal type | Predictions | Precision | Base rate | Lift | Recall | Hit rate |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        for st, by in sorted(m.items()):
            a = by[mk]
            if not a["predictions"] and not a["events"]:
                continue
            lines.append(f"| {st.replace('_', ' ')} | {a['predictions']} | {_fmt(a['precision'])} ({a['labelled']}) | "
                         f"{_fmt(a['base_rate'])} | {a['lift'] if a['lift'] is not None else '–'}x | "
                         f"{_fmt(a['recall'])} ({a['events']}) | {_fmt(a['hit_rate'])} ({a['directional_n']}) |")
        lines.append("")
    lines += [
        "## Method and caveats",
        "",
        "- Detection in the replay uses SEC filings, NGX disclosures and date-restricted Google News. The live "
        "product also reads ~50 African RSS feeds and JSE SENS, which have no searchable history, so live "
        "coverage is broader than the replay's.",
        "- Ground truth is limited to what the sources record. An event reported only by outlets below the "
        "credibility bar counts as not confirmed, which biases precision down, not up.",
        "- NGX and NSE Kenya have no free per-stock price history, so African hit rates cover JSE names only; "
        "NGX/NSE price outcomes accumulate from the daily snapshot going forward.",
        "- M&A is confirmed by completion or by a live deal's regulated milestones (merger proxy, Form 425 "
        "business-combination communications, tender offer filings, shareholder or regulatory approval, definitive "
        "agreement), since large deals rarely close within the 90-day horizon. Base rates use the same events.",
        "- Static calibration only: adaptive calibration, which learns from outcomes, is off so that later "
        "results cannot leak into earlier predictions.",
        "",
    ]
    return "\n".join(lines)
