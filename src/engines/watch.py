"""
Corporate event monitoring and alerts.

A watchlist names companies, countries and event types. Every corporate event
and deal in the daily feed is matched against it:
  * a company matches when its name appears as a whole phrase in the headline
    or as a party to the deal;
  * a country matches when the event or deal is placed there;
  * event types, when given, restrict events to those signal types.

Alerts are delivered three ways, none of which needs an account: the
watchlist page, an RSS feed (any reader, Slack or email-by-RSS service can
subscribe), and an optional webhook that receives new matches as JSON after
each daily run.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Iterable, Optional

from src.engines.investors import parties


def _phrase(name: str) -> re.Pattern:
    words = [re.escape(w) for w in name.split() if w]
    return re.compile(r"(?<![\w])" + r"\s+".join(words) + r"(?![\w])", re.IGNORECASE)


def matches_event(event: dict, wl: dict) -> list[str]:
    """Reasons an event matches a watchlist (empty when it does not)."""
    types = set(wl.get("signal_types") or [])
    if types and event.get("signal_type") not in types:
        return []
    why = [f"company: {c}" for c in wl.get("companies") or [] if c.strip() and _phrase(c).search(event.get("headline", ""))]
    countries = set(wl.get("countries") or [])
    if countries & set(event.get("countries") or [event.get("country")]):
        why.append(f"country: {', '.join(sorted(countries & set(event.get('countries') or [event.get('country')])))}")
    return why


def matches_deal(deal: dict, wl: dict) -> list[str]:
    if not wl.get("include_deals", True):
        return []
    names = [n for n in [deal.get("target"), deal.get("buyer"), deal.get("seller"), *(deal.get("investors") or [])] if n]
    names += [n for n, _ in parties(deal)]
    why = []
    for c in wl.get("companies") or []:
        if c.strip() and (any(_phrase(c).search(n) for n in names) or _phrase(c).search(deal.get("headline") or "")):
            why.append(f"company: {c}")
    countries = set(wl.get("countries") or [])
    hit = countries & set(deal.get("countries") or [deal.get("country")])
    if hit:
        why.append(f"country: {', '.join(sorted(hit))}")
    return why


def matches(wl: dict, events: Iterable[dict], deals: Iterable[dict], since: Optional[str] = None,
            limit: int = 200) -> list[dict]:
    """Matched alerts, newest first: {kind, day, title, url, why, item}."""
    out = []
    for e in events:
        if since and (e.get("day") or "") < since:
            continue
        why = matches_event(e, wl)
        if why:
            out.append({"kind": "event", "id": e["id"], "day": e.get("day"), "title": e["headline"],
                        "signal_type": e.get("signal_type"), "url": e.get("url"), "publisher": e.get("publisher"),
                        "why": why})
    for d in deals:
        if since and (d.get("announced") or "") < since:
            continue
        why = matches_deal(d, wl)
        if why:
            src = (d.get("sources") or [{}])[0]
            out.append({"kind": "deal", "id": d["id"], "day": d.get("announced"), "title": d.get("headline"),
                        "deal_type": d.get("deal_type"), "amount_usd": d.get("amount_usd"), "url": src.get("url"),
                        "publisher": src.get("publisher"), "why": why})
    out.sort(key=lambda a: a.get("day") or "", reverse=True)
    return out[:limit]


def rss(wl: dict, alerts: list[dict], link: str) -> str:
    """RSS 2.0 feed of a watchlist's alerts."""
    def item(a: dict) -> str:
        try:
            pub = format_datetime(datetime.fromisoformat(a["day"]).replace(tzinfo=timezone.utc)) if a.get("day") else ""
        except ValueError:
            pub = ""
        label = (a.get("signal_type") or a.get("deal_type") or a["kind"]).replace("_", " ")
        desc = f"{label}. Matched on {'; '.join(a['why'])}." + (f" Source: {a['publisher']}." if a.get("publisher") else "")
        return (f"<item><title>{html.escape(a.get('title') or '')}</title>"
                f"<link>{html.escape(a.get('url') or link)}</link>"
                f"<guid isPermaLink=\"false\">{html.escape(a['kind'] + ':' + a['id'])}</guid>"
                f"<pubDate>{pub}</pubDate><description>{html.escape(desc)}</description></item>")
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?><rss version=\"2.0\"><channel>"
            f"<title>{html.escape(wl.get('name') or 'Watchlist')} | Deal Intelligence</title>"
            f"<link>{html.escape(link)}</link>"
            "<description>Corporate events and deals matching this watchlist.</description>"
            + "".join(item(a) for a in alerts[:100]) + "</channel></rss>")


def webhook_payload(wl: dict, alerts: list[dict], link: str) -> dict:
    return {"watchlist": {"id": str(wl.get("id")), "name": wl.get("name"), "url": link},
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "alerts": alerts}


_PRIVATE_HOST = re.compile(r"^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|0\.|169\.254\.|\[?::1|\[?f[cd])",
                           re.IGNORECASE)


def valid_webhook(url: Optional[str]) -> bool:
    """HTTPS to a public host only (no internal addresses)."""
    if not url:
        return True
    m = re.match(r"^https://([^/:?#]+)", url.strip())
    return bool(m) and not _PRIVATE_HOST.match(m.group(1)) and "." in m.group(1) and len(url) <= 500
