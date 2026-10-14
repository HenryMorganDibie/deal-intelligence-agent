"""
Alpha Score Engine.

The alpha score is a 0-100 ranking of how actionable a confirmed signal is. It is
a weighted composite, and the weights are design choices, stated here rather than
presented as fitted:

    alpha = 100 x (0.35 severity + 0.25 source credibility + 0.20 corroboration
                   + 0.10 recency + 0.10 liquidity)

Whether a higher alpha actually goes with more confirmed events is measured in the
walk-forward backtest (docs/BACKTEST.md, "Does alpha rank signals?"), and the
result is published whatever it shows.

The expected move attached to each score is measured, not assumed: the
distribution of market-adjusted 10-day returns that followed the same kind of
flag in the backtest (src/engines/measured.py), given as a signed interquartile
range with its median and sample size, or "insufficient history" when there are
fewer than 10 observations. Its direction is the text's own (an earnings beat,
an insider purchase) when the source states one, else the measured majority.

The alpha score is NOT a buy/sell recommendation.
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

# ─── Component weights (design choices; see the module docstring) ─────────────
WEIGHTS = {"severity": 0.35, "source_credibility": 0.25, "corroboration": 0.20, "recency": 0.10, "liquidity": 0.10}

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
    r"|\bsignificantly\s+above\s+(expectations?|guidance|consensus)\b"
    r"|\b(d[eé]passe(nt)?|sup[eé]rieurs?\s+aux)\s+(les\s+)?(attentes|pr[eé]visions|estimations)\b"
    r"|\b(rel[eè]ve|am[eé]liore|rehausse)\s+(ses|son)\s+(pr[eé]visions|objectifs?|perspectives)\b"
    r"|\b(sobem|sobe|disparam|crescem|acima\s+das\s+(expectativas|estimativas))\b"
    r"|(ترتفع|ارتفاع|قفزة|تقفز|تتجاوز\s+التوقعات|نمو)",
    re.IGNORECASE,
)
_NEGATIVE_EARNINGS = re.compile(
    r"\b(miss(es|ed)?|warning|below|cut|lowered|reduced|withdrawn|declin\w*|fell|dropped|disappointing|weaker|loss|restatement"
    r"|avertissement|baisse|recul|recule|chute|perte|inf[eé]rieurs?|abaisse|retraitement"
    r"|caem|cai|recua|recuam|desce|descem|queda|preju[ií]zo)\b"
    r"|(تتراجع|تراجع|تنخفض|انخفاض|هبوط|خسائر|خسارة)",
    re.IGNORECASE,
)


INSIDER_SALE = re.compile(
    r"\b(open-market\s+sale|insider\s+selling|director\s+sale|disposal"
    r"|(cession|vente)\s+d['’]?\s*actions\s+par)\b", re.IGNORECASE)
INSIDER_PURCHASE = re.compile(
    r"\b(open-market\s+purchase|insider\s+buying|director\s+purchase"
    r"|(achat|acquisition)\s+d['’]?\s*actions\s+par)\b", re.IGNORECASE)


_DEALING_NOTICE = re.compile(r"\b(directors?'?\s*dealings?|share\s+dealings?|insider\s+(dealings?|notification))\b", re.IGNORECASE)


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
        sale, purchase = bool(INSIDER_SALE.search(text)), bool(INSIDER_PURCHASE.search(text))
        if sale and not purchase:
            return "negative"
        if not sale and not purchase and _DEALING_NOTICE.search(text):
            return "neutral"        # an exchange dealing notice that does not say buy or sell
    return default


def evidence_direction(signal_type: SignalType, text: str) -> Optional[str]:
    """
    Direction the evidence itself states, or None when it does not say. Unlike
    signal_direction there is no default: an earnings item is a miss only if the
    text reports one, and insider activity is buying only if it shows a purchase.
    """
    text = text or ""
    if signal_type == SignalType.EARNINGS_SURPRISE:
        pos, neg = bool(_POSITIVE_EARNINGS.search(text)), bool(_NEGATIVE_EARNINGS.search(text))
    elif signal_type == SignalType.INSIDER_ACTIVITY:
        pos, neg = bool(INSIDER_PURCHASE.search(text)), bool(INSIDER_SALE.search(text))
    else:
        return None
    if pos == neg:
        return None
    return "positive" if pos else "negative"


def _recency_decay(detected_at: datetime, half_life_days: float = 14.0, now: Optional[datetime] = None) -> float:
    """
    Exponential recency decay.
    Signal at detection time = 1.0. Halves every `half_life_days` days.
    Minimum floor: 0.30 (signal doesn't expire completely).
    """
    age_days = ((now or utcnow()) - detected_at).total_seconds() / 86400
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


def alpha_components(severity: Severity, candidate: SignalCandidate, liquidity: LiquidityTier,
                     now: Optional[datetime] = None) -> dict[str, float]:
    """The five component values (0-1) and the weighted 0-100 score."""
    c = {
        "severity": SEVERITY_WEIGHT[severity],
        "source_credibility": _source_credibility_for_signal(candidate),
        "corroboration": _corroboration_weight(candidate.corroboration_count),
        "recency": _recency_decay(candidate.source_date or candidate.detected_at, now=now),
        "liquidity": LIQUIDITY_WEIGHT[liquidity],
    }
    c["score"] = round(100 * sum(WEIGHTS[k] * c[k] for k in WEIGHTS), 1)
    return c


def expected_move_for(signal_type: SignalType, severity: Severity, source_text: str) -> dict:
    """Measured move after this kind of flag, with the text's own direction when it states one."""
    from src.engines.measured import expected_move, measured_direction, move_confidence
    move = expected_move(signal_type.value, severity.value)
    stated = evidence_direction(signal_type, source_text)
    if signal_type == SignalType.INSIDER_ACTIVITY and stated is None and _DEALING_NOTICE.search(source_text or ""):
        stated = "neutral"
    direction = stated or measured_direction(move)
    if not move:
        return {"direction": stated, "low": None, "high": None, "median": None, "n": 0,
                "confidence": "insufficient", "basis": "insufficient history for this kind of flag"}
    return {"direction": direction, "low": move["p25"], "high": move["p75"], "median": move["median"],
            "n": move["n"], "confidence": move_confidence(move["n"]),
            "basis": f"market-adjusted 10-day return after {move['basis']} in the backtest"
                     + ("; direction stated by the source" if stated else "")}


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

    Formula (design weights, validated in the backtest):
        alpha = 100 × (
            severity_weight × 0.35
          + source_credibility × 0.25
          + corroboration_weight × 0.20
          + recency_weight × 0.10
          + liquidity_weight × 0.10
        )
    """
    liq_tier = _infer_liquidity_tier(ticker, exchange, sector)
    c = alpha_components(signal.severity, candidate, liq_tier)
    alpha_score = c["score"]
    move = expected_move_for(signal.signal_type, signal.severity, candidate.source_text)

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
        severity_component=round(c["severity"], 3),
        source_credibility=round(c["source_credibility"], 3),
        corroboration_weight=round(c["corroboration"], 3),
        recency_weight=round(c["recency"], 3),
        liquidity_tier=liq_tier,
        expected_direction=move["direction"],
        expected_magnitude_pct_low=move["low"],
        expected_magnitude_pct_high=move["high"],
        expected_median_pct=move["median"],
        comparable_events_n=move["n"],
        move_confidence=move["confidence"],
        move_basis=move["basis"],
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
