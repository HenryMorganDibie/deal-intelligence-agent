"""
Signal Interaction Engine (#1).

Reasons over combinations of detected signals and temporal patterns
to produce CompoundSignal objects. Moves from isolated event detection
to contextual financial reasoning.

Interaction rules are deterministic — no LLM involved.
The LLM synthesis layer explains compound events, it does not define them.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from src.schemas.models import (
    DetectedSignal, SignalCandidate, CompoundSignal,
    InteractionType, SystemicRiskLevel, SignalType, Severity, AgentState
)

# ─── Interaction Rule Library ─────────────────────────────────────────────────
# Format: (frozenset of signal types, InteractionType, escalation_score,
#          systemic_risk_level, alpha_multiplier, reasoning)

INTERACTION_RULES: list[tuple[frozenset, InteractionType, float, SystemicRiskLevel, float, str]] = [

    # ── Compound Distress Escalation (highest severity combos) ───────────────
    (
        frozenset({SignalType.LEADERSHIP_CHANGE, SignalType.CREDIT_RISK, SignalType.INSIDER_ACTIVITY}),
        InteractionType.CASCADING, 0.95, SystemicRiskLevel.CONTAINED, 2.5,
        "CEO/CFO departure + covenant stress + insider selling = classic distress escalation pattern. "
        "Historically precedes credit events or forced restructuring within 60–90 days."
    ),
    (
        frozenset({SignalType.CREDIT_RISK, SignalType.DISTRESSED_ASSET}),
        InteractionType.ESCALATING, 0.92, SystemicRiskLevel.CONTAINED, 2.2,
        "Credit risk signals followed by formal distress language indicates transition from "
        "financial stress to potential insolvency proceedings."
    ),
    (
        frozenset({SignalType.CREDIT_RISK, SignalType.DEBT_RESTRUCTURE, SignalType.LEADERSHIP_CHANGE}),
        InteractionType.CASCADING, 0.90, SystemicRiskLevel.CONTAINED, 2.3,
        "Debt restructuring concurrent with leadership change signals governance crisis under "
        "financial pressure. Management transition under creditor pressure is high-risk."
    ),
    (
        frozenset({SignalType.DISTRESSED_ASSET, SignalType.REGULATORY_ACTION}),
        InteractionType.ESCALATING, 0.93, SystemicRiskLevel.SYSTEMIC, 2.4,
        "Formal insolvency concurrent with regulatory action suggests systemic governance failure. "
        "Regulatory intervention during distress dramatically reduces recovery probability."
    ),

    # ── Elevated M&A Probability ──────────────────────────────────────────────
    (
        frozenset({SignalType.INSIDER_ACTIVITY, SignalType.MA_ACTIVITY}),
        InteractionType.REINFORCING, 0.88, SystemicRiskLevel.ISOLATED, 1.8,
        "Activist 13D/13G filing concurrent with M&A language strongly suggests coordinated "
        "acquisition campaign. Activist + strategic review = high deal probability."
    ),
    (
        frozenset({SignalType.MA_ACTIVITY, SignalType.LEADERSHIP_CHANGE}),
        InteractionType.REINFORCING, 0.82, SystemicRiskLevel.ISOLATED, 1.6,
        "Executive departure concurrent with M&A signals often reflects management resistance "
        "to transaction or post-deal integration planning."
    ),
    (
        frozenset({SignalType.INSIDER_ACTIVITY, SignalType.MA_ACTIVITY, SignalType.LEADERSHIP_CHANGE}),
        InteractionType.CONVERGING, 0.91, SystemicRiskLevel.ISOLATED, 2.0,
        "Three-way convergence: activist position + deal language + leadership change. "
        "All three independently point to corporate control event in progress."
    ),

    # ── Severe Credit Deterioration ───────────────────────────────────────────
    (
        frozenset({SignalType.CREDIT_RISK, SignalType.EARNINGS_SURPRISE}),
        InteractionType.REINFORCING, 0.85, SystemicRiskLevel.CONTAINED, 1.7,
        "Revenue miss compounding existing credit stress creates debt service coverage concern. "
        "Earnings deterioration accelerates covenant breach timeline."
    ),
    (
        frozenset({SignalType.DEBT_RESTRUCTURE, SignalType.EARNINGS_SURPRISE, SignalType.CREDIT_RISK}),
        InteractionType.ESCALATING, 0.92, SystemicRiskLevel.CONTAINED, 2.2,
        "Triple-layer credit deterioration: restructuring negotiations + earnings miss + "
        "credit signals. Suggests active debt workouts under deteriorating fundamentals."
    ),

    # ── Regulatory Escalation ─────────────────────────────────────────────────
    (
        frozenset({SignalType.REGULATORY_ACTION, SignalType.LEADERSHIP_CHANGE}),
        InteractionType.CASCADING, 0.87, SystemicRiskLevel.CONTAINED, 1.8,
        "Regulatory action triggering leadership departure. Common pattern in enforcement "
        "cases — management exits precede or accompany consent orders."
    ),
    (
        frozenset({SignalType.REGULATORY_ACTION, SignalType.INSIDER_ACTIVITY}),
        InteractionType.REINFORCING, 0.84, SystemicRiskLevel.CONTAINED, 1.7,
        "Regulatory investigation concurrent with insider selling may indicate informed "
        "exit ahead of enforcement action announcement."
    ),
    (
        frozenset({SignalType.REGULATORY_ACTION, SignalType.CREDIT_RISK}),
        InteractionType.ESCALATING, 0.88, SystemicRiskLevel.SYSTEMIC, 1.9,
        "Regulatory action during credit stress creates compounding pressure — legal costs, "
        "reputational damage, and potential licence suspension worsen credit position."
    ),

    # ── Contradictory / Offsetting Signals ───────────────────────────────────
    (
        frozenset({SignalType.MA_ACTIVITY, SignalType.DISTRESSED_ASSET}),
        InteractionType.CONTRADICTORY, 0.60, SystemicRiskLevel.ISOLATED, 0.8,
        "M&A activity concurrent with distress signals may represent rescue acquisition "
        "or distressed sale. Contradictory signals — reduce confidence, flag for human review."
    ),
    (
        frozenset({SignalType.INSIDER_ACTIVITY, SignalType.EARNINGS_SURPRISE}),
        InteractionType.REINFORCING, 0.80, SystemicRiskLevel.ISOLATED, 1.5,
        "Insider selling ahead of earnings miss suggests possible informed trading. "
        "Timing correlation warrants regulatory attention flag."
    ),
]

# Minimum severity to participate in compound detection
MIN_SEVERITY_FOR_COMPOUND = {Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL}

# Temporal window: signals must be detected within this many days to interact
INTERACTION_WINDOW_DAYS = 30


def _signals_qualify(signals: list[DetectedSignal]) -> list[DetectedSignal]:
    """Filter to signals that qualify for compound detection."""
    return [s for s in signals if s.severity in MIN_SEVERITY_FOR_COMPOUND]


def _find_interactions(
    signals: list[DetectedSignal],
) -> list[CompoundSignal]:
    """
    Match detected signal combinations against interaction rules.
    Returns CompoundSignal for each rule that fires.
    """
    qualified = _signals_qualify(signals)
    signal_types = frozenset(s.signal_type for s in qualified)

    compounds: list[CompoundSignal] = []

    for rule_types, interaction_type, escalation_score, systemic_level, alpha_mult, reasoning in INTERACTION_RULES:
        # Check if all required signal types are present
        if not rule_types.issubset(signal_types):
            continue

        # Compute compounded confidence: geometric mean of participating signal confidences
        participating = [s for s in qualified if s.signal_type in rule_types]
        if not participating:
            continue

        confidences = [s.confidence for s in participating]
        compound_conf = min(
            (sum(c ** 2 for c in confidences) / len(confidences)) ** 0.5,
            1.0
        )

        # Boost confidence for high-corroboration signals
        avg_corroboration = sum(s.corroboration_count for s in participating) / len(participating)
        if avg_corroboration >= 3:
            compound_conf = min(compound_conf * 1.1, 1.0)

        compounds.append(CompoundSignal(
            compound_id=str(uuid.uuid4()),
            component_signal_types=list(rule_types),
            interaction_type=interaction_type,
            escalation_score=escalation_score,
            compounded_confidence=round(compound_conf, 3),
            systemic_risk_level=systemic_level,
            reasoning_chain=reasoning,
            temporal_window_days=INTERACTION_WINDOW_DAYS,
            alpha_multiplier=alpha_mult,
        ))

    # Sort by escalation score descending
    compounds.sort(key=lambda c: c.escalation_score, reverse=True)
    return compounds


def _apply_alpha_multipliers(
    signals: list[DetectedSignal],
    compounds: list[CompoundSignal],
) -> list[DetectedSignal]:
    """
    Apply compound alpha multipliers back to participating signals.
    Signals involved in compound events get boosted alpha scores.
    """
    if not compounds or not signals:
        return signals

    # Find the highest multiplier applicable to each signal type
    type_multiplier: dict[SignalType, float] = {}
    for compound in compounds:
        if compound.interaction_type == InteractionType.CONTRADICTORY:
            continue  # contradictory compounds reduce, handled separately
        for sig_type in compound.component_signal_types:
            existing = type_multiplier.get(sig_type, 1.0)
            type_multiplier[sig_type] = max(existing, compound.alpha_multiplier)

    updated = []
    for sig in signals:
        mult = type_multiplier.get(sig.signal_type, 1.0)
        if mult == 1.0 or sig.alpha_score is None:
            updated.append(sig)
            continue
        new_score = min(sig.alpha_score.score * mult, 100.0)
        updated.append(sig.model_copy(update={
            "alpha_score": sig.alpha_score.model_copy(update={"score": round(new_score, 1)})
        }))

    updated.sort(key=lambda s: s.alpha_score.score if s.alpha_score else 0.0, reverse=True)
    return updated


def _get_systemic_risk(compounds: list[CompoundSignal]) -> "SystemicRiskLevel":
    """Derive overall systemic risk from highest compound."""
    if not compounds:
        return SystemicRiskLevel.ISOLATED
    order = {
        SystemicRiskLevel.SYSTEMIC:  0,
        SystemicRiskLevel.CONTAINED: 1,
        SystemicRiskLevel.ISOLATED:  2,
    }
    return sorted(compounds, key=lambda c: order[c.systemic_risk_level])[0].systemic_risk_level


class SignalInteractionEngine:
    """
    LangGraph node: reasons over detected signal combinations.
    Produces CompoundSignal objects and applies alpha multipliers.
    Runs after alpha scoring, before brief synthesis.
    """

    def run(self, state: AgentState) -> AgentState:
        state.log("signal_interaction", f"Analysing interactions across {len(state.detected_signals)} signals")

        if len(state.detected_signals) < 2:
            state.log("signal_interaction", "Fewer than 2 signals — no interactions possible")
            return state

        compounds = _find_interactions(state.detected_signals)
        state.compound_signals = compounds

        if compounds:
            # Apply multipliers back to signal alpha scores
            state.detected_signals = _apply_alpha_multipliers(state.detected_signals, compounds)
            state.log(
                "signal_interaction",
                f"{len(compounds)} compound events detected",
                {
                    "compounds": [
                        {
                            "types": [t.value for t in c.component_signal_types],
                            "interaction": c.interaction_type.value,
                            "escalation": c.escalation_score,
                            "multiplier": c.alpha_multiplier,
                        }
                        for c in compounds
                    ]
                }
            )
        else:
            state.log("signal_interaction", "No interaction rules fired")

        return state
