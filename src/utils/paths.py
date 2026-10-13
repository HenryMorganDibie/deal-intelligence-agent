"""Location of the local JSON/SQLite stores.

Defaults to <repo>/data. Set DEAL_INTEL_DATA_DIR to move it, for example to
/tmp on a read-only serverless filesystem.
"""
from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DEAL_INTEL_DATA_DIR") or Path(__file__).resolve().parents[2] / "data")
