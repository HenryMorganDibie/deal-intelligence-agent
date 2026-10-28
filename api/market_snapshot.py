"""
The daily market snapshot, deployed as its own function in Paris (cdg1).

Some exchange sources answer only European addresses (ilboursa's Tunis board returns 403 to the US region the
main API runs in), so the snapshot runs closer to them; everything else stays in api/index.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DEAL_INTEL_DATA_DIR", "/tmp/deal-intel-data")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI  # noqa: E402

from src.hosted_market import cron_market_snapshot  # noqa: E402

app = FastAPI(title="Deal Intelligence market snapshot", docs_url=None, redoc_url=None, openapi_url=None)
app.add_api_route("/api/cron/market-snapshot", cron_market_snapshot, methods=["GET"])
