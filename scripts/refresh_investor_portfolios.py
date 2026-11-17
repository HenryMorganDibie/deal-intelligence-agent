"""Refresh src/data/investor_portfolios.json: African investors' published portfolios."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.engines import investor_portfolios  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

if __name__ == "__main__":
    print(json.dumps(investor_portfolios.refresh(), indent=2))
