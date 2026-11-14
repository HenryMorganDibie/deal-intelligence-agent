"""
Visible deal and event pages through Vercel's CDN, so cold API instances stop reading the database.

A cold API instance used to download every visible row from Supabase: about 90 full loads a day, most of the
database's egress. Each page is now fetched from a URL that names the store version and carries a signature only
the server can make; the CDN keeps each version's pages for a day, so the database is read once per change of data
(a handful a day). The URL is answered by its own small function (api/visible_page.py): a request from the main
API back to itself would queue behind the busy instance that made it.

This module stays light (no app imports) because that function loads it on every cold start.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional

import httpx

PATH = "/api/internal/visible-page"
SNAPSHOT_PATH = "/api/internal/market-snapshot-page"
SNAPSHOT_KINDS = ("quotes", "indices", "fx", "intraday", "instruments")
_BACKOFF = 3600            # after a failure this instance reads the database directly for an hour
_failed_at = 0.0


def available() -> bool:
    return bool(base()) and time.monotonic() - _failed_at > _BACKOFF if _failed_at else bool(base())


def failed() -> None:
    global _failed_at
    _failed_at = time.monotonic()


def base() -> str:
    explicit = os.environ.get("DATA_CDN_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL", "").strip()
    return f"https://{host}" if host and os.environ.get("VERCEL_ENV") == "production" else ""


def version_key(version: Optional[dict]) -> Optional[str]:
    """The store version as a URL-safe key, or None when it is unknown."""
    if not isinstance(version, dict) or version.get("changed") is None:
        return None
    return f"{version.get('count')}-{version.get('changed')}"


def day_key(now: Optional[float] = None) -> str:
    """Today's key (UTC). Pages cached under it hold the data as of the first read that day; a reader patches them
    with the rows changed since midnight, so the database is read in full about once a day rather than once per
    write (see hosted_market._load_visible)."""
    return "d" + time.strftime("%Y-%m-%d", time.gmtime(now))


def day_start_iso(now: Optional[float] = None) -> str:
    """Midnight UTC of today, less ten minutes of margin, as the change-feed watermark for day-keyed pages."""
    import calendar
    t = time.gmtime(now)
    start = calendar.timegm((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0)) - 600
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start))


def hour_key(now: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%dT%H", time.gmtime(now))


def snapshot_signature(secret: str, kind: str, bucket: str) -> str:
    return hmac.new(secret.encode(), f"snapshot|{kind}|{bucket}".encode(), hashlib.sha256).hexdigest()[:40]


def fetch_snapshot(secret: str, kind: str) -> httpx.Response:
    """The latest market snapshot rows of a kind, through the CDN: one database read per kind per hour."""
    bucket = hour_key()
    return httpx.get(f"{base()}{SNAPSHOT_PATH}", timeout=httpx.Timeout(15, connect=3),
                     params={"kind": kind, "b": bucket, "k": snapshot_signature(secret, kind, bucket)})


def signature(secret: str, kind: str, v: str, since: str, limit: int, after: Optional[str], max_id: Optional[str]) -> str:
    msg = "|".join([kind, v, since, str(limit), after or "", max_id or ""]).encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:40]


def page_params(secret: str, kind: str, v: str, args: dict) -> dict:
    """Query parameters for one page; `args` are list_visible_page's RPC arguments."""
    params = {"kind": kind, "v": v, "since": args["p_since"], "limit": args["p_limit"]}
    if args.get("p_after_id"):
        params["after"] = args["p_after_id"]
    if args.get("p_max_id"):
        params["max_id"] = args["p_max_id"]
    params["k"] = signature(secret, kind, v, params["since"], params["limit"], params.get("after"), params.get("max_id"))
    return params


def fetch(secret: str, kind: str, v: str, args: dict) -> httpx.Response:
    return httpx.get(f"{base()}{PATH}", params=page_params(secret, kind, v, args),
                     timeout=httpx.Timeout(15, connect=3))
