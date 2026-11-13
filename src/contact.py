"""
Requests sent to the team's inbox from the site itself (demonstrations, pilots, Institutional access, election
coverage). A mailto link depends on the visitor's device having a mail app, and in most desktop browsers and in-app
browsers it does nothing; this always works.

The message goes only to the team's own address, never anywhere the form names, so it cannot be used to mail
anyone else. Signed in, the reply-to is the account's confirmed email, read on the server. Signed out, the visitor
gives a name and email, and spam is kept out by a hidden field people never fill, a minimum time on the form,
three requests per address in ten minutes and a cap on public requests per hour.
"""
from __future__ import annotations

import html
import re
import time
import uuid
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from src import hosted_market as hm
from src.engines import email_alerts

router = APIRouter()

TOPICS = {
    "demo": "Demonstration request",
    "pilot": "Pilot discussion",
    "data": "Methodology or data question",
    "institutional": "Institutional access",
    "election_alerts": "Election alerts",
    "election_coverage": "Election coverage request",
}
_WINDOW, _MAX = 600, 3            # per account or address: three requests in ten minutes
_PUBLIC_HOURLY = 30               # signed-out requests per hour, per instance
_MIN_SECONDS = 3                  # a person takes longer than this to fill the form
_recent: dict[str, list[float]] = {}
_public: list[float] = []
_EMAIL = re.compile(r"^[^@\s<>\"']{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")


class ContactIn(BaseModel):
    topic: Literal["demo", "pilot", "data", "institutional", "election_alerts", "election_coverage"] = "institutional"
    message: str = Field(..., min_length=10, max_length=4000)
    organisation: Optional[str] = Field(None, max_length=120)
    subject_detail: Optional[str] = Field(None, max_length=120)    # e.g. "Angola, August 2027"
    name: Optional[str] = Field(None, max_length=100)               # signed out only
    email: Optional[str] = Field(None, max_length=254)              # signed out only
    website: Optional[str] = Field(None, max_length=200)            # hidden from people; bots fill it
    elapsed_ms: Optional[int] = Field(None, ge=0)                   # time the form was open


def inbox() -> str:
    return email_alerts.reply_to()


def _account_email(owner: str) -> Optional[str]:
    r = hm._rpc_sync("election_alert_recipient", {"p_owner": owner})
    return (r.json() or None) if r.status_code == 200 else None


def render(topic: str, owner: Optional[str], email: Optional[str], plan: str, body: ContactIn) -> tuple[str, str, str]:
    title = TOPICS[topic] + (f": {body.subject_detail.strip()}" if body.subject_detail and body.subject_detail.strip() else "")
    subject = f"[Request] {title}"
    if owner:
        lines = [("From", email or "unconfirmed email"), ("Account", owner), ("Plan", plan)]
    else:
        lines = [("From", f"{(body.name or '').strip()} <{email}>"), ("Account", "not signed in")]
    if body.organisation and body.organisation.strip():
        lines.append(("Organisation", body.organisation.strip()))
    text = "\n".join(f"{k}: {v}" for k, v in lines) + "\n\n" + body.message.strip()
    rows = "".join(f"<tr><td style='color:#64748b;padding:2px 12px 2px 0'>{html.escape(k)}</td>"
                   f"<td>{html.escape(str(v))}</td></tr>" for k, v in lines)
    page = (f"<div style='font-family:system-ui,sans-serif;font-size:14px;color:#0f172a'>"
            f"<h2 style='font-size:16px'>{html.escape(title)}</h2><table>{rows}</table>"
            f"<p style='white-space:pre-wrap;margin-top:16px'>{html.escape(body.message.strip())}</p></div>")
    return subject, page, text


def _visitor(body: ContactIn) -> str:
    """The signed-out visitor's email, checked; raises on anything a person would not send."""
    email = (body.email or "").strip()
    if not (body.name or "").strip():
        raise HTTPException(400, "Please add your name.")
    if not _EMAIL.match(email):
        raise HTTPException(400, "Please add a valid email address so we can reply.")
    return email


async def submit(owner: Optional[str], plan: str, body: ContactIn, ip: str = "unknown") -> dict:
    now = time.monotonic()
    key = owner or f"ip:{ip}"
    recent = [t for t in _recent.get(key, []) if now - t < _WINDOW]
    if len(recent) >= _MAX:
        raise HTTPException(429, "You have sent several requests in the last few minutes. We will reply to those first.")
    if owner:
        email = await run_in_threadpool(_account_email, owner)
    else:
        email = _visitor(body)
        if body.website or (body.elapsed_ms is not None and body.elapsed_ms < _MIN_SECONDS * 1000):
            _recent[key] = recent + [now]          # looks automated: accept quietly, send nothing
            return {"sent": True, "reply_to": email}
        _public[:] = [t for t in _public if now - t < 3600]
        if len(_public) >= _PUBLIC_HOURLY:
            raise HTTPException(429, "We are receiving a lot of requests just now. Please try again within the hour.")
    subject, page, text = render(body.topic, owner, email, plan, body)
    async with httpx.AsyncClient() as client:
        result = await email_alerts.send(client, inbox(), subject, page, text, None, "contact-" + uuid.uuid4().hex,
                                         tags=["contact-request"], reply_to_address=email)
    if not result["sent"]:
        raise HTTPException(503, "Your request could not be sent just now. Please try again in a few minutes.")
    _recent[key] = recent + [now]
    if not owner:
        _public.append(now)
    return {"sent": True, "reply_to": email}


@router.post("/api/contact")
async def app_contact(body: ContactIn, request: Request) -> dict:
    """A request from the site: signed in (reply to the account's email) or signed out (name and email given)."""
    from src import plans
    from src import request_identity as rid
    owner = rid.account(request)
    plan = str((await plans.limits(owner)).get("plan") or "free") if owner else "none"
    return await submit(owner, plan, body, rid.caller_ip(request))
