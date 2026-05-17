"""
Historical Event Warehouse (#2).

Persistent SQLite database storing all raw data, signals, briefs,
and market outcomes. Enables self-evaluation, backtesting,
longitudinal research, and calibration.

Schema:
  filings          — raw SEC/exchange filings
  news_items       — raw news articles
  signal_candidates — deterministic engine output
  detected_signals  — LLM-explained signals
  compound_events   — signal interaction engine output
  analyst_briefs    — final briefs (JSON)
  market_outcomes   — post-signal market reactions
  replay_runs       — deterministic replay snapshots
  scoring_history   — alpha score evolution over time
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import (
    create_engine, Column, String, Float, Integer,
    Boolean, DateTime, Text, Index
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "warehouse.db"


class Base(DeclarativeBase):
    pass


class FilingRecord(Base):
    __tablename__ = "filings"
    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id          = Column(String, index=True)
    company_name    = Column(String, index=True)
    accession_number = Column(String, index=True)
    form_type       = Column(String)
    filing_date     = Column(String)
    cik             = Column(String)
    document_url    = Column(String)
    description     = Column(Text)
    raw_excerpt     = Column(Text)
    ingested_at     = Column(DateTime, default=datetime.utcnow)


class NewsRecord(Base):
    __tablename__ = "news_items"
    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id          = Column(String, index=True)
    company_name    = Column(String, index=True)
    title           = Column(Text)
    source          = Column(String)
    published_date  = Column(String)
    url             = Column(String)
    snippet         = Column(Text)
    relevance_score = Column(Float)
    ingested_at     = Column(DateTime, default=datetime.utcnow)


class SignalCandidateRecord(Base):
    __tablename__ = "signal_candidates"
    id                  = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id              = Column(String, index=True)
    company_name        = Column(String, index=True)
    signal_type         = Column(String, index=True)
    matched_patterns    = Column(Text)   # JSON
    source_text         = Column(Text)
    source_type         = Column(String)
    source_name         = Column(String)
    raw_score           = Column(Float)
    corroboration_count = Column(Integer)
    detected_at         = Column(DateTime)
    ingested_at         = Column(DateTime, default=datetime.utcnow)


class DetectedSignalRecord(Base):
    __tablename__ = "detected_signals"
    id                  = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id              = Column(String, index=True)
    company_name        = Column(String, index=True)
    signal_type         = Column(String, index=True)
    severity            = Column(String)
    headline            = Column(Text)
    confidence          = Column(Float)
    corroboration_count = Column(Integer)
    alpha_score         = Column(Float)
    alpha_json          = Column(Text)   # full AlphaScore JSON
    candidate_patterns  = Column(Text)   # JSON
    evidence            = Column(Text)   # JSON
    reasoning           = Column(Text)
    detected_at         = Column(DateTime)
    ingested_at         = Column(DateTime, default=datetime.utcnow)


class CompoundEventRecord(Base):
    __tablename__ = "compound_events"
    id                    = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id                = Column(String, index=True)
    company_name          = Column(String, index=True)
    compound_id           = Column(String)
    component_types       = Column(Text)   # JSON
    interaction_type      = Column(String)
    escalation_score      = Column(Float)
    compounded_confidence = Column(Float)
    systemic_risk_level   = Column(String)
    alpha_multiplier      = Column(Float)
    reasoning_chain       = Column(Text)
    detected_at           = Column(DateTime, default=datetime.utcnow)


class AnalystBriefRecord(Base):
    __tablename__ = "analyst_briefs"
    id                      = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id                  = Column(String, unique=True, index=True)
    company_name            = Column(String, index=True)
    ticker                  = Column(String)
    brief_date              = Column(DateTime)
    overall_severity        = Column(String)
    confidence_score        = Column(Float)
    top_alpha_score         = Column(Float)
    signal_count            = Column(Integer)
    compound_signal_count   = Column(Integer)
    requires_human_review   = Column(Boolean)
    compliance_mode         = Column(Boolean)
    processing_time_seconds = Column(Float)
    brief_json              = Column(Text)    # full serialised brief
    created_at              = Column(DateTime, default=datetime.utcnow)


class MarketOutcomeRecord(Base):
    __tablename__ = "market_outcomes"
    id                       = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id                   = Column(String, index=True)
    company_name             = Column(String, index=True)
    signal_type              = Column(String)
    severity_at_detection    = Column(String)
    alpha_score_at_detection = Column(Float)
    detection_date           = Column(String)
    price_change_5d_pct      = Column(Float)
    price_change_10d_pct     = Column(Float)
    price_change_30d_pct     = Column(Float)
    event_confirmed          = Column(Boolean)
    confirmation_date        = Column(String)
    direction_correct        = Column(Boolean)
    magnitude_error_pct      = Column(Float)
    recorded_at              = Column(DateTime, default=datetime.utcnow)


class ReplayRunRecord(Base):
    __tablename__ = "replay_runs"
    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    original_run_id = Column(String, index=True)
    company_name    = Column(String, index=True)
    replay_date     = Column(String)  # Date replayed as-of
    ruleset_version = Column(String)
    model_version   = Column(String)
    prompt_version  = Column(String)
    scoring_version = Column(String)
    config_snapshot = Column(Text)   # JSON
    brief_json      = Column(Text)
    created_at      = Column(DateTime, default=datetime.utcnow)


class ScoringHistoryRecord(Base):
    __tablename__ = "scoring_history"
    id           = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    company_name = Column(String, index=True)
    run_id       = Column(String, index=True)
    signal_type  = Column(String)
    alpha_score  = Column(Float)
    severity     = Column(String)
    confidence   = Column(Float)
    recorded_at  = Column(DateTime, default=datetime.utcnow)


# ─── Engine & Session ─────────────────────────────────────────────────────────

def get_engine():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine


def get_session() -> Session:
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


# ─── Warehouse API ────────────────────────────────────────────────────────────

class EventWarehouse:
    """
    High-level interface for storing and querying the event warehouse.
    All writes are transactional. Reads return typed dicts.
    """

    def __init__(self):
        self.session = get_session()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.session.close()

    def store_run(self, run_id: str, brief: Any) -> None:
        """Persist a complete analysis run to all relevant tables."""
        try:
            # Store filings
            for f in brief.filings_reviewed:
                self.session.merge(FilingRecord(
                    id=str(uuid.uuid4()), run_id=run_id,
                    company_name=brief.company_name,
                    accession_number=f.accession_number,
                    form_type=f.form_type, filing_date=f.filing_date,
                    cik=f.cik, document_url=f.document_url,
                    description=f.description, raw_excerpt=f.raw_excerpt,
                ))

            # Store news
            for n in brief.news_reviewed:
                self.session.merge(NewsRecord(
                    id=str(uuid.uuid4()), run_id=run_id,
                    company_name=brief.company_name,
                    title=n.title, source=n.source,
                    published_date=n.published_date, url=n.url,
                    snippet=n.snippet, relevance_score=n.relevance_score,
                ))

            # Store detected signals
            for sig in brief.detected_signals:
                alpha_json = sig.alpha_score.model_dump_json() if sig.alpha_score else None
                self.session.add(DetectedSignalRecord(
                    run_id=run_id, company_name=brief.company_name,
                    signal_type=sig.signal_type.value,
                    severity=sig.severity.value,
                    headline=sig.headline, confidence=sig.confidence,
                    corroboration_count=sig.corroboration_count,
                    alpha_score=sig.alpha_score.score if sig.alpha_score else None,
                    alpha_json=alpha_json,
                    candidate_patterns=json.dumps(sig.candidate_patterns),
                    evidence=json.dumps(sig.evidence),
                    reasoning=sig.reasoning,
                    detected_at=sig.detected_at,
                ))

            # Store compound signals
            for c in getattr(brief, "compound_signals", []):
                self.session.add(CompoundEventRecord(
                    run_id=run_id, company_name=brief.company_name,
                    compound_id=c.compound_id,
                    component_types=json.dumps([t.value for t in c.component_signal_types]),
                    interaction_type=c.interaction_type.value,
                    escalation_score=c.escalation_score,
                    compounded_confidence=c.compounded_confidence,
                    systemic_risk_level=c.systemic_risk_level.value,
                    alpha_multiplier=c.alpha_multiplier,
                    reasoning_chain=c.reasoning_chain,
                ))

            # Store scoring history
            for sig in brief.detected_signals:
                self.session.add(ScoringHistoryRecord(
                    company_name=brief.company_name, run_id=run_id,
                    signal_type=sig.signal_type.value,
                    alpha_score=sig.alpha_score.score if sig.alpha_score else None,
                    severity=sig.severity.value, confidence=sig.confidence,
                ))

            # Store brief summary
            self.session.merge(AnalystBriefRecord(
                id=str(uuid.uuid4()), run_id=run_id,
                company_name=brief.company_name,
                ticker=brief.ticker, brief_date=brief.brief_date,
                overall_severity=brief.overall_severity.value,
                confidence_score=brief.confidence_score,
                top_alpha_score=brief.top_alpha_score,
                signal_count=len(brief.detected_signals),
                compound_signal_count=len(getattr(brief, "compound_signals", [])),
                requires_human_review=brief.requires_human_review,
                compliance_mode=brief.compliance_mode,
                processing_time_seconds=brief.processing_time_seconds,
                brief_json=brief.model_dump_json(),
            ))

            self.session.commit()
        except Exception as e:
            self.session.rollback()
            raise RuntimeError(f"Warehouse store_run failed: {e}") from e

    def get_company_history(self, company_name: str, limit: int = 20) -> list[dict]:
        """Return historical brief summaries for a company."""
        rows = (
            self.session.query(AnalystBriefRecord)
            .filter(AnalystBriefRecord.company_name.ilike(f"%{company_name}%"))
            .order_by(AnalystBriefRecord.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "run_id": r.run_id, "company_name": r.company_name,
                "brief_date": str(r.brief_date), "severity": r.overall_severity,
                "alpha_score": r.top_alpha_score, "signals": r.signal_count,
                "compounds": r.compound_signal_count,
            }
            for r in rows
        ]

    def get_signal_history(self, company_name: str, signal_type: Optional[str] = None) -> list[dict]:
        """Return historical signal detections for a company."""
        q = (
            self.session.query(DetectedSignalRecord)
            .filter(DetectedSignalRecord.company_name.ilike(f"%{company_name}%"))
        )
        if signal_type:
            q = q.filter(DetectedSignalRecord.signal_type == signal_type)
        rows = q.order_by(DetectedSignalRecord.detected_at.desc()).limit(50).all()
        return [
            {
                "signal_type": r.signal_type, "severity": r.severity,
                "headline": r.headline, "confidence": r.confidence,
                "alpha_score": r.alpha_score, "detected_at": str(r.detected_at),
            }
            for r in rows
        ]

    def get_scoring_trend(self, company_name: str) -> list[dict]:
        """Return alpha score history for trend analysis."""
        rows = (
            self.session.query(ScoringHistoryRecord)
            .filter(ScoringHistoryRecord.company_name.ilike(f"%{company_name}%"))
            .order_by(ScoringHistoryRecord.recorded_at.asc())
            .limit(100)
            .all()
        )
        return [
            {
                "signal_type": r.signal_type, "alpha_score": r.alpha_score,
                "severity": r.severity, "recorded_at": str(r.recorded_at),
            }
            for r in rows
        ]

    def record_outcome(self, outcome: Any) -> None:
        """Store a market outcome after signal materialisation."""
        try:
            self.session.add(MarketOutcomeRecord(
                run_id=getattr(outcome, "outcome_id", str(uuid.uuid4())),
                company_name=outcome.company_name,
                signal_type=outcome.signal_type.value,
                severity_at_detection=outcome.severity_at_detection.value,
                alpha_score_at_detection=outcome.alpha_score_at_detection,
                detection_date=outcome.detection_date,
                price_change_5d_pct=outcome.price_change_5d_pct,
                price_change_10d_pct=outcome.price_change_10d_pct,
                price_change_30d_pct=outcome.price_change_30d_pct,
                event_confirmed=outcome.event_confirmed,
                confirmation_date=outcome.confirmation_date,
                direction_correct=outcome.direction_correct,
                magnitude_error_pct=outcome.magnitude_error_pct,
            ))
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            raise RuntimeError(f"Warehouse record_outcome failed: {e}") from e

    def get_outcome_stats(self) -> dict:
        """Aggregate market outcome accuracy metrics."""
        rows = self.session.query(MarketOutcomeRecord).all()
        if not rows:
            return {}
        total = len(rows)
        confirmed = sum(1 for r in rows if r.event_confirmed)
        direction_correct = sum(1 for r in rows if r.direction_correct)
        avg_mag_error = sum(abs(r.magnitude_error_pct or 0) for r in rows) / total
        return {
            "total_outcomes_tracked": total,
            "event_confirmation_rate": round(confirmed / total, 3),
            "direction_accuracy": round(direction_correct / max(total, 1), 3),
            "avg_magnitude_error_pct": round(avg_mag_error, 2),
        }


def store_analysis_run(run_id: str, brief: Any) -> None:
    """Convenience wrapper."""
    with EventWarehouse() as wh:
        wh.store_run(run_id, brief)
