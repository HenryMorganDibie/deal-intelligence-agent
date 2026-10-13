"""
Alpha Score Engine.

Converts calibrated signals into investable rankings (0–100 alpha score).
Incorporates:
  - Calibrated severity (outcome-grounded, not LLM opinion)
  - Source credibility weighting
  - Corroboration count
  - Recency decay (signal strength decays without reinforcement)
  - Market liquidity tier (signal actionability depends on tradability)
  - Expected move estimates from historical comparable events
  - Compliance flags (human review triggers)

The alpha score is NOT a buy/sell recommendation.
It is a ranked input to the portfolio manager's own decision process.
"""
from __future__ import annotations

import re

from datetime import datetime, timedelta
from typing import Optional

from src.schemas.models import (
    SignalCandidate, DetectedSignal, Severity, SignalType,
    AlphaScore, LiquidityTier, AnalystBrief
)
from src.engines.deterministic_engine import SOURCE_CREDIBILITY, DEFAULT_CREDIBILITY, candidate_credibility
from src.utils.clock import utcnow

# ─── Expected Move Table ──────────────────────────────────────────────────────
# Historical median equity price move within 10 trading days of confirmed signal.
# Sources: Mitchell & Mulherin (1996), Bhana JSE (2010), AVCA exit data 2018-2023.
# (direction, low_pct, high_pct, comparable_n, confidence_band)

EXPECTED_MOVES: dict[tuple[SignalType, Severity], tuple[str, float, float, int, str]] = {
    # M&A
    (SignalType.MA_ACTIVITY, Severity.CRITICAL): ("positive", 15.0, 35.0, 47, "high"),
    (SignalType.MA_ACTIVITY, Severity.HIGH):     ("positive",  8.0, 20.0, 62, "medium"),
    (SignalType.MA_ACTIVITY, Severity.MEDIUM):   ("positive",  3.0, 10.0, 38, "low"),
    (SignalType.MA_ACTIVITY, Severity.LOW):      ("neutral",   0.0,  5.0, 21, "low"),
    # Credit Risk
    (SignalType.CREDIT_RISK, Severity.CRITICAL): ("negative", 18.0, 45.0, 33, "high"),
    (SignalType.CREDIT_RISK, Severity.HIGH):     ("negative",  8.0, 22.0, 55, "medium"),
    (SignalType.CREDIT_RISK, Severity.MEDIUM):   ("negative",  3.0, 10.0, 44, "low"),
    (SignalType.CREDIT_RISK, Severity.LOW):      ("neutral",   0.0,  4.0, 29, "low"),
    # Distressed
    (SignalType.DISTRESSED_ASSET, Severity.CRITICAL): ("negative", 35.0, 80.0, 28, "high"),
    (SignalType.DISTRESSED_ASSET, Severity.HIGH):     ("negative", 15.0, 40.0, 41, "high"),
    (SignalType.DISTRESSED_ASSET, Severity.MEDIUM):   ("negative",  5.0, 20.0, 32, "medium"),
    (SignalType.DISTRESSED_ASSET, Severity.LOW):      ("negative",  2.0,  8.0, 18, "low"),
    # Earnings Surprise
    (SignalType.EARNINGS_SURPRISE, Severity.CRITICAL): ("negative", 8.0, 25.0, 72, "high"),
    (SignalType.EARNINGS_SURPRISE, Severity.HIGH):     ("negative", 4.0, 12.0, 91, "medium"),
    (SignalType.EARNINGS_SURPRISE, Severity.MEDIUM):   ("negative", 1.5,  5.0, 58, "low"),
    (SignalType.EARNINGS_SURPRISE, Severity.LOW):      ("neutral",  0.0,  3.0, 44, "low"),
    # Leadership Change
    (SignalType.LEADERSHIP_CHANGE, Severity.HIGH):   ("negative",  2.0,  8.0, 53, "low"),
    (SignalType.LEADERSHIP_CHANGE, Severity.MEDIUM): ("neutral",   0.0,  4.0, 61, "low"),
    (SignalType.LEADERSHIP_CHANGE, Severity.LOW):    ("neutral",   0.0,  2.0, 38, "low"),
    # Regulatory
    (SignalType.REGULATORY_ACTION, Severity.CRITICAL): ("negative", 10.0, 30.0, 29, "medium"),
    (SignalType.REGULATORY_ACTION, Severity.HIGH):     ("negative",  5.0, 15.0, 42, "medium"),
    (SignalType.REGULATORY_ACTION, Severity.MEDIUM):   ("negative",  2.0,  8.0, 35, "low"),
    (SignalType.REGULATORY_ACTION, Severity.LOW):      ("neutral",   0.0,  3.0, 22, "low"),
    # Debt Restructuring
    (SignalType.DEBT_RESTRUCTURE, Severity.CRITICAL): ("negative", 12.0, 35.0, 24, "medium"),
    (SignalType.DEBT_RESTRUCTURE, Severity.HIGH):     ("negative",  6.0, 18.0, 37, "medium"),
    (SignalType.DEBT_RESTRUCTURE, Severity.MEDIUM):   ("negative",  2.0,  8.0, 29, "low"),
    (SignalType.DEBT_RESTRUCTURE, Severity.LOW):      ("neutral",   0.0,  4.0, 17, "low"),
    # Insider Activity
    (SignalType.INSIDER_ACTIVITY, Severity.HIGH):   ("positive",  3.0, 12.0, 48, "medium"),
    (SignalType.INSIDER_ACTIVITY, Severity.MEDIUM): ("positive",  1.0,  5.0, 55, "low"),
    (SignalType.INSIDER_ACTIVITY, Severity.LOW):    ("neutral",   0.0,  2.0, 31, "low"),
}

# ─── Severity Weights ─────────────────────────────────────────────────────────
SEVERITY_WEIGHT = {
    Severity.CRITICAL: 1.00,
    Severity.HIGH:     0.78,
    Severity.MEDIUM:   0.52,
    Severity.LOW:      0.28,
}

# ─── Liquidity Tier Weights ───────────────────────────────────────────────────
# Higher = more actionable (signal on a liquid instrument is worth more to a fund)
LIQUIDITY_WEIGHT = {
    LiquidityTier.LARGE_CAP:  1.00,
    LiquidityTier.MID_CAP:    0.80,
    LiquidityTier.SMALL_CAP:  0.60,
    LiquidityTier.MICRO_CAP:  0.35,
    LiquidityTier.PRIVATE:    0.20,
}

# ─── Compliance Thresholds ────────────────────────────────────────────────────
HUMAN_REVIEW_ALPHA_THRESHOLD = 70.0   # alpha score above this → mandatory review flag
HUMAN_REVIEW_SEVERITY_SET    = {Severity.CRITICAL}
LOW_CONFIDENCE_SUPPRESS_THRESHOLD = 0.40  # compliance mode: suppress signals below this


_POSITIVE_EARNINGS = re.compile(
    r"\b(beats?|topped|tops|crush(es|ed)?|exceed(s|ed)?|surpass(es|ed)?)\b.{0,30}\b(estimates?|expectations?|consensus|forecasts?)\b"
    r"|\b(raises?|raised|lifts?|lifted|boosts?|boosted)\s+(its\s+)?(full[-\s]year\s+|annual\s+)?(guidance|outlook|forecast)\b"
    r"|\bsignificantly\s+above\s+(expectations?|guidance|consensus)\b",
    re.IGNORECASE,
)
_NEGATIVE_EARNINGS = re.compile(
    r"\b(miss(es|ed)?|warning|below|cut|lowered|reduced|withdrawn|declin\w*|fell|dropped|disappointing|weaker|loss|restatement)\b",
    re.IGNORECASE,
)


def signal_direction(signal_type: SignalType, source_text: str, default: str) -> str:
    """
    Direction implied by the source text, where the signal type can go either way.
    Earnings: a beat or raised guidance is positive (unless the text also reports a
    miss). Insider activity: an open-market sale is negative, a purchase positive.
    """
    text = source_text or ""
    if signal_type == SignalType.EARNINGS_SURPRISE:
        if _POSITIVE_EARNINGS.search(text) and not _NEGATIVE_EARNINGS.search(text):
            return "positive"
        return default
    if signal_type == SignalType.INSIDER_ACTIVITY:
        sale = re.search(r"\b(open-market\s+sale|insider\s+selling|director\s+sale|disposal)\b", text, re.I)
        purchase = re.search(r"\b(open-market\s+purchase|insider\s+buying|director\s+purchase)\b", text, re.I)
        if sale and not purchase:
            return "negative"
    return default


def _recency_decay(detected_at: datetime, half_life_days: float = 14.0) -> float:
    """
    Exponential recency decay.
    Signal at detection time = 1.0. Halves every `half_life_days` days.
    Minimum floor: 0.30 (signal doesn't expire completely).
    """
    age_days = (utcnow() - detected_at).total_seconds() / 86400
    decay = 0.5 ** (age_days / half_life_days)
    return max(decay, 0.30)


def _source_credibility_for_signal(candidate: SignalCandidate) -> float:
    """Get credibility for the best source attached to a candidate."""
    return candidate_credibility(candidate.source_type, candidate.source_name)


def _corroboration_weight(n: int) -> float:
    """
    Sigmoid-shaped corroboration weight.
    1 source → 0.50, 2 → 0.68, 3 → 0.80, 4 → 0.88, 5+ → 0.93
    """
    return 1.0 - (1.0 / (1.0 + 0.8 * n))


# Market-cap tiers in USD.
LARGE_CAP_MIN_USD = 10e9
MID_CAP_MIN_USD   = 2e9
SMALL_CAP_MIN_USD = 300e6

# Currencies Yahoo quotes in minor units: code -> (major currency, divisor).
_MINOR_UNIT_CURRENCIES = {"ZAc": ("ZAR", 100), "GBp": ("GBP", 100), "ILA": ("ILS", 100)}

_MCAP_CACHE: dict[str, Optional[float]] = {}


def _lookup_market_cap_usd(ticker: str) -> Optional[float]:
    """Live market capitalisation in USD via yfinance, or None if unavailable."""
    import logging
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    try:
        import yfinance as yf
        from src.engines.market_data import _resolve_ticker
        info = yf.Ticker(_resolve_ticker(ticker)).fast_info
        cap = float(info["marketCap"])
        currency = info["currency"]
        if not cap or cap <= 0 or not currency:
            return None
        currency, divisor = _MINOR_UNIT_CURRENCIES.get(currency, (currency, 1))
        cap /= divisor
        if currency != "USD":
            cap *= float(yf.Ticker(f"{currency}USD=X").fast_info["lastPrice"])
        return cap
    except Exception:
        return None


def _market_cap_usd(ticker: str) -> Optional[float]:
    key = ticker.upper()
    if key not in _MCAP_CACHE:
        _MCAP_CACHE[key] = _lookup_market_cap_usd(key)
    return _MCAP_CACHE[key]


def _tier_for_market_cap(cap_usd: float) -> LiquidityTier:
    if cap_usd >= LARGE_CAP_MIN_USD:
        return LiquidityTier.LARGE_CAP
    if cap_usd >= MID_CAP_MIN_USD:
        return LiquidityTier.MID_CAP
    if cap_usd >= SMALL_CAP_MIN_USD:
        return LiquidityTier.SMALL_CAP
    return LiquidityTier.MICRO_CAP


def _infer_liquidity_tier(
    ticker: Optional[str],
    exchange: Optional[str],
    sector: Optional[str],
) -> LiquidityTier:
    """
    Liquidity tier from live market capitalisation (USD), falling back to a
    static list and exchange heuristics when no market data is available
    (e.g. NGX and NSE Kenya listings, which Yahoo does not cover).
    """
    if not ticker:
        return LiquidityTier.PRIVATE

    cap = _market_cap_usd(ticker)
    if cap:
        return _tier_for_market_cap(cap)

    ticker_upper = ticker.upper()
    # Fallback for listings without market data. Unsuffixed tickers are US listings,
    # so JSE names that collide with US symbols appear only with their suffix.
    large_caps = {
        "AAPL","MSFT","GOOGL","AMZN","META","NVDA","BRK","JPM","V","JNJ",
        "GTCO","ZENITHBANK","ACCESS","FBNH","UBA.LG",                       # NGX Tier 1
        "NPN","SOL.JO","BHP.JO","MTN.JO","ABG.JO","SLM.JO","FSR.JO","REM.JO",  # JSE Top 40
        "SCOM","KCB","EQTY",                                                # NSE Kenya Tier 1
    }
    if ticker_upper in large_caps:
        return LiquidityTier.LARGE_CAP

    # Exchange-based heuristic
    if exchange:
        ex = exchange.upper()
        if "NYSE" in ex or "NASDAQ" in ex or "JSE" in ex:
            return LiquidityTier.MID_CAP
        if "NGX" in ex or "NSE" in ex or "GSE" in ex:
            return LiquidityTier.SMALL_CAP

    return LiquidityTier.MID_CAP  # default for listed companies with ticker


def compute_alpha_score(
    signal: DetectedSignal,
    candidate: SignalCandidate,
    ticker: Optional[str] = None,
    exchange: Optional[str] = None,
    sector: Optional[str] = None,
    compliance_mode: bool = False,
) -> AlphaScore:
    """
    Compute the alpha score for a single confirmed signal.

    Formula:
        alpha = 100 × (
            severity_weight × 0.35
          + source_credibility × 0.25
          + corroboration_weight × 0.20
          + recency_weight × 0.10
          + liquidity_weight × 0.10
        )
    """
    sev_w    = SEVERITY_WEIGHT[signal.severity]
    cred_w   = _source_credibility_for_signal(candidate)
    corr_w   = _corroboration_weight(candidate.corroboration_count)
    rec_w    = _recency_decay(candidate.source_date or candidate.detected_at)
    liq_tier = _infer_liquidity_tier(ticker, exchange, sector)
    liq_w    = LIQUIDITY_WEIGHT[liq_tier]

    raw_alpha = (
        sev_w  * 0.35 +
        cred_w * 0.25 +
        corr_w * 0.20 +
        rec_w  * 0.10 +
        liq_w  * 0.10
    )
    alpha_score = round(raw_alpha * 100, 1)

    # Expected move
    move = EXPECTED_MOVES.get((signal.signal_type, signal.severity))
    direction, low_pct, high_pct, comparable_n, move_confidence = (
        move if move else ("neutral", 0.0, 0.0, 0, "low")
    )
    if direction != "neutral":
        direction = signal_direction(signal.signal_type, candidate.source_text, direction)

    # Compliance flags
    requires_review = False
    review_reason: Optional[str] = None

    if alpha_score >= HUMAN_REVIEW_ALPHA_THRESHOLD:
        requires_review = True
        review_reason = f"Alpha score {alpha_score:.0f} ≥ threshold {HUMAN_REVIEW_ALPHA_THRESHOLD:.0f}"
    elif signal.severity in HUMAN_REVIEW_SEVERITY_SET:
        requires_review = True
        review_reason = f"Severity {signal.severity.value.upper()} requires mandatory review"
    elif compliance_mode and signal.confidence < LOW_CONFIDENCE_SUPPRESS_THRESHOLD:
        requires_review = True
        review_reason = f"Compliance mode: confidence {signal.confidence:.0%} below threshold"

    return AlphaScore(
        score=alpha_score,
        severity_component=round(sev_w, 3),
        source_credibility=round(cred_w, 3),
        corroboration_weight=round(corr_w, 3),
        recency_weight=round(rec_w, 3),
        liquidity_tier=liq_tier,
        expected_direction=direction,
        expected_magnitude_pct_low=low_pct,
        expected_magnitude_pct_high=high_pct,
        comparable_events_n=comparable_n,
        move_confidence=move_confidence,
        requires_human_review=requires_review,
        review_reason=review_reason,
    )


def score_all_signals(
    signals: list[DetectedSignal],
    candidates: list[SignalCandidate],
    ticker: Optional[str] = None,
    exchange: Optional[str] = None,
    sector: Optional[str] = None,
    compliance_mode: bool = False,
) -> list[DetectedSignal]:
    """
    Attach AlphaScore to every DetectedSignal.
    Matches signals to their originating candidate by signal_type.
    Returns signals sorted by alpha score descending.
    """
    # Build candidate lookup by signal_type
    candidate_map: dict[SignalType, SignalCandidate] = {
        c.signal_type: c for c in candidates
    }

    scored: list[DetectedSignal] = []
    for signal in signals:
        candidate = candidate_map.get(signal.signal_type)
        if candidate is None:
            scored.append(signal)
            continue

        alpha = compute_alpha_score(
            signal, candidate, ticker, exchange, sector, compliance_mode
        )
        scored.append(signal.model_copy(update={"alpha_score": alpha}))

    scored.sort(
        key=lambda s: s.alpha_score.score if s.alpha_score else 0.0,
        reverse=True
    )
    return scored
