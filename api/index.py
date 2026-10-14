"""HTTP API for the hosted app (Vercel Python function).

Open access, no accounts:
  POST /api/analyse      run the pipeline, store the brief, return its id
  GET  /api/briefs/{id}  fetch a stored brief (ids are random UUIDs: share links)
  GET  /api/health
  GET  /api/cron/label   daily (Vercel Cron): label briefs' outcomes for calibration
  plus the market-data routes in src/hosted_market.py (countries, deals, investors,
  companies, research, watchlists, coverage, evaluation, daily ingestion)

Writes go through Supabase functions that require DEAL_INTEL_API_SECRET, which
only this function holds; the publishable key alone can read a brief by id and
nothing else. Each caller is identified by a salted hash of their IP, never the
IP itself, for a per-visitor daily limit and a global daily cap.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# The filesystem is read-only on Vercel apart from /tmp. Set before the
# pipeline modules import, since they resolve their store paths at import.
os.environ.setdefault("DEAL_INTEL_DATA_DIR", "/tmp/deal-intel-data")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hashlib  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402

import httpx  # noqa: E402
from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field, field_validator  # noqa: E402

log = logging.getLogger("deal_intel.api")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
API_SECRET = os.environ.get("DEAL_INTEL_API_SECRET", "")
PER_VISITOR_DAILY = int(os.environ.get("DEAL_INTEL_PER_VISITOR_DAILY", "10"))
GLOBAL_DAILY = int(os.environ.get("DEAL_INTEL_GLOBAL_DAILY", "300"))
CRON_SECRET = os.environ.get("CRON_SECRET", "")
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]

app = FastAPI(title="Deal Intelligence API", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["http://localhost:3000"],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
    max_age=600,
)


class AnalyseBody(BaseModel):
    company: str = Field(..., min_length=1, max_length=120)
    ticker: str | None = Field(None, max_length=20)
    country: str | None = Field(None, max_length=3)
    lookback_days: int = Field(90, ge=1, le=365)
    compliance: bool = False

    @field_validator("company", "ticker", "country")
    @classmethod
    def strip(cls, v: str | None) -> str | None:
        v = v.strip() if v else v
        return v or None


def _configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY and API_SECRET)


def _headers() -> dict[str, str]:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}


def _client_hash(request: Request) -> str:
    """Salted hash of the caller's IP (Vercel sets x-forwarded-for)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
    return hashlib.sha256(f"{API_SECRET}:{ip}".encode()).hexdigest()[:32]


async def _rpc(client: httpx.AsyncClient, fn: str, args: dict) -> httpx.Response:
    return await client.post(f"{SUPABASE_URL}/rest/v1/rpc/{fn}", headers=_headers(), json=args)


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "configured": _configured(),
        "llm": bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GROQ_API_KEY")),
        "daily_limit": PER_VISITOR_DAILY,
    }


def _install_shared_llm_cache() -> None:
    """LLM replies cached in Supabase, so identical requests read the same text on every instance."""
    if not _configured():
        return
    from src.agents.signal_agent import set_shared_llm_cache

    def get(key: str):
        r = httpx.post(f"{SUPABASE_URL}/rest/v1/rpc/llm_cache_get", headers=_headers(),
                       json={"secret": API_SECRET, "p_key": key}, timeout=10)
        return r.json() if r.status_code == 200 else None

    def put(key: str, text: str) -> None:
        httpx.post(f"{SUPABASE_URL}/rest/v1/rpc/llm_cache_put", headers=_headers(),
                   json={"secret": API_SECRET, "p_key": key, "p_text": text}, timeout=10)

    set_shared_llm_cache(get, put)


_install_shared_llm_cache()

from src.hosted_market import router as market_router  # noqa: E402

app.include_router(market_router)


async def _refresh_outcome_stats(client: httpx.AsyncClient) -> None:
    """Live outcome counts and observations for calibration, refreshed at most hourly per instance."""
    from src.hosted_market import refresh_live
    await refresh_live(client)


@app.post("/api/analyse")
async def analyse(body: AnalyseBody, request: Request) -> dict:
    if not _configured():
        raise HTTPException(503, "The API is not configured.")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await _rpc(client, "start_run", {
            "secret": API_SECRET, "p_client_hash": _client_hash(request),
            "p_company": body.company, "p_ticker": body.ticker,
            "per_client_daily": PER_VISITOR_DAILY, "global_daily": GLOBAL_DAILY,
        })
    if resp.status_code != 200:
        message = resp.text
        if "client_limit" in message:
            raise HTTPException(429, f"You have run {PER_VISITOR_DAILY} analyses today. The limit resets at 00:00 UTC.")
        if "global_limit" in message:
            raise HTTPException(429, "The free service has reached today's capacity. Try again tomorrow.")
        log.error("start_run failed: %s %s", resp.status_code, message[:300])
        raise HTTPException(503, "The service is busy. Try again shortly.")
    run_id = int(resp.json())
    async with httpx.AsyncClient(timeout=10) as client:
        await _refresh_outcome_stats(client)

    from src.agents.graph import run_analysis
    from src.schemas.models import AnalysisRequest
    from src.utils.formatter import brief_to_markdown

    try:
        request_model = AnalysisRequest(company_name=body.company, ticker=body.ticker, country=body.country,
                                        lookback_days=body.lookback_days)
    except ValueError as e:
        async with httpx.AsyncClient(timeout=15) as client:
            await _rpc(client, "fail_run", {"secret": API_SECRET, "p_run_id": run_id})
        raise HTTPException(422, str(e).splitlines()[-1][:200])
    try:
        brief = await run_analysis(request_model, compliance_mode=body.compliance)
    except Exception:
        log.exception("analysis failed for %r", body.company)
        async with httpx.AsyncClient(timeout=15) as client:
            await _rpc(client, "fail_run", {"secret": API_SECRET, "p_run_id": run_id})
        raise HTTPException(502, "The analysis failed. The data sources may be unavailable; try again in a minute.")

    brief_json = json.loads(brief.model_dump_json())
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await _rpc(client, "finish_run", {
            "secret": API_SECRET, "p_run_id": run_id,
            "p_company": brief.company_name, "p_ticker": body.ticker,
            "p_severity": brief_json.get("overall_severity"),
            "p_signal_count": len(brief.detected_signals),
            "p_llm_used": "LLM unavailable" not in (brief_json.get("analyst_model") or ""),
            "p_brief": brief_json, "p_markdown": brief_to_markdown(brief),
        })
    if resp.status_code != 200:
        log.error("finish_run failed: %s %s", resp.status_code, resp.text[:300])
        raise HTTPException(502, "The brief was generated but could not be saved.")
    return {
        "id": resp.json(), "company": brief.company_name, "ticker": body.ticker,
        "severity": brief_json.get("overall_severity"), "signal_count": len(brief.detected_signals),
    }


@app.get("/api/briefs/{brief_id}")
async def get_brief(brief_id: str) -> dict:
    try:
        uuid.UUID(brief_id)
    except ValueError:
        raise HTTPException(404, "Brief not found.")
    if not _configured():
        raise HTTPException(503, "The API is not configured.")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await _rpc(client, "get_brief", {"p_id": brief_id})
    rows = resp.json() if resp.status_code == 200 else []
    if not rows:
        raise HTTPException(404, "Brief not found.")
    return rows[0]


def _label_brief(row: dict, today: date) -> tuple[int, list[dict], list[dict]]:
    """Outcomes for one stored brief's signals, plus ground truth for its company."""
    from src.engines.outcome_labeller import CONFIRMATION_WINDOW_DAYS, fetch_events, ground_truth, label_prediction
    from src.schemas.models import SignalType

    created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")).astimezone(timezone.utc).date()
    stage = 2 if (today - created).days >= CONFIRMATION_WINDOW_DAYS + 5 else 1
    ticker = row.get("ticker")
    events = fetch_events(row["company"], ticker, created, today)
    outcomes = []
    for sig in (row.get("brief") or {}).get("detected_signals", []):
        alpha = sig.get("alpha_score") or {}
        try:
            signal_type = SignalType(sig["signal_type"])
        except (KeyError, ValueError):
            continue
        o = label_prediction(
            company_name=row["company"], ticker=ticker, signal_type=signal_type,
            severity=sig.get("severity", "low"), detection_date=created, alpha_score=alpha.get("score"),
            expected_direction=alpha.get("expected_direction"),
            expected_low=alpha.get("expected_magnitude_pct_low"),
            expected_high=alpha.get("expected_magnitude_pct_high"),
            events=events, today=today,
        )
        if o:
            outcomes.append(o)
    truth = ground_truth(row["company"], events, created, today) if events else []
    return stage, outcomes, truth


@app.get("/api/cron/label")
async def cron_label(request: Request) -> dict:
    """Daily: label due briefs (price reaction at 12+ days, confirmation at 95+)."""
    if not CRON_SECRET or request.headers.get("authorization") != f"Bearer {CRON_SECRET}":
        raise HTTPException(401, "Unauthorized")
    if not _configured():
        raise HTTPException(503, "The API is not configured.")
    deadline = time.monotonic() + 240
    today = datetime.now(timezone.utc).date()
    done = outcomes_written = 0
    from src.tools.african_prices import set_snapshot, snapshot_rows
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Snapshot today's NGX / NSE closes: the only way to build their price history.
        try:
            price_rows = await run_in_threadpool(snapshot_rows)
            r = await _rpc(client, "save_prices", {"secret": API_SECRET, "p_rows": price_rows})
            prices_saved = int(r.json()) if r.status_code == 200 else 0
        except Exception:
            log.exception("price snapshot failed")
            prices_saved = 0
        # 2. Price history for labelling African briefs.
        r = await _rpc(client, "get_prices", {"secret": API_SECRET, "p_since": (today - timedelta(days=140)).isoformat()})
        set_snapshot(r.json() if r.status_code == 200 else {})
        resp = await _rpc(client, "briefs_to_label", {"secret": API_SECRET, "max_n": 60})
        rows = resp.json() if resp.status_code == 200 else []
        for row in rows:
            if time.monotonic() > deadline:
                break
            try:
                stage, outcomes, truth = await run_in_threadpool(_label_brief, row, today)
            except Exception:
                log.exception("labelling failed for brief %s", row.get("id"))
                continue
            r = await _rpc(client, "save_labels", {
                "secret": API_SECRET, "p_brief_id": row["id"], "p_stage": stage,
                "p_outcomes": outcomes, "p_events": truth,
            })
            if r.status_code == 200:
                done += 1
                outcomes_written += len(outcomes)
    set_snapshot(None)
    from src.hosted_market import refresh_live
    async with httpx.AsyncClient(timeout=30) as client:
        await refresh_live(client, force=True)
    return {"prices_saved": prices_saved, "due": len(rows), "labelled": done, "outcomes": outcomes_written}
