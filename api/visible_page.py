"""
One page of visible deals or events for a given store version, for Vercel's CDN to keep (see src/visible_cdn.py).

Its own function, so the main API's request for a page never waits behind the instance that sent it. Only a URL
signed with the server secret is answered; the version in the URL changes whenever the data does, so a cached page
is never stale for its URL.
"""
from __future__ import annotations

import hmac
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import Response  # noqa: E402

from src import visible_cdn  # noqa: E402

app = FastAPI(title="Deal Intelligence visible pages", docs_url=None, redoc_url=None, openapi_url=None)


@app.get(visible_cdn.PATH)
def visible_page(kind: str, v: str, since: str, limit: int, k: str,
                 after: Optional[str] = None, max_id: Optional[str] = None) -> Response:
    secret = os.environ.get("DEAL_INTEL_API_SECRET", "")
    if not secret or not hmac.compare_digest(k, visible_cdn.signature(secret, kind, v, since, limit, after, max_id)):
        raise HTTPException(404, "Not found.")
    if kind not in ("deals", "events") or not 1 <= limit <= 1000:
        raise HTTPException(400, "Bad page request.")
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
    r = httpx.post(f"{url}/rest/v1/rpc/list_visible_page", timeout=30,
                   headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                   json={"secret": secret, "p_kind": kind, "p_since": since, "p_limit": limit,
                         "p_after_id": after, "p_max_id": max_id})
    if r.status_code != 200:
        raise HTTPException(502, "Data store unavailable.")
    return Response(r.content, media_type="application/json",
                    headers={"Cache-Control": "public, max-age=0, s-maxage=86400"})


@app.get(visible_cdn.SNAPSHOT_PATH)
def snapshot_page(kind: str, b: str, k: str) -> Response:
    """The latest market snapshot rows of a kind for one hour bucket (b), for the CDN to keep for that hour."""
    secret = os.environ.get("DEAL_INTEL_API_SECRET", "")
    if not secret or not hmac.compare_digest(k, visible_cdn.snapshot_signature(secret, kind, b)):
        raise HTTPException(404, "Not found.")
    if kind not in visible_cdn.SNAPSHOT_KINDS:
        raise HTTPException(400, "Bad snapshot request.")
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
    r = httpx.post(f"{url}/rest/v1/rpc/list_market_snapshots", timeout=30,
                   headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                   json={"secret": secret, "p_kind": kind})
    if r.status_code != 200:
        raise HTTPException(502, "Data store unavailable.")
    return Response(r.content, media_type="application/json",
                    headers={"Cache-Control": "public, max-age=0, s-maxage=3600"})
