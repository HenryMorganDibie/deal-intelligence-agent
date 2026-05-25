"""
Alpha Score Explainer (#8 from improvements doc).
SHAP-style deterministic breakdown of every alpha score.
Shows exactly why a signal scored 82 vs 45 — every component
contribution, interaction boost, calibration adjustment, and
compliance flag is traced to its source.
"""
from __future__ import annotations

from typing import Optional
from src.schemas.models import DetectedSignal, SignalCandidate, AlphaScore, Severity, SignalType
from src.engines.alpha_scorer import (
    SEVERITY_WEIGHT, LIQUIDITY_WEIGHT, _recency_decay,
    _corroboration_weight, _infer_liquidity_tier,
    HUMAN_REVIEW_ALPHA_THRESHOLD,
)
from src.engines.deterministic_engine import SOURCE_CREDIBILITY, DEFAULT_CREDIBILITY


def explain_alpha(
    signal: DetectedSignal,
    candidate: Optional[SignalCandidate] = None,
    compound_multiplier: float = 1.0,
) -> dict:
    """
    Produce a full deterministic breakdown of an alpha score.
    Every point in the 0-100 range is attributed to a specific component.

    Returns a dict with:
      - component_contributions: each component's weighted contribution
      - interaction_boost: points added by compound signal multiplier
      - compliance_notes: why flags were triggered
      - score_trace: step-by-step reconstruction
      - plain_english: analyst-readable explanation
    """
    if signal.alpha_score is None:
        return {"error": "Signal has no alpha score attached"}

    a = signal.alpha_score

    # Raw component values before weighting
    sev_raw  = a.severity_component
    cred_raw = a.source_credibility
    corr_raw = a.corroboration_weight
    rec_raw  = a.recency_weight
    liq_raw  = LIQUIDITY_WEIGHT.get(a.liquidity_tier, 0.5)

    # Weighted contributions (these sum to raw_alpha before ×100)
    sev_contrib  = sev_raw  * 0.35
    cred_contrib = cred_raw * 0.25
    corr_contrib = corr_raw * 0.20
    rec_contrib  = rec_raw  * 0.10
    liq_contrib  = liq_raw  * 0.10

    raw_alpha      = sev_contrib + cred_contrib + corr_contrib + rec_contrib + liq_contrib
    base_score     = round(raw_alpha * 100, 1)
    compound_boost = round((compound_multiplier - 1.0) * base_score, 1) if compound_multiplier > 1.0 else 0.0
    final_score    = min(base_score + compound_boost, 100.0)

    # Component contributions in final points
    point_contributions = {
        "severity":       round(sev_contrib  * 100, 1),
        "source_credibility": round(cred_contrib * 100, 1),
        "corroboration":  round(corr_contrib * 100, 1),
        "recency":        round(rec_contrib  * 100, 1),
        "liquidity":      round(liq_contrib  * 100, 1),
    }

    # Why each component scored what it did
    severity_reason = {
        Severity.CRITICAL: "CRITICAL severity — highest evidential weight",
        Severity.HIGH:     "HIGH severity — strong evidential weight",
        Severity.MEDIUM:   "MEDIUM severity — moderate evidential weight",
        Severity.LOW:      "LOW severity — minimal evidential weight",
    }.get(signal.severity, "Unknown severity")

    cred_reason = f"Source credibility {cred_raw:.2f}"
    if cred_raw >= 0.95:
        cred_reason += " — regulatory/exchange filing (maximum credibility)"
    elif cred_raw >= 0.85:
        cred_reason += " — Tier 1 financial press"
    elif cred_raw >= 0.70:
        cred_reason += " — Tier 2/3 financial media"
    else:
        cred_reason += " — lower-credibility source"

    corr_n = signal.corroboration_count
    corr_reason = f"{corr_n} independent source(s) confirming"
    if corr_n >= 3:
        corr_reason += " — strong corroboration"
    elif corr_n == 2:
        corr_reason += " — moderate corroboration"
    else:
        corr_reason += " — single source (lower confidence)"

    rec_reason = f"Recency weight {rec_raw:.2f}"
    if rec_raw >= 0.90:
        rec_reason += " — very fresh signal"
    elif rec_raw >= 0.70:
        rec_reason += " — signal aging but still relevant"
    else:
        rec_reason += " — aging signal, recency decay applied"

    liq_reason = f"Liquidity tier: {a.liquidity_tier.value.replace('_',' ')}"
    if a.liquidity_tier.value == "large_cap":
        liq_reason += " — fully actionable (liquid instrument)"
    elif a.liquidity_tier.value == "private":
        liq_reason += " — limited actionability (unlisted)"

    # Compliance notes
    compliance_notes = []
    if a.requires_human_review:
        compliance_notes.append(a.review_reason or "Human review required")
    if final_score >= HUMAN_REVIEW_ALPHA_THRESHOLD:
        compliance_notes.append(f"Score {final_score:.1f} ≥ threshold {HUMAN_REVIEW_ALPHA_THRESHOLD:.0f} — mandatory review")
    if signal.severity == Severity.CRITICAL and corr_n < 2:
        compliance_notes.append("CRITICAL severity with <2 sources — severity may be conservative")

    # Plain English summary
    top_driver = max(point_contributions, key=lambda k: point_contributions[k])
    driver_labels = {
        "severity":           "signal severity",
        "source_credibility": "source credibility",
        "corroboration":      "multi-source corroboration",
        "recency":            "signal recency",
        "liquidity":          "market liquidity",
    }
    plain = (
        f"Alpha score {final_score:.1f}/100. "
        f"Primary driver: {driver_labels[top_driver]} ({point_contributions[top_driver]:.1f} pts). "
    )
    if compound_boost > 0:
        plain += f"Compound signal interaction added {compound_boost:.1f} pts ({compound_multiplier:.1f}× multiplier). "
    if signal.severity == Severity.HIGH or signal.severity == Severity.CRITICAL:
        plain += f"Expected move: {a.expected_direction or 'neutral'} "
        if a.expected_magnitude_pct_low is not None:
            plain += f"{a.expected_magnitude_pct_low:.0f}–{a.expected_magnitude_pct_high:.0f}% "
        plain += f"(based on {a.comparable_events_n} comparable historical events, {a.move_confidence} confidence)."

    return {
        "signal_type":    signal.signal_type.value,
        "severity":       signal.severity.value,
        "final_score":    final_score,
        "base_score":     base_score,
        "compound_boost": compound_boost,
        "compound_multiplier": compound_multiplier,
        "component_contributions": point_contributions,
        "component_reasons": {
            "severity":           severity_reason,
            "source_credibility": cred_reason,
            "corroboration":      corr_reason,
            "recency":            rec_reason,
            "liquidity":          liq_reason,
        },
        "raw_components": {
            "severity_weight":    sev_raw,
            "source_credibility": cred_raw,
            "corroboration_weight": corr_raw,
            "recency_weight":     rec_raw,
            "liquidity_weight":   liq_raw,
        },
        "weights_used": {
            "severity": 0.35, "source_credibility": 0.25,
            "corroboration": 0.20, "recency": 0.10, "liquidity": 0.10,
        },
        "compliance_notes":   compliance_notes,
        "plain_english":      plain,
        "expected_move": {
            "direction":   a.expected_direction,
            "range_pct":   f"{a.expected_magnitude_pct_low:.0f}–{a.expected_magnitude_pct_high:.0f}%" if a.expected_magnitude_pct_low else None,
            "comparables": a.comparable_events_n,
            "confidence":  a.move_confidence,
        } if a.expected_direction else None,
    }


def explain_brief(brief) -> list[dict]:
    """Return alpha explanations for all signals in a brief."""
    explanations = []
    for sig in brief.detected_signals:
        if sig.alpha_score:
            exp = explain_alpha(sig)
            explanations.append(exp)
    return explanations
