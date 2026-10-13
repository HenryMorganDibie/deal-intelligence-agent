"""Current UTC time as a naive datetime.

Replaces the deprecated datetime.utcnow() with the same value. It stays naive on
purpose: every timestamp already stored (JSON stores, SQLite) is naive UTC, and
comparing naive with aware datetimes raises TypeError.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
