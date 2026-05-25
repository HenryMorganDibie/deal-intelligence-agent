"""
Market Data Engine.
Automated price reaction fetching using yfinance.
Resolves tickers for US and African listed companies,
fetches post-signal price moves, and records outcomes
automatically — replacing the manual outcome tracking workflow.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

import yfinance as yf

from src.schemas.models import SignalType, Severity, MarketOutcome

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

# Known African ticker mappings (extend as coverage grows)
AFRICAN_TICKER_MAP: dict[str, str] = {
    "GTCO":         "GTCO.LG",
    "ZENITHBANK":   "ZENITHBANK.LG",
    "ACCESS":       "ACCESS.LG",
    "FBNH":         "FBNH.LG",
    "UBA":          "UBA.LG",
    "DANGCEM":      "DANGCEM.LG",
    "MTNN":         "MTNN.LG",
    "NPN":          "NPN.JO",
    "MTN":          "MTN.JO",
    "SOL":          "SOL.JO",
    "BHP":          "BHP.JO",
    "ABG":          "ABG.JO",
    "FSR":          "FSR.JO",
    "REM":          "REM.JO",
    "SLM":          "SLM.JO",
    "SCOM":         "SCOM.NR",
    "KCB":          "KCB.NR",
    "EQTY":         "EQTY.NR",
}


def _resolve_ticker(ticker: str) -> str:
    """Resolve ticker to yfinance-compatible symbol."""
    upper = ticker.upper()
    if upper in AFRICAN_TICKER_MAP:
        return AFRICAN_TICKER_MAP[upper]
    # Already has suffix
    if "." in ticker:
        return ticker
    return ticker  # assume US listed


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
        # Fetch 60 days of data from detection date
        end_dt = det_dt + timedelta(days=max(windows) + 10)
        hist   = yf.Ticker(resolved).history(
            start=det_dt.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
            auto_adjust=True,
        )

        if hist.empty or len(hist) < 2:
            return results

        # Use first available close as baseline
        baseline = float(hist["Close"].iloc[0])
        if baseline == 0:
            return results

        dates = hist.index.tolist()

        for w in windows:
            target_dt = det_dt + timedelta(days=w)
            # Find closest trading day at or after target
            future = [d for d in dates if d.date() >= target_dt.date()]
            if not future:
                continue
            close_price = float(hist.loc[future[0], "Close"])
            pct_change  = (close_price - baseline) / baseline * 100
            results[f"{w}d"] = round(pct_change, 2)

    except Exception:
        pass

    return results


def _fetch_volume_spike(ticker: str, detection_date: str, window_days: int = 5) -> Optional[float]:
    """Fetch average volume spike % in first window_days after detection vs prior 20d average."""
    resolved = _resolve_ticker(ticker)
    try:
        det_dt   = datetime.strptime(detection_date, "%Y-%m-%d")
        pre_start = det_dt - timedelta(days=30)
        post_end  = det_dt + timedelta(days=window_days + 5)

        hist = yf.Ticker(resolved).history(
            start=pre_start.strftime("%Y-%m-%d"),
            end=post_end.strftime("%Y-%m-%d"),
            auto_adjust=True,
        )
        if hist.empty or "Volume" not in hist.columns:
            return None

        pre_vol  = hist[hist.index.date < det_dt.date()]["Volume"].mean()
        post_vol = hist[hist.index.date >= det_dt.date()]["Volume"].mean()

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
    magnitude_error: Optional[float] = None
    if (p10 is not None and
            expected_magnitude_low is not None and
            expected_magnitude_high is not None):
        mid = (expected_magnitude_low + expected_magnitude_high) / 2
        magnitude_error = round(abs(abs(p10) - mid), 2)

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
        resolved = _resolve_ticker(ticker)
        hist = yf.Ticker(resolved).history(period="5d", auto_adjust=True)
        if hist.empty:
            return None
        return round(float(hist["Close"].iloc[-1]), 2)
    except Exception:
        return None


def get_volatility(ticker: str, days: int = 30) -> Optional[float]:
    """Annualised volatility estimate over `days` trading days."""
    try:
        resolved = _resolve_ticker(ticker)
        hist = yf.Ticker(resolved).history(
            start=(datetime.utcnow() - timedelta(days=days + 10)).strftime("%Y-%m-%d"),
            auto_adjust=True,
        )
        if len(hist) < 5:
            return None
        import math
        returns = hist["Close"].pct_change().dropna()
        daily_std = float(returns.std())
        return round(daily_std * math.sqrt(252) * 100, 2)  # annualised %
    except Exception:
        return None
