"""Watchlist alert emails, sent through SendByte to each subscriber's verified account address.

Every message carries its subscriber's own unsubscribe link (also in the List-Unsubscribe headers, so mail clients
show a one-click button) and an idempotency key, so a retried run never sends the same batch twice.
"""
from __future__ import annotations

import hashlib
import html
import os
from typing import Optional

import httpx

SENDBYTE_URL = "https://api.sendbyte.africa/v1/emails"
MAX_ALERTS_IN_EMAIL = 25


def api_key() -> str:
    return os.environ.get("SENDBYTE_API_KEY", "").strip()


def sender() -> str:
    return os.environ.get("ALERT_EMAIL_FROM", "Deal Intelligence <alerts@deal-intelligence.app>").strip()


def reply_to() -> str:
    return os.environ.get("ALERT_EMAIL_REPLY_TO", "info@deal-intelligence.app").strip()


def api_base() -> str:
    return os.environ.get("DEAL_INTEL_API_PUBLIC_URL", "https://api.deal-intelligence.app").rstrip("/")


def unsubscribe_link(token: str) -> str:
    return f"{api_base()}/api/watchlists/email/unsubscribe?token={token}"


def _alert_line(alert: dict) -> tuple[str, str, Optional[str]]:
    """(headline, detail, source url) for one alert."""
    title = str(alert.get("title") or alert.get("headline") or alert.get("company") or "New match").strip()
    bits = [str(alert.get(k)) for k in ("day", "publisher", "signal_type", "deal_type") if alert.get(k)]
    if alert.get("change_type") == "updated":
        bits.append("updated")
    source = alert.get("url") or alert.get("source_url")
    return title, " · ".join(bits), source if isinstance(source, str) and source.startswith("https://") else None


def render(wl: dict, alerts: list[dict], watch_link: str, unsubscribe: str,
           display_name: Optional[str] = None) -> tuple[str, str, str]:
    """(subject, html, text) for one subscriber."""
    name = str(wl.get("name") or "Watchlist")
    count = len(alerts)
    subject = f"{count} new match{'es' if count != 1 else ''} on {name}"
    shown = alerts[:MAX_ALERTS_IN_EMAIL]
    more = count - len(shown)
    greeting = f"Hello {display_name}," if display_name else "Hello,"

    text_lines = [greeting, "", f"Your watchlist \"{name}\" has {count} new match{'es' if count != 1 else ''}:", ""]
    rows = []
    for alert in shown:
        title, detail, source = _alert_line(alert)
        text_lines.append(f"- {title}" + (f" ({detail})" if detail else ""))
        if source:
            text_lines.append(f"  {source}")
        link = f'<a href="{html.escape(source)}" style="color:#0f172a">{html.escape(title)}</a>' if source \
            else html.escape(title)
        rows.append(
            f'<tr><td style="padding:10px 0;border-bottom:1px solid #e5e7eb">'
            f'<div style="font-weight:600">{link}</div>'
            f'<div style="color:#64748b;font-size:13px">{html.escape(detail)}</div></td></tr>')
    if more > 0:
        text_lines.append(f"...and {more} more.")
        rows.append(f'<tr><td style="padding:10px 0;color:#64748b">and {more} more</td></tr>')
    text_lines += ["", f"Open the watchlist: {watch_link}", "",
                   "You receive this because you turned on email alerts for this watchlist.",
                   f"Stop these emails: {unsubscribe}"]

    body = (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:600px;'
        'margin:0 auto;color:#0f172a;line-height:1.5">'
        f'<p>{html.escape(greeting)}</p>'
        f'<p>Your watchlist <strong>{html.escape(name)}</strong> has {count} new match{"es" if count != 1 else ""}.</p>'
        f'<table role="presentation" style="width:100%;border-collapse:collapse">{"".join(rows)}</table>'
        f'<p style="margin:24px 0"><a href="{html.escape(watch_link)}" style="background:#0f172a;color:#ffffff;'
        'padding:10px 16px;border-radius:6px;text-decoration:none;display:inline-block">Open the watchlist</a></p>'
        '<p style="color:#64748b;font-size:12px">You receive this because you turned on email alerts for this '
        f'watchlist in Deal Intelligence. <a href="{html.escape(unsubscribe)}" style="color:#64748b">Stop these '
        'emails</a>.</p></div>')
    return subject, body, "\n".join(text_lines)


def idempotency_key(batch_key: str, token: str) -> str:
    """One key per subscriber per alert batch."""
    return "di-email-" + hashlib.sha256(f"{batch_key}|{token}".encode()).hexdigest()[:48]


async def send(client: httpx.AsyncClient, to: str, subject: str, html_body: str, text_body: str,
               unsubscribe: Optional[str], key: str, *, from_address: Optional[str] = None,
               tags: Optional[list[str]] = None) -> dict:
    """Send one message. Returns {"sent": bool, "status": int|None, "error": str|None}; never raises.
    Account emails (sign-up, password reset, security alerts) pass unsubscribe=None: they are transactional and
    carry no unsubscribe link."""
    if not api_key():
        return {"sent": False, "status": None, "error": "email_not_configured"}
    payload = {
        "from": from_address or sender(), "to": [to], "subject": subject, "html": html_body, "text": text_body,
        "reply_to": reply_to(), "tags": tags or ["watchlist-alert"], "idempotency_key": key,
        "tracking": {"opens": False, "clicks": False},
    }
    if unsubscribe:
        payload["headers"] = {"List-Unsubscribe": f"<{unsubscribe}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    try:
        response = await client.post(SENDBYTE_URL, json=payload,
                                     headers={"Authorization": f"Bearer {api_key()}"}, timeout=10)
    except httpx.HTTPError as exc:
        return {"sent": False, "status": None, "error": type(exc).__name__}
    if response.status_code in (200, 201):
        return {"sent": True, "status": response.status_code, "error": None}
    return {"sent": False, "status": response.status_code, "error": f"http_{response.status_code}"}
