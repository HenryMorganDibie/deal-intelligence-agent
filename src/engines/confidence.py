"""
Evidence-quality breakdown (#5).

A rubric, not a probability: seven graded components of how well a signal is
supported (source reliability, corroboration, filing strength, historical
precision, entity matches, recency, extraction), combined with the fixed
weights below. The grade steps are design choices and are stated as such.
The one measured component is historical precision: the measured hit rate for
the signal type (src/engines/measured.py), or the analysts' observed precision
once there are enough labelled reviews. The probability a signal materialises
is the separate, measured `confidence` on the signal.
"""
from __future__ import annotations

import re

from src.schemas.models import (
    SignalCandidate, ConfidenceDecomposition,
    SignalType
)
from src.engines.deterministic_engine import candidate_credibility
from src.engines.feedback import get_signal_stats, get_source_reliability
from src.utils.clock import utcnow

# Component weights — must sum to 1.0
WEIGHTS = {
    "source_reliability":   0.22,
    "corroboration":        0.20,
    "filing_strength":      0.18,
    "historical_precision": 0.15,
    "entity_match":         0.10,
    "temporal_relevance":   0.10,
    "extraction":           0.05,
}

# Filing types ranked by evidential strength
FILING_STRENGTH: dict[str, float] = {
    "8-K":                1.00,  # material event — highest
    "JSE SENS":           1.00,
    "NGX Disclosure":     0.95,
    "NSE Disclosure":     0.93,
    "SC 13D":             0.95,
    "SCHEDULE 13D":       0.95,
    "SC 13G":             0.90,
    "4":                  0.88,  # Form 4 (EDGAR form type "4")
    "DEF 14A":            0.85,
    "10-K":               0.80,
    "10-Q":               0.75,
    "news":               0.50,  # news baseline
    "pe_source":          0.60,
}

HALF_LIFE_DAYS = 21.0  # temporal relevance half-life


def _source_reliability_score(candidate: SignalCandidate) -> float:
    """Combined static + learned source reliability."""
    static_score = candidate_credibility(candidate.source_type, candidate.source_name)
    learned = get_source_reliability()
    learned_score = learned.get(candidate.source_name, static_score)
    # Blend: 70% static (stable), 30% learned (adaptive)
    return round(0.70 * static_score + 0.30 * learned_score, 4)


def _corroboration_score(n: int) -> float:
    """Sigmoid-shaped corroboration score: 1→0.40, 2→0.60, 3→0.75, 4→0.85, 5+→0.92."""
    return round(1.0 - 1.0 / (1.0 + 0.9 * n), 4)


def _filing_strength_score(candidate: SignalCandidate) -> float:
    """Score based on the type of source that triggered the signal."""
    if candidate.source_type == "filing":
        return FILING_STRENGTH.get(candidate.source_name, 0.70)
    if candidate.source_type == "pe_source":
        return FILING_STRENGTH["pe_source"]
    return FILING_STRENGTH["news"]


def _historical_precision_score(signal_type: SignalType) -> float:
    """Analysts' observed precision once there are enough labels, else the measured backtest rate."""
    from src.engines.adaptive_calibration import MIN_SAMPLES_FOR_ADAPTATION, _labelled_samples
    from src.engines.measured import confirmation_rate
    s = get_signal_stats().get(signal_type.value)
    if not s or _labelled_samples(s) < MIN_SAMPLES_FOR_ADAPTATION:
        return round(confirmation_rate(signal_type.value, "")["rate"], 4)
    return round(s["precision"], 4)


def _entity_match_score(candidate: SignalCandidate) -> float:
    """Score verified target attribution; unverified candidates receive a neutral score."""
    if candidate.target_entity_matched is True:
        return 0.95
    if candidate.target_entity_matched is False:
        return 0.10
    return 0.50


def _temporal_relevance_score(candidate: SignalCandidate) -> float:
    """Exponential decay from detection time. Floor at 0.35."""
    age_days = (utcnow() - (candidate.source_date or candidate.detected_at)).total_seconds() / 86400
    decay = 0.5 ** (age_days / HALF_LIFE_DAYS)
    return round(max(decay, 0.35), 4)


def _extraction_confidence(candidate: SignalCandidate) -> float:
    """Measure how many distinct source clauses reproduce a fired extraction rule."""
    text = candidate.source_text.strip()
    if not text:
        return 0.25
    if not candidate.matched_patterns:
        return 0.35

    matched_clauses = 0
    for clause in re.split(r"(?<=[.!?;])\s+|\n+", text):
        if any(re.search(pattern, clause, re.IGNORECASE) for pattern in candidate.matched_patterns):
            matched_clauses += 1

    if matched_clauses == 0:
        return 0.40
    if matched_clauses == 1:
        return 0.65
    if matched_clauses == 2:
        return 0.80
    return 0.90


def decompose(candidate: SignalCandidate, calibration_adjustment: float = 1.0) -> ConfidenceDecomposition:
    """
    Compute full confidence decomposition for a signal candidate.
    Returns a ConfidenceDecomposition with all component scores.
    """
    sr  = _source_reliability_score(candidate)
    cs  = _corroboration_score(candidate.corroboration_count)
    fs  = _filing_strength_score(candidate)
    hp  = _historical_precision_score(candidate.signal_type)
    em  = _entity_match_score(candidate)
    tr  = _temporal_relevance_score(candidate)
    exc = _extraction_confidence(candidate)

    components = {
        "source_reliability":   sr,
        "corroboration":        cs,
        "filing_strength":      fs,
        "historical_precision": hp,
        "entity_match":         em,
        "temporal_relevance":   tr,
        "extraction":           exc,
    }

    weighted_sum = sum(components[k] * WEIGHTS[k] for k in WEIGHTS)
    final = min(weighted_sum * calibration_adjustment, 1.0)

    reasoning_parts = []
    if sr < 0.60:
        reasoning_parts.append(f"low source reliability ({sr:.0%})")
    if cs < 0.55:
        reasoning_parts.append(f"single-source ({candidate.corroboration_count} corroboration)")
    if hp < 0.50:
        reasoning_parts.append("limited historical precision data")
    if tr < 0.50:
        reasoning_parts.append("signal age reducing temporal relevance")
    reasoning = "Confidence reduced by: " + ", ".join(reasoning_parts) if reasoning_parts else "All components within normal range."

    return ConfidenceDecomposition(
        final_confidence=round(final, 4),
        source_reliability_score=sr,
        corroboration_score=cs,
        filing_strength_score=fs,
        historical_precision_score=hp,
        entity_match_confidence=em,
        temporal_relevance_score=tr,
        extraction_confidence=exc,
        calibration_adjustment=calibration_adjustment,
        component_weights=WEIGHTS,
        reasoning=reasoning,
    )


def decompose_all(candidates: list[SignalCandidate]) -> dict[str, ConfidenceDecomposition]:
    """Return decompositions keyed by signal_type.value."""
    return {c.signal_type.value: decompose(c) for c in candidates}
