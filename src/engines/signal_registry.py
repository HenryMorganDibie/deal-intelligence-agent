"""
Signal Registry & Modular Rule System (#10).
Centralises all signal definitions as typed, testable, versioned classes.
Each signal type is a self-contained specification: patterns, semantic
templates, corroboration rules, severity model reference, escalation rules.
Replaces scattered pattern lists with a structured, extensible registry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.schemas.models import SignalType


@dataclass
class SignalSpec:
    """
    Full specification for one signal type.
    Self-contained: contains everything needed to detect, calibrate,
    and escalate this signal type.
    """
    signal_type: SignalType
    display_name: str
    description: str
    version: str = "1.0.0"

    # Detection patterns (regex strings, case-insensitive)
    trigger_patterns_high: list[str] = field(default_factory=list)   # high-confidence
    trigger_patterns_medium: list[str] = field(default_factory=list)  # medium-confidence
    trigger_patterns_low: list[str] = field(default_factory=list)     # low-confidence

    # Semantic evidence types to look for (from semantic.py)
    semantic_evidence_types: list[str] = field(default_factory=list)

    # Corroboration rules
    min_corroboration_for_critical: int = 2
    min_corroboration_for_high: int = 1
    corroboration_boost_threshold: int = 3  # above this, confidence boosted

    # Historical precision (updated by adaptive calibration)
    historical_precision: float = 0.60
    false_positive_rate: float = 0.20

    # Escalation: which other signals this interacts with
    escalates_with: list[SignalType] = field(default_factory=list)
    contradicts: list[SignalType] = field(default_factory=list)

    # Alpha score parameters
    base_alpha_weight: float = 1.0
    max_alpha_multiplier: float = 2.5


# ─── Signal Registry ──────────────────────────────────────────────────────────

SIGNAL_REGISTRY: dict[SignalType, SignalSpec] = {

    SignalType.MA_ACTIVITY: SignalSpec(
        signal_type=SignalType.MA_ACTIVITY,
        display_name="M&A Activity",
        description="Merger, acquisition, or corporate control event indicators",
        semantic_evidence_types=["merger_language"],
        escalates_with=[SignalType.INSIDER_ACTIVITY, SignalType.LEADERSHIP_CHANGE],
        contradicts=[SignalType.DISTRESSED_ASSET],
        base_alpha_weight=1.0,
        max_alpha_multiplier=2.0,
    ),

    SignalType.CREDIT_RISK: SignalSpec(
        signal_type=SignalType.CREDIT_RISK,
        display_name="Credit Risk",
        description="Debt covenant, liquidity, and creditworthiness deterioration",
        semantic_evidence_types=["going_concern","covenant_breach","liquidity_stress","impairment_statement"],
        min_corroboration_for_critical=2,
        escalates_with=[SignalType.DISTRESSED_ASSET, SignalType.DEBT_RESTRUCTURE, SignalType.LEADERSHIP_CHANGE],
        base_alpha_weight=1.1,
        max_alpha_multiplier=2.2,
    ),

    SignalType.DISTRESSED_ASSET: SignalSpec(
        signal_type=SignalType.DISTRESSED_ASSET,
        display_name="Distressed Asset",
        description="Formal insolvency, business rescue, and liquidation signals",
        semantic_evidence_types=["insolvency_formal","going_concern","liquidity_stress"],
        min_corroboration_for_critical=2,
        escalates_with=[SignalType.CREDIT_RISK, SignalType.REGULATORY_ACTION, SignalType.LEADERSHIP_CHANGE],
        historical_precision=0.82,
        base_alpha_weight=1.2,
        max_alpha_multiplier=2.5,
    ),

    SignalType.EARNINGS_SURPRISE: SignalSpec(
        signal_type=SignalType.EARNINGS_SURPRISE,
        display_name="Earnings Surprise",
        description="Revenue misses, profit warnings, guidance cuts",
        semantic_evidence_types=["impairment_statement"],
        escalates_with=[SignalType.CREDIT_RISK, SignalType.DEBT_RESTRUCTURE],
        base_alpha_weight=0.9,
        max_alpha_multiplier=1.8,
    ),

    SignalType.LEADERSHIP_CHANGE: SignalSpec(
        signal_type=SignalType.LEADERSHIP_CHANGE,
        display_name="Leadership Change",
        description="Executive departures and governance disruptions",
        semantic_evidence_types=["governance_deterioration"],
        escalates_with=[SignalType.CREDIT_RISK, SignalType.REGULATORY_ACTION, SignalType.MA_ACTIVITY],
        base_alpha_weight=0.8,
        max_alpha_multiplier=1.6,
    ),

    SignalType.REGULATORY_ACTION: SignalSpec(
        signal_type=SignalType.REGULATORY_ACTION,
        display_name="Regulatory Action",
        description="Regulatory investigation, enforcement, and sanctions",
        semantic_evidence_types=["litigation_language"],
        min_corroboration_for_critical=2,
        escalates_with=[SignalType.CREDIT_RISK, SignalType.LEADERSHIP_CHANGE],
        base_alpha_weight=1.05,
        max_alpha_multiplier=2.0,
    ),

    SignalType.DEBT_RESTRUCTURE: SignalSpec(
        signal_type=SignalType.DEBT_RESTRUCTURE,
        display_name="Debt Restructuring",
        description="Active debt renegotiation, forbearance, and haircuts",
        semantic_evidence_types=["restructuring_clause"],
        escalates_with=[SignalType.CREDIT_RISK, SignalType.DISTRESSED_ASSET],
        base_alpha_weight=1.0,
        max_alpha_multiplier=2.2,
    ),

    SignalType.INSIDER_ACTIVITY: SignalSpec(
        signal_type=SignalType.INSIDER_ACTIVITY,
        display_name="Insider Activity",
        description="Insider trading disclosures and activist investor positions",
        semantic_evidence_types=[],
        escalates_with=[SignalType.MA_ACTIVITY, SignalType.REGULATORY_ACTION],
        base_alpha_weight=0.9,
        max_alpha_multiplier=1.8,
    ),
}


# ─── Patterns come from the rule engine ───────────────────────────────────────
# deterministic_engine.SIGNAL_RULES is the single source of detection patterns.
# The registry used to keep its own copies, which the engine never read and
# which drifted from the live rules; the tiers below are derived instead.

HIGH_TIER_MIN   = 0.85
MEDIUM_TIER_MIN = 0.65
_NOMINAL_TIER_SCORES = (0.90, 0.72, 0.52)


def _tiers_from_rules(signal_type: SignalType) -> tuple[list[tuple[list[str], float]], ...]:
    from src.engines.deterministic_engine import SIGNAL_RULES
    high, medium, low = [], [], []
    for sig_type, patterns, base_score in SIGNAL_RULES:
        if sig_type != signal_type:
            continue
        bucket = high if base_score >= HIGH_TIER_MIN else medium if base_score >= MEDIUM_TIER_MIN else low
        bucket.append((list(patterns), base_score))
    return high, medium, low


def _populate_patterns() -> None:
    for sig_type, spec in SIGNAL_REGISTRY.items():
        high, medium, low = _tiers_from_rules(sig_type)
        spec.trigger_patterns_high   = [p for ps, _ in high for p in ps]
        spec.trigger_patterns_medium = [p for ps, _ in medium for p in ps]
        spec.trigger_patterns_low    = [p for ps, _ in low for p in ps]


_populate_patterns()


def get_signal_spec(signal_type: SignalType) -> Optional[SignalSpec]:
    return SIGNAL_REGISTRY.get(signal_type)


def get_all_patterns(signal_type: SignalType) -> list[tuple[list[str], float]]:
    """Return all patterns for a signal type with their base scores."""
    spec = SIGNAL_REGISTRY.get(signal_type)
    if not spec:
        return []
    tiers = _tiers_from_rules(signal_type)
    result = []
    for bucket, nominal in zip(tiers, _NOMINAL_TIER_SCORES):
        result.append(([p for ps, _ in bucket for p in ps], max((sc for _, sc in bucket), default=nominal)))
    return result


def list_all_signals() -> list[dict]:
    """Return a summary of all registered signal types."""
    return [
        {
            "signal_type": spec.signal_type.value,
            "display_name": spec.display_name,
            "description": spec.description,
            "version": spec.version,
            "total_patterns": (
                len(spec.trigger_patterns_high) +
                len(spec.trigger_patterns_medium) +
                len(spec.trigger_patterns_low)
            ),
            "escalates_with": [s.value for s in spec.escalates_with],
            "contradicts": [s.value for s in spec.contradicts],
            "historical_precision": spec.historical_precision,
        }
        for spec in SIGNAL_REGISTRY.values()
    ]
