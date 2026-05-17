"""
Market Impact & Outcome Modeling (#8).
Tracks actual market reactions after signals are raised.
Computes accuracy metrics: direction accuracy, magnitude error,
event confirmation rate. Feeds back into adaptive calibration.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.schemas.models import SignalType, Severity, MarketOutcome

OUTCOMES_PATH = Path(__file__).resolve().parents[2] / "data" / "market_outcomes.json"


def _load() -> list[dict]:
    OUTCOMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not OUTCOMES_PATH.exists():
        return []
    try:
        return json.loads(OUTCOMES_PATH.read_text())
    except Exception:
        return []


def _save(data: list) -> None:
    OUTCOMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTCOMES_PATH.write_text(json.dumps(data, indent=2, default=str))


def record_outcome(
    company_name: str,
    signal_type: SignalType,
    severity_at_detection: Severity,
    detection_date: str,
    alpha_score_at_detection: Optional[float] = None,
    price_change_5d_pct: Optional[float] = None,
    price_change_10d_pct: Optional[float] = None,
    price_change_30d_pct: Optional[float] = None,
    event_confirmed: Optional[bool] = None,
    confirmation_date: Optional[str] = None,
    confirmation_source: Optional[str] = None,
    expected_direction: Optional[str] = None,
    expected_magnitude_low: Optional[float] = None,
    expected_magnitude_high: Optional[float] = None,
) -> MarketOutcome:
    """Record an actual market outcome after a signal was raised."""
    # Compute accuracy metrics
    direction_correct: Optional[bool] = None
    magnitude_error: Optional[float] = None

    if price_change_10d_pct is not None and expected_direction:
        actual_dir = "positive" if price_change_10d_pct > 0 else "negative" if price_change_10d_pct < 0 else "neutral"
        direction_correct = (actual_dir == expected_direction)

    if (price_change_10d_pct is not None and
            expected_magnitude_low is not None and expected_magnitude_high is not None):
        expected_mid = (expected_magnitude_low + expected_magnitude_high) / 2
        magnitude_error = round(abs(abs(price_change_10d_pct) - expected_mid), 2)

    outcome = MarketOutcome(
        outcome_id=str(uuid.uuid4()),
        company_name=company_name,
        signal_type=signal_type,
        severity_at_detection=severity_at_detection,
        alpha_score_at_detection=alpha_score_at_detection,
        detection_date=detection_date,
        price_change_5d_pct=price_change_5d_pct,
        price_change_10d_pct=price_change_10d_pct,
        price_change_30d_pct=price_change_30d_pct,
        event_confirmed=event_confirmed,
        confirmation_date=confirmation_date,
        confirmation_source=confirmation_source,
        direction_correct=direction_correct,
        magnitude_error_pct=magnitude_error,
    )

    data = _load()
    data.append(json.loads(outcome.model_dump_json()))
    _save(data)
    return outcome


def get_accuracy_metrics() -> dict:
    """Aggregate accuracy metrics across all recorded outcomes."""
    data = _load()
    if not data:
        return {"message": "No outcomes recorded yet."}

    total = len(data)
    confirmed    = sum(1 for r in data if r.get("event_confirmed") is True)
    dir_correct  = sum(1 for r in data if r.get("direction_correct") is True)
    has_dir      = sum(1 for r in data if r.get("direction_correct") is not None)
    mag_errors   = [r["magnitude_error_pct"] for r in data if r.get("magnitude_error_pct") is not None]

    # Per signal type breakdown
    by_type: dict[str, dict] = {}
    for r in data:
        st = r.get("signal_type","unknown")
        if st not in by_type:
            by_type[st] = {"total":0,"confirmed":0,"direction_correct":0,"has_dir":0,"mag_errors":[]}
        by_type[st]["total"] += 1
        if r.get("event_confirmed"):
            by_type[st]["confirmed"] += 1
        if r.get("direction_correct") is not None:
            by_type[st]["has_dir"] += 1
            if r["direction_correct"]:
                by_type[st]["direction_correct"] += 1
        if r.get("magnitude_error_pct") is not None:
            by_type[st]["mag_errors"].append(r["magnitude_error_pct"])

    per_signal = {}
    for st, s in by_type.items():
        per_signal[st] = {
            "total": s["total"],
            "event_confirmation_rate": round(s["confirmed"] / max(s["total"], 1), 3),
            "direction_accuracy": round(s["direction_correct"] / max(s["has_dir"], 1), 3),
            "avg_magnitude_error_pct": round(sum(s["mag_errors"]) / max(len(s["mag_errors"]), 1), 2),
        }

    return {
        "total_outcomes": total,
        "event_confirmation_rate": round(confirmed / total, 3),
        "direction_accuracy": round(dir_correct / max(has_dir, 1), 3),
        "avg_magnitude_error_pct": round(sum(mag_errors) / max(len(mag_errors), 1), 2) if mag_errors else None,
        "by_signal_type": per_signal,
    }


def get_signal_accuracy(signal_type: SignalType) -> dict:
    """Accuracy metrics for a specific signal type."""
    data = _load()
    relevant = [r for r in data if r.get("signal_type") == signal_type.value]
    if not relevant:
        return {"signal_type": signal_type.value, "samples": 0}

    confirmed   = sum(1 for r in relevant if r.get("event_confirmed"))
    dir_correct = sum(1 for r in relevant if r.get("direction_correct"))
    has_dir     = sum(1 for r in relevant if r.get("direction_correct") is not None)

    avg_5d  = sum(abs(r.get("price_change_5d_pct")  or 0) for r in relevant) / len(relevant)
    avg_10d = sum(abs(r.get("price_change_10d_pct") or 0) for r in relevant) / len(relevant)
    avg_30d = sum(abs(r.get("price_change_30d_pct") or 0) for r in relevant) / len(relevant)

    return {
        "signal_type": signal_type.value,
        "samples": len(relevant),
        "event_confirmation_rate": round(confirmed / len(relevant), 3),
        "direction_accuracy": round(dir_correct / max(has_dir, 1), 3),
        "avg_abs_move_5d_pct":  round(avg_5d, 2),
        "avg_abs_move_10d_pct": round(avg_10d, 2),
        "avg_abs_move_30d_pct": round(avg_30d, 2),
    }
