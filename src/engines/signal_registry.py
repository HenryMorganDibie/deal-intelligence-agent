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

from src.schemas.models import SignalType, Severity


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
        trigger_patterns_high=[
            r"\bdefinitive\s+(merger|acquisition|agreement)\b",
            r"\bletter\s+of\s+intent\b",
            r"\bscheme\s+of\s+arrangement\b",
            r"\btender\s+offer\b",
            r"\bgoing\s+private\b",
        ],
        trigger_patterns_medium=[
            r"\b(acquires?|acquired)\b.{0,60}\b(company|corp|group)\b",
            r"\b(merger|acquisition)\s+(talks?|discussions?|negotiations?)\b",
            r"\bstrategic\s+(review|alternatives)\b",
            r"\bexclusive\s+negotiations?\b",
        ],
        trigger_patterns_low=[
            r"\b(merger|acquisition|takeover|buyout)\b",
            r"\b(deal|transaction)\s+(announced?|confirmed)\b",
        ],
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
        trigger_patterns_high=[
            r"\bcovenant\s+(breach|violation|default|waiver)\b",
            r"\bgoing\s+concern\b",
            r"\bsubstantial\s+doubt\b.{0,40}\b(continue|viability)\b",
            r"\bdowngraded?\b.{0,40}\b(Moody|S&P|Fitch|GCR|rating)\b",
            r"\bevent\s+of\s+default\b",
        ],
        trigger_patterns_medium=[
            r"\bliquidity\s+(crisis|concern|risk|shortage)\b",
            r"\bdebt\s+(maturity|covenant|restructur)\b",
            r"\bimpairment\s+(charge|loss|write[\s-]down)\b",
            r"\bcash\s+(burn|runway|shortage)\b",
        ],
        trigger_patterns_low=[
            r"\b(credit\s+rating|leverage\s+ratio)\b",
            r"\bnet\s+debt\b.{0,30}\b(exceeded?|increased?)\b",
        ],
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
        trigger_patterns_high=[
            r"\b(chapter\s+11|chapter\s+7|bankruptcy)\s+(fil|petition|protect)",
            r"\bbusiness\s+rescue\s+(proceedings?|practitioner|commenced)\b",
            r"\bprovisional\s+liquidation\b",
            r"\bjudicial\s+management\b",
            r"\breceivers?ship\b.{0,20}\b(appointed?|placed?)\b",
            r"\binsolvency\s+(proceedings?|petition|filed?)\b",
        ],
        trigger_patterns_medium=[
            r"\b(liquidat|wind(ing)?\s+up)\b",
            r"\bcreditor\s+(protection|committee|arrangement)\b",
            r"\b(distressed|impaired)\s+(asset|portfolio|loan)\b",
        ],
        trigger_patterns_low=[
            r"\bnon[-\s]performing\s+(loan|asset)\b",
            r"\bwrite[-\s]off\b",
        ],
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
        trigger_patterns_high=[
            r"\bprofit\s+warning\b",
            r"\bguidance\s+(cut|lowered?|reduced?|withdrawn?)\b",
            r"\bsignificantly\s+below\s+(expectations?|guidance|consensus)\b",
            r"\bheadline\s+earnings?\b.{0,30}\b(declin|fall|drop|miss|below)\b",
        ],
        trigger_patterns_medium=[
            r"\b(revenue|earnings|profit)\b.{0,20}\b(miss|below|declin|fell)\b",
            r"\bloss\s+(after\s+tax|before\s+tax)\b",
            r"\bbelow[-\s](plan|budget|forecast|expectations?)\b",
        ],
        trigger_patterns_low=[
            r"\bweaker\s+than\s+expected\b",
            r"\bdisappointing\s+(results?|earnings?)\b",
        ],
        semantic_evidence_types=["impairment_statement"],
        escalates_with=[SignalType.CREDIT_RISK, SignalType.DEBT_RESTRUCTURE],
        base_alpha_weight=0.9,
        max_alpha_multiplier=1.8,
    ),

    SignalType.LEADERSHIP_CHANGE: SignalSpec(
        signal_type=SignalType.LEADERSHIP_CHANGE,
        display_name="Leadership Change",
        description="Executive departures and governance disruptions",
        trigger_patterns_high=[
            r"\b(ceo|cfo|coo|cto|md|managing\s+director|chairman)\b.{0,30}(resign|depart|step.?down|terminat|dismiss)",
            r"\bsudden\s+(departure|resignation|exit).{0,30}(ceo|cfo|md|executive|director)",
            r"\babrupt\s+(departure|resignation)\b",
        ],
        trigger_patterns_medium=[
            r"\b(executive|board)\s+(reshuffle|shake[-\s]up|overhaul)",
            r"\b(independent\s+)?director\s+(resign|step.?down|depart)",
            r"\binterim\s+(ceo|cfo|md|chief\s+executive)",
        ],
        trigger_patterns_low=[
            r"\b(leadership|management)\s+(change|transition|succession)\b",
            r"\bsuccession\s+plan\b",
        ],
        semantic_evidence_types=["governance_deterioration"],
        escalates_with=[SignalType.CREDIT_RISK, SignalType.REGULATORY_ACTION, SignalType.MA_ACTIVITY],
        base_alpha_weight=0.8,
        max_alpha_multiplier=1.6,
    ),

    SignalType.REGULATORY_ACTION: SignalSpec(
        signal_type=SignalType.REGULATORY_ACTION,
        display_name="Regulatory Action",
        description="Regulatory investigation, enforcement, and sanctions",
        trigger_patterns_high=[
            r"\b(sec|fsca|cma|cbn|sarb|cbk)\b.{0,30}\b(invest|probe|enforcement|sanction|fine|penalty|subpoena)\b",
            r"\blicen(c|s)e\s+(revoked?|suspended?|cancelled?)\b",
            r"\bconsent\s+(order|decree)\b.{0,30}\b(regulat|enforce)\b",
            r"\bcriminal\s+(charge|referral|indictment)\b.{0,30}\b(fraud|financ)\b",
        ],
        trigger_patterns_medium=[
            r"\bregulatory\s+(action|enforcement|sanction|inquiry)\b",
            r"\b(fraud|misconduct)\s+(alleg|invest|probe)\b",
            r"\bnon[-\s]compliance\b.{0,30}\b(regulat|penalt|fine)\b",
        ],
        trigger_patterns_low=[
            r"\bregulatory\s+(concern|issue|breach)\b",
            r"\bwarning\s+letter\b.{0,30}\b(regulat|author)\b",
        ],
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
        trigger_patterns_high=[
            r"\bdebt\s+(restructur|renegotiat|relief|forgiven)\b",
            r"\bhaircut\b.{0,20}\b(debt|bond|creditor|lender)\b",
            r"\bforbearance\s+(agreement|period|granted)\b",
            r"\bprincipal\s+(reduction|write[\s-]down|forgiven)\b",
        ],
        trigger_patterns_medium=[
            r"\b(bond|loan|facility)\s+(restructur|amendment|waiver)\b",
            r"\bcreditor\s+(negotiation|settlement)\b",
            r"\bdebt[-\s](for[-\s]equity|swap)\b",
        ],
        trigger_patterns_low=[
            r"\brefinanc(ing|ed?)\b.{0,20}\b(debt|facility|bond)\b",
            r"\bmaturity\s+(extension|wall)\b",
        ],
        semantic_evidence_types=["restructuring_clause"],
        escalates_with=[SignalType.CREDIT_RISK, SignalType.DISTRESSED_ASSET],
        base_alpha_weight=1.0,
        max_alpha_multiplier=2.2,
    ),

    SignalType.INSIDER_ACTIVITY: SignalSpec(
        signal_type=SignalType.INSIDER_ACTIVITY,
        display_name="Insider Activity",
        description="Insider trading disclosures and activist investor positions",
        trigger_patterns_high=[
            r"\b(sc\s+13[dg]|schedule\s+13[dg])\b",
            r"\bform\s+4\b.{0,30}\b(filed|purchase|sale|acquisition)\b",
            r"\bactivist\s+(investor|shareholder|campaign)\b",
            r"\bblock\s+(purchase|acquisition)\b.{0,20}\b(shares?|stake)\b",
        ],
        trigger_patterns_medium=[
            r"\binsider\s+(buying|selling|purchase|disposal)\b",
            r"\bdirector\s+(purchase|sale|dealing)\b.{0,20}\b(share|equity)\b",
            r"\bstake\s+(built|increased|acquired)\b.{0,20}\b(\d+\.?\d*%)\b",
        ],
        trigger_patterns_low=[
            r"\bopen[-\s]market\s+(purchase|sale)\b",
            r"\bsignificant\s+beneficial\s+(owner|holding)\b",
        ],
        semantic_evidence_types=[],
        escalates_with=[SignalType.MA_ACTIVITY, SignalType.REGULATORY_ACTION],
        base_alpha_weight=0.9,
        max_alpha_multiplier=1.8,
    ),
}


def get_signal_spec(signal_type: SignalType) -> Optional[SignalSpec]:
    return SIGNAL_REGISTRY.get(signal_type)


def get_all_patterns(signal_type: SignalType) -> list[tuple[list[str], float]]:
    """Return all patterns for a signal type with their base scores."""
    spec = SIGNAL_REGISTRY.get(signal_type)
    if not spec:
        return []
    return [
        (spec.trigger_patterns_high,   0.90),
        (spec.trigger_patterns_medium, 0.72),
        (spec.trigger_patterns_low,    0.52),
    ]


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
