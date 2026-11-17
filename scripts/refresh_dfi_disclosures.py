"""Refresh src/data/dfi_disclosures.json: development-finance investments in African companies (IATI via d-portal)."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.engines import dfi_disclosures  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

if __name__ == "__main__":
    print(json.dumps(dfi_disclosures.refresh(), indent=2))
