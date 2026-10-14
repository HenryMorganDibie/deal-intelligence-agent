"""
Adaptive Calibration Engine (#7).
Outcome-aware calibration that improves with historical feedback.
Adjusts severity thresholds, confidence weights, and alpha multipliers
based on accumulated signal precision/recall data.
Replaces static base rate tables when sufficient data exists.
"""
from __future__ import annotations

from typing import Optional

from src.schemas.models import SignalType, Severity, SignalCandidate
from src.engines.feedback import get_signal_stats, false_positive_rate
from src.engines.calibration import BASE_RATES, calibrate as static_calibrate

# Minimum feedback samples before adaptive calibration activates
MIN_SAMPLES_FOR_ADAPTATION = 10

# How much adaptive calibration can shift the base rate (max ±30%)
MAX_ADAPTATION_SHIFT = 0.30

# Sector-specific precision adjustments (illustrative — extend with real data)
SECTOR_PRECISION_MAP: dict[str, dict[str, float]] = {
    "fintech":     {"credit_risk": 1.15, "regulatory_action": 1.20},
    "mining":      {"distressed_asset": 1.10, "credit_risk": 1.05},
    "telecom":     {"regulatory_action": 1.15, "m_and_a_activity": 0.95},
    "real_estate": {"credit_risk": 1.10, "debt_restructuring": 1.12},
}


def _labelled_samples(s: dict) -> int:
    """Feedback that says whether a flagged signal was right: confirmations and false positives.
    Missed-event and severity reports do not, so they must not activate precision adjustments."""
    return s.get("confirmed", 0) + s.get("false_positive", 0)


# Outcome counts per (signal type, market): {"credit_risk|africa": {"confirmed": n, "refuted": m}}.
# Read from the local outcome store unless a caller (the hosted API) supplies them.
_OUTCOME_STATS: Optional[dict[str, dict[str, int]]] = None


def set_outcome_stats(stats: Optional[dict[str, dict[str, int]]]) -> None:
    """Use these outcome counts instead of the local store (None: back to the store)."""
    global _OUTCOME_STATS
    _OUTCOME_STATS = stats


def outcome_stats() -> dict[str, dict[str, int]]:
    if _OUTCOME_STATS is not None:
        return _OUTCOME_STATS
    from src.engines.market_impact import _load
    stats: dict[str, dict[str, int]] = {}
    for o in _load():
        if o.get("event_confirmed") is None or not o.get("market"):
            continue
        s = stats.setdefault(f"{o['signal_type']}|{o['market']}", {"confirmed": 0, "refuted": 0})
        s["confirmed" if o["event_confirmed"] else "refuted"] += 1
    return stats


def _market_precision(signal_type: SignalType, market: Optional[str]) -> Optional[float]:
    """Observed precision for this signal type in this market, once there are enough outcomes."""
    if not market:
        return None
    s = outcome_stats().get(f"{signal_type.value}|{market}", {})
    n = s.get("confirmed", 0) + s.get("refuted", 0)
    return s["confirmed"] / n if n >= MIN_SAMPLES_FOR_ADAPTATION else None


def _get_precision_adjustment(signal_type: SignalType, market: Optional[str] = None) -> float:
    """
    Derive a precision-based adjustment factor. Prefers observed outcomes for the
    company's own market (so African signals calibrate on African outcomes), then
    analyst feedback. Returns a multiplier (>1 = more confident, <1 = less).
    """
    precision = _market_precision(signal_type, market)
    if precision is None:
        s = get_signal_stats().get(signal_type.value, {})
        if _labelled_samples(s) < MIN_SAMPLES_FOR_ADAPTATION:
            return 1.0  # not enough data — use static calibration
        precision = s.get("precision", 0.60)
    # Map precision to adjustment: precision 0.8 → 1.2x, precision 0.4 → 0.7x
    # Linear interpolation: adjustment = 0.5 + precision
    adjustment = 0.50 + precision
    # Clamp to allowed range
    return max(1.0 - MAX_ADAPTATION_SHIFT, min(1.0 + MAX_ADAPTATION_SHIFT, adjustment))


def _get_fp_penalty(signal_type: SignalType) -> float:
    """
    Penalty factor based on false positive rate.
    High FP rate → reduce effective score.
    """
    s = get_signal_stats().get(signal_type.value, {})
    labelled = _labelled_samples(s)
    if labelled < MIN_SAMPLES_FOR_ADAPTATION:
        return 1.0  # one or two reports must not move every future score
    fp_rate = s.get("false_positive", 0) / labelled
    # FP rate 0.5 → 0.75x penalty; FP rate 0 → 1.0x (no penalty)
    return max(0.60, 1.0 - fp_rate * 0.5)


def adaptive_calibrate(
    candidate: SignalCandidate,
    sector: Optional[str] = None,
    market: Optional[str] = None,
) -> tuple[Severity, float, float]:
    """
    Calibrate a candidate using adaptive + static calibration.

    Algorithm:
    1. Start with static calibration (base rate tables)
    2. Apply precision adjustment: observed outcomes in the company's market
       (us / africa) when there are enough, else analyst feedback
    3. Apply false positive penalty
    4. Apply sector-specific adjustment if available
    5. Re-derive severity from adjusted score

    Returns: (severity, confidence, materialisation_rate)
    """
    from src.engines.calibration import calibrate_all, CORROBORATION_MULTIPLIER, MAX_CORROBORATION_MULT, CRITICAL_MIN_CORROBORATION

    # Step 1: static calibration
    static_sev, static_conf, mat_rate = static_calibrate(candidate)

    # Step 2: precision adjustment
    precision_adj = _get_precision_adjustment(candidate.signal_type, market)

    # Step 3: FP penalty
    fp_penalty = _get_fp_penalty(candidate.signal_type)

    # Step 4: sector adjustment
    sector_adj = 1.0
    if sector:
        sector_lower = sector.lower()
        for sector_key, adjustments in SECTOR_PRECISION_MAP.items():
            if sector_key in sector_lower:
                sector_adj = adjustments.get(candidate.signal_type.value, 1.0)
                break

    # Compose adjusted score
    adjusted_score = candidate.raw_score * precision_adj * fp_penalty * sector_adj

    # Corroboration boost (same as static)
    corr_n = candidate.corroboration_count
    corr_mult = CORROBORATION_MULTIPLIER.get(corr_n, MAX_CORROBORATION_MULT)
    adjusted_score = min(adjusted_score * corr_mult, 1.0)

    # Re-derive severity from adjusted score using static band table
    from src.engines.calibration import BASE_RATES
    bands = BASE_RATES.get(candidate.signal_type, [
        (0.70, 1.01, 0.50, Severity.HIGH),
        (0.40, 0.70, 0.25, Severity.MEDIUM),
        (0.00, 0.40, 0.10, Severity.LOW),
    ])

    severity = Severity.LOW
    new_mat_rate = 0.10
    for min_s, max_s, mr, sev in bands:
        if min_s <= adjusted_score < max_s:
            severity = sev
            new_mat_rate = mr
            break

    # Compliance constraint: CRITICAL requires ≥2 sources
    if severity == Severity.CRITICAL and corr_n < CRITICAL_MIN_CORROBORATION:
        severity = Severity.HIGH
        new_mat_rate = min(new_mat_rate, 0.70)

    confidence = min(new_mat_rate * corr_mult * precision_adj, 1.0)

    return severity, round(confidence, 3), round(new_mat_rate, 3)


def get_calibration_report() -> dict:
    """
    Return a report showing how adaptive calibration differs from static
    for each signal type based on current feedback data.
    """
    stats = get_signal_stats()
    report = {}
    for sig_type in SignalType:
        s = stats.get(sig_type.value, {})
        total = s.get("total", 0)
        precision_adj = _get_precision_adjustment(sig_type)
        fp_penalty = _get_fp_penalty(sig_type)
        report[sig_type.value] = {
            "feedback_samples": total,
            "labelled_samples": _labelled_samples(s),
            "adaptive_active": _labelled_samples(s) >= MIN_SAMPLES_FOR_ADAPTATION,
            "precision_adjustment": round(precision_adj, 3),
            "fp_penalty": round(fp_penalty, 3),
            "net_adjustment": round(precision_adj * fp_penalty, 3),
            "precision": round(s.get("precision", 0.60), 3) if total > 0 else "insufficient data",
            "false_positive_rate": round(false_positive_rate(sig_type), 3),
        }
    return report
