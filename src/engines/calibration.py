"""
Signal Calibration Engine.

Maps a candidate's raw rule score to a severity, and attaches the measured
probability that signals like it materialise.

Severity bands are rule-strength thresholds: a design choice, stated here and
not presented as data. "Definitive agreement" language scores higher than
"in talks", so it lands in a higher band.

Confidence is measured, not asserted: the share of past flags of the same type
and severity that were followed within 90 days by a confirming filing,
exchange disclosure or credible report, from the walk-forward backtest
(src/engines/measured.py, docs/BACKTEST.md). For earnings and insider signals,
whose event is the disclosure itself, it is the share whose market-adjusted
move went the hypothesised way. Small samples are smoothed toward the
type-level rate, and adaptive calibration then shifts it with live outcomes.
"""
from __future__ import annotations

from src.schemas.models import (
    SignalCandidate, SignalType, Severity
)

# ─── Severity Bands ───────────────────────────────────────────────────────────
# signal_type -> (min_score, max_score, severity), on the corroboration-adjusted rule score.
# Thresholds are design choices (rule strength), not measured rates.
SEVERITY_BANDS: dict[SignalType, list[tuple[float, float, Severity]]] = {
    SignalType.MA_ACTIVITY:       [(0.85, 1.01, Severity.CRITICAL), (0.70, 0.85, Severity.HIGH), (0.50, 0.70, Severity.MEDIUM), (0.00, 0.50, Severity.LOW)],
    SignalType.CREDIT_RISK:       [(0.88, 1.01, Severity.CRITICAL), (0.72, 0.88, Severity.HIGH), (0.50, 0.72, Severity.MEDIUM), (0.00, 0.50, Severity.LOW)],
    SignalType.DISTRESSED_ASSET:  [(0.88, 1.01, Severity.CRITICAL), (0.72, 0.88, Severity.HIGH), (0.50, 0.72, Severity.MEDIUM), (0.00, 0.50, Severity.LOW)],
    SignalType.EARNINGS_SURPRISE: [(0.82, 1.01, Severity.CRITICAL), (0.65, 0.82, Severity.HIGH), (0.45, 0.65, Severity.MEDIUM), (0.00, 0.45, Severity.LOW)],
    SignalType.LEADERSHIP_CHANGE: [(0.85, 1.01, Severity.HIGH), (0.65, 0.85, Severity.MEDIUM), (0.00, 0.65, Severity.LOW)],
    SignalType.REGULATORY_ACTION: [(0.88, 1.01, Severity.CRITICAL), (0.70, 0.88, Severity.HIGH), (0.48, 0.70, Severity.MEDIUM), (0.00, 0.48, Severity.LOW)],
    SignalType.DEBT_RESTRUCTURE:  [(0.84, 1.01, Severity.CRITICAL), (0.65, 0.84, Severity.HIGH), (0.45, 0.65, Severity.MEDIUM), (0.00, 0.45, Severity.LOW)],
    SignalType.INSIDER_ACTIVITY:  [(0.80, 1.01, Severity.HIGH), (0.55, 0.80, Severity.MEDIUM), (0.00, 0.55, Severity.LOW)],
}
DEFAULT_BANDS = [(0.70, 1.01, Severity.HIGH), (0.40, 0.70, Severity.MEDIUM), (0.00, 0.40, Severity.LOW)]


def severity_for_score(signal_type: SignalType, adjusted_score: float) -> Severity:
    for lo, hi, sev in SEVERITY_BANDS.get(signal_type, DEFAULT_BANDS):
        if lo <= adjusted_score < hi:
            return sev
    return Severity.LOW


def measured_rate(signal_type: SignalType, severity: Severity) -> float:
    from src.engines.measured import confirmation_rate
    return confirmation_rate(signal_type.value, severity.value)["rate"]


# Corroboration raises the rule score used for the severity band (not the measured confidence).
CORROBORATION_MULTIPLIER: dict[int, float] = {
    1: 1.00,
    2: 1.12,
    3: 1.20,
    4: 1.25,
    5: 1.28,
}
MAX_CORROBORATION_MULT = 1.30

# Minimum corroboration required to reach CRITICAL (compliance constraint)
CRITICAL_MIN_CORROBORATION = 2


def _corroboration_mult(n: int) -> float:
    return CORROBORATION_MULTIPLIER.get(n, MAX_CORROBORATION_MULT)


def calibrate(candidate: SignalCandidate) -> tuple[Severity, float, float]:
    """
    (severity, confidence, materialisation_rate) for a candidate.

    severity: from the rule score (raised by corroboration) and the type's bands; CRITICAL needs at
    least two corroborating sources. confidence and materialisation_rate: the measured rate for this
    type and severity (they are the same number; both names are kept for callers).
    """
    adjusted_score = min(candidate.raw_score * _corroboration_mult(candidate.corroboration_count), 1.0)
    severity = severity_for_score(candidate.signal_type, adjusted_score)
    if severity == Severity.CRITICAL and candidate.corroboration_count < CRITICAL_MIN_CORROBORATION:
        severity = Severity.HIGH
    rate = measured_rate(candidate.signal_type, severity)
    return severity, round(rate, 3), round(rate, 3)


def calibrate_all(candidates: list[SignalCandidate]) -> list[tuple[SignalCandidate, Severity, float, float]]:
    """
    Calibrate a full list of candidates.
    Returns list of (candidate, severity, confidence, materialisation_rate).
    """
    results = []
    for c in candidates:
        severity, confidence, mat_rate = calibrate(c)
        results.append((c, severity, confidence, mat_rate))
    return results
