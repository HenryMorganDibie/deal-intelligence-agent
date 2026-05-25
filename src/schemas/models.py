"""
Core Pydantic schemas for the Deal Intelligence Agent system.
All data flowing through the agent graph is typed and validated here.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class SignalType(str, Enum):
    MA_ACTIVITY        = "m_and_a_activity"
    CREDIT_RISK        = "credit_risk"
    DISTRESSED_ASSET   = "distressed_asset"
    EARNINGS_SURPRISE  = "earnings_surprise"
    LEADERSHIP_CHANGE  = "leadership_change"
    REGULATORY_ACTION  = "regulatory_action"
    DEBT_RESTRUCTURE   = "debt_restructuring"
    INSIDER_ACTIVITY   = "insider_activity"


class Severity(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class FilingType(str, Enum):
    FORM_8K   = "8-K"
    FORM_10K  = "10-K"
    FORM_10Q  = "10-Q"
    FORM_SC13 = "SC 13D"
    FORM_SC13G = "SC 13G"
    FORM_DEF14A = "DEF 14A"
    FORM_4    = "Form 4"
    OTHER     = "other"


# ─────────────────────────────────────────────
# Input / Request
# ─────────────────────────────────────────────

class AnalysisRequest(BaseModel):
    """Entry point: what the user wants analysed."""
    company_name: str = Field(..., description="Target company name")
    ticker: Optional[str] = Field(None, description="Stock ticker if public (e.g. AAPL)")
    cik: Optional[str] = Field(None, description="SEC CIK identifier if known")
    focus_signals: list[SignalType] = Field(
        default_factory=list,
        description="Specific signals to prioritise. Empty = all signals."
    )
    lookback_days: int = Field(default=90, ge=1, le=365, description="Days of history to scan")
    depth: str = Field(default="standard", pattern="^(quick|standard|deep)$")

    @field_validator("ticker")
    @classmethod
    def normalise_ticker(cls, v: Optional[str]) -> Optional[str]:
        return v.upper().strip() if v else v


# ─────────────────────────────────────────────
# Data Collection Layer
# ─────────────────────────────────────────────

class SECFiling(BaseModel):
    """A single SEC filing retrieved from EDGAR."""
    accession_number: str
    form_type: str
    filing_date: str
    company_name: str
    cik: str
    document_url: str
    description: Optional[str] = None
    raw_excerpt: Optional[str] = None


class NewsItem(BaseModel):
    """A news article or press release."""
    title: str
    source: str
    published_date: str
    url: str
    snippet: str
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)


class CompanyProfile(BaseModel):
    """Basic company metadata resolved during data collection."""
    name: str
    ticker: Optional[str] = None
    cik: Optional[str] = None
    exchange: Optional[str] = None
    sector: Optional[str] = None
    description: Optional[str] = None
    resolved_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────
# Deterministic Engine Layer
# ─────────────────────────────────────────────

class SignalCandidate(BaseModel):
    """
    Output of the deterministic signal engine.
    Produced WITHOUT any LLM — pure rule-based pattern matching + NER.
    The LLM only sees confirmed candidates and explains them.
    """
    signal_type: SignalType
    matched_patterns: list[str] = Field(..., description="Exact patterns/keywords that fired")
    source_text: str = Field(..., description="Raw text excerpt that triggered the signal")
    source_url: str = ""
    source_type: str = Field(..., description="filing | news | pe_source")
    source_name: str = ""
    filing_reference: str = ""
    entity_mentions: list[str] = Field(default_factory=list, description="Named entities found")
    corroboration_count: int = Field(default=1, description="Number of independent sources confirming")
    raw_score: float = Field(..., ge=0.0, le=1.0, description="Pre-calibration score")
    detected_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────
# Alpha Score Layer
# ─────────────────────────────────────────────

class LiquidityTier(str, Enum):
    LARGE_CAP  = "large_cap"    # JSE Top 40 / S&P 500
    MID_CAP    = "mid_cap"      # NGX 30 / S&P MidCap
    SMALL_CAP  = "small_cap"    # Smaller listed
    MICRO_CAP  = "micro_cap"    # Thin volume
    PRIVATE    = "private"      # Unlisted


class AlphaScore(BaseModel):
    """
    Composite investable ranking for a signal.
    Combines calibrated severity, source credibility, corroboration,
    recency, and market liquidity into a single 0–100 score.
    """
    score: float = Field(..., ge=0.0, le=100.0, description="Overall alpha score 0-100")

    # Component breakdown
    severity_component: float = Field(..., ge=0.0, le=1.0)
    source_credibility: float = Field(..., ge=0.0, le=1.0)
    corroboration_weight: float = Field(..., ge=0.0, le=1.0)
    recency_weight: float = Field(..., ge=0.0, le=1.0)
    liquidity_tier: LiquidityTier = LiquidityTier.PRIVATE

    # Expected move (backtested estimate)
    expected_direction: Optional[str] = None          # "positive" | "negative" | "neutral"
    expected_magnitude_pct_low: Optional[float] = None
    expected_magnitude_pct_high: Optional[float] = None
    comparable_events_n: int = 0
    move_confidence: str = "low"                       # "low" | "medium" | "high"

    # Compliance flag
    requires_human_review: bool = False
    review_reason: Optional[str] = None


# ─────────────────────────────────────────────
# Signal Detection Layer
# ─────────────────────────────────────────────

class DetectedSignal(BaseModel):
    """
    A confirmed intelligence signal.
    Always originates from the deterministic engine (SignalCandidate).
    LLM provides explanation only — never originates the signal.
    """
    signal_type: SignalType
    severity: Severity
    headline: str = Field(..., description="One-line signal description")
    evidence: list[str] = Field(..., description="Supporting evidence snippets")
    source_urls: list[str] = Field(default_factory=list)
    filing_references: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0, description="Calibrated confidence score")
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    reasoning: str = Field(..., description="LLM explanation of the deterministic signal")

    # Provenance — links back to the deterministic engine output
    candidate_patterns: list[str] = Field(default_factory=list, description="Patterns that fired in deterministic engine")
    corroboration_count: int = Field(default=1)
    alpha_score: Optional[AlphaScore] = None


# ─────────────────────────────────────────────
# Feedback Loop Layer
# ─────────────────────────────────────────────

class FeedbackType(str, Enum):
    FALSE_POSITIVE   = "false_positive"
    CONFIRMED        = "confirmed"
    MISSED_EVENT     = "missed_event"
    SEVERITY_TOO_HIGH = "severity_too_high"
    SEVERITY_TOO_LOW  = "severity_too_low"


class FeedbackEntry(BaseModel):
    """Analyst correction or system-generated feedback on a signal."""
    feedback_id: str
    company_name: str
    signal_type: SignalType
    feedback_type: FeedbackType
    original_severity: Severity
    corrected_severity: Optional[Severity] = None
    analyst_note: str = ""
    source_patterns: list[str] = Field(default_factory=list)
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    # Outcome tracking
    event_materialised: Optional[bool] = None
    days_to_event: Optional[int] = None


# ─────────────────────────────────────────────
# Audit Log Layer
# ─────────────────────────────────────────────

class AuditEntry(BaseModel):
    """
    Immutable audit record for every decision in the pipeline.
    Stored with a hash chain for tamper-evidence.
    """
    entry_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    pipeline_step: str
    company_name: str
    action: str
    detail: str
    data_hash: str = Field(..., description="SHA256 of the input data at this step")
    prev_hash: str = Field(default="GENESIS", description="Hash of previous entry — chain integrity")
    model_version: str = ""
    analyst_id: str = "system"


# ─────────────────────────────────────────────
# Analyst Brief Layer
# ─────────────────────────────────────────────

class RiskFactor(BaseModel):
    factor: str
    impact: str
    likelihood: Severity
    mitigation: Optional[str] = None


class KeyMetric(BaseModel):
    name: str
    value: str
    period: str
    interpretation: str


class AnalystBrief(BaseModel):
    """The final structured output — the decision artifact."""
    # Header
    company_name: str
    ticker: Optional[str] = None
    brief_date: datetime = Field(default_factory=datetime.utcnow)
    analyst_model: str = Field(default="claude-sonnet-4-20250514")

    # Executive summary
    executive_summary: str
    overall_severity: Severity
    recommendation: str = Field(..., description="Actionable recommendation for the analyst")
    confidence_score: float = Field(..., ge=0.0, le=1.0)

    # Signals — always from deterministic engine, explained by LLM
    detected_signals: list[DetectedSignal]
    signal_candidates_count: int = Field(default=0, description="Total candidates from deterministic engine before LLM explanation")

    # Alpha scoring
    top_alpha_score: Optional[float] = None
    liquidity_tier: Optional[LiquidityTier] = None
    requires_human_review: bool = False
    human_review_reasons: list[str] = Field(default_factory=list)

    # Deep analysis
    key_metrics: list[KeyMetric] = Field(default_factory=list)
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    competitive_context: Optional[str] = None
    recent_developments: list[str] = Field(default_factory=list)

    # Sourcing
    filings_reviewed: list[SECFiling] = Field(default_factory=list)
    news_reviewed: list[NewsItem] = Field(default_factory=list)
    total_sources: int = 0

    # Compliance mode
    compliance_mode: bool = False
    compliance_flags: list[str] = Field(default_factory=list)
    low_confidence_signals_suppressed: int = Field(default=0)

    # Compound events (from SignalInteractionEngine)
    compound_signals: list["CompoundSignal"] = Field(default_factory=list)
    systemic_risk_level: "SystemicRiskLevel" = Field(default="isolated")

    # Reasoning trace + audit
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)
    audit_entries: list[AuditEntry] = Field(default_factory=list)
    processing_time_seconds: Optional[float] = None

    def signal_count_by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in Severity}
        for sig in self.detected_signals:
            counts[sig.severity.value] += 1
        return counts

    def top_signals(self, n: int = 3) -> list[DetectedSignal]:
        order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
        return sorted(self.detected_signals, key=lambda s: (order[s.severity], -s.confidence))[:n]


# ─────────────────────────────────────────────
# Agent State (LangGraph graph state)
# ─────────────────────────────────────────────

class AgentState(BaseModel):
    """Mutable state object passed between LangGraph nodes."""
    request: AnalysisRequest

    # Populated progressively
    company_profile: Optional[CompanyProfile] = None
    filings: list[SECFiling] = Field(default_factory=list)
    news_items: list[NewsItem] = Field(default_factory=list)

    # Phase 2 — deterministic engine output (before LLM)
    signal_candidates: list[SignalCandidate] = Field(default_factory=list)

    # Phase 3 — LLM-explained + alpha-scored signals
    detected_signals: list[DetectedSignal] = Field(default_factory=list)

    # Phase 4 — compound event engine output
    compound_signals: list["CompoundSignal"] = Field(default_factory=list)

    brief: Optional[AnalystBrief] = None

    # Control flow
    errors: list[str] = Field(default_factory=list)
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)
    audit_entries: list[AuditEntry] = Field(default_factory=list)
    current_step: str = "init"
    retry_count: int = 0
    compliance_mode: bool = False

    def log(self, step: str, detail: str, data: Any = None) -> None:
        self.reasoning_trace.append({
            "step": step,
            "detail": detail,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        })
        self.current_step = step


# ─────────────────────────────────────────────
# Signal Interaction & Compound Event Layer (#1)
# ─────────────────────────────────────────────

class InteractionType(str, Enum):
    REINFORCING    = "reinforcing"     # signals confirm each other → raise severity
    CASCADING      = "cascading"       # one signal leads to another predictably
    CONTRADICTORY  = "contradictory"   # signals conflict — reduce confidence
    ESCALATING     = "escalating"      # temporal sequence suggests worsening
    CONVERGING     = "converging"      # multiple independent paths to same event


class SystemicRiskLevel(str, Enum):
    ISOLATED   = "isolated"    # single company, no contagion risk
    CONTAINED  = "contained"   # limited to sector/geography
    SYSTEMIC   = "systemic"    # potential broader market impact


class CompoundSignal(BaseModel):
    """
    A compound event produced by the SignalInteractionEngine.
    Represents interaction between 2+ individual signals.
    """
    compound_id: str
    component_signal_types: list[SignalType]
    interaction_type: InteractionType
    escalation_score: float = Field(..., ge=0.0, le=1.0)
    compounded_confidence: float = Field(..., ge=0.0, le=1.0)
    systemic_risk_level: SystemicRiskLevel = SystemicRiskLevel.ISOLATED
    reasoning_chain: str = ""
    temporal_window_days: int = Field(default=30)
    alpha_multiplier: float = Field(default=1.0, ge=0.5, le=3.0)
    detected_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────
# Confidence Decomposition Framework (#5)
# ─────────────────────────────────────────────

class ConfidenceDecomposition(BaseModel):
    """
    Transparent breakdown of every confidence score.
    Replaces opaque single float with auditable components.
    """
    final_confidence: float = Field(..., ge=0.0, le=1.0)

    # Components
    source_reliability_score: float = Field(..., ge=0.0, le=1.0)
    corroboration_score: float = Field(..., ge=0.0, le=1.0)
    filing_strength_score: float = Field(..., ge=0.0, le=1.0)
    historical_precision_score: float = Field(..., ge=0.0, le=1.0)
    entity_match_confidence: float = Field(..., ge=0.0, le=1.0)
    temporal_relevance_score: float = Field(..., ge=0.0, le=1.0)
    extraction_confidence: float = Field(..., ge=0.0, le=1.0)
    calibration_adjustment: float = Field(default=1.0, ge=0.0, le=2.0)

    # Audit trail
    component_weights: dict[str, float] = Field(default_factory=dict)
    reasoning: str = ""
    computed_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────
# Company Memory Layer (#4)
# ─────────────────────────────────────────────

class CompanyRiskProfile(BaseModel):
    """
    Persistent longitudinal risk profile for a monitored company.
    Updated on every analysis run. Enables trend detection.
    """
    company_id: str          # normalised company name or CIK
    company_name: str
    ticker: Optional[str] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    # Rolling risk scores (0-100, higher = more risk)
    rolling_risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    governance_score: float = Field(default=50.0, ge=0.0, le=100.0)
    liquidity_score: float = Field(default=50.0, ge=0.0, le=100.0)
    regulatory_risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    credit_risk_score: float = Field(default=0.0, ge=0.0, le=100.0)

    # Velocity & trends
    event_velocity: float = Field(default=0.0, description="Signals per 30 days")
    risk_trend: str = Field(default="stable", description="improving|stable|deteriorating")
    risk_delta_30d: float = Field(default=0.0, description="Change in risk score over 30 days")

    # Historical signal density
    total_signals_detected: int = 0
    total_analyses_run: int = 0
    historical_signal_density: dict[str, int] = Field(
        default_factory=dict, description="signal_type -> count"
    )
    repeated_patterns: list[str] = Field(default_factory=list)

    # Historical alpha scores
    alpha_score_history: list[dict[str, Any]] = Field(default_factory=list)
    analyst_attention_score: float = Field(default=0.0, ge=0.0, le=100.0)

    # Management turnover tracking
    leadership_change_count: int = 0
    last_leadership_change: Optional[str] = None

    # Debt trajectory
    debt_restructure_count: int = 0
    regulatory_action_count: int = 0


# ─────────────────────────────────────────────
# Market Impact & Outcome Layer (#8)
# ─────────────────────────────────────────────

class MarketOutcome(BaseModel):
    """Tracks actual market reaction after a signal was raised."""
    outcome_id: str
    company_name: str
    signal_type: SignalType
    severity_at_detection: Severity
    alpha_score_at_detection: Optional[float] = None
    detection_date: str

    # Realised market reaction
    price_change_5d_pct: Optional[float] = None
    price_change_10d_pct: Optional[float] = None
    price_change_30d_pct: Optional[float] = None
    volume_spike_pct: Optional[float] = None

    # Event confirmation
    event_confirmed: Optional[bool] = None
    confirmation_date: Optional[str] = None
    confirmation_source: Optional[str] = None

    # Accuracy metrics
    direction_correct: Optional[bool] = None
    magnitude_error_pct: Optional[float] = None

    recorded_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────
# Extend AgentState with new layers
# ─────────────────────────────────────────────

# NOTE: AgentState already defined above. We extend it by monkey-patching
# the compound_signals field via the interaction engine at runtime.
# The field is added to the existing AgentState dynamically in graph.py
# to avoid redefining the class. Compound signals are stored on AnalystBrief.
