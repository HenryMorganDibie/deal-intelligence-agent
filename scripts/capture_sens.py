#!/usr/bin/env python3
"""Append today's (and the previous trading day's) JSE SENS announcements to the capture log.

Run each weekday after the JSE close; the one-day overlap means a missed run loses nothing.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.engines import sens_log  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

if __name__ == "__main__":
    result = sens_log.capture()
    logging.info("SENS: %d added, %d held", result["added"], result["total"])
