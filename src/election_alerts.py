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
LIST_FILTERS = ("states", "lgas", "incident_types", "candidates", "parties", "topics")
DOCS = "https://deal-intelligence.app/developers#elections"


def clean_filters(raw: Optional[dict]) -> dict:
    raw = raw or {}
    kind = raw.get("kind", "incidents")
    if kind not in KINDS:
        raise HTTPException(400, "kind must be incidents or news.")
    out: dict = {"kind": kind}
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

def create(owner: str, name: str, webhook_url: str, filters: Optional[dict]) -> dict:
    url = (webhook_url or "").strip()
    if not watch.valid_webhook(url) or not url or not hm._public_host(url):
        raise HTTPException(400, "webhook_url must be an https URL on a public host.")
    f = clean_filters(filters)
    r = hm._rpc_sync("election_alert_create", {"p_owner": owner, "p_name": name.strip()[:80] or "Election alert",
                                                 "p_url": url, "p_filters": f})
    if r.status_code != 200:
        if "alert_limit" in r.text:
            raise HTTPException(400, "An account can have up to 10 election alerts.")
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


def backfill(owner: str, sub_id: str, days: int = 3) -> dict:
    """Send the alert's matching stories from the last few days now (at most 7), so a new alert starts with recent
    context. Stories already sent to it are skipped, as always."""
    from datetime import timedelta
    from src import election_feed
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
    sample = {"id": "test", "title": "Test alert: this is how an election incident will look",
              "url": DOCS, "day": datetime.now(timezone.utc).date().isoformat(), "severity": "high",
              "incident_types": ["violence"], "states": ["Lagos"], "lgas": ["Ikeja, Lagos"], "outlets": ["Deal Intelligence"]}
    result = asyncio.run(watch.deliver_webhook(subs[0]["webhook_url"], _payload(subs[0], [sample]),
                                               "di-election-test-" + uuid.uuid4().hex[:16]))
    return {"delivered": bool(result["delivered"]), "status_code": result.get("status_code"), "error": result.get("error")}
