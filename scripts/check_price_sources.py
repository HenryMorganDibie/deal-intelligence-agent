"""Report exchange price sources that stop answering, so a dead one is replaced before it is needed.

    python scripts/check_price_sources.py

Prints how many shares each second source priced and the date it carries. Exits 1 when an exchange has no
working second source at all; a single dead source among several is reported as a warning.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from src.engines import price_sources  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
           "Accept": "text/html,application/json"}


def main() -> int:
    today = date.today()
    dead_exchanges = []
    with httpx.Client(timeout=30, follow_redirects=True, headers=HEADERS) as client:
        for exchange, sources in price_sources.SOURCES.items():
            working = 0
            for name, fetch in sources:
                try:
                    priced = fetch(client, today)
                except Exception as e:  # noqa: BLE001 - every failure is reported
                    priced, error = {}, type(e).__name__
                else:
                    error = "no prices"
                if priced:
                    working += 1
                    latest = max((q.get("date") or "") for q in priced.values())
                    print(f"{exchange:5} {name:20} {len(priced):4} shares, dated {latest}")
                else:
                    print(f"::warning::{exchange} price source {name} failed: {error}")
            if not working:
                dead_exchanges.append(exchange)
    for exchange in dead_exchanges:
        print(f"::error::{exchange} has no working second price source")
    return 1 if dead_exchanges else 0


if __name__ == "__main__":
    sys.exit(main())
