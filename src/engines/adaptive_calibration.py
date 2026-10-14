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
from src.engines.calibration import calibrate as static_calibrate

# Minimum feedback samples before adaptive calibration activates
MIN_SAMPLES_FOR_ADAPTATION = 10

# How much adaptive calibration can shift the base rate (max ±30%)
MAX_ADAPTATION_SHIFT = 0.30

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
    Static calibration, then adjusted by what has been observed since:
    1. Severity and the measured rate from the static (backtest-based) calibration.
    2. Once a signal type has MIN_SAMPLES_FOR_ADAPTATION live outcomes in the company's market
       (us / africa), or that many labelled analyst reviews, the rule score is scaled by observed
       precision and false-positive rate, and severity re-derived from the same bands.
    3. Confidence is the measured rate for the resulting severity, replaced by the live market
       precision when it exists. `sector` is accepted for interface stability; no sector effect is
       applied, because none has been measured.

    Returns: (severity, confidence, materialisation_rate)
    """
    from src.engines.calibration import (CORROBORATION_MULTIPLIER, CRITICAL_MIN_CORROBORATION,
                                         MAX_CORROBORATION_MULT, measured_rate, severity_for_score)

    static_sev, static_conf, mat_rate = static_calibrate(candidate)
    precision_adj = _get_precision_adjustment(candidate.signal_type, market)
    fp_penalty = _get_fp_penalty(candidate.signal_type)
    if precision_adj == 1.0 and fp_penalty == 1.0:
        return static_sev, static_conf, mat_rate

    corr_n = candidate.corroboration_count
    corr_mult = CORROBORATION_MULTIPLIER.get(corr_n, MAX_CORROBORATION_MULT)
    adjusted_score = min(candidate.raw_score * precision_adj * fp_penalty * corr_mult, 1.0)
    severity = severity_for_score(candidate.signal_type, adjusted_score)
    if severity == Severity.CRITICAL and corr_n < CRITICAL_MIN_CORROBORATION:
        severity = Severity.HIGH
    live = _market_precision(candidate.signal_type, market)
    confidence = live if live is not None else measured_rate(candidate.signal_type, severity)
    return severity, round(confidence, 3), round(confidence, 3)


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
