"""HTTP API for the hosted app (Vercel Python function).

POST /api/analyse runs the pipeline for a signed-in user and stores the brief.
Identity, the daily quota and storage all go through Supabase using the
caller's own access token, so row level security applies to every write and
the function needs no service-role key.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# The filesystem is read-only on Vercel apart from /tmp. Set before the
# pipeline modules import, since they resolve their store paths at import.
os.environ.setdefault("DEAL_INTEL_DATA_DIR", "/tmp/deal-intel-data")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json  # noqa: E402
import logging  # noqa: E402

import httpx  # noqa: E402
from fastapi import FastAPI, Header, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field, field_validator  # noqa: E402

log = logging.getLogger("deal_intel.api")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
DAILY_LIMIT = int(os.environ.get("DEAL_INTEL_DAILY_LIMIT", "10"))
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]

app = FastAPI(title="Deal Intelligence API", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["http://localhost:3000"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)


class AnalyseBody(BaseModel):
    company: str = Field(..., min_length=1, max_length=120)
    ticker: str | None = Field(None, max_length=20)
    lookback_days: int = Field(90, ge=1, le=365)
    compliance: bool = False

    @field_validator("company", "ticker")
    @classmethod
    def strip(cls, v: str | None) -> str | None:
        v = v.strip() if v else v
        return v or None


def _rest_headers(token: str) -> dict[str, str]:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def _user_id(client: httpx.AsyncClient, authorization: str | None) -> tuple[str, str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in to run an analysis.")
    token = authorization.split(" ", 1)[1].strip()
    resp = await client.get(f"{SUPABASE_URL}/auth/v1/user", headers=_rest_headers(token))
    if resp.status_code != 200:
        raise HTTPException(401, "Your session has expired. Sign in again.")
    return resp.json()["id"], token


async def _consume_run(client: httpx.AsyncClient, token: str) -> int:
    resp = await client.post(
        f"{SUPABASE_URL}/rest/v1/rpc/consume_run",
        headers=_rest_headers(token),
        json={"daily_limit": DAILY_LIMIT},
    )
    if resp.status_code != 200:
        log.error("consume_run failed: %s %s", resp.status_code, resp.text[:300])
        raise HTTPException(503, "Could not check your usage. Try again shortly.")
    return int(resp.json())


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "configured": bool(SUPABASE_URL and SUPABASE_KEY),
        "llm": bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GROQ_API_KEY")),
        "daily_limit": DAILY_LIMIT,
    }


@app.post("/api/analyse")
async def analyse(body: AnalyseBody, authorization: str | None = Header(None)) -> dict:
    if not (SUPABASE_URL and SUPABASE_KEY):
        raise HTTPException(503, "The API is not configured.")

    async with httpx.AsyncClient(timeout=15) as client:
        user_id, token = await _user_id(client, authorization)
        used = await _consume_run(client, token)
        if used < 0:
            raise HTTPException(429, f"You have used all {DAILY_LIMIT} analyses for today. The limit resets at 00:00 UTC.")

    from src.agents.graph import run_analysis
    from src.schemas.models import AnalysisRequest
    from src.utils.formatter import brief_to_markdown

    request = AnalysisRequest(company_name=body.company, ticker=body.ticker, lookback_days=body.lookback_days)
    try:
        brief = await run_analysis(request, compliance_mode=body.compliance)
    except Exception:
        log.exception("analysis failed for %r", body.company)
        raise HTTPException(502, "The analysis failed. The data sources may be unavailable; try again in a minute.")

    brief_json = json.loads(brief.model_dump_json())
    row = {
        "user_id": user_id,
        "company": brief.company_name,
        "ticker": body.ticker,
        "severity": brief_json.get("overall_severity"),
        "signal_count": len(brief.detected_signals),
        "llm_used": "LLM unavailable" not in (brief_json.get("analyst_model") or ""),
        "brief": brief_json,
        "markdown": brief_to_markdown(brief),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/briefs",
            headers={**_rest_headers(token), "Prefer": "return=representation"},
            json=row,
        )
    if resp.status_code not in (200, 201):
        log.error("brief insert failed: %s %s", resp.status_code, resp.text[:300])
        raise HTTPException(502, "The brief was generated but could not be saved.")
    saved = resp.json()[0]
    return {"id": saved["id"], "runs_used": used, "daily_limit": DAILY_LIMIT}
