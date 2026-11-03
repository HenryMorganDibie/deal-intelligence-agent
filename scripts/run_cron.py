"""Run the API's scheduled jobs inside GitHub Actions instead of on Vercel.

The jobs are the same route handlers the API serves; this loads the app in-process and calls them, so the work
(feeds, parsing, translation, alert delivery) runs on the Actions runner and costs no Vercel function time. The
database is reached exactly as from Vercel: through the shared-secret functions, with DEAL_INTEL_API_SECRET.

    python scripts/run_cron.py /api/cron/ingest /api/cron/country-snapshot
    python scripts/run_cron.py --until-empty 60 "/api/cron/enrich-rounds?limit=40"

Exits non-zero when any job answers with an error, so the workflow run shows as failed.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DEAL_INTEL_DATA_DIR", "/tmp/deal-intel-data")
# Secrets pasted into GitHub often carry a stray space or line break; the database compares them exactly.
for _name in ("DEAL_INTEL_API_SECRET", "SUPABASE_PUBLISHABLE_KEY", "GROQ_API_KEY", "OLLAMA_API_KEY",
              "OPENCODE_API_KEY", "SENDBYTE_API_KEY"):
    if os.environ.get(_name):
        os.environ[_name] = os.environ[_name].strip()
# A one-off bearer token for this process only, set before the app reads its configuration.
os.environ["CRON_SECRET"] = secrets.token_urlsafe(32)


def _summary(body: object, limit: int = 4000) -> str:
    text = json.dumps(body, default=str, ensure_ascii=False) if not isinstance(body, str) else body
    return text if len(text) <= limit else text[:limit] + "…"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", help="cron routes to call, in order")
    parser.add_argument("--until-empty", type=int, default=0, metavar="N",
                        help="repeat each route up to N times while it reports remaining work")
    args = parser.parse_args()

    for name in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "DEAL_INTEL_API_SECRET"):
        if not os.environ.get(name):
            print(f"::error::{name} is not set. Add it under Settings, Secrets and variables, Actions.")
            return 2

    from fastapi.testclient import TestClient
    from api.index import app

    failed = False
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = {"Authorization": f"Bearer {os.environ['CRON_SECRET']}", "Accept": "application/json"}
        for path in args.paths:
            rounds = max(1, args.until_empty)
            for i in range(1, rounds + 1):
                started = time.monotonic()
                response = client.get(path, headers=headers)
                took = time.monotonic() - started
                try:
                    body = response.json()
                except ValueError:
                    body = response.text
                label = f"{path} (round {i})" if rounds > 1 else path
                print(f"{label}: HTTP {response.status_code} in {took:.1f}s")
                print(_summary(body))
                if response.status_code >= 400:
                    print(f"::error::{path} failed with HTTP {response.status_code}")
                    failed = True
                    break
                if rounds > 1:
                    remaining = body.get("remaining", 0) if isinstance(body, dict) else 0
                    processed = body.get("processed", 0) if isinstance(body, dict) else 0
                    if not remaining or not processed:
                        break
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
