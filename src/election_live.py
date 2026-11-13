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
# What results alerts can follow: each live election, with the 28 governorship races as one.
ALERT_ELECTIONS = {v.get("alert_election", k): ("Nigeria: governorship elections, 6 February 2027" if v.get("alert_election") else v["label"])
                   for k, v in le.SPECS.items()}
PLANS = ("pro", "team", "institutional")
_TTL = 15
_cache: dict[str, tuple[float, list[dict]]] = {}


def operators() -> set[str]:
    return {x.strip() for x in os.environ.get("DEAL_INTEL_OPERATORS", "").split(",") if x.strip()}


def _check_election(election: str) -> None:
    if election not in ELECTIONS:
        raise HTTPException(400, "election must be one of: " + ", ".join(ELECTIONS) + ".")


def _load_store(store: str) -> list[dict]:
    hit = _cache.get(store)
    if hit and time.monotonic() - hit[0] < _TTL:
        return hit[1]
    r = hm._rpc_sync("live_result_list", {"p_election": store})
    if r.status_code != 200:
        log.error("live results read failed: %s %s", r.status_code, r.text[:200])
        raise HTTPException(503, "Live results are unavailable.")
    rows = r.json() or []
    _cache[store] = (time.monotonic(), rows)
    return rows


def _store(election: str) -> str:
    """Where an election's rows are kept: the 28 governorship races share one store, keyed "State|LGA"."""
    return le.spec(election).get("store", election)


def _area_key(election: str, unit: str) -> str:
    sp = le.spec(election)
    return f"{sp['state']}|{unit}" if sp.get("store") else unit


def _load(election: str) -> list[dict]:
    rows = _load_store(_store(election))
    state = le.spec(election).get("state")
    return [r for r in rows if r.get("state") == state] if le.spec(election).get("store") else rows


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
    sp = le.spec(election)
    data = {**clean, "entered_by": operator, "entered_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if sp.get("state"):
        data["state"] = sp["state"]
    r = hm._rpc_sync("live_result_upsert", {"p_election": _store(election), "p_area": _area_key(election, clean["unit"]),
                                            "p_data": data})
    if r.status_code != 200:
        raise HTTPException(503, f"The result could not be saved: {r.status_code}")
    saved = r.json() or data
    _cache.pop(_store(election), None)
    alerts = None
    if clean["status"] == "declared":
        from src import election_alerts
        if sp.get("store"):
            # Governorship: one alert when the state's last LGA is in, not one per LGA.
            story = _state_complete_story(election)
            alerts = election_alerts.deliver([story]) if story else None
        else:
            alerts = election_alerts.deliver([_story(saved, election)])
    return {"saved": saved, "warnings": warnings, "alerts": alerts}


def _state_complete_story(election: str) -> Optional[dict]:
    """The governorship result for a state once every LGA is in and declared."""
    t = results(election)
    nat = t["national"]
    if not nat["complete"] or nat["declared"] < nat["units"] or not nat["leader"]:
        return None
    sp = le.spec(election)
    lead = nat["results"][0]
    spread = (nat.get("spread") or {}).get(nat["leader"]) or {}
    facts = [f"{x['candidate']} ({x['party']}) {x['votes']:,}" for x in nat["results"][:4] if x["votes"]]
    facts.append(f"25% in {spread.get('states_at_25', 0)} of {spread.get('of', nat['units'])} LGAs"
                 + (" (met)" if spread.get("met") else " (not met)"))
    app = os.environ.get("DEAL_INTEL_APP_URL", "https://deal-intelligence.app").rstrip("/")
    return {"id": f"result:{sp['alert_election']}:{sp['state']}:complete", "kind": "result",
            "election": sp["alert_election"], "states": [sp["state"]],
            "title": f"{sp['state']} governorship: {lead['candidate']} ({lead['party']}) leads with all {nat['units']} LGAs in, "
                     f"{lead['votes']:,} votes ({lead['share']:.1%})",
            "url": f"{app}{sp['page']}", "day": datetime.now(timezone.utc).date().isoformat(),
            "facts_line": " · ".join(facts) + f" · margin {nat['margin']:,}"}


def governorship() -> dict:
    """Every governorship race at a glance: status, units in, leader and margin, and the 2023 winner."""
    from src.data import ng_governorship as gov
    rows = _load_store(gov.ELECTION)
    races = []
    for state, key in sorted(le.gov_elections().items()):
        t = lr.tally([r for r in rows if r.get("state") == state], key)
        nat = t["national"]
        lead = nat["results"][0] if nat["valid"] else None
        races.append({"state": state, "election": key, "lgas": nat["units"], "reported": nat["reported"],
                      "declared": nat["declared"], "complete": nat["complete"],
                      "leader": lead and {"name": lead["candidate"], "party": lead["party"], "share": lead["share"]},
                      "margin": nat["margin"], "spread": (nat.get("spread") or {}).get(nat["leader"]) if nat["leader"] else None,
                      "won_2023": gov.winner_2023(state), "candidates": len(lr.candidates(key))})
    return {"election": gov.ELECTION, "polling_day": gov.POLLING_DAY, "races": races,
            "reported_states": sum(1 for r in races if r["reported"]), "complete_states": sum(1 for r in races if r["complete"])}


def remove(operator: str, unit: str, election: str = gm.ELECTION) -> dict:
    _check_election(election)
    if operator not in operators():
        raise HTTPException(403, "Only the service's operators enter results.")
    con = le.spec(election)["unit"](unit)
    if not con:
        raise HTTPException(404, "No such " + le.spec(election)["unit_word"] + ".")
    r = hm._rpc_sync("live_result_delete", {"p_election": _store(election), "p_area": _area_key(election, con)})
    _cache.pop(_store(election), None)
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


@router.get("/api/elections/live/governorship")
async def app_governorship(request: Request) -> dict:
    user, plan = await _me(request)
    if plan not in PLANS and user not in operators():
        raise HTTPException(403, "Live results come with the Pro plan and above.")
    return {**await run_in_threadpool(governorship), "operator": user in operators()}


@router.get("/api/elections/live")
async def app_results(request: Request, election: str = gm.ELECTION) -> dict:
    user, plan = await _me(request)
    is_operator = user in operators()
    if plan not in PLANS and not is_operator:
        raise HTTPException(403, "Live results come with the Pro plan and above.")
    out = await run_in_threadpool(results, election)
    return {**out, "operator": is_operator, "plan": plan, "rejected_ballots": le.spec(election)["rejected"],
            "ballot": [{k: c.get(k) for k in ("name", "party", "running_mate")} for c in lr.candidates(election)]}


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



# ── Past results and sheet import, for the app's Nigeria page ──

@router.get("/api/elections/history")
async def app_history(request: Request, state: Optional[str] = None) -> dict:
    """Nigeria's presidential results by state, 2015 to 2023 (Pro and above)."""
    from src.data import ng_results_history as hist
    user, plan = await _me(request)
    if plan not in PLANS and user not in operators():
        raise HTTPException(403, "Past results come with the Pro plan and above.")
    if state:
        unit = le.spec("ng-2027")["unit"](state)
        if not unit:
            raise HTTPException(400, "state must be a Nigerian state or FCT.")
        return hist.history(unit)
    return {**hist.history(), "candidates": {str(k): v for k, v in hist.CANDIDATES.items()}}


class ImportIn(BaseModel):
    election: str = Field("presidential-2027", max_length=40)
    sheets: list[dict] = Field(..., min_length=1, max_length=2000)


@router.post("/api/elections/results/import")
async def app_import(body: ImportIn, request: Request) -> dict:
    """Queue polling-unit sheet links for reading (Institutional plan)."""
    from src import election_results
    user, plan = await _me(request)
    if plan != "institutional":
        raise HTTPException(403, "Importing result sheets is part of the Institutional plan.")
    return await run_in_threadpool(election_results.queue, user, body.election, body.sheets)


@router.get("/api/elections/results/queue")
async def app_queue(request: Request, election: str = "presidential-2027") -> dict:
    from src import election_results
    user, plan = await _me(request)
    if plan != "institutional":
        raise HTTPException(403, "Importing result sheets is part of the Institutional plan.")
    return {**await run_in_threadpool(election_results.queue_status, user, election), "plan": plan}
