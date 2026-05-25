"""
Company Memory Layer (#4).
Persistent longitudinal risk profiles for monitored companies.
Tracks rolling distress scores, governance trends, signal density,
alpha history, and event velocity across analysis runs.
Stored in data/company_memory.json — drop-in replaceable with Postgres.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.schemas.models import (
    CompanyRiskProfile, AnalystBrief, SignalType, Severity
)

MEMORY_PATH = Path(__file__).resolve().parents[2] / "data" / "company_memory.json"

# EMA smoothing factor for rolling score updates
EMA_ALPHA = 0.25

# Severity → risk score contribution
SEVERITY_RISK = {
    Severity.LOW:      10.0,
    Severity.MEDIUM:   30.0,
    Severity.HIGH:     60.0,
    Severity.CRITICAL: 90.0,
}

# Signal type → which dimension it affects
SIGNAL_DIMENSION_MAP: dict[SignalType, str] = {
    SignalType.LEADERSHIP_CHANGE:  "governance_score",
    SignalType.REGULATORY_ACTION:  "regulatory_risk_score",
    SignalType.CREDIT_RISK:        "credit_risk_score",
    SignalType.DISTRESSED_ASSET:   "credit_risk_score",
    SignalType.DEBT_RESTRUCTURE:   "credit_risk_score",
    SignalType.MA_ACTIVITY:        "rolling_risk_score",
    SignalType.EARNINGS_SURPRISE:  "rolling_risk_score",
    SignalType.INSIDER_ACTIVITY:   "rolling_risk_score",
}


def _load() -> dict[str, dict]:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MEMORY_PATH.exists():
        return {}
    try:
        return json.loads(MEMORY_PATH.read_text())
    except Exception:
        return {}


def _save(data: dict) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(data, indent=2, default=str))


def _company_id(name: str, ticker: Optional[str] = None) -> str:
    return (ticker or name).upper().strip().replace(" ", "_")


def _ema(current: float, new_value: float) -> float:
    return round(current + EMA_ALPHA * (new_value - current), 2)


def _risk_trend(old_score: float, new_score: float) -> str:
    delta = new_score - old_score
    if delta > 5:
        return "deteriorating"
    if delta < -5:
        return "improving"
    return "stable"


def update_profile(brief: AnalystBrief) -> CompanyRiskProfile:
    """
    Update or create a CompanyRiskProfile from a completed brief.
    Applies EMA updates to all rolling scores and trends.
    """
    data = _load()
    cid  = _company_id(brief.company_name, brief.ticker)

    existing = data.get(cid)
    if existing:
        profile = CompanyRiskProfile.model_validate(existing)
    else:
        profile = CompanyRiskProfile(
            company_id=cid,
            company_name=brief.company_name,
            ticker=brief.ticker,
        )

    old_risk = profile.rolling_risk_score

    # Update rolling risk score from overall severity
    new_risk_contribution = SEVERITY_RISK.get(brief.overall_severity, 0.0)
    if brief.top_alpha_score:
        new_risk_contribution = max(new_risk_contribution, brief.top_alpha_score * 0.9)

    profile.rolling_risk_score = _ema(profile.rolling_risk_score, new_risk_contribution)

    # Update dimension-specific scores
    for sig in brief.detected_signals:
        dimension = SIGNAL_DIMENSION_MAP.get(sig.signal_type)
        if dimension:
            contribution = SEVERITY_RISK.get(sig.severity, 0.0)
            current_val  = getattr(profile, dimension, 0.0)
            setattr(profile, dimension, _ema(current_val, contribution))

        # Signal density tracking
        profile.historical_signal_density[sig.signal_type.value] = (
            profile.historical_signal_density.get(sig.signal_type.value, 0) + 1
        )
        profile.total_signals_detected += 1

        # Leadership tracking
        if sig.signal_type == SignalType.LEADERSHIP_CHANGE:
            profile.leadership_change_count += 1
            profile.last_leadership_change = datetime.utcnow().strftime("%Y-%m-%d")

        # Debt restructuring tracking
        if sig.signal_type == SignalType.DEBT_RESTRUCTURE:
            profile.debt_restructure_count += 1

        # Regulatory tracking
        if sig.signal_type == SignalType.REGULATORY_ACTION:
            profile.regulatory_action_count += 1

    # Event velocity: signals per 30 days (simplified EMA)
    velocity = len(brief.detected_signals)
    profile.event_velocity = _ema(profile.event_velocity, velocity)

    # Trend detection
    profile.risk_delta_30d = round(profile.rolling_risk_score - old_risk, 2)
    profile.risk_trend = _risk_trend(old_risk, profile.rolling_risk_score)

    # Alpha score history (keep last 20)
    if brief.top_alpha_score is not None:
        profile.alpha_score_history.append({
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "alpha": brief.top_alpha_score,
            "severity": brief.overall_severity.value,
        })
        profile.alpha_score_history = profile.alpha_score_history[-20:]

    # Analyst attention score: driven by event velocity + alpha
    attention = (profile.event_velocity * 10) + (brief.top_alpha_score or 0) * 0.3
    profile.analyst_attention_score = min(round(attention, 1), 100.0)

    # Repeated pattern detection
    for sig_type, count in profile.historical_signal_density.items():
        if count >= 3 and sig_type not in profile.repeated_patterns:
            profile.repeated_patterns.append(sig_type)

    # Clamp all scores to 0–100
    for field in ["rolling_risk_score","governance_score","liquidity_score",
                  "regulatory_risk_score","credit_risk_score","analyst_attention_score"]:
        val = getattr(profile, field)
        setattr(profile, field, max(0.0, min(100.0, val)))

    profile.total_analyses_run += 1
    profile.last_updated = datetime.utcnow()

    data[cid] = json.loads(profile.model_dump_json())
    _save(data)
    return profile


def get_profile(company_name: str, ticker: Optional[str] = None) -> Optional[CompanyRiskProfile]:
    """Retrieve a company's risk profile."""
    data = _load()
    cid  = _company_id(company_name, ticker)
    raw  = data.get(cid)
    if not raw:
        return None
    return CompanyRiskProfile.model_validate(raw)


def list_profiles(limit: int = 50) -> list[CompanyRiskProfile]:
    """Return all tracked company profiles sorted by risk score descending."""
    data = _load()
    profiles = [CompanyRiskProfile.model_validate(v) for v in data.values()]
    return sorted(profiles, key=lambda p: p.rolling_risk_score, reverse=True)[:limit]


def get_watchlist_alerts(threshold: float = 60.0) -> list[CompanyRiskProfile]:
    """Return companies whose rolling risk score exceeds threshold."""
    return [p for p in list_profiles() if p.rolling_risk_score >= threshold]
