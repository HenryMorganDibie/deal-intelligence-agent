"""
Requests from signed-in customers (Institutional access, coverage for another election), sent to the team's inbox
from the page itself. A mailto link depends on the visitor's device having a mail app, and in most desktop browsers
and in-app browsers it does nothing; this always works.

The message goes only to the team's own address. Its reply-to is the account's confirmed email, read on the server
(never taken from the form), so a reply reaches the right person and the form cannot be used to mail anyone else.
"""
from __future__ import annotations

import html
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
    "institutional": "Institutional access",
    "election_alerts": "Election alerts",
    "election_coverage": "Election coverage request",
}
_WINDOW, _MAX = 600, 3            # per account: three requests in ten minutes
_recent: dict[str, list[float]] = {}


class ContactIn(BaseModel):
    topic: Literal["institutional", "election_alerts", "election_coverage"] = "institutional"
    message: str = Field(..., min_length=10, max_length=4000)
    organisation: Optional[str] = Field(None, max_length=120)
    subject_detail: Optional[str] = Field(None, max_length=120)    # e.g. "Angola, August 2027"


def inbox() -> str:
    return email_alerts.reply_to()


def _account_email(owner: str) -> Optional[str]:
    r = hm._rpc_sync("election_alert_recipient", {"p_owner": owner})
    return (r.json() or None) if r.status_code == 200 else None


def render(topic: str, owner: str, email: Optional[str], plan: str, body: ContactIn) -> tuple[str, str, str]:
    title = TOPICS[topic] + (f": {body.subject_detail.strip()}" if body.subject_detail and body.subject_detail.strip() else "")
    subject = f"[Request] {title}"
    lines = [("From", email or "unconfirmed email"), ("Account", owner), ("Plan", plan)]
    if body.organisation and body.organisation.strip():
        lines.append(("Organisation", body.organisation.strip()))
    text = "\n".join(f"{k}: {v}" for k, v in lines) + "\n\n" + body.message.strip()
    rows = "".join(f"<tr><td style='color:#64748b;padding:2px 12px 2px 0'>{html.escape(k)}</td>"
                   f"<td>{html.escape(str(v))}</td></tr>" for k, v in lines)
    page = (f"<div style='font-family:system-ui,sans-serif;font-size:14px;color:#0f172a'>"
            f"<h2 style='font-size:16px'>{html.escape(title)}</h2><table>{rows}</table>"
            f"<p style='white-space:pre-wrap;margin-top:16px'>{html.escape(body.message.strip())}</p></div>")
    return subject, page, text


async def submit(owner: str, plan: str, body: ContactIn) -> dict:
    now = time.monotonic()
    recent = [t for t in _recent.get(owner, []) if now - t < _WINDOW]
    if len(recent) >= _MAX:
        raise HTTPException(429, "You have sent several requests in the last few minutes. We will reply to those first.")
    email = await run_in_threadpool(_account_email, owner)
    subject, page, text = render(body.topic, owner, email, plan, body)
    async with httpx.AsyncClient() as client:
        result = await email_alerts.send(client, inbox(), subject, page, text, None, "contact-" + uuid.uuid4().hex,
                                         tags=["contact-request"], reply_to_address=email)
    if not result["sent"]:
        raise HTTPException(503, "Your request could not be sent just now. Please try again in a few minutes.")
    _recent[owner] = recent + [now]
    return {"sent": True, "reply_to": email}


@router.post("/api/contact")
async def app_contact(body: ContactIn, request: Request) -> dict:
    from src import plans
    from src import request_identity as rid
    owner = rid.account(request)
    if not owner:
        raise HTTPException(401, "Sign in to send a request.")
    plan = str((await plans.limits(owner)).get("plan") or "free")
    return await submit(owner, plan, body)
