"""Refresh src/data/debt_filings.json: commercial paper and bonds announced by FMDQ Exchange."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.engines import debt_filings  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

if __name__ == "__main__":
    print(json.dumps(debt_filings.refresh(), indent=2))
