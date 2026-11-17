"""Refresh src/data/licensed_institutions.json: banks and other financial institutions licensed in Nigeria and Ghana."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.engines import licensed_institutions  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

if __name__ == "__main__":
    print(json.dumps(licensed_institutions.refresh(), indent=2))
