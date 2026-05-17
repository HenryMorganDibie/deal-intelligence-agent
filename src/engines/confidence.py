"""
Confidence Decomposition Framework (#5).
Replaces opaque single confidence floats with a fully auditable
breakdown of every component that contributed to the score.
Every DetectedSignal gets a ConfidenceDecomposition object.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from src.schemas.models import (
    SignalCandidate, DetectedSignal, ConfidenceDecomposition,
    SignalType, Severity
)
from src.engines.deterministic_engine import SOURCE_CREDIBILITY, DEFAULT_CREDIBILITY
from src.engines.feedback import get_signal_stats, get_source_reliability

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
    "NGX Announcement":   0.95,
    "NSE Kenya Disclosure": 0.93,
    "SC 13D":             0.95,
    "SC 13G":             0.90,
    "Form 4":             0.88,
    "DEF 14A":            0.85,
    "10-K":               0.80,
    "10-Q":               0.75,
    "news":               0.50,  # news baseline
    "pe_source":          0.60,
}

HALF_LIFE_DAYS = 21.0  # temporal relevance half-life


def _source_reliability_score(candidate: SignalCandidate) -> float:
    """Combined static + learned source reliability."""
    static_score = SOURCE_CREDIBILITY.get(candidate.source_name, DEFAULT_CREDIBILITY)
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
    """Use accumulated feedback precision for this signal type."""
    stats = get_signal_stats()
    s = stats.get(signal_type.value)
    if not s or s.get("total", 0) < 5:
        # Not enough data — use conservative default
        return 0.60
    return round(s.get("precision", 0.60), 4)


def _entity_match_score(candidate: SignalCandidate) -> float:
    """Score based on quality and quantity of named entity matches."""
    n = len(candidate.entity_mentions)
    if n == 0:
        return 0.30
    if n == 1:
        return 0.55
    if n == 2:
        return 0.72
    if n >= 3:
        return 0.88
    return 0.50


def _temporal_relevance_score(candidate: SignalCandidate) -> float:
    """Exponential decay from detection time. Floor at 0.35."""
    age_days = (datetime.utcnow() - candidate.detected_at).total_seconds() / 86400
    decay = 0.5 ** (age_days / HALF_LIFE_DAYS)
    return round(max(decay, 0.35), 4)


def _extraction_confidence(candidate: SignalCandidate) -> float:
    """Confidence in the extraction quality based on pattern specificity."""
    n_patterns = len(candidate.matched_patterns)
    # More patterns firing = higher extraction confidence
    if n_patterns >= 3:
        return 0.92
    if n_patterns == 2:
        return 0.80
    return 0.65


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
