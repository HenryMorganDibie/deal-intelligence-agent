"""
Watchlist alerts formatted for the chat tool behind a webhook URL.

The destination is recognised from the URL the user pasted, so there is nothing to choose or configure:
  * Slack incoming webhooks (hooks.slack.com)                     -> Block Kit message
  * Microsoft Teams Workflows / Power Automate and the older
    Office 365 connectors (*.powerplatform.com, *.logic.azure.com,
    *.webhook.office.com)                                         -> Adaptive Card
  * Discord webhooks (discord.com/api/webhooks)                    -> embeds
  * Google Chat spaces (chat.googleapis.com)                       -> text message
  * anything else (Zapier, Make, n8n, your own server)             -> the documented JSON payload

Each message shows at most MAX_SHOWN alerts and links to the watchlist for the rest, which keeps every
format inside its platform's size limits (Slack 50 blocks, Discord 10 embeds, Teams about 28 KB).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit

MAX_SHOWN = 8
BRAND = "Deal Intelligence"
ACCENT = 0x0D7A5F

_TEAMS_HOSTS = (".webhook.office.com", ".logic.azure.com", ".powerplatform.com", ".powerautomate.com")


def destination(url: Optional[str]) -> str:
    """slack, teams, discord, google_chat or json."""
    if not url:
        return "json"
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if host == "hooks.slack.com":
        return "slack"
    if host in ("discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com") \
            and parts.path.startswith("/api/webhooks/"):
        return "discord"
    if host == "chat.googleapis.com":
        return "google_chat"
    if host.endswith(_TEAMS_HOSTS):
        return "teams"
    return "json"


LABELS = {"slack": "Slack", "teams": "Microsoft Teams", "discord": "Discord", "google_chat": "Google Chat",
          "json": "JSON webhook"}


def _words(v: Optional[str]) -> str:
    return (v or "").replace("_", " ").strip().capitalize()


def _money(v) -> Optional[str]:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    for div, unit in ((1e9, "bn"), (1e6, "m"), (1e3, "k")):
        if n >= div:
            return f"${n / div:.1f}".rstrip("0").rstrip(".") + unit
    return f"${n:,.0f}"


def _day(v: Optional[str]) -> Optional[str]:
    try:
        return datetime.fromisoformat(str(v)[:10]).strftime("%-d %b %Y")
    except (TypeError, ValueError):
        return None


def facts(alert: dict) -> str:
    """One plain line under the headline: kind, type, amount, date, source."""
    kind = "Deal" if alert.get("kind") == "deal" else "Event"
    bits = [kind, _words(alert.get("deal_type") or alert.get("signal_type")) or None, _money(alert.get("amount_usd")),
            _day(alert.get("day")), alert.get("publisher")]
    if alert.get("change_type") == "updated":
        bits.append("updated")
    return " · ".join(b for b in bits if b)


def _title(alert: dict) -> str:
    return re.sub(r"\s+", " ", alert.get("title") or "Untitled").strip()[:240]


def summary_line(wl: dict, alerts: list[dict]) -> str:
    n = len(alerts)
    return f"{n} new {'alert' if n == 1 else 'alerts'} for {wl.get('name') or 'your watchlist'}"


# ── Slack ──
def _slack_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def slack(wl: dict, alerts: list[dict], link: str) -> dict:
    blocks: list[dict] = [{"type": "header", "text": {"type": "plain_text", "text": summary_line(wl, alerts)[:150]}}]
    for a in alerts[:MAX_SHOWN]:
        title = _slack_escape(_title(a))
        head = f"*<{a['url']}|{title}>*" if a.get("url") else f"*{title}*"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"{head}\n{_slack_escape(facts(a))}"}})
    more = len(alerts) - MAX_SHOWN
    blocks.append({"type": "actions", "elements": [{"type": "button", "url": link, "style": "primary",
                                                     "text": {"type": "plain_text", "text":
                                                              f"Open watchlist{f' ({more} more)' if more > 0 else ''}"}}]})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"{BRAND} watchlist alert"}]})
    return {"text": summary_line(wl, alerts), "blocks": blocks, "unfurl_links": False}


# ── Microsoft Teams ──
def teams(wl: dict, alerts: list[dict], link: str) -> dict:
    body: list[dict] = [{"type": "TextBlock", "text": summary_line(wl, alerts), "weight": "Bolder", "size": "Medium",
                         "wrap": True}]
    for a in alerts[:MAX_SHOWN]:
        title = _title(a).replace("[", "(").replace("]", ")")
        body.append({"type": "Container", "separator": True, "spacing": "Medium", "items": [
            {"type": "TextBlock", "text": f"[{title}]({a['url']})" if a.get("url") else title, "wrap": True,
             "weight": "Bolder"},
            {"type": "TextBlock", "text": facts(a), "wrap": True, "isSubtle": True, "spacing": "Small", "size": "Small"}]})
    more = len(alerts) - MAX_SHOWN
    card = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4",
            "body": body, "actions": [{"type": "Action.OpenUrl", "url": link,
                                       "title": f"Open watchlist{f' ({more} more)' if more > 0 else ''}"}]}
    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive",
                                                 "contentUrl": None, "content": card}]}


# ── Discord ──
def discord(wl: dict, alerts: list[dict], link: str) -> dict:
    embeds = []
    for a in alerts[:MAX_SHOWN]:
        e = {"title": _title(a)[:250], "description": facts(a)[:500], "color": ACCENT}
        if a.get("url"):
            e["url"] = a["url"]
        embeds.append(e)
    more = len(alerts) - MAX_SHOWN
    content = f"**{summary_line(wl, alerts)}**\n<{link}>" + (f" ({more} more)" if more > 0 else "")
    return {"username": BRAND, "content": content[:1900], "embeds": embeds, "allowed_mentions": {"parse": []}}


# ── Google Chat ──
def google_chat(wl: dict, alerts: list[dict], link: str) -> dict:
    lines = [f"*{summary_line(wl, alerts)}*"]
    for a in alerts[:MAX_SHOWN]:
        title = _title(a).replace("|", "/").replace("<", "(").replace(">", ")")
        lines.append(f"• <{a['url']}|{title}>" if a.get("url") else f"• {title}")
        lines.append(f"   {facts(a)}")
    more = len(alerts) - MAX_SHOWN
    lines.append(f"<{link}|Open watchlist{f' ({more} more)' if more > 0 else ''}>")
    return {"text": "\n".join(lines)}


def payload(url: Optional[str], wl: dict, alerts: list[dict], link: str, generic: dict) -> dict:
    """The body to POST to this webhook: a chat message, or the generic JSON payload otherwise."""
    kind = destination(url)
    if kind == "json":
        return generic
    return {"slack": slack, "teams": teams, "discord": discord, "google_chat": google_chat}[kind](wl, alerts, link)


def sample_alerts() -> list[dict]:
    """What a test message shows: clearly marked examples, never real records."""
    today = datetime.now(timezone.utc).date().isoformat()
    return [
        {"kind": "deal", "id": "test-1", "day": today, "title": "Test alert: this is how a new deal will look",
         "deal_type": "equity_funding", "amount_usd": 12_000_000, "publisher": BRAND,
         "url": "https://deal-intelligence.app/app/deals"},
        {"kind": "event", "id": "test-2", "day": today, "title": "Test alert: this is how a corporate event will look",
         "signal_type": "leadership_change", "publisher": BRAND, "url": "https://deal-intelligence.app/app"},
    ]
