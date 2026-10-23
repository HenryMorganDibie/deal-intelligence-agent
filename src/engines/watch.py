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

import asyncio
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

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


def _evidence(alert: dict, record: dict) -> dict:
    """Expose only source evidence already present in the underlying record."""
    sources = record.get("sources") if isinstance(record.get("sources"), list) else []
    valid_sources = [s for s in sources if isinstance(s, dict) and (s.get("url") or s.get("publisher"))]
    verification = record.get("verification")
    if isinstance(verification, dict):
        verification_tier = verification.get("tier") or verification.get("tier_label")
        independent_stories = verification.get("independent_stories")
    else:
        verification_tier = verification if isinstance(verification, str) else None
        independent_stories = record.get("independent_stories")
    if not isinstance(independent_stories, int) or independent_stories < 0:
        independent_stories = None
    if not valid_sources and (alert.get("url") or alert.get("publisher")):
        valid_sources = [{"publisher": alert.get("publisher"), "url": alert.get("url"),
                          "date": record.get("published") or record.get("day") or record.get("announced"),
                          "title": alert.get("title")}]
    return {
        **alert,
        "country": record.get("country"),
        "countries": record.get("countries") or ([record.get("country")] if record.get("country") else []),
        "source_count": len(valid_sources),
        "independent_stories": independent_stories,
        "verification": verification_tier,
        "sources": [
            {"publisher": s.get("publisher"), "url": s.get("url"), "date": s.get("date"), "title": s.get("title")}
            for s in valid_sources[:10]
        ],
    }


def _canonical_url(value: Optional[str]) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
            return None
        host = parsed.hostname.lower()
        if host.startswith("www."):
            host = host[4:]
        port = parsed.port
        netloc = host if port is None or (parsed.scheme.lower() == "https" and port == 443) or (parsed.scheme.lower() == "http" and port == 80) else f"{host}:{port}"
        query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                 if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source"}]
        return urlunsplit((parsed.scheme.lower(), netloc, parsed.path.rstrip("/") or "/", urlencode(sorted(query)), ""))
    except (ValueError, UnicodeError):
        return None


def _identity_keys(alert: dict) -> list[str]:
    """Conservative cross-source identities: canonical source URL or exact dated headline/type/country."""
    keys = []
    kind = alert.get("kind") or ""
    event_type = alert.get("signal_type") or alert.get("deal_type") or ""
    day = alert.get("day") or ""
    url = _canonical_url(alert.get("url"))
    if url and day and event_type:
        keys.append(f"url|{kind}|{event_type}|{day}|{url}")
    title = re.sub(r"[^a-z0-9]+", " ", (alert.get("title") or "").casefold()).strip()
    countries = sorted({str(x).upper() for x in (alert.get("countries") or []) if x})
    if title and day and event_type:
        keys.append(f"title|{kind}|{event_type}|{day}|{','.join(countries)}|{title}")
    return keys


def _merge_alert(prior: dict, incoming: dict) -> None:
    prior["duplicate_reports_merged"] = prior.get("duplicate_reports_merged", 0) + 1 + incoming.get("duplicate_reports_merged", 0)
    prior["why"] = sorted(set(prior.get("why", []) + incoming.get("why", [])))
    sources = prior.get("sources", []) + incoming.get("sources", [])
    unique = {}
    for source in sources:
        key = _canonical_url(source.get("url")) or source.get("url") or (source.get("publisher"), source.get("title"))
        unique[key] = source
    prior["sources"] = list(unique.values())[:10]
    prior["source_count"] = max(prior.get("source_count", 0), incoming.get("source_count", 0), len(unique))
    prior["countries"] = sorted({str(x).upper() for x in prior.get("countries", []) + incoming.get("countries", []) if x})
    if not prior.get("country"):
        prior["country"] = incoming.get("country")
    if not prior.get("url"):
        prior["url"] = incoming.get("url")
    if not prior.get("publisher"):
        prior["publisher"] = incoming.get("publisher")
    prior_stories = prior.get("independent_stories")
    incoming_stories = incoming.get("independent_stories")
    if isinstance(incoming_stories, int) and (not isinstance(prior_stories, int) or incoming_stories > prior_stories):
        prior["independent_stories"] = incoming_stories
    tiers = {prior.get("verification"), incoming.get("verification")}
    if "corroborated" in tiers:
        prior["verification"] = "corroborated"
    elif not prior.get("verification"):
        prior["verification"] = incoming.get("verification")


def matches(wl: dict, events: Iterable[dict], deals: Iterable[dict], since: Optional[str] = None,
            limit: int = 200) -> list[dict]:
    """Matched alerts, newest first; same-ID and conservative cross-source duplicates are merged."""
    by_key: dict[str, dict] = {}
    identity_to_key: dict[str, str] = {}
    for kind, records, date_key in (("event", events, "day"), ("deal", deals, "announced")):
        for record in records:
            day = record.get(date_key) or ""
            if since and day < since:
                continue
            reasons = matches_event(record, wl) if kind == "event" else matches_deal(record, wl)
            if not reasons:
                continue
            record_id = str(record.get("id") or "")
            if not record_id:
                continue
            key = f"{kind}:{record_id}"
            if kind == "event":
                alert = {"kind": kind, "id": record_id, "day": record.get("day"),
                         "title": record.get("headline") or "", "signal_type": record.get("signal_type"),
                         "url": record.get("url"), "publisher": record.get("publisher"), "why": reasons}
            else:
                sources = record.get("sources") if isinstance(record.get("sources"), list) else []
                primary = next((s for s in sources if isinstance(s, dict) and (s.get("url") or s.get("publisher"))), {})
                alert = {"kind": kind, "id": record_id, "day": record.get("announced"),
                         "title": record.get("headline") or "", "deal_type": record.get("deal_type"),
                         "amount_usd": record.get("amount_usd"), "url": primary.get("url"),
                         "publisher": primary.get("publisher"), "why": reasons}
            alert = _evidence(alert, record)
            alert["duplicate_reports_merged"] = 0
            identity_key = next((identity_to_key[k] for k in _identity_keys(alert) if k in identity_to_key), None)
            if key in by_key:
                _merge_alert(by_key[key], alert)
                for identity in _identity_keys(alert):
                    identity_to_key[identity] = key
                continue
            if identity_key and identity_key in by_key:
                _merge_alert(by_key[identity_key], alert)
                for identity in _identity_keys(alert):
                    identity_to_key[identity] = identity_key
                continue
            by_key[key] = alert
            for identity in _identity_keys(alert):
                identity_to_key[identity] = key
    out = list(by_key.values())
    out.sort(key=lambda a: a.get("day") or "", reverse=True)
    return out[:max(0, limit)]


def quality_metrics(alerts: list[dict]) -> dict:
    """Descriptive coverage metrics, not estimates of precision or factual accuracy."""
    count = len(alerts)
    with_source = sum(bool(a.get("url") or a.get("sources")) for a in alerts)
    with_independent_evidence = sum(
        isinstance(a.get("independent_stories"), int) and a["independent_stories"] >= 2 for a in alerts
    )
    known_verification = sum(bool(a.get("verification")) for a in alerts)
    duplicate_reports_merged = sum(max(0, int(a.get("duplicate_reports_merged") or 0)) for a in alerts)
    return {
        "alert_count": count,
        "duplicate_reports_merged": duplicate_reports_merged,
        "with_source_evidence": with_source,
        "source_evidence_coverage_pct": round(100 * with_source / count, 1) if count else None,
        "with_two_or_more_independent_stories": with_independent_evidence,
        "with_verification_label": known_verification,
        "accuracy_estimate": None,
        "note": "Coverage describes available metadata; it is not a measured accuracy or confidence score.",
    }


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




def alert_fingerprint(alert: dict) -> str:
    """Fingerprint meaningful alert facts so material corrections can be re-alerted."""
    source_count = alert.get("source_count")
    evidence_bucket = None
    if isinstance(source_count, int):
        evidence_bucket = "multiple" if source_count >= 2 else ("single" if source_count == 1 else "none")
    material = {
        "kind": alert.get("kind"),
        "title": alert.get("title"),
        "day": alert.get("day"),
        "type": alert.get("signal_type") or alert.get("deal_type"),
        "amount_usd": alert.get("amount_usd"),
        "verification": alert.get("verification"),
        "independent_stories": alert.get("independent_stories"),
        "evidence_bucket": evidence_bucket,
        "why": sorted(alert.get("why") or []),
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()




def delivery_due(frequency: str, now: Optional[datetime] = None) -> bool:
    """Daily webhooks run every ingestion; weekly digests run on Friday UTC."""
    if frequency == "daily":
        return True
    if frequency == "weekly":
        return (now or datetime.now(timezone.utc)).weekday() == 4
    return False



def delivery_idempotency_key(wl_id: str, alerts: list[dict]) -> str:
    """Stable key for the same watchlist/event batch across retries."""
    keys = sorted(f"{a.get('kind', '')}:{a.get('id', '')}:{alert_fingerprint(a)}" for a in alerts)
    digest = hashlib.sha256((str(wl_id) + "|" + "|".join(keys)).encode("utf-8")).hexdigest()
    return "deal-intel-" + digest[:40]


async def deliver_webhook(url: str, payload: dict, idempotency_key: str) -> dict:
    """Bounded retry for transient webhook errors; never follows redirects."""
    last_status = None
    last_error = None
    for attempt in range(1, 4):
        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=False) as client:
                response = await client.post(
                    url, json=payload,
                    headers={"Idempotency-Key": idempotency_key, "X-Deal-Intel-Delivery": idempotency_key},
                )
            last_status = response.status_code
            if 200 <= response.status_code < 300:
                return {"delivered": True, "attempts": attempt, "status_code": last_status, "error": None}
            last_error = f"http_{response.status_code}"
            if response.status_code < 500 and response.status_code not in (408, 425, 429):
                break
        except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
            last_error = type(exc).__name__
        if attempt < 3:
            await asyncio.sleep(0.5 * attempt)
    return {"delivered": False, "attempts": attempt, "status_code": last_status, "error": last_error}



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
