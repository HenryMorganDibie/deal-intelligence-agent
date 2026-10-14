"""
Automatic outcome labelling.

Backtesting and adaptive calibration need to know whether each flagged signal
came true. Waiting for analysts to record outcomes by hand meant the numbers
stayed at bootstrap level indefinitely. This module labels outcomes without a
human:

  * Market reaction: the stock's move 5, 10 and 30 days after detection, and
    the same move net of a market benchmark (abnormal return), so a signal is
    not credited with a move the whole market made.
  * Event confirmation from primary filings: for US companies, a later SEC
    8-K item or form that is the event itself (Item 2.01 completed acquisition
    after an M&A signal, 5.02 after a leadership signal, 1.03 after a distress
    signal, ...). No confirming filing within the window = not confirmed.
  * Ground truth for recall: every confirming filing for an analysed company is
    an event the engine should have flagged beforehand. Events with no earlier
    prediction are misses.

Signal types with no filing that evidences them (regulatory action; any type
outside the US) keep event_confirmed = None: unknown, never counted as wrong.
Each outcome records its market, so calibration can learn African rates
separately from US ones as they accumulate.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Optional

import httpx

from src.schemas.models import SignalType
from src.utils.clock import utcnow

log = logging.getLogger(__name__)

# A signal predicts an event within this many days of detection.
CONFIRMATION_WINDOW_DAYS = 90
# Price reaction is read 10 trading-ish days after detection; label no earlier.
MIN_AGE_DAYS = 12

AFRICAN_SUFFIXES = (".JO", ".LG", ".NR", ".GH", ".CA", ".CS", ".BV")

# Market benchmark per listing, for abnormal returns: SPY, the Satrix 40 tracker
# (JSE), the NGX All-Share Index and the NSE All-Share Index. Other markets
# (GSE, BRVM, EGX, ...) stay raw and say so (benchmark = None).
BENCHMARKS = {"us": "SPY", ".JO": "STX40.JO", ".LG": "^ASI", ".NR": "^NASI"}


def default_price_moves(symbol: str, iso_date: str) -> dict:
    """Yahoo Finance, except NGX/NSE listings and indices, which come from the exchanges."""
    from src.engines.market_data import _fetch_price_moves, _resolve_ticker
    from src.tools.african_prices import african_price_moves, market_of
    resolved = symbol if symbol.startswith("^") else _resolve_ticker(symbol)
    if market_of(resolved):
        return african_price_moves(resolved, iso_date)
    return _fetch_price_moves(resolved, iso_date)

# SEC filings that are the event a signal type predicts.
CONFIRMING_8K_ITEMS: dict[SignalType, set[str]] = {
    SignalType.MA_ACTIVITY:       {"2.01", "5.01"},
    SignalType.LEADERSHIP_CHANGE: {"5.02"},
    SignalType.DISTRESSED_ASSET:  {"1.03", "3.01"},
    SignalType.CREDIT_RISK:       {"2.04", "2.06"},
    SignalType.DEBT_RESTRUCTURE:  {"2.04", "1.03"},
    SignalType.EARNINGS_SURPRISE: {"4.02"},
}
CONFIRMING_FORMS: dict[SignalType, set[str]] = {
    SignalType.MA_ACTIVITY:      {"SC TO-T", "SC TO-C", "SC 14D9", "DEFM14A", "PREM14A", "S-4", "SCHEDULE TO"},
    SignalType.DISTRESSED_ASSET: {"25-NSE", "15-12B", "15-12G"},
    SignalType.INSIDER_ACTIVITY: {"SC 13D", "SCHEDULE 13D", "SC 13D/A"},
}

SEC_HEADERS = {"User-Agent": "DealIntelligenceAgent research@dealintel.ai"}


def market_for_ticker(ticker: Optional[str]) -> str:
    """'africa' for an African listing, else 'us' (unsuffixed tickers are US-listed)."""
    if not ticker:
        return "us"
    from src.engines.market_data import _resolve_ticker
    resolved = _resolve_ticker(ticker).upper()
    return "africa" if resolved.endswith(AFRICAN_SUFFIXES) else "us"


def benchmark_for(ticker: Optional[str]) -> Optional[str]:
    if not ticker:
        return None
    from src.engines.market_data import _resolve_ticker
    resolved = _resolve_ticker(ticker).upper()
    for suffix, bench in BENCHMARKS.items():
        if suffix != "us" and resolved.endswith(suffix):
            return bench
    return BENCHMARKS["us"] if market_for_ticker(ticker) == "us" else None


# ── SEC ground truth ──────────────────────────────────────────────────────────

_TICKER_CIK: dict[str, str] = {}


def _cik_for(ticker: Optional[str], client: httpx.Client) -> Optional[str]:
    if not ticker or market_for_ticker(ticker) != "us":
        return None
    if not _TICKER_CIK:
        try:
            r = client.get("https://www.sec.gov/files/company_tickers.json")
            r.raise_for_status()
            for row in r.json().values():
                _TICKER_CIK[str(row["ticker"]).upper()] = str(row["cik_str"]).zfill(10)
        except Exception as e:  # network or format problem: no ground truth this run
            log.warning("SEC ticker map unavailable: %s", e)
            return None
    return _TICKER_CIK.get(ticker.upper())


def filing_events(submissions: dict) -> list[dict]:
    """(date, form, items) for every recent filing in an EDGAR submissions payload."""
    recent = submissions.get("filings", {}).get("recent", {})
    forms, dates, items = recent.get("form", []), recent.get("filingDate", []), recent.get("items", [])
    out = []
    for i, form in enumerate(forms):
        if i >= len(dates):
            break
        codes = {c.strip() for c in (items[i] if i < len(items) else "").split(",") if c.strip()}
        out.append({"date": dates[i], "form": form.upper(), "items": codes})
    return out


# Event types that exchange disclosures and credible news can confirm for any
# market (event_sources). Earnings surprises and insider trades are excluded:
# the signal is the event itself, so they are judged on price direction.
NEWS_CONFIRMABLE = {
    SignalType.MA_ACTIVITY, SignalType.LEADERSHIP_CHANGE, SignalType.DISTRESSED_ASSET,
    SignalType.CREDIT_RISK, SignalType.DEBT_RESTRUCTURE, SignalType.REGULATORY_ACTION,
}


def confirming_events(events: list[dict], signal_type: SignalType) -> list[dict]:
    """The events (SEC filings, exchange disclosures, credible reports) that evidence `signal_type`."""
    items, forms = CONFIRMING_8K_ITEMS.get(signal_type, set()), CONFIRMING_FORMS.get(signal_type, set())
    out = []
    for e in events:
        hit = sorted(e.get("items", set()) & items) if e.get("form") in ("8-K", "8-K/A") else []
        if hit:
            out.append({**e, "source": f"SEC 8-K Item {', '.join(hit)} ({e['date']})"})
        elif e.get("form") in forms:
            out.append({**e, "source": f"SEC {e['form']} ({e['date']})"})
        elif signal_type in NEWS_CONFIRMABLE and signal_type.value in e.get("signal_types", ()):
            out.append({**e, "source": f"{e['source']} ({e['date']})"})
    return out


def has_ground_truth(signal_type: SignalType, market: str) -> bool:
    if signal_type in NEWS_CONFIRMABLE:
        return True                    # exchange disclosures and credible reports, any market
    return market == "us" and (signal_type in CONFIRMING_8K_ITEMS or signal_type in CONFIRMING_FORMS)


def fetch_filing_events(ticker: Optional[str], client: Optional[httpx.Client] = None) -> Optional[list[dict]]:
    """Filing events for a US ticker, or None when there is no SEC ground truth."""
    own = client is None
    client = client or httpx.Client(headers=SEC_HEADERS, timeout=20, follow_redirects=True)
    try:
        cik = _cik_for(ticker, client)
        if not cik:
            return None
        time.sleep(0.15)   # stay well inside SEC fair access
        r = client.get(f"https://data.sec.gov/submissions/CIK{cik}.json")
        r.raise_for_status()
        return filing_events(r.json())
    except Exception as e:
        log.warning("SEC submissions unavailable for %s: %s", ticker, e)
        return None
    finally:
        if own:
            client.close()


def fetch_events(company: str, ticker: Optional[str], since: date, until: date) -> Optional[list[dict]]:
    """All ground truth for a company: SEC filings (US) plus exchange disclosures and credible news."""
    from src.engines.event_sources import collect_events
    market = market_for_ticker(ticker)
    sec = fetch_filing_events(ticker) if market == "us" else None
    other = collect_events(company, ticker, market, since, until)
    if sec is None and other is None:
        return None
    return (sec or []) + (other or [])


# ── Labelling ─────────────────────────────────────────────────────────────────

def _day(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def confirmation(
    signal_type: SignalType, market: str, detected: date, events: Optional[list[dict]], today: date,
) -> tuple[Optional[bool], Optional[str], Optional[str]]:
    """
    (event_confirmed, confirmation_date, source). True: a confirming filing came
    within the window after detection. False: the window has fully elapsed with
    none. None: no ground truth for this type/market, or the window is still open.
    """
    if events is None or not has_ground_truth(signal_type, market):
        return None, None, None
    window_end = detected + timedelta(days=CONFIRMATION_WINDOW_DAYS)
    for e in sorted(confirming_events(events, signal_type), key=lambda e: e["date"]):
        d = _day(e["date"])
        if d and detected < d <= window_end:     # strictly after: the trigger cannot confirm itself
            return True, e["date"], e["source"]
    if today > window_end:
        return False, None, f"No confirming filing, disclosure or credible report within {CONFIRMATION_WINDOW_DAYS} days"
    return None, None, None


def label_prediction(
    *,
    company_name: str,
    ticker: Optional[str],
    signal_type: SignalType,
    severity: str,
    detection_date: Any,
    alpha_score: Optional[float] = None,
    expected_direction: Optional[str] = None,
    expected_low: Optional[float] = None,
    expected_high: Optional[float] = None,
    events: Optional[list[dict]] = None,
    today: Optional[date] = None,
    price_moves=None,
) -> Optional[dict]:
    """
    One outcome record for one prediction, or None when it is too recent or there
    is nothing to measure (no price data and no ground truth).
    `price_moves(symbol, iso_date)` -> {"5d","10d","30d"}; defaults to Yahoo Finance.
    """
    today = today or utcnow().date()
    detected = _day(detection_date)
    if detected is None or (today - detected).days < MIN_AGE_DAYS:
        return None
    if price_moves is None:
        price_moves = default_price_moves
    market = market_for_ticker(ticker)
    iso = detected.isoformat()

    stock = price_moves(ticker, iso) if ticker else {}
    bench_symbol = benchmark_for(ticker)
    bench = price_moves(bench_symbol, iso) if (bench_symbol and stock) else {}
    abnormal = {
        w: round(stock[w] - bench[w], 2)
        for w in ("5d", "10d", "30d")
        if stock.get(w) is not None and bench.get(w) is not None
    }

    confirmed, confirmed_on, source = confirmation(signal_type, market, detected, events, today)
    if not any(v is not None for v in stock.values()) and confirmed is None:
        return None

    move = abnormal.get("10d", stock.get("10d"))
    direction_correct = None
    if move is not None and expected_direction in ("positive", "negative"):
        direction_correct = (move > 0) == (expected_direction == "positive") if move != 0 else False
    magnitude_error = None
    if move is not None and expected_low is not None and expected_high is not None:
        magnitude_error = round(abs(abs(move) - (expected_low + expected_high) / 2), 2)

    return {
        "outcome_id": str(uuid.uuid4()),
        "company_name": company_name,
        "ticker": ticker,
        "market": market,
        "signal_type": signal_type.value,
        "severity_at_detection": severity,
        "alpha_score_at_detection": alpha_score,
        "detection_date": iso,
        "price_change_5d_pct": stock.get("5d"),
        "price_change_10d_pct": stock.get("10d"),
        "price_change_30d_pct": stock.get("30d"),
        "benchmark": bench_symbol if abnormal else None,
        "abnormal_return_5d_pct": abnormal.get("5d"),
        "abnormal_return_10d_pct": abnormal.get("10d"),
        "abnormal_return_30d_pct": abnormal.get("30d"),
        "event_confirmed": confirmed,
        "confirmation_date": confirmed_on,
        "confirmation_source": source,
        "direction_correct": direction_correct,
        "magnitude_error_pct": magnitude_error,
        "labelled_by": "auto",
        "recorded_at": utcnow().isoformat(),
    }


def ground_truth(company_name: str, events: list[dict], since: date, until: date) -> list[dict]:
    """Every confirming event for the company in [since, until]: events the engine should catch."""
    out = []
    for signal_type in set(CONFIRMING_8K_ITEMS) | set(CONFIRMING_FORMS) | NEWS_CONFIRMABLE:
        for e in confirming_events(events, signal_type):
            d = _day(e["date"])
            if d and since <= d <= until:
                out.append({"company_name": company_name, "signal_type": signal_type.value,
                            "date": e["date"], "source": e["source"]})
    return out


def recall_by_type(events: list[dict], predictions: list[dict], lead_days: int = CONFIRMATION_WINDOW_DAYS) -> dict:
    """
    Share of ground-truth events that a prediction of the same company and type
    preceded by at most `lead_days`. predictions: [{company_name, signal_type, date}].
    """
    by_key: dict[tuple, list[date]] = {}
    for p in predictions:
        d = _day(p["date"])
        if d:
            by_key.setdefault((p["company_name"], p["signal_type"]), []).append(d)
    out: dict[str, dict] = {}
    for e in events:
        d = _day(e["date"])
        if not d:
            continue
        caught = any(0 <= (d - p).days <= lead_days for p in by_key.get((e["company_name"], e["signal_type"]), []))
        s = out.setdefault(e["signal_type"], {"events": 0, "caught": 0, "missed": []})
        s["events"] += 1
        if caught:
            s["caught"] += 1
        else:
            s["missed"].append({"company_name": e["company_name"], "date": e["date"], "source": e["source"]})
    for s in out.values():
        s["recall"] = round(s["caught"] / s["events"], 3) if s["events"] else None
    return out


# ── Local store (CLI) ─────────────────────────────────────────────────────────

def label_warehouse(today: Optional[date] = None, price_moves=None, fetch_events=None) -> dict:
    """
    Label every warehouse prediction old enough and not yet auto-labelled, write
    the outcomes to the market-impact store and refresh the ground-truth events.
    Returns counts. Used by `python main.py outcomes --auto-label`.
    """
    import json as _json
    from src.engines.backtest import load_ground_truth, save_ground_truth
    from src.engines.market_impact import _load, _save
    from src.engines.warehouse import AnalystBriefRecord, DetectedSignalRecord, get_session

    today = today or utcnow().date()
    fetch_events = fetch_events or globals()["fetch_events"]   # (company, ticker, since, until)
    session = get_session()
    try:
        tickers = {b.run_id: b.ticker for b in session.query(AnalystBriefRecord).all()}
        signals = session.query(DetectedSignalRecord).all()
    finally:
        session.close()

    store = _load()
    done = {(o.get("company_name"), o.get("signal_type"), o.get("detection_date"))
            for o in store if o.get("labelled_by") == "auto"}

    predictions: dict[tuple, Any] = {}
    first_seen: dict[tuple, date] = {}
    for sig in signals:
        d = _day(sig.detected_at)
        if d is None:
            continue
        ticker = tickers.get(sig.run_id)
        predictions.setdefault((sig.company_name, sig.signal_type, d), (sig, ticker))
        key = (sig.company_name, ticker)
        first_seen[key] = min(first_seen.get(key, d), d)

    events_cache: dict[tuple, Optional[list[dict]]] = {}

    def events_for(company, ticker):
        key = (company, ticker)
        if key not in events_cache:
            events_cache[key] = fetch_events(company, ticker, first_seen[key], today)
        return events_cache[key]

    added = skipped = 0
    for (company, stype, d), (sig, ticker) in predictions.items():
        if (company, stype, d.isoformat()) in done:
            continue
        try:
            alpha = _json.loads(sig.alpha_json) if sig.alpha_json else {}
        except ValueError:
            alpha = {}
        outcome = label_prediction(
            company_name=company, ticker=ticker, signal_type=SignalType(stype), severity=sig.severity,
            detection_date=d, alpha_score=sig.alpha_score,
            expected_direction=alpha.get("expected_direction"),
            expected_low=alpha.get("expected_magnitude_pct_low"),
            expected_high=alpha.get("expected_magnitude_pct_high"),
            events=events_for(company, ticker), today=today, price_moves=price_moves,
        )
        if outcome is None:
            skipped += 1
            continue
        store.append(outcome)
        added += 1
    _save(store)

    truth = load_ground_truth()
    for (company, ticker), since in first_seen.items():
        events = events_for(company, ticker)
        if events:
            truth.extend(ground_truth(company, events, since, today))
    save_ground_truth(truth)
    return {"labelled": added, "not_yet_labellable": skipped, "ground_truth_events": len(load_ground_truth())}
