"""Weekly: filed accounts of African companies' UK holding companies, from Companies House (src/engines/companies_house)."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import hosted_market as hm  # noqa: E402
from src.engines import companies_house  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

if __name__ == "__main__":
    print(json.dumps(companies_house.refresh(hm._directory()), indent=2))
