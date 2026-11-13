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
KINDS = ("incidents", "news", "results")   # results: each constituency as it is declared (live-results elections)
# Elections an alert can follow: Nigeria and every country profile (src/data/election_profiles.py). Adding a
# profile adds it here, to the API and to the page, without changing alerts.
ELECTIONS = {"ng-2027": "Nigeria: 2027 general elections",
             **{k: p["label"] for k, p in __import__("src.data.election_profiles", fromlist=["PROFILES"]).PROFILES.items()}}
LIST_FILTERS = ("states", "lgas", "incident_types", "candidates", "gov_candidates", "senate_candidates", "people",
                "parties", "topics")
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
        raise HTTPException(400, "kind must be incidents, news or results.")
    election = raw.get("election", "ng-2027")
    if election not in ELECTIONS:
        raise HTTPException(400, "election must be one of " + ", ".join(ELECTIONS) + ".")
    if kind == "results":
        from src.election_live import ELECTIONS as LIVE
        if election not in LIVE:
            raise HTTPException(400, "Results alerts are for elections with live results: " + ", ".join(LIVE) + ".")
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
    if (story.get("kind") == "result") != (filters.get("kind") == "results"):
        return False                             # results go to results alerts only, and only results do
    if filters.get("kind") == "results":
        return all(_has(story, key, filters[key]) for key in ("states",) if filters.get(key))
    if filters.get("kind", "incidents") == "incidents":
        if not story.get("incident_types"):
            return False
        if SEVERITY.get(story.get("severity") or "low", 1) < SEVERITY.get(filters.get("min_severity") or "low", 1):
            return False
    return all(_has(story, key, filters[key]) for key in LIST_FILTERS if filters.get(key))


def _alert_item(story: dict) -> dict:
    if story.get("kind") == "result":            # a declared constituency: its own summary line
        return {"kind": "event", "id": story["id"], "title": story.get("title"), "url": story.get("url"),
                "day": story.get("day"), "facts_line": story.get("facts_line"), "severity": None,
                "incident_types": [], "states": story.get("states") or [], "lgas": [], "candidates": [],
                "parties": [], "outlets": ["IEC"]}
    where = ", ".join(story.get("lgas") or []) or ", ".join(story.get("states") or [])
    election = story.get("election", "ng-2027")
    if election != "ng-2027" and election in ELECTIONS:
        country = ELECTIONS[election].split(":")[0]
        where = f"{where}, {country}" if where else country
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


def unsubscribe_token(sub_id: str) -> str:
    import hashlib
    import hmac
    return hmac.new(hm.API_SECRET.encode(), f"election-alert:{sub_id}".encode(), hashlib.sha256).hexdigest()[:40]


def unsubscribe_link(sub_id: str) -> str:
    from src.engines import email_alerts
    return f"{email_alerts.api_base()}/api/elections/alerts/unsubscribe?id={sub_id}&token={unsubscribe_token(str(sub_id))}"


def render_email(sub: dict, stories: list[dict]) -> tuple[str, str, str]:
    """(subject, html, text): one email bundling the incidents this run found for the alert."""
    import html as _h
    from src.engines import email_alerts
    items = [_alert_item(s) for s in stories]
    n, name = len(items), sub.get("name") or "Election alert"
    high = sum(1 for i in items if i.get("severity") == "high")
    noun = {"incidents": "incident", "results": "result"}.get((sub.get("filters") or {}).get("kind", "incidents"), "story")
    subject = (f"{n} new election {noun}"
               f"{'s' if n != 1 else ''} · {name}" + (f" ({high} high severity)" if high else ""))
    unsub = unsubscribe_link(str(sub["id"]))
    app = __import__("os").environ.get("DEAL_INTEL_APP_URL", "https://deal-intelligence.app").rstrip("/")
    manage = f"{app}/app/watchlists"
    rows, text = [], [f"{name}: {n} new item{'s' if n != 1 else ''}", ""]
    for i in items[:25]:
        title = str(i.get("title") or "")
        url = i.get("url") if str(i.get("url") or "").startswith("https://") else None
        link = f'<a href="{_h.escape(url)}" style="color:#0f172a">{_h.escape(title)}</a>' if url else _h.escape(title)
        colour = {"high": "#b91c1c", "medium": "#b45309"}.get(i.get("severity") or "", "#64748b")
        rows.append(f'<tr><td style="padding:10px 0;border-bottom:1px solid #e5e7eb"><div style="font-weight:600">{link}</div>'
                    f'<div style="color:{colour};font-size:13px">{_h.escape(i["facts_line"])}</div></td></tr>')
        text += [f"- {title}", f"  {i['facts_line']}"] + ([f"  {url}"] if url else [])
    if n > 25:
        rows.append(f'<tr><td style="padding:10px 0;color:#64748b">and {n - 25} more</td></tr>')
        text.append(f"...and {n - 25} more.")
    text += ["", f"Manage your election alerts: {manage}", f"Stop this alert: {unsub}"]
    body = ('<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:600px;'
            'margin:0 auto;color:#0f172a;line-height:1.5">' + email_alerts.brand_header() +
            f'<p>Your election alert <strong>{_h.escape(name)}</strong> found {n} new item{"s" if n != 1 else ""}.</p>'
            f'<table role="presentation" style="width:100%;border-collapse:collapse">{"".join(rows)}</table>'
            f'<p style="margin:24px 0"><a href="{_h.escape(manage)}" style="background:#0f172a;color:#ffffff;'
            'padding:10px 16px;border-radius:6px;text-decoration:none;display:inline-block">Manage election alerts</a></p>'
            '<p style="color:#64748b;font-size:12px">You receive this because you set up this election alert in Deal '
            f'Intelligence. <a href="{_h.escape(unsub)}" style="color:#64748b">Stop this alert</a>.</p></div>')
    return subject, body, "\n".join(text)


async def _email(sub: dict, stories: list[dict]) -> bool:
    import httpx
    from src.engines import email_alerts
    r = hm._rpc_sync("election_alert_recipient", {"p_owner": sub["owner"]})
    to = r.json() if r.status_code == 200 else None
    if not to:
        return False
    subject, body, text = render_email(sub, stories)
    async with httpx.AsyncClient() as client:
        res = await email_alerts.send(client, to, subject, body, text, unsubscribe_link(str(sub["id"])),
                                      email_alerts.idempotency_key(f"election-{sub['id']}-{stories[0]['id']}", str(sub["id"])),
                                      tags=["election-alert"])
    return bool(res["sent"])


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
        # Email: one message bundling this run's items. Webhook: batches of up to MAX_SHOWN. A batch counts as
        # delivered if any of the alert's channels took it; otherwise its claim is released for the next run.
        emailed = await _email(sub, due) if sub.get("email") else False
        hook = sub.get("webhook_url")
        for i in range(0, len(due), chat_formats.MAX_SHOWN):
            batch = due[i:i + chat_formats.MAX_SHOWN]
            hooked = False
            if hook:
                result = await watch.deliver_webhook(hook, _payload(sub, batch), f"di-election-{sub['id']}-{batch[0]['id']}")
                hooked = bool(result["delivered"])
                if not hooked:
                    log.warning("election alert %s webhook not delivered: %s", sub["id"], result.get("error"))
            if hooked or emailed:
                sent += len(batch)
            else:
                failed += len(batch)
                hm._rpc_sync("election_alert_release", {"p_sub": sub["id"], "p_story_ids": [key[s["id"]] for s in batch]})
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

def create(owner: str, name: str, webhook_url: Optional[str], filters: Optional[dict], plan: str = "institutional",
           email: bool = False) -> dict:
    limit = allowance(plan)
    if limit == 0:
        raise HTTPException(403, "Election alerts start with the Pro plan.")
    url = (webhook_url or "").strip()
    if not url and not email:
        raise HTTPException(400, "Choose where to send the alert: your email, a webhook, or both.")
    if url and (not watch.valid_webhook(url) or not hm._public_host(url)):
        raise HTTPException(400, "webhook_url must be an https URL on a public host.")
    f = clean_filters(filters)
    if f["kind"] == "news" and plan not in FULL_FEATURES:
        raise HTTPException(403, "Alerts on all election coverage come with the Team plan; Pro alerts cover incidents.")
    r = hm._rpc_sync("election_alert_create_v3", {"p_owner": owner, "p_name": name.strip()[:80] or "Election alert",
                                                    "p_url": url or None, "p_filters": f, "p_max": limit, "p_email": bool(email)})
    if r.status_code != 200:
        if "email_not_confirmed" in r.text:
            raise HTTPException(403, "Confirm your account's email address first, then turn on email for alerts.")
        if "alert_limit" in r.text:
            raise HTTPException(400, f"Your {plan} plan allows {limit} election alert{'s' if limit != 1 else ''} at a time. "
                                     "Delete one, or upgrade for more.")
        raise HTTPException(503, "The alert could not be saved.")
    return _public(r.json())


def _public(row: dict) -> dict:
    out = {k: row.get(k) for k in ("id", "name", "filters", "active", "created_at", "sent") if k in row}
    url = row.get("webhook_url") or ""
    out["email"] = bool(row.get("email"))
    channels = ([chat_formats.LABELS[chat_formats.destination(url)]] if url else []) + (["Email"] if out["email"] else [])
    out["destination"] = " and ".join(channels)
    out["webhook"] = (url[:28] + "…" if len(url) > 28 else url) or None   # never echo the full secret URL
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
    if not subs[0].get("webhook_url"):
        ok = asyncio.run(_email(subs[0], [sample]))
        return {"delivered": ok, "status_code": None, "error": None if ok else "email_not_sent"}
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
    webhook_url: Optional[str] = Field(None, max_length=500)
    email: bool = False
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
    from src import election_feed
    return {"alerts": rows, "allowance": allowance(plan), "plan": plan, "full_features": plan in FULL_FEATURES,
            "elections": ELECTIONS, "election_details": election_feed.elections()}


@router.post("/api/elections/alerts")
async def app_create(body: AlertIn, request: Request) -> dict:
    owner, plan = await _me(request)
    row = await run_in_threadpool(create, owner, body.name, body.webhook_url, body.filters, plan, body.email)
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


@router.post("/api/elections/alerts/{alert_id}/active")
async def app_set_active(alert_id: str, request: Request) -> dict:
    """Resume (or pause) one of the account's alerts: {"active": true}."""
    owner, _ = await _me(request)
    body = await request.json()
    rows = await run_in_threadpool(list_for, owner)
    if not any(str(r["id"]) == _id(alert_id) for r in rows):
        raise HTTPException(404, "No such alert.")
    r = hm._rpc_sync("election_alert_set_active", {"p_id": alert_id, "p_active": bool(body.get("active"))})
    if r.status_code != 200 or not r.json():
        raise HTTPException(503, "The alert could not be updated.")
    return r.json()


def _unsub_page(title: str, message: str, form: str = ""):
    import html as _h
    from fastapi.responses import Response
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,'
            f'initial-scale=1"><meta name="robots" content="noindex"><title>{_h.escape(title)}</title></head>'
            '<body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:520px;margin:60px auto;padding:0 16px;'
            f'color:#0f172a"><h1 style="font-size:22px">{_h.escape(title)}</h1><p>{_h.escape(message)}</p>{form}</body></html>')
    return Response(page, media_type="text/html", headers={"Cache-Control": "no-store"})


def _check_unsub(alert_id: str, token: str) -> None:
    import hmac
    if not hmac.compare_digest(token or "", unsubscribe_token(_id(alert_id))):
        raise HTTPException(404, "This link is not valid.")


@router.get("/api/elections/alerts/unsubscribe")
async def unsubscribe_page(id: str = "", token: str = ""):
    """A confirmation page (email scanners open links; only the button stops the alert)."""
    import html as _h
    try:
        _check_unsub(id, token)
    except HTTPException:
        return _unsub_page("Link not valid", "This unsubscribe link is not valid.")
    form = (f'<form method="post"><input type="hidden" name="id" value="{_h.escape(id)}"><input type="hidden" '
            f'name="token" value="{_h.escape(token)}"><button type="submit" style="background:#0f172a;color:#fff;border:0;'
            'border-radius:6px;padding:10px 16px;font-size:15px;cursor:pointer">Stop this alert</button></form>')
    return _unsub_page("Stop this election alert?", "Emails and channel messages for this alert will stop. You can "
                       "turn it back on from the Alerts page.", form)


@router.post("/api/elections/alerts/unsubscribe")
async def unsubscribe(request: Request, id: str = "", token: str = ""):
    """One-click unsubscribe (also the List-Unsubscribe-Post target): pauses the alert."""
    if not id or not token:
        try:
            form = await request.form()
            id, token = str(form.get("id") or id), str(form.get("token") or token)
        except Exception:                             # noqa: BLE001
            pass
    try:
        _check_unsub(id, token)
    except HTTPException:
        return _unsub_page("Link not valid", "This unsubscribe link is not valid.")
    r = hm._rpc_sync("election_alert_set_active", {"p_id": id, "p_active": False})
    name = (r.json() or {}).get("name") if r.status_code == 200 else None
    return _unsub_page("Alert stopped", f"The election alert \"{name or 'this alert'}\" will send nothing more. "
                       "Turn it back on any time from the Alerts page.")
