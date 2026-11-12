"""Load INEC's polling-unit delimitation into the database (table polling_units).

    python scripts/load_polling_units.py scripts/data/polling_units_2025-09-27.csv.gz

Rows are upserted in batches through the shared-secret function upsert_polling_units; a unit whose name, ward or kind
is unchanged is not rewritten, so a repeat load writes nothing. Run by the "Polling units" workflow.

Source of the bundled file: INEC's public polling-unit locator (inecnigeria.org/polling-units), as collected on
27 September 2025 by the open-source inec-polling-units-scraper (github.com/JayCodist/inec-polling-units-scraper,
ISC licence), cleaned by scripts/data/build_polling_units.py: one blank placeholder row per ward removed, codes
normalised to SS/LL/WW/UUU, and ward names taken from the unit codes where the source listed a few units under a
neighbouring ward. Result: 37 states, 774 LGAs, 8,809 wards and 176,623 polling units (INEC's published total is
176,846).
"""
from __future__ import annotations

import csv
import gzip
import json
import os
import sys
from pathlib import Path

import httpx

SOURCE = "INEC polling-unit locator, collected 2025-09-27 (github.com/JayCodist/inec-polling-units-scraper)"
BATCH = 2000


def rows(path: Path):
    with gzip.open(path, "rt", newline="") as fh:
        yield from csv.DictReader(fh)


def main(argv: list[str]) -> int:
    path = Path(argv[0] if argv else "scripts/data/polling_units_2025-09-27.csv.gz")
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_PUBLISHABLE_KEY"].strip()
    secret = os.environ["DEAL_INTEL_API_SECRET"].strip()
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    batch, sent, written = [], 0, 0
    with httpx.Client(timeout=60) as client:
        def flush():
            nonlocal sent, written, batch
            if not batch:
                return
            r = client.post(f"{url}/rest/v1/rpc/upsert_polling_units", headers=headers,
                            json={"secret": secret, "p_rows": batch, "p_source": SOURCE})
            r.raise_for_status()
            sent += len(batch)
            written += int(r.json() or 0)
            batch = []
        for row in rows(path):
            batch.append(row)
            if len(batch) >= BATCH:
                flush()
        flush()
    print(json.dumps({"rows": sent, "written": written}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
