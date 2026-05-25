"""
Feedback Loop Engine.

Stores and retrieves analyst corrections, false positive logs,
and missed event records. Updates source reliability scores
based on accumulated signal outcomes.

Storage: JSON file (data/feedback.json) — drop-in replaceable
with Postgres/MongoDB in production without changing the interface.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.schemas.models import (
    FeedbackEntry, FeedbackType, SignalType, Severity
)

FEEDBACK_PATH = Path(__file__).resolve().parents[2] / "data" / "feedback.json"


def _load() -> dict:
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not FEEDBACK_PATH.exists():
        return {"entries": [], "source_reliability": {}, "signal_stats": {}}
    try:
        return json.loads(FEEDBACK_PATH.read_text())
    except Exception:
        return {"entries": [], "source_reliability": {}, "signal_stats": {}}


def _save(data: dict) -> None:
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEEDBACK_PATH.write_text(json.dumps(data, indent=2, default=str))


def submit_feedback(
    company_name: str,
    signal_type: SignalType,
    feedback_type: FeedbackType,
    original_severity: Severity,
    corrected_severity: Optional[Severity] = None,
    analyst_note: str = "",
    source_patterns: list[str] | None = None,
    event_materialised: Optional[bool] = None,
    days_to_event: Optional[int] = None,
) -> FeedbackEntry:
    """
    Submit analyst feedback on a signal.
    Used to track false positives, confirmations, and missed events.
    """
    entry = FeedbackEntry(
        feedback_id=str(uuid.uuid4()),
        company_name=company_name,
        signal_type=signal_type,
        feedback_type=feedback_type,
        original_severity=original_severity,
        corrected_severity=corrected_severity,
        analyst_note=analyst_note,
        source_patterns=source_patterns or [],
        event_materialised=event_materialised,
        days_to_event=days_to_event,
    )

    data = _load()
    data["entries"].append(json.loads(entry.model_dump_json()))
    _update_signal_stats(data, entry)
    _save(data)
    return entry


def _update_signal_stats(data: dict, entry: FeedbackEntry) -> None:
    """Update rolling precision/recall stats per signal_type."""
    key = entry.signal_type.value
    stats = data["signal_stats"].get(key, {
        "total": 0, "confirmed": 0, "false_positive": 0,
        "missed": 0, "severity_adjusted": 0
    })
    stats["total"] += 1
    if entry.feedback_type == FeedbackType.CONFIRMED:
        stats["confirmed"] += 1
    elif entry.feedback_type == FeedbackType.FALSE_POSITIVE:
        stats["false_positive"] += 1
    elif entry.feedback_type == FeedbackType.MISSED_EVENT:
        stats["missed"] += 1
    elif entry.feedback_type in (FeedbackType.SEVERITY_TOO_HIGH, FeedbackType.SEVERITY_TOO_LOW):
        stats["severity_adjusted"] += 1
    data["signal_stats"][key] = stats


def get_signal_stats() -> dict[str, dict]:
    """
    Return precision/recall stats per signal type.
    Format: {signal_type: {total, confirmed, false_positive, precision, recall_proxy}}
    """
    data = _load()
    stats = data.get("signal_stats", {})
    result = {}
    for sig_type, s in stats.items():
        total = s.get("total", 0)
        confirmed = s.get("confirmed", 0)
        fp = s.get("false_positive", 0)
        precision = confirmed / max(confirmed + fp, 1)
        result[sig_type] = {
            **s,
            "precision": round(precision, 3),
            "recall_proxy": round(confirmed / max(total, 1), 3),
        }
    return result


def get_source_reliability() -> dict[str, float]:
    """Return accumulated source reliability scores (0–1)."""
    data = _load()
    return data.get("source_reliability", {})


def update_source_reliability(source_name: str, was_correct: bool) -> None:
    """
    Update a source's reliability score using exponential moving average.
    Correct signal → score nudges up. False positive → score nudges down.
    """
    data = _load()
    rel = data.get("source_reliability", {})
    current = rel.get(source_name, 0.70)  # start at 0.70 for unknown sources
    alpha = 0.15  # EMA smoothing factor
    new_score = current + alpha * ((1.0 if was_correct else 0.0) - current)
    rel[source_name] = round(new_score, 4)
    data["source_reliability"] = rel
    _save(data)


def get_recent_feedback(limit: int = 50) -> list[FeedbackEntry]:
    """Return the most recent feedback entries."""
    data = _load()
    entries = data.get("entries", [])[-limit:]
    return [FeedbackEntry.model_validate(e) for e in reversed(entries)]


def false_positive_rate(signal_type: SignalType) -> float:
    """Return the accumulated false positive rate for a signal type."""
    stats = get_signal_stats()
    s = stats.get(signal_type.value, {})
    total = s.get("total", 0)
    fp = s.get("false_positive", 0)
    return round(fp / max(total, 1), 3)
