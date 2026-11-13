"""
The live results tracker: results entered by the service's operators as the electoral commission announces them,
served to the app (Pro and above) and to /v1. Each declared result is pushed to the results alerts.

Operators are the accounts listed in DEAL_INTEL_OPERATORS (account ids, comma-separated). Every saved result
keeps its earlier versions, so a correction never loses what was shown before.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from src import hosted_market as hm
from src.data import gm_2026 as gm
from src.data import live_elections as le
from src.engines import live_results as lr

log = logging.getLogger("deal_intel.election_live")
router = APIRouter()

ELECTIONS = {k: v["label"] for k, v in le.SPECS.items()}
PLANS = ("pro", "team", "institutional")
_TTL = 15
_cache: dict[str, tuple[float, list[dict]]] = {}


def operators() -> set[str]:
    return {x.strip() for x in os.environ.get("DEAL_INTEL_OPERATORS", "").split(",") if x.strip()}


def _check_election(election: str) -> None:
    if election not in ELECTIONS:
        raise HTTPException(400, "election must be one of: " + ", ".join(ELECTIONS) + ".")


def _load(election: str) -> list[dict]:
    hit = _cache.get(election)
    if hit and time.monotonic() - hit[0] < _TTL:
        return hit[1]
    r = hm._rpc_sync("live_result_list", {"p_election": election})
    if r.status_code != 200:
        log.error("live results read failed: %s %s", r.status_code, r.text[:200])
        raise HTTPException(503, "Live results are unavailable.")
    rows = r.json() or []
    _cache[election] = (time.monotonic(), rows)
    return rows


def results(election: str = gm.ELECTION) -> dict:
    _check_election(election)
    return lr.tally(_load(election), election)


def _story(row: dict, election: str) -> dict:
    """A declared result as an alert item."""
    spec = le.spec(election)
    ranked = sorted(((n, v) for n, v in row["votes"].items() if v), key=lambda kv: -kv[1]) or list(row["votes"].items())
    total = row.get("valid") or sum(row["votes"].values()) or 1
    lead, second = ranked[0], ranked[1] if len(ranked) > 1 else (None, 0)
    parties = {c["name"]: c.get("party") for c in lr.candidates(election)}
    label = lambda n: f"{n} ({parties[n]})" if parties.get(n) else n          # noqa: E731
    title = f"{row['unit']}: {label(lead[0])} wins with {lead[1]:,} votes ({lead[1] / total:.1%})"
    facts = [f"{label(n)} {v:,}" for n, v in ranked[:5]]
    if row.get("registered"):
        facts.append(f"turnout {row['votes_cast'] / row['registered']:.1%}")
    region = spec["areas"][row["area"]]["region"]
    facts.append(f"{region}, {spec['country']}")
    app = os.environ.get("DEAL_INTEL_APP_URL", "https://deal-intelligence.app").rstrip("/")
    return {"id": f"result:{election}:{row['unit']}:{row.get('versions', 1)}", "kind": "result",
            "election": election, "title": title, "url": f"{app}{spec['page']}",
            "day": datetime.now(timezone.utc).date().isoformat(), "states": [row["unit"], region],
            "facts_line": " · ".join(facts) + (f" · margin {lead[1] - second[1]:,}" if second[0] else "")}


def submit(operator: str, entry: dict, election: str = gm.ELECTION) -> dict:
    _check_election(election)
    if operator not in operators():
        raise HTTPException(403, "Only the service's operators enter results.")
    try:
        clean = lr.check(entry, election)
    except lr.ResultError as e:
        raise HTTPException(400, str(e))
    warnings = clean.pop("warnings")
    data = {**clean, "entered_by": operator, "entered_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    r = hm._rpc_sync("live_result_upsert", {"p_election": election, "p_area": clean["unit"], "p_data": data})
    if r.status_code != 200:
        raise HTTPException(503, f"The result could not be saved: {r.status_code}")
    saved = r.json() or data
    _cache.pop(election, None)
    alerts = None
    if clean["status"] == "declared":
        from src import election_alerts
        alerts = election_alerts.deliver([_story(saved, election)])
    return {"saved": saved, "warnings": warnings, "alerts": alerts}


def remove(operator: str, unit: str, election: str = gm.ELECTION) -> dict:
    _check_election(election)
    if operator not in operators():
        raise HTTPException(403, "Only the service's operators enter results.")
    con = le.spec(election)["unit"](unit)
    if not con:
        raise HTTPException(404, "No such " + le.spec(election)["unit_word"] + ".")
    r = hm._rpc_sync("live_result_delete", {"p_election": election, "p_area": con})
    _cache.pop(election, None)
    return {"deleted": bool(r.status_code == 200 and r.json())}


class ResultIn(BaseModel):
    unit: Optional[str] = Field(None, max_length=60)              # constituency or state
    constituency: Optional[str] = Field(None, max_length=60)
    votes: dict[str, int]
    votes_cast: Optional[int] = None
    rejected: Optional[int] = None
    accredited: Optional[int] = None
    registered: Optional[int] = None
    others_zero: bool = False
    status: str = "declared"
    source: Optional[str] = Field(None, max_length=300)


async def _me(request: Request) -> tuple[str, str]:
    from src import plans
    from src import request_identity as rid
    user = rid.account(request)
    if not user:
        raise HTTPException(401, "Sign in to see live results.")
    return user, str((await plans.limits(user)).get("plan") or "free")


@router.get("/api/elections/live")
async def app_results(request: Request, election: str = gm.ELECTION) -> dict:
    user, plan = await _me(request)
    is_operator = user in operators()
    if plan not in PLANS and not is_operator:
        raise HTTPException(403, "Live results come with the Pro plan and above.")
    out = await run_in_threadpool(results, election)
    return {**out, "operator": is_operator, "plan": plan, "rejected_ballots": le.spec(election)["rejected"],
            "ballot": [{k: c.get(k) for k in ("name", "party")} for c in lr.candidates(election)]}


@router.post("/api/elections/live")
async def app_submit(body: ResultIn, request: Request, election: str = gm.ELECTION) -> dict:
    user, _ = await _me(request)
    return await run_in_threadpool(submit, user, body.model_dump(), election)


@router.delete("/api/elections/live/{unit}")
async def app_remove(unit: str, request: Request, election: str = gm.ELECTION) -> dict:
    user, _ = await _me(request)
    return await run_in_threadpool(remove, user, unit, election)



@router.get("/api/cron/sheet-queue")
async def cron_sheet_queue(request: Request) -> dict:
    """Read queued result sheets within the day's budget (scheduled job; a no-op when the queue is empty)."""
    from src import election_results
    if not hm._authorized_cron(request):
        raise HTTPException(status_code=401, detail="Scheduled workflow authorization required.")
    return await run_in_threadpool(election_results.read_queue)
