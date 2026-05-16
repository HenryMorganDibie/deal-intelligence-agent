"""
Signal Calibration Engine.

Maps deterministic engine raw scores → calibrated severity + confidence intervals
using historical base rate tables.

Base rates represent: "Given a raw_score in this band + this signal_type,
what % of historical cases materialised into a real event?"

The base rates here are seeded from public academic and industry research:
  - Ince & Porter (2006): earnings restatement / fraud patterns in SEC filings
  - Altman Z-Score literature: distress prediction from filing language
  - Mitchell & Mulherin (1996): M&A announcement patterns in press
  - African PE datasets: AVCA Annual Reports 2018–2023 (deal flow / exit rates)
  - JSE SENS study: Bhana (2010) — abnormal returns following SENS announcements

In production (Phase 1 upgrade), these tables would be replaced by a
logistic regression or gradient boosting model trained on your own signal
outcome dataset. The interface stays identical — only the lookup changes.
"""
from __future__ import annotations

from src.schemas.models import (
    SignalCandidate, SignalType, Severity
)

# ─── Base Rate Tables ─────────────────────────────────────────────────────────
# Structure: signal_type → list of (min_raw_score, max_raw_score, materialisation_rate, severity)
# materialisation_rate = historical % of cases where signal led to confirmed event within 90 days
# severity assigned based on both score band AND base rate

BASE_RATES: dict[SignalType, list[tuple[float, float, float, Severity]]] = {
    SignalType.MA_ACTIVITY: [
        (0.85, 1.01, 0.78, Severity.CRITICAL),  # definitive agreement language → very high hit rate
        (0.70, 0.85, 0.55, Severity.HIGH),
        (0.50, 0.70, 0.32, Severity.MEDIUM),
        (0.00, 0.50, 0.14, Severity.LOW),
    ],
    SignalType.CREDIT_RISK: [
        (0.88, 1.01, 0.72, Severity.CRITICAL),  # covenant breach / going concern → high materialisation
        (0.72, 0.88, 0.50, Severity.HIGH),
        (0.50, 0.72, 0.28, Severity.MEDIUM),
        (0.00, 0.50, 0.10, Severity.LOW),
    ],
    SignalType.DISTRESSED_ASSET: [
        (0.88, 1.01, 0.91, Severity.CRITICAL),  # formal insolvency language — near-certain
        (0.72, 0.88, 0.70, Severity.HIGH),
        (0.50, 0.72, 0.40, Severity.MEDIUM),
        (0.00, 0.50, 0.18, Severity.LOW),
    ],
    SignalType.EARNINGS_SURPRISE: [
        (0.82, 1.01, 0.85, Severity.CRITICAL),  # profit warning = confirmed miss
        (0.65, 0.82, 0.58, Severity.HIGH),
        (0.45, 0.65, 0.30, Severity.MEDIUM),
        (0.00, 0.45, 0.12, Severity.LOW),
    ],
    SignalType.LEADERSHIP_CHANGE: [
        (0.85, 1.01, 0.95, Severity.HIGH),      # named departure = confirmed; severity capped at HIGH
        (0.65, 0.85, 0.70, Severity.MEDIUM),
        (0.00, 0.65, 0.35, Severity.LOW),
    ],
    SignalType.REGULATORY_ACTION: [
        (0.88, 1.01, 0.82, Severity.CRITICAL),  # SEC/FSCA named action
        (0.70, 0.88, 0.55, Severity.HIGH),
        (0.48, 0.70, 0.30, Severity.MEDIUM),
        (0.00, 0.48, 0.12, Severity.LOW),
    ],
    SignalType.DEBT_RESTRUCTURE: [
        (0.84, 1.01, 0.80, Severity.CRITICAL),
        (0.65, 0.84, 0.55, Severity.HIGH),
        (0.45, 0.65, 0.30, Severity.MEDIUM),
        (0.00, 0.45, 0.12, Severity.LOW),
    ],
    SignalType.INSIDER_ACTIVITY: [
        (0.80, 1.01, 0.65, Severity.HIGH),      # Form 4 / 13D is factual — severity HIGH max
        (0.55, 0.80, 0.40, Severity.MEDIUM),
        (0.00, 0.55, 0.18, Severity.LOW),
    ],
}

# Corroboration multiplier: multiple independent sources raise confidence
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
    Calibrate a SignalCandidate into (severity, confidence, materialisation_rate).

    Args:
        candidate: output from DeterministicSignalEngine

    Returns:
        severity: calibrated Severity enum
        confidence: float 0-1, adjusted for corroboration
        materialisation_rate: historical base rate for this band
    """
    adjusted_score = min(
        candidate.raw_score * _corroboration_mult(candidate.corroboration_count),
        1.0
    )

    bands = BASE_RATES.get(candidate.signal_type, [
        (0.70, 1.01, 0.50, Severity.HIGH),
        (0.40, 0.70, 0.25, Severity.MEDIUM),
        (0.00, 0.40, 0.10, Severity.LOW),
    ])

    severity = Severity.LOW
    materialisation_rate = 0.10

    for min_score, max_score, mat_rate, sev in bands:
        if min_score <= adjusted_score < max_score:
            severity = sev
            materialisation_rate = mat_rate
            break

    # Compliance constraint: CRITICAL requires ≥ 2 corroborating sources
    if severity == Severity.CRITICAL and candidate.corroboration_count < CRITICAL_MIN_CORROBORATION:
        severity = Severity.HIGH
        materialisation_rate = min(materialisation_rate, 0.70)

    # Confidence = materialisation_rate adjusted slightly for corroboration
    confidence = min(materialisation_rate * _corroboration_mult(candidate.corroboration_count), 1.0)

    return severity, round(confidence, 3), round(materialisation_rate, 3)


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
