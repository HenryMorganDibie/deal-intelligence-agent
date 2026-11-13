"""
Opinion polls for an election: each published poll entered by an operator (pollster, fieldwork dates, sample, method,
candidates' shares, source), with a simple average across pollsters, and the recent stories the news monitor tagged
as polls, so a new poll is not missed.

The average takes each pollster's latest poll with fieldwork ending in the last 90 days and weights it by the square
root of its sample, so one large poll cannot drown the rest. It is an average of what was published, not a forecast.

Polls are kept in the live-results table under the key "polls:<election>", one row per poll, with every correction
kept, so they need no table of their own.
"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from src import hosted_market as hm
from src.data import live_elections as le

router = APIRouter()
WINDOW_DAYS = 90


def _key(election: str) -> str:
    if election not in le.SPECS:
        raise HTTPException(400, "election must be one of: " + ", ".join(le.SPECS) + ".")
    return f"polls:{election}"


def _ballot(election: str) -> dict[str, str]:
    """Names (and parties, surnames) a poll may use for each candidate."""
    out = {}
    for c in le.spec(election)["ballot"]():
        for k in (c["name"], c.get("party"), c["name"].split()[-1]):
            if k:
                out[k.lower()] = c["name"]
    return out


def check(entry: dict, election: str) -> dict:
    pollster = " ".join(str(entry.get("pollster") or "").split())[:80]
    if not pollster:
        raise HTTPException(400, "pollster is required.")
    try:
        start = date.fromisoformat(str(entry.get("fieldwork_start")))
        end = date.fromisoformat(str(entry.get("fieldwork_end")))
    except ValueError:
        raise HTTPException(400, "fieldwork_start and fieldwork_end must be dates, YYYY-MM-DD.")
    if start > end or end > datetime.now(timezone.utc).date():
        raise HTTPException(400, "Fieldwork must start before it ends, and end by today.")
    sample = entry.get("sample")
    if not isinstance(sample, int) or isinstance(sample, bool) or not 100 <= sample <= 1_000_000:
        raise HTTPException(400, "sample must be the number of respondents (100 or more).")
    names = _ballot(election)
    shares: dict[str, float] = {}
    for k, v in (entry.get("shares") or {}).items():
        cand = names.get(str(k).strip().lower())
        if not cand:
            raise HTTPException(400, f"Unknown candidate: {k!r}.")
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v <= 100:
            raise HTTPException(400, f"The share for {cand} must be a percentage from 0 to 100.")
        shares[cand] = float(v)
    if len(shares) < 2:
        raise HTTPException(400, "Enter the shares of at least two candidates.")
    undecided = entry.get("undecided")
    total = sum(shares.values()) + (undecided or 0)
    if total > 100.5:
        raise HTTPException(400, f"Shares add up to {total:.1f}%, more than 100.")
    source = str(entry.get("source") or "").strip()
    if not re.match(r"https://", source):
        raise HTTPException(400, "source must be an https link to the published poll.")
    pid = hashlib.sha256(f"{pollster.lower()}|{start}|{end}".encode()).hexdigest()[:16]
    return {"id": pid, "pollster": pollster, "fieldwork_start": str(start), "fieldwork_end": str(end), "sample": sample,
            "method": " ".join(str(entry.get("method") or "").split())[:60] or None, "shares": shares,
            "undecided": undecided, "source": source[:300]}


def _load(election: str) -> list[dict]:
    r = hm._rpc_sync("live_result_list", {"p_election": _key(election)})
    if r.status_code != 200:
        raise HTTPException(503, "Polls are unavailable.")
    return r.json() or []


def average(polls: list[dict], today: Optional[date] = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    recent = [p for p in polls if date.fromisoformat(p["fieldwork_end"]) >= today - timedelta(days=WINDOW_DAYS)]
    latest: dict[str, dict] = {}
    for p in sorted(recent, key=lambda p: p["fieldwork_end"]):
        latest[p["pollster"].lower()] = p
    used = list(latest.values())
    if not used:
        return {"polls_used": 0, "window_days": WINDOW_DAYS, "shares": []}
    names = {n for p in used for n in p["shares"]}
    out = []
    for n in names:
        having = [p for p in used if n in p["shares"]]
        w = sum(math.sqrt(p["sample"]) for p in having)
        out.append({"candidate": n, "share": round(sum(p["shares"][n] * math.sqrt(p["sample"]) for p in having) / w, 1),
                    "polls": len(having)})
    return {"polls_used": len(used), "pollsters": sorted(p["pollster"] for p in used), "window_days": WINDOW_DAYS,
            "shares": sorted(out, key=lambda x: -x["share"])}


def polls(election: str) -> dict:
    rows = sorted(_load(election), key=lambda p: p["fieldwork_end"], reverse=True)
    stories = []
    if election == "ng-2027":
        try:
            from src import election_feed
            since = (datetime.now(timezone.utc).date() - timedelta(days=30)).isoformat()
            stories = [{"title": s["title"], "url": s.get("url"), "day": s.get("day"), "outlets": s.get("outlets")}
                       for s in election_feed.search(topic="polls", since=since, limit=15)["stories"]]
        except HTTPException:
            stories = []
    return {"election": election, "polls": rows, "average": average(rows), "recent_poll_stories": stories,
            "method": __doc__.split("\n\n")[1].replace("\n", " ")}


def add(operator: str, entry: dict, election: str) -> dict:
    from src.election_live import operators
    if operator not in operators():
        raise HTTPException(403, "Only the service's operators enter polls.")
    clean = check(entry, election)
    r = hm._rpc_sync("live_result_upsert", {"p_election": _key(election), "p_area": clean["id"],
                                            "p_data": {**clean, "entered_by": operator}})
    if r.status_code != 200:
        raise HTTPException(503, "The poll could not be saved.")
    return r.json()


class PollIn(BaseModel):
    pollster: str = Field(..., max_length=80)
    fieldwork_start: str = Field(..., max_length=10)
    fieldwork_end: str = Field(..., max_length=10)
    sample: int
    method: Optional[str] = Field(None, max_length=60)
    shares: dict[str, float]
    undecided: Optional[float] = None
    source: str = Field(..., max_length=300)


@router.get("/api/elections/polls")
async def app_polls(request: Request, election: str = "ng-2027") -> dict:
    from src.election_live import PLANS, _me, operators
    user, plan = await _me(request)
    if plan not in PLANS and user not in operators():
        raise HTTPException(403, "Polls come with the Pro plan and above.")
    out = await run_in_threadpool(polls, election)
    return {**out, "operator": user in operators()}


@router.post("/api/elections/polls")
async def app_add_poll(body: PollIn, request: Request, election: str = "ng-2027") -> dict:
    from src.election_live import _me
    user, _ = await _me(request)
    return await run_in_threadpool(add, user, body.model_dump(), election)
