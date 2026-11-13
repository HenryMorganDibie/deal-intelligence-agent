"""
Election alerts: an account's subscriptions to election incidents or coverage, pushed to a webhook as stories arrive.

The hourly election-news job calls deliver() with the stories it stored or changed. A story is sent to a subscription
when it matches the subscription's filters, is dated no earlier than the subscription (no backlog flood on creation),
and has not been sent before: it is claimed in the database first and the claim released if delivery fails, so a
retry next hour sends it then. Delivery reuses the watchlist formats (Slack, Teams, Discord, Google Chat or JSON).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Iterable, Optional

from fastapi import HTTPException

from src import hosted_market as hm
from src.engines import chat_formats, watch

log = logging.getLogger("deal_intel.election_alerts")
SEVERITY = {"low": 1, "medium": 2, "high": 3}
KINDS = ("incidents", "news")
# Elections an alert can follow. One today; another country's election is added here (and its sources and tagging)
# without changing alerts, the API or the page.
ELECTIONS = {"ng-2027": "Nigeria: 2027 general elections"}
LIST_FILTERS = ("states", "lgas", "incident_types", "candidates", "parties", "topics")
DOCS = "https://deal-intelligence.app/developers#elections"
# How many election alerts an account can have at once; messages are not capped. Following all coverage (kind=news)
# and the recent-stories starter come with Team and above.
ALLOWANCE = {"free": 0, "pro": 2, "team": 5, "institutional": 25}
FULL_FEATURES = ("team", "institutional")


def allowance(plan: Optional[str]) -> int:
    return ALLOWANCE.get(plan or "free", 0)


def clean_filters(raw: Optional[dict]) -> dict:
    raw = raw or {}
    kind = raw.get("kind", "incidents")
    if kind not in KINDS:
        raise HTTPException(400, "kind must be incidents or news.")
    election = raw.get("election", "ng-2027")
    if election not in ELECTIONS:
        raise HTTPException(400, "election must be one of " + ", ".join(ELECTIONS) + ".")
    out: dict = {"kind": kind, "election": election}
    sev = raw.get("min_severity")
    if sev is not None:
        if sev not in SEVERITY:
            raise HTTPException(400, "min_severity must be low, medium or high.")
        out["min_severity"] = sev
    for key in LIST_FILTERS:
        vals = raw.get(key)
        if vals is None:
            continue
        if not isinstance(vals, list) or len(vals) > 40 or not all(isinstance(v, str) and 0 < len(v) <= 60 for v in vals):
            raise HTTPException(400, f"{key} must be a list of up to 40 names.")
        out[key] = [v.strip() for v in vals]
    return out


def _has(story: dict, field: str, wanted: list[str]) -> bool:
    have = [x.lower() for x in story.get(field) or []]
    if field == "lgas":
        have = [x.split(",")[0].strip() for x in have]
    return any(w.lower() in have or (field == "candidates" and any(w.lower() in h for h in have)) for w in wanted)


def matches(story: dict, filters: dict) -> bool:
    if filters.get("election", "ng-2027") != story.get("election", "ng-2027"):
        return False
    if filters.get("kind", "incidents") == "incidents":
        if not story.get("incident_types"):
            return False
        if SEVERITY.get(story.get("severity") or "low", 1) < SEVERITY.get(filters.get("min_severity") or "low", 1):
            return False
    return all(_has(story, key, filters[key]) for key in LIST_FILTERS if filters.get(key))


def _alert_item(story: dict) -> dict:
    where = ", ".join(story.get("lgas") or []) or ", ".join(story.get("states") or [])
    bits = []
    if story.get("severity"):
        bits.append(f"{story['severity'].capitalize()} severity: " + ", ".join(t.replace("_", " ") for t in story.get("incident_types") or []))
    if where:
        bits.append(where)
    outlets = story.get("outlets") or [story.get("outlet")]
    bits.append(", ".join(o for o in outlets if o))
    if story.get("day"):
        bits.append(story["day"])
    if (story.get("event_size") or 1) > 1:
        bits.append(f"{story['event_size']} reports of this incident")
    return {"kind": "event", "id": story["id"], "title": story.get("title"), "url": story.get("url"),
            "day": story.get("day"), "facts_line": " · ".join(b for b in bits if b),
            "severity": story.get("severity"), "incident_types": story.get("incident_types") or [],
            "states": story.get("states") or [], "lgas": story.get("lgas") or [], "candidates": story.get("candidates") or [],
            "parties": story.get("parties") or [], "outlets": outlets}


def _payload(sub: dict, stories: list[dict]) -> dict:
    items = [_alert_item(s) for s in stories]
    wl = {"id": sub["id"], "name": sub["name"], "button": "API documentation", "kind_label": "election alert"}
    generic = {"subscription": {"id": str(sub["id"]), "name": sub["name"]}, "type": "election_alert",
               "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stories": items}
    return chat_formats.payload(sub["webhook_url"], wl, items, DOCS, generic)


async def _send_all(subs: list[dict], stories: list[dict]) -> dict:
    sent = failed = 0
    for sub in subs:
        since = str(sub.get("created_at") or "")[:10]
        due = [s for s in stories if (s.get("day") or "") >= since and matches(s, sub.get("filters") or {})]
        if not due:
            continue
        # One message per incident: stories of an event already alerted are not sent again.
        key = {s["id"]: (f"event:{s['event_id']}" if s.get("event_id") else s["id"]) for s in due}
        firsts = list({key[s["id"]]: s for s in reversed(due)}.values())[::-1]
        r = hm._rpc_sync("election_alert_claim", {"p_sub": sub["id"], "p_story_ids": [key[s["id"]] for s in firsts]})
        claimed = set(r.json() or []) if r.status_code == 200 else set()
        due = [s for s in firsts if key[s["id"]] in claimed]
        if not due:
            continue
        for i in range(0, len(due), chat_formats.MAX_SHOWN):
            batch = due[i:i + chat_formats.MAX_SHOWN]
            result = await watch.deliver_webhook(sub["webhook_url"], _payload(sub, batch),
                                                 f"di-election-{sub['id']}-{batch[0]['id']}")
            if result["delivered"]:
                sent += len(batch)
            else:
                failed += len(batch)
                hm._rpc_sync("election_alert_release", {"p_sub": sub["id"], "p_story_ids": [key[s["id"]] for s in batch]})
                log.warning("election alert %s not delivered: %s", sub["id"], result.get("error"))
    return {"subscriptions": len(subs), "sent": sent, "failed": failed}


def deliver(stories: Iterable[dict]) -> dict:
    """Push matching stories to every active subscription. Never raises: alerts must not fail the collection job."""
    stories = [s for s in stories if s.get("id")]
    if not stories:
        return {"subscriptions": 0, "sent": 0, "failed": 0}
    try:
        r = hm._rpc_sync("election_alert_active", {})
        subs = (r.json() or []) if r.status_code == 200 else []
        return asyncio.run(_send_all(subs, stories)) if subs else {"subscriptions": 0, "sent": 0, "failed": 0}
    except Exception as e:                       # noqa: BLE001
        log.error("election alerts failed: %s", e)
        return {"error": type(e).__name__}


# ── Managing subscriptions (Institutional plan) ──

def create(owner: str, name: str, webhook_url: str, filters: Optional[dict], plan: str = "institutional") -> dict:
    limit = allowance(plan)
    if limit == 0:
        raise HTTPException(403, "Election alerts start with the Pro plan.")
    url = (webhook_url or "").strip()
    if not watch.valid_webhook(url) or not url or not hm._public_host(url):
        raise HTTPException(400, "webhook_url must be an https URL on a public host.")
    f = clean_filters(filters)
    if f["kind"] == "news" and plan not in FULL_FEATURES:
        raise HTTPException(403, "Alerts on all election coverage come with the Team plan; Pro alerts cover incidents.")
    r = hm._rpc_sync("election_alert_create_limited", {"p_owner": owner, "p_name": name.strip()[:80] or "Election alert",
                                                         "p_url": url, "p_filters": f, "p_max": limit})
    if r.status_code != 200:
        if "alert_limit" in r.text:
            raise HTTPException(400, f"Your {plan} plan allows {limit} election alert{'s' if limit != 1 else ''} at a time. "
                                     "Delete one, or upgrade for more.")
        raise HTTPException(503, "The alert could not be saved.")
    return _public(r.json())


def _public(row: dict) -> dict:
    out = {k: row.get(k) for k in ("id", "name", "filters", "active", "created_at", "sent") if k in row}
    url = row.get("webhook_url") or ""
    out["destination"] = chat_formats.LABELS[chat_formats.destination(url)]
    out["webhook"] = url[:28] + "…" if len(url) > 28 else url        # never echo the full secret URL
    return out


def list_for(owner: str) -> list[dict]:
    r = hm._rpc_sync("election_alert_list", {"p_owner": owner})
    if r.status_code != 200:
        raise HTTPException(503, "Alerts are unavailable.")
    return [_public(x) for x in r.json() or []]


def delete(owner: str, sub_id: str) -> dict:
    r = hm._rpc_sync("election_alert_delete", {"p_owner": owner, "p_id": sub_id})
    if r.status_code != 200 or not r.json():
        raise HTTPException(404, "No such alert.")
    return {"deleted": True}


def _sample_story() -> dict:
    return {"id": "test", "title": "Test alert: this is how an election incident will look", "url": DOCS,
            "day": datetime.now(timezone.utc).date().isoformat(), "severity": "high", "incident_types": ["violence"],
            "states": ["Lagos"], "lgas": ["Ikeja, Lagos"], "outlets": ["Deal Intelligence"]}


def test_url(webhook_url: str, name: str = "Election alert") -> dict:
    """Send a clearly marked sample to a webhook before it is saved."""
    url = (webhook_url or "").strip()
    if not url or not watch.valid_webhook(url) or not hm._public_host(url):
        raise HTTPException(400, "webhook_url must be an https URL on a public host.")
    sub = {"id": "test", "name": name.strip()[:80] or "Election alert", "webhook_url": url}
    result = asyncio.run(watch.deliver_webhook(url, _payload(sub, [_sample_story()]), "di-election-test-" + uuid.uuid4().hex[:16]))
    kind = chat_formats.destination(url)
    return {"delivered": bool(result["delivered"]), "destination": chat_formats.LABELS[kind],
            "status_code": result.get("status_code"), "error": result.get("error")}


def backfill(owner: str, sub_id: str, days: int = 3, plan: str = "institutional") -> dict:
    """Send the alert's matching stories from the last few days now (at most 7), so a new alert starts with recent
    context. Stories already sent to it are skipped, as always."""
    from datetime import timedelta
    from src import election_feed
    if plan not in FULL_FEATURES:
        raise HTTPException(403, "Starting an alert with recent incidents comes with the Team plan.")
    days = max(1, min(int(days), 7))
    r = hm._rpc_sync("election_alert_active", {})
    subs = [s for s in (r.json() or []) if str(s["id"]) == sub_id and str(s["owner"]) == owner] if r.status_code == 200 else []
    if not subs:
        raise HTTPException(404, "No such alert.")
    since = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    stories = sorted(election_feed._load(since), key=lambda s: s.get("day") or "")
    sub = dict(subs[0], created_at=since)
    return asyncio.run(_send_all([sub], stories)) | {"since": since}


def test(owner: str, sub_id: str) -> dict:
    """Send a clearly marked sample to the subscription's webhook."""
    r = hm._rpc_sync("election_alert_active", {})
    subs = [s for s in (r.json() or []) if str(s["id"]) == sub_id and str(s["owner"]) == owner] if r.status_code == 200 else []
    if not subs:
        raise HTTPException(404, "No such alert.")
    sample = _sample_story()
    result = asyncio.run(watch.deliver_webhook(subs[0]["webhook_url"], _payload(subs[0], [sample]),
                                               "di-election-test-" + uuid.uuid4().hex[:16]))
    return {"delivered": bool(result["delivered"]), "status_code": result.get("status_code"), "error": result.get("error")}


# ── For the web app: the signed-in account, passed by the site's proxy ──

from fastapi import APIRouter, Request                      # noqa: E402
from fastapi.concurrency import run_in_threadpool          # noqa: E402
from pydantic import BaseModel, Field                      # noqa: E402

router = APIRouter()
_tests: dict[str, list[float]] = {}


class AlertIn(BaseModel):
    name: str = Field("Election alert", max_length=80)
    webhook_url: str = Field(..., max_length=500)
    filters: Optional[dict] = None
    backfill_days: int = Field(0, ge=0, le=7)


class TestIn(BaseModel):
    webhook_url: str = Field(..., max_length=500)
    name: str = Field("Election alert", max_length=80)


def _id(alert_id: str) -> str:
    import re
    if not re.fullmatch(r"[0-9a-f-]{36}", alert_id or ""):
        raise HTTPException(400, "That is not an alert id.")
    return alert_id


async def _me(request: Request) -> tuple[str, str]:
    from src import plans
    from src import request_identity as rid
    user = rid.account(request)
    if not user:
        raise HTTPException(401, "Sign in to manage election alerts.")
    return user, str((await plans.limits(user)).get("plan") or "free")


@router.get("/api/elections/alerts")
async def app_list(request: Request) -> dict:
    owner, plan = await _me(request)
    rows = await run_in_threadpool(list_for, owner)
    return {"alerts": rows, "allowance": allowance(plan), "plan": plan, "full_features": plan in FULL_FEATURES,
            "elections": ELECTIONS}


@router.post("/api/elections/alerts")
async def app_create(body: AlertIn, request: Request) -> dict:
    owner, plan = await _me(request)
    row = await run_in_threadpool(create, owner, body.name, body.webhook_url, body.filters, plan)
    if body.backfill_days:
        row["backfill"] = await run_in_threadpool(backfill, owner, str(row["id"]), body.backfill_days, plan)
    return row


@router.post("/api/elections/alerts/test")
async def app_test_url(body: TestIn, request: Request) -> dict:
    owner, plan = await _me(request)
    if allowance(plan) == 0:
        raise HTTPException(403, "Election alerts start with the Pro plan.")
    import time
    now = time.monotonic()
    recent = [t for t in _tests.get(owner, []) if now - t < 60]
    if len(recent) >= 5:
        raise HTTPException(429, "Too many test messages. Wait a minute and try again.")
    _tests[owner] = recent + [now]
    return await run_in_threadpool(test_url, body.webhook_url, body.name)


@router.post("/api/elections/alerts/{alert_id}/test")
async def app_test_saved(alert_id: str, request: Request) -> dict:
    owner, _ = await _me(request)
    return await run_in_threadpool(test, owner, _id(alert_id))


@router.delete("/api/elections/alerts/{alert_id}")
async def app_delete(alert_id: str, request: Request) -> dict:
    owner, _ = await _me(request)
    return await run_in_threadpool(delete, owner, _id(alert_id))
