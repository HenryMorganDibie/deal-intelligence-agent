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
directional hit rate and median abnormal return. Results are written to
docs/BACKTEST.md and data/historical_backtest.json.

HTTP responses are cached under data/hist_cache, so a rerun resumes cheaply.
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from src.schemas.models import AgentState, AnalysisRequest, NewsItem, SECFiling, SignalType
from src.utils.paths import DATA_DIR

log = logging.getLogger(__name__)

CACHE_DIR = DATA_DIR / "hist_cache"
RESULTS_PATH = DATA_DIR / "historical_backtest.json"
RUNS_DIR = DATA_DIR / "backtest_runs"          # one checkpoint file per company, so a run resumes
_SEC_LOCK = threading.Lock()
_SEC_LAST = [0.0]
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


_ORIGINAL_TICKERS = {e[1].upper() for e in UNIVERSE}


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
        tmp = path.with_suffix(f".{threading.get_ident()}.tmp")   # atomic: parallel workers share the cache
        tmp.write_text(json.dumps(value, default=sorted))
        tmp.replace(path)
    return value


# ── Sources ───────────────────────────────────────────────────────────────────

class Sources:
    def __init__(self) -> None:
        self.http = httpx.Client(timeout=30, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"})
        self.sec = httpx.Client(timeout=30, follow_redirects=True, headers=SEC_HEADERS)

    def _sec_get(self, url: str) -> httpx.Response:
        with _SEC_LOCK:                                      # under SEC's 10 requests/second, across threads
            wait = 0.13 - (time.monotonic() - _SEC_LAST[0])
            if wait > 0:
                time.sleep(wait)
            _SEC_LAST[0] = time.monotonic()
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

    def news(
        self, company: str, since: date, until: date, french: bool, ticker: Optional[str] = None
    ) -> list[dict]:
        from src.engines.event_sources import historical_news
        # Strict: a window that cannot be fetched completely raises, so it is neither cached nor used,
        # and the company is retried rather than scored on partial news.
        return _cached(f"news:{company}:{ticker or ''}:{since}:{until}:{french}",
                       lambda: historical_news(self.http, company, since, until, french,
                                               strict=True, ticker=ticker)) or []

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
    event_subtype: str = "unspecified"   # the named sub-signal ("capital_raise", "strategic_review", ...)


def _french(ticker: str) -> bool:
    """French-language news searches for francophone markets (Casablanca, BRVM, Tunis) and the original
    African companies, which were run with them."""
    from src.engines.outcome_labeller import market_for_ticker
    t = ticker.upper()
    return t.endswith((".CS", ".BV", ".TN")) or (market_for_ticker(ticker) == "africa" and t in _ORIGINAL_TICKERS)


def _as_of_dates(start: date, end: date, step_days: int) -> list[date]:
    """Every step_days from start; step_days=0 means the same day of each calendar month, so consecutive
    monthly replays share their windows and reuse cached news and filings."""
    if step_days == 0:
        out, y, m = [], start.year, start.month
        while (d := date(y, m, min(start.day, 28))) <= end:
            out.append(d)
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return out
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
            for n in src.news(company, since, as_of, french=_french(ticker), ticker=ticker)]

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
                              direction, cand.source_text[:160], cand.source_type, alpha,
                              getattr(cand, "event_subtype", None) or "unspecified"))
    return out


# Raised when price outcomes are fetched differently, so finished companies get their prices filled again.
# Version 2: the backtest machines had no Yahoo client, and every lookup was cached as "no prices".
PRICES_VERSION = 2


def _price_moves(symbol: str, iso: str) -> dict:
    """Cached price moves; a lookup that found no prices is not cached, so a later run tries again."""
    from src.engines.outcome_labeller import default_price_moves

    def fetch():
        moves = default_price_moves(symbol, iso) or {}
        return moves if any(v is not None for v in moves.values()) else None
    return _cached(f"px2:{symbol}:{iso}", fetch) or {}


def _refresh_prices(checkpoint: dict, today: date) -> dict:
    """A finished company's predictions with price outcomes filled where they are missing. Confirmation
    labels are kept as they are: only the stock and benchmark moves are looked up again."""
    from src.engines.outcome_labeller import benchmark_for
    out = []
    for p in checkpoint.get("predictions", []):
        if p.get("price_change_10d_pct") is None and p.get("ticker") and p.get("as_of") \
                and (today - date.fromisoformat(p["as_of"])).days >= 10:
            stock = _price_moves(p["ticker"], p["as_of"])
            bench_symbol = benchmark_for(p["ticker"])
            bench = _price_moves(bench_symbol, p["as_of"]) if (bench_symbol and stock) else {}
            if stock.get("10d") is not None:
                abnormal = round(stock["10d"] - bench["10d"], 2) if bench.get("10d") is not None else None
                move = abnormal if abnormal is not None else stock["10d"]
                p = {**p, "price_change_10d_pct": stock["10d"], "abnormal_return_10d_pct": abnormal}
                if p.get("direction") in ("positive", "negative"):
                    p["direction_correct"] = (move > 0) == (p["direction"] == "positive") if move != 0 else False
        out.append(p)
    return {**checkpoint, "predictions": out, "prices_version": PRICES_VERSION}


def _company_run(entry: tuple, start: date, end: date, dates: list[date], truth_dates: list[date],
                 horizon_end: date, today: date, src: "Sources") -> dict:
    """Detections, outcome labels, ground truth and base-rate hits for one company."""
    from src.engines.event_sources import news_events
    from src.engines.outcome_labeller import (
        filing_events, ground_truth, label_prediction, market_for_ticker, confirming_events,
    )

    company, ticker, cik = (tuple(entry) + (None,))[:3]
    market = market_for_ticker(ticker)
    sec_rows = src.sec_filings(ticker, start - timedelta(days=LOOKBACK_DAYS), cik) if market == "us" else []
    events: list[dict] = []
    if market == "us":
        events += filing_events({"filings": {"recent": {
            "form": [r["form"] for r in sec_rows], "filingDate": [r["date"] for r in sec_rows],
            "items": [r["items"] for r in sec_rows]}}})
    if ticker.upper().endswith(".LG"):
        events += src.ngx_events(ticker, company, start, horizon_end)
    # Official merger-control filings (COMESA, South Africa) naming the company: M&A ground truth that does
    # not depend on the press, read from the committed snapshot.
    from src.engines import merger_filings
    events += [e for e in merger_filings.events_for(company, ticker)
               if start.isoformat() <= e["date"] <= horizon_end.isoformat()]
    # JSE SENS announcements from the daily capture log (going forward from the first capture).
    from src.engines import sens_log
    events += [e for e in sens_log.events_for(company, ticker)
               if start.isoformat() <= e["date"] <= horizon_end.isoformat()]
    headlines = 0
    for d in truth_dates:
        window = src.news(company, d - timedelta(days=LOOKBACK_DAYS), d, french=_french(ticker), ticker=ticker)
        headlines += len(window)
        events += news_events(src.http, company, d - timedelta(days=LOOKBACK_DAYS), d,
                              headlines=window, ticker=ticker) or []
    truth = ground_truth(company, events, start, horizon_end)

    base: dict[str, int] = {}
    predictions: list[dict] = []
    last_seen: dict[str, date] = {}
    for as_of in dates:
        for st in {e["signal_type"] for e in ground_truth(company, events, as_of + timedelta(days=1),
                                                          as_of + timedelta(days=HORIZON_DAYS))}:
            base[st] = base.get(st, 0) + 1
        for p in detect(src, company, ticker, as_of, sec_rows, cik):
            prev = last_seen.get(p.signal_type)
            last_seen[p.signal_type] = as_of
            if prev and (as_of - prev).days < HORIZON_DAYS:
                continue                      # same signal still live: not a new prediction
            o = label_prediction(company_name=company, ticker=ticker, signal_type=SignalType(p.signal_type),
                                 severity=p.severity, detection_date=as_of, expected_direction=p.direction,
                                 events=events, today=today, price_moves=_price_moves) or {}
            official = None
            if o.get("event_confirmed") is not None:
                official_events = [e for e in events if not e.get("signal_types") or e.get("official")
                                   or e["source"].startswith(("NGX disclosure", "NSE Kenya disclosure"))]
                hit = [e for e in confirming_events(official_events, SignalType(p.signal_type))
                       if as_of.isoformat() < e["date"] <= (as_of + timedelta(days=HORIZON_DAYS)).isoformat()]
                official = bool(hit) if (market == "us" or ticker.upper().endswith(".LG")
                                         or _merger_control_market(ticker, p.signal_type)
                                         or _sens_covers(ticker, as_of)) else None
            predictions.append({**p.__dict__, "event_confirmed": o.get("event_confirmed"),
                                "confirmed_by_official_filing": official,
                                "confirmation_source": o.get("confirmation_source"),
                                "abnormal_return_10d_pct": o.get("abnormal_return_10d_pct"),
                                "price_change_10d_pct": o.get("price_change_10d_pct"),
                                "direction_correct": o.get("direction_correct")})
    return {"company": company, "ticker": ticker, "market": market, "as_of_dates": len(dates),
            "headlines": headlines, "filings": len(sec_rows), "covered": bool(headlines or sec_rows),
            "predictions": predictions, "truth": truth, "base": base, "prices_version": PRICES_VERSION}


def _merger_control_market(ticker: str, signal_type: str) -> bool:
    """An African M&A flag whose market publishes merger-control decisions (South Africa, COMESA), so an
    official filing could confirm it."""
    from src.data.africa_countries import from_ticker
    from src.engines.merger_filings import COMESA_MEMBERS
    c = from_ticker(ticker)
    return signal_type == "m_and_a_activity" and c is not None and (c.iso2 == "ZA" or c.iso2 in COMESA_MEMBERS)


def _sens_covers(ticker: str, as_of: date) -> bool:
    """A JSE listing whose whole horizon after `as_of` falls inside the SENS capture log, so the absence of
    an announcement there means none was made (before capture began it means nothing)."""
    from src.engines import sens_log
    entries = sens_log.load()
    first = sens_log.covered_since(entries)
    return (ticker.upper().endswith(".JO") and first is not None and as_of >= first
            and (as_of + timedelta(days=HORIZON_DAYS)).isoformat() <= max(e["date"] for e in entries))


def rolling_period(today: date, months: int = 17) -> tuple[date, date]:
    """The latest replay whose every 90-day horizon has closed: the last as-of date falls on the 15th of
    the month at least HORIZON_DAYS + 30 days ago; the first is `months` months earlier."""
    last = today - timedelta(days=HORIZON_DAYS + 30)
    end = date(last.year, last.month, 15) if last.day >= 15 else \
        date(last.year - (last.month == 1), (last.month - 2) % 12 + 1, 15)
    y, m = divmod(end.year * 12 + end.month - 1 - months, 12)
    return date(y, m + 1, 15), end


def _checkpoint(run_dir: Path, ticker: str) -> Path:
    import re
    return run_dir / (re.sub(r"[^A-Za-z0-9.]+", "_", ticker) + ".json")


def _checkpoint_needs_run(path: Path) -> bool:
    """Retry companies previously marked uncovered (their missing history may be transient), and those
    whose price outcomes predate PRICES_VERSION (only their prices are looked up again)."""
    return _checkpoint_state(path) != "done"


def _checkpoint_state(path: Path) -> str:
    """'run' (no usable checkpoint), 'prices' (finished, but its price outcomes need filling) or 'done'."""
    if not path.exists():
        return "run"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return "run"
    if not data.get("covered", True):
        return "run"
    if data.get("predictions") and data.get("prices_version", 1) < PRICES_VERSION:
        return "prices"
    return "done"


# A published period whose last as-of date is this far behind the latest rolling period is abandoned
# for the latest one even while companies remain, so results (and the return-forecast validation fed
# by them) cannot stay frozen on old dates.
MAX_PERIOD_LAG_DAYS = 120


def current_period(today: date) -> tuple[date, date, int]:
    """(start, end, step_days) the monthly run works on: the published period while some of its companies
    are still to run and it is recent, so each month adds to it; otherwise the latest rolling period."""
    try:
        pub = json.loads(SUMMARY_PATH.read_text())
    except (OSError, ValueError):
        pub = {}
    start, end = rolling_period(today)
    if pub.get("missing_companies") and pub.get("start") and pub.get("end"):
        pub_end = date.fromisoformat(pub["end"])
        if (end - pub_end).days <= MAX_PERIOD_LAG_DAYS:
            return date.fromisoformat(pub["start"]), pub_end, int(pub.get("step_days", 30))
    return start, end, 0


def publish_decision(start: date, end: date, universe: list[tuple]) -> tuple[bool, str]:
    """Whether the finished companies of [start, end] should replace the published results: always when
    every company is done; for an unfinished run only when it is the published period and covers more
    companies than are published now, so a partial month never replaces a fuller result."""
    run_dir = RUNS_DIR / f"{start}_{end}"
    covered = missing = priced = 0
    for e in universe:
        path = _checkpoint(run_dir, e[1])
        if not path.exists():
            missing += 1
            continue
        data = json.loads(path.read_text())
        if data.get("covered", True):
            covered += 1
            priced += sum(1 for p in data.get("predictions", []) if p.get("price_change_10d_pct") is not None)
    if not missing:
        return True, f"all {len(universe)} companies done ({covered} with usable history)"
    try:
        pub = json.loads(SUMMARY_PATH.read_text())
    except (OSError, ValueError):
        pub = {}
    same = pub.get("start") == start.isoformat() and pub.get("end") == end.isoformat()
    published = int(pub.get("companies") or 0)
    if same and covered > published:
        return True, f"{covered} companies now, {published} published; {missing} still to run"
    published_priced = int(pub.get("predictions_with_returns") or 0)
    if same and covered == published and priced > published_priced:
        return True, (f"price outcomes for {priced} predictions, {published_priced} published; "
                      f"{missing} still to run")
    newer = bool(pub.get("end")) and end > date.fromisoformat(pub["end"])
    if newer and covered >= published:
        return True, (f"a more recent period covers {covered} companies, at least the {published} published; "
                      f"{missing} still to run")
    return False, (f"{covered} companies done, {published} published"
                   f"{'' if same else ' for another period'}; {missing} still to run, keeping the published results")


def plan_shards(start: date, end: date, universe: list[tuple], shards: int) -> dict:
    """Split the companies of [start, end] that have no checkpoint yet into `shards` interleaved groups,
    one per machine, so each runner (with its own address) searches news for a different set."""
    run_dir = RUNS_DIR / f"{start}_{end}"
    todo_entries = [e for e in universe if _checkpoint_needs_run(_checkpoint(run_dir, e[1]))]
    # Give African listings first access to each run instead of leaving them behind a
    # US-heavy alphabetical ticker list. Interleaving then spreads them across runners.
    from src.engines.backtest_universe import UNIVERSE_PATH
    market_by_ticker = {}
    try:
        with UNIVERSE_PATH.open(newline="", encoding="utf-8") as f:
            market_by_ticker = {r["ticker"]: r.get("market", "") for r in csv.DictReader(f)}
    except OSError:
        pass
    todo_entries.sort(key=lambda e: (0 if market_by_ticker.get(e[1]) == "africa" else 1, e[1]))
    todo = [e[1] for e in todo_entries]
    groups = [todo[i::shards] for i in range(max(shards, 1))]
    return {"start": start.isoformat(), "end": end.isoformat(), "remaining": len(todo),
            "shards": [{"shard": i + 1, "tickers": ",".join(g)} for i, g in enumerate(groups) if g]}


def run(
    start: date, end: date, universe: Optional[list[tuple]] = None, step_days: int = 30,
    progress: Callable[[str], None] = lambda m: None, workers: int = 8, deadline_minutes: Optional[float] = None,
    aggregate_results: bool = True,
) -> Optional[dict]:
    """Walk forward over [start, end] for every company (in parallel, resumable); label, aggregate, save.
    With a deadline, no new company starts after it and failed companies are not retried past it (one
    already running is let finish); returns None if any company is still to run, so a later call resumes
    from the checkpoints."""
    from src.engines import backtest_universe

    universe = universe or backtest_universe.load()
    today = date.today()
    horizon_end = min(end + timedelta(days=HORIZON_DAYS), today)
    dates = _as_of_dates(start, end, step_days)
    truth_dates = _as_of_dates(start, horizon_end, step_days)
    run_dir = RUNS_DIR / f"{start}_{end}"
    run_dir.mkdir(parents=True, exist_ok=True)
    todo = [e for e in universe if _checkpoint_needs_run(_checkpoint(run_dir, e[1]))]
    progress(f"{len(universe) - len(todo)} of {len(universe)} companies already done; {len(todo)} to run")
    local = threading.local()
    stop_at = time.monotonic() + deadline_minutes * 60 if deadline_minutes else None

    def work(entry: tuple) -> str:
        if stop_at and time.monotonic() > stop_at:
            return f"{entry[0]} ({entry[1]}): deferred to the next run"
        path = _checkpoint(run_dir, entry[1])
        if _checkpoint_state(path) == "prices":
            out = _refresh_prices(json.loads(path.read_text(encoding="utf-8")), today)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(out, default=str))
            tmp.replace(path)
            priced = sum(1 for p in out["predictions"] if p.get("price_change_10d_pct") is not None)
            return f"{entry[0]} ({entry[1]}): prices filled for {priced} of {len(out['predictions'])} predictions"
        if not hasattr(local, "src"):
            local.src = Sources()
        for attempt in range(3):
            try:
                out = _company_run(entry, start, end, dates, truth_dates, horizon_end, today, local.src)
                tmp = path.with_suffix(".json.tmp")   # atomic: a run stopped mid-write leaves no torn checkpoint
                tmp.write_text(json.dumps(out, default=str))
                tmp.replace(path)
                return f"{entry[0]} ({entry[1]}): {len(out['predictions'])} predictions, {out['headlines']} headlines"
            except Exception as e:                  # one company's failure never stops the run
                log.warning("company %s failed (attempt %d): %r", entry[1], attempt + 1, e)
                if stop_at and time.monotonic() > stop_at:
                    break                               # past the deadline: leave the retry to the next run
                time.sleep(60 * (attempt + 1))         # let a news cool-down pass before retrying
        return f"{entry[0]} ({entry[1]}): failed"

    done = len(universe) - len(todo)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in as_completed([pool.submit(work, e) for e in todo]):
            done += 1
            progress(f"[{done}/{len(universe)}] {fut.result()}")
    remaining = [e for e in universe if not _checkpoint(run_dir, e[1]).exists()]
    if not aggregate_results:
        if remaining:
            progress(f"{len(remaining)} companies still to run in this shard")
        return None
    if remaining:
        progress(f"{len(remaining)} companies still to run; resume to finish")
        return None
    return aggregate(start, end, universe, dates, run_dir, step_days)


def aggregate(start: date, end: date, universe: list[tuple], dates: list[date], run_dir: Path,
              step_days: Optional[int] = None) -> dict:
    """Combine per-company checkpoints into metrics, tables and reports. Companies with no news and no
    filings in the whole period (delisted, or never covered) are left out of every denominator."""
    predictions: list[dict] = []
    truth: list[dict] = []
    base: dict[str, dict[str, int]] = {}
    months: dict[str, int] = {}
    companies: dict[str, int] = {}
    uncovered: dict[str, int] = {}
    market_of: dict[str, str] = {}
    missing = 0
    for entry in universe:
        path = _checkpoint(run_dir, entry[1])
        if not path.exists():
            missing += 1
            continue
        c = json.loads(path.read_text())
        if not c.get("covered", True):
            uncovered[c["market"]] = uncovered.get(c["market"], 0) + 1
            continue
        mk = c["market"]
        market_of[c["company"]] = mk
        companies[mk] = companies.get(mk, 0) + 1
        months[mk] = months.get(mk, 0) + c["as_of_dates"]
        predictions += c["predictions"]
        truth += c["truth"]
        for st, n in c["base"].items():
            base.setdefault(st, {}).setdefault(mk, 0)
            base[st][mk] += n
    metrics = compute_metrics(predictions, truth, base, months, market_of)
    if step_days is None:                  # monthly on the start's day of month, or a fixed spacing
        step_days = 0 if all(d.day == start.day for d in dates) else (dates[1] - dates[0]).days if len(dates) > 1 else 0
    result = {"start": start.isoformat(), "end": end.isoformat(), "step_days": step_days, "as_of_dates": len(dates),
              "companies": sum(companies.values()), "companies_by_market": companies, "company_months": months,
              "uncovered_companies": uncovered, "missing_companies": missing, "universe_size": len(universe),
              "lookback_days": LOOKBACK_DAYS, "horizon_days": HORIZON_DAYS,
              "predictions_with_returns": sum(1 for p in predictions if p.get("price_change_10d_pct") is not None),
              "predictions": predictions, "ground_truth_events": truth, "metrics": metrics,
              "by_severity": by_severity(predictions), "alpha_validation": alpha_validation(predictions)}
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=1, default=str))
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(result))
    write_tables(result)
    from src.engines import evaluation_report
    evaluation_report.write(result)
    SUMMARY_PATH.write_text(json.dumps({k: result[k] for k in ("start", "end", "step_days", "as_of_dates", "companies",
                                                                "companies_by_market", "company_months",
                                                                "uncovered_companies", "missing_companies", "universe_size",
                                                                "lookback_days", "horizon_days",
                                                                "predictions_with_returns", "metrics",
                                                                "by_severity", "alpha_validation")},
                                       indent=1, default=str))
    return result


# ── Metrics ───────────────────────────────────────────────────────────────────

def _rate(num: int, den: int) -> Optional[float]:
    return round(num / den, 3) if den else None


def compute_metrics(predictions: list[dict], truth: list[dict], base: dict, months: dict[str, int],
                    market_of: Optional[dict[str, str]] = None) -> dict:
    """Per signal type, per market ('all', 'us', 'africa')."""
    market_of = market_of or {p["company"]: p["market"] for p in predictions}
    by_key: dict[tuple, list[date]] = {}
    for p in predictions:
        by_key.setdefault((p["company"], p["signal_type"]), []).append(date.fromisoformat(p["as_of"]))
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
                  and (mk == "all" or market_of.get(e["company_name"]) in (mk, None))]
            caught = 0
            for e in ev:
                d = date.fromisoformat(e["date"])
                caught += any(0 < (d - a).days <= HORIZON_DAYS for a in by_key.get((e["company_name"], st), ()))
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
                "caught": caught,
                "confirmed": conf,
                "recall": _rate(caught, len(ev)),
                "base_hits": base_hits,
                "company_months": n_months,
                "base_rate": base_rate,
                "lift": round(precision / base_rate, 2) if precision is not None and base_rate else None,
                "price_only": price_only,
                "hit_rate": _rate(sum(directional), len(directional)),
                "directional_n": len(directional),
                # The median: a handful of thinly traded listings with three- and four-digit moves made the
                # mean read +108% for M&A, which describes no typical flag.
                "median_abnormal_return_10d_pct": round(statistics.median(abn), 2) if abn else None,
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
    lo, mid, hi = (out["bands"][k]["precision"] for k in ("low", "middle", "high"))
    if None in (lo, mid, hi):
        out["verdict"] = "too few labelled flags to compare alpha thirds"
    elif lo < mid < hi:
        out["verdict"] = "confirmations rose with alpha across all three thirds"
    elif hi > lo and mid > lo:
        out["verdict"] = "the lowest alpha third confirmed least; the top third did not beat the middle"
    else:
        out["verdict"] = "higher alpha did not go with more confirmations"
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


def _fmt(v, pct=True) -> str:
    if v is None:
        return "–"
    return f"{v:.0%}" if pct else f"{v}"


def _market_counts(result: dict) -> str:
    by = result.get("companies_by_market") or {}
    return ", ".join(f"{n} {'US' if mk == 'us' else 'African'}" for mk, n in sorted(by.items(), reverse=True)) or "US and African"


def _coverage_note(result: dict) -> str:
    size = result.get("universe_size")
    if not size:
        return ""
    parts = [f", from a universe of {size}"]
    uncovered = sum((result.get("uncovered_companies") or {}).values())
    if uncovered:
        parts.append(f"; {uncovered} had no usable price or news history")
    if result.get("missing_companies"):
        parts.append(f"; {result['missing_companies']} not yet replayed, joining in the next monthly run")
    return "".join(parts)


def render_report(result: dict) -> str:
    m = result["metrics"]
    lines = [
        "# Historical backtest",
        "",
        f"Walk-forward replay over **{result['start']} to {result['end']}**: {result['companies']} companies "
        f"({_market_counts(result)}) x {result['as_of_dates']} monthly as-of dates{_coverage_note(result)}. "
        f"On each date the engine sees "
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
        "(10 calendar days: first close on or after day 10). Earnings surprises and insider trades are judged on price only.",
        "",
        "| Signal type | Predictions | Precision | Official | Base rate | Lift | Recall | Hit rate | Median abn. return 10d |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for st, by in sorted(m.items()):
        a = by["all"]
        lines.append(
            f"| {st.replace('_', ' ')} | {a['predictions']} | {_fmt(a['precision'])} ({a['labelled']}) | "
            f"{_fmt(a['precision_official_filings'])} ({a['official_labelled']}) | {_fmt(a['base_rate'])} | "
            f"{a['lift'] if a['lift'] is not None else '–'}x | {_fmt(a['recall'])} ({a['events']}) | "
            f"{_fmt(a['hit_rate'])} ({a['directional_n']}) | "
            f"{(str(a['median_abnormal_return_10d_pct']) + '%') if a.get('median_abnormal_return_10d_pct') is not None else '–'} |")
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
