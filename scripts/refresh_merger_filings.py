#!/usr/bin/env python3
"""Refresh the committed snapshot of official merger-control filings (COMESA and South Africa).

Reads only documents not already in src/data/merger_filings.json, so a weekly run is light.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.engines import merger_filings  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

if __name__ == "__main__":
    result = merger_filings.refresh()
    logging.info("merger filings: %d added, %d held", result["added"], result["total"])
