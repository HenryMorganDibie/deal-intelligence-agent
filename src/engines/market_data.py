"""
Market Data Engine.
Automated price reaction fetching from Yahoo Finance.
Resolves tickers for US and African listed companies,
fetches post-signal price moves, and records outcomes
automatically — replacing the manual outcome tracking workflow.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


from src.schemas.models import SignalType, Severity, MarketOutcome
from src.utils.clock import utcnow

# African exchange ticker suffixes
EXCHANGE_SUFFIXES = {
    "NGX": ".LG",    # Nigerian Exchange — Lagos
    "JSE": ".JO",    # Johannesburg
    "NSE": ".NR",    # Nairobi
    "GSE": ".GH",    # Ghana
    "EGX": ".CA",    # Egyptian Exchange (Cairo)
    "CSE": ".CS",    # Casablanca
    "BRVM": ".BV",   # BRVM West Africa
}

# Known African ticker mappings (extend as coverage grows).
# Only symbols that are NOT also US tickers belong here: an unsuffixed ticker is
# assumed US-listed. JSE/NGX names that collide with US symbols (e.g. SLM is
# Sallie Mae in the US and Sanlam on the JSE; MTN is Vail Resorts in the US)
# must be given with their exchange suffix (SLM.JO, MTN.JO, UBA.LG, ...).
AFRICAN_TICKER_MAP: dict[str, str] = {
    "GTCO":         "GTCO.LG",
    "ZENITHBANK":   "ZENITHBANK.LG",
    "ACCESS":       "ACCESS.LG",
    "FBNH":         "FBNH.LG",
    "DANGCEM":      "DANGCEM.LG",
    "MTNN":         "MTNN.LG",
    "NPN":          "NPN.JO",
    "SCOM":         "SCOM.NR",
    "KCB":          "KCB.NR",
    "EQTY":         "EQTY.NR",
}


def _resolve_ticker(ticker: str) -> str:
    """Resolve ticker to a Yahoo Finance symbol."""
    upper = ticker.upper()
    if upper in AFRICAN_TICKER_MAP:
        return AFRICAN_TICKER_MAP[upper]
    # Already has suffix
    if "." in ticker:
        return ticker
    return ticker  # assume US listed


def _bars(resolved: str, start=None, end=None, range_=None) -> list[dict]:
    from src.engines import yahoo
    return yahoo.history(resolved, start=start, end=end, range_=range_)


def _fetch_price_moves(
    ticker: str,
    detection_date: str,
    windows: list[int] = [5, 10, 30],
) -> dict[str, Optional[float]]:
    """
    Fetch percentage price changes at specified day windows after detection_date.
    Returns dict: {"5d": pct, "10d": pct, "30d": pct} — None if unavailable.
    """
    resolved = _resolve_ticker(ticker)
    results: dict[str, Optional[float]] = {f"{w}d": None for w in windows}

    try:
        det_dt = datetime.strptime(detection_date, "%Y-%m-%d")
        end_dt = det_dt + timedelta(days=max(windows) + 10)
        bars = _bars(resolved, start=det_dt, end=end_dt)
        if len(bars) < 2:
            return results

        # Use first available close as baseline
        baseline = bars[0]["close"]
        if baseline == 0:
            return results

        for w in windows:
            target = (det_dt + timedelta(days=w)).date()
            # Closest trading day at or after target
            future = next((b for b in bars if b["date"] >= target), None)
            if future is None:
                continue
            results[f"{w}d"] = round((future["close"] - baseline) / baseline * 100, 2)

    except Exception:
        pass

    return results


def _fetch_volume_spike(ticker: str, detection_date: str, window_days: int = 5) -> Optional[float]:
    """Fetch average volume spike % in first window_days after detection vs prior 20d average."""
    resolved = _resolve_ticker(ticker)
    try:
        det_dt   = datetime.strptime(detection_date, "%Y-%m-%d")
        bars = _bars(resolved, start=det_dt - timedelta(days=30), end=det_dt + timedelta(days=window_days + 5))
        pre  = [b["volume"] for b in bars if b["volume"] is not None and b["date"] < det_dt.date()]
        post = [b["volume"] for b in bars if b["volume"] is not None and b["date"] >= det_dt.date()]
        if not pre or not post:
            return None
        pre_vol, post_vol = sum(pre) / len(pre), sum(post) / len(post)
        if pre_vol == 0:
            return None
        return round((post_vol - pre_vol) / pre_vol * 100, 1)

    except Exception:
        return None


def auto_record_outcome(
    company_name: str,
    ticker: str,
    signal_type: SignalType,
    severity_at_detection: Severity,
    detection_date: str,
    alpha_score_at_detection: Optional[float] = None,
    expected_direction: Optional[str] = None,
    expected_magnitude_low: Optional[float] = None,
    expected_magnitude_high: Optional[float] = None,
) -> Optional[MarketOutcome]:
    """
    Automatically fetch market data and record an outcome.
    Returns MarketOutcome if ticker is fetchable, None if data unavailable.
    """
    import uuid
    moves = _fetch_price_moves(ticker, detection_date)
    vol_spike = _fetch_volume_spike(ticker, detection_date)

    p5  = moves.get("5d")
    p10 = moves.get("10d")
    p30 = moves.get("30d")

    if p10 is None and p5 is None:
        return None  # no data

    # Direction accuracy
    direction_correct: Optional[bool] = None
    if p10 is not None and expected_direction:
        actual = "positive" if p10 > 0 else "negative" if p10 < 0 else "neutral"
        direction_correct = (actual == expected_direction)

    # Magnitude error
    from src.engines.measured import magnitude_error as _magnitude_error
    magnitude_error = _magnitude_error(p10, expected_direction, expected_magnitude_low, expected_magnitude_high)

    outcome = MarketOutcome(
        outcome_id=str(uuid.uuid4()),
        company_name=company_name,
        signal_type=signal_type,
        severity_at_detection=severity_at_detection,
        alpha_score_at_detection=alpha_score_at_detection,
        detection_date=detection_date,
        price_change_5d_pct=p5,
        price_change_10d_pct=p10,
        price_change_30d_pct=p30,
        volume_spike_pct=vol_spike,
        direction_correct=direction_correct,
        magnitude_error_pct=magnitude_error,
    )

    # Persist via market_impact module
    try:
        from src.engines.market_impact import _save, _load
        data = _load()
        import json
        data.append(json.loads(outcome.model_dump_json()))
        _save(data)
    except Exception:
        pass

    return outcome


def get_current_price(ticker: str) -> Optional[float]:
    """Fetch latest closing price for a ticker."""
    try:
        bars = _bars(_resolve_ticker(ticker), range_="5d")
        return round(bars[-1]["close"], 2) if bars else None
    except Exception:
        return None


def get_volatility(ticker: str, days: int = 30) -> Optional[float]:
    """Annualised volatility estimate over `days` trading days."""
    try:
        import math
        import statistics
        bars = _bars(_resolve_ticker(ticker), start=utcnow() - timedelta(days=days + 10))
        if len(bars) < 5:
            return None
        closes = [b["close"] for b in bars]
        returns = [b / a - 1 for a, b in zip(closes, closes[1:]) if a]
        if len(returns) < 2:
            return None
        return round(statistics.stdev(returns) * math.sqrt(252) * 100, 2)  # annualised %
    except Exception:
        return None

