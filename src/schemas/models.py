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
# Signal Detection Layer
# ─────────────────────────────────────────────

class DetectedSignal(BaseModel):
    """A single intelligence signal surfaced by the detection agent."""
    signal_type: SignalType
    severity: Severity
    headline: str = Field(..., description="One-line signal description")
    evidence: list[str] = Field(..., description="Supporting evidence snippets")
    source_urls: list[str] = Field(default_factory=list)
    filing_references: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0, description="Agent confidence score")
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    reasoning: str = Field(..., description="Chain-of-thought reasoning trace")


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

    # Signals
    detected_signals: list[DetectedSignal]

    # Deep analysis
    key_metrics: list[KeyMetric] = Field(default_factory=list)
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    competitive_context: Optional[str] = None
    recent_developments: list[str] = Field(default_factory=list)

    # Sourcing
    filings_reviewed: list[SECFiling] = Field(default_factory=list)
    news_reviewed: list[NewsItem] = Field(default_factory=list)
    total_sources: int = 0

    # Reasoning trace (for auditability)
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)
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
    detected_signals: list[DetectedSignal] = Field(default_factory=list)
    brief: Optional[AnalystBrief] = None

    # Control flow
    errors: list[str] = Field(default_factory=list)
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)
    current_step: str = "init"
    retry_count: int = 0

    def log(self, step: str, detail: str, data: Any = None) -> None:
        self.reasoning_trace.append({
            "step": step,
            "detail": detail,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        })
        self.current_step = step
