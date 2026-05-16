"""
Audit Log Engine.

Immutable, hash-chained audit trail for every pipeline decision.
Every entry references the SHA-256 of the previous entry,
creating a tamper-evident chain inspectable by compliance teams.

Storage: data/audit_log.jsonl (newline-delimited JSON).
Each line is one AuditEntry. Append-only. Never modified.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.schemas.models import AuditEntry, AgentState

AUDIT_PATH = Path(__file__).resolve().parents[2] / "data" / "audit_log.jsonl"
MODEL_VERSION = "claude-sonnet-4-20250514"
ENGINE_VERSION = "1.0.0"


def _hash(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _last_hash() -> str:
    """Read the hash of the last written entry for chain continuity."""
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not AUDIT_PATH.exists():
        return "GENESIS"
    try:
        lines = AUDIT_PATH.read_text().strip().split("\n")
        for line in reversed(lines):
            if line.strip():
                entry = json.loads(line)
                return entry.get("data_hash", "GENESIS")
    except Exception:
        pass
    return "GENESIS"


def _append(entry: AuditEntry) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("a") as f:
        f.write(entry.model_dump_json() + "\n")


def log_entry(
    pipeline_step: str,
    company_name: str,
    action: str,
    detail: str,
    data: Any = None,
    analyst_id: str = "system",
) -> AuditEntry:
    """
    Write one immutable audit entry to the append-only log.
    Each entry's data_hash is the SHA-256 of its own content.
    prev_hash chains it to the entry before it.
    """
    entry_id = str(uuid.uuid4())
    prev_hash = _last_hash()
    data_hash = _hash({
        "entry_id": entry_id,
        "pipeline_step": pipeline_step,
        "company_name": company_name,
        "action": action,
        "detail": detail,
        "data": data,
        "prev_hash": prev_hash,
        "model_version": MODEL_VERSION,
    })
    entry = AuditEntry(
        entry_id=entry_id,
        pipeline_step=pipeline_step,
        company_name=company_name,
        action=action,
        detail=detail,
        data_hash=data_hash,
        prev_hash=prev_hash,
        model_version=MODEL_VERSION,
        analyst_id=analyst_id,
    )
    _append(entry)
    return entry


def log_state(state: AgentState, action: str, detail: str) -> AuditEntry:
    """Convenience: log from AgentState context."""
    return log_entry(
        pipeline_step=state.current_step,
        company_name=state.request.company_name,
        action=action,
        detail=detail,
        data={
            "filings_count": len(state.filings),
            "news_count": len(state.news_items),
            "candidates_count": len(state.signal_candidates),
            "signals_count": len(state.detected_signals),
        }
    )


def verify_chain(limit: int = 1000) -> tuple[bool, str]:
    """
    Verify the hash chain integrity of the audit log.
    Returns (is_valid, message).
    """
    if not AUDIT_PATH.exists():
        return True, "No audit log exists yet."

    lines = [l for l in AUDIT_PATH.read_text().strip().split("\n") if l.strip()]
    if not lines:
        return True, "Audit log is empty."

    prev_hash = "GENESIS"
    for i, line in enumerate(lines[:limit]):
        try:
            raw = json.loads(line)
            if raw.get("prev_hash") != prev_hash:
                return False, f"Chain broken at entry {i+1}: prev_hash mismatch"
            prev_hash = raw.get("data_hash", "")
        except Exception as e:
            return False, f"Parse error at entry {i+1}: {e}"

    return True, f"Chain valid — {len(lines)} entries verified."


def read_log(limit: int = 100) -> list[AuditEntry]:
    """Read most recent audit entries."""
    if not AUDIT_PATH.exists():
        return []
    lines = [l for l in AUDIT_PATH.read_text().strip().split("\n") if l.strip()]
    recent = lines[-limit:]
    entries = []
    for line in reversed(recent):
        try:
            entries.append(AuditEntry.model_validate(json.loads(line)))
        except Exception:
            continue
    return entries
