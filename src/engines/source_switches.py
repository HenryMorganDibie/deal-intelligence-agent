"""Sources the owner has switched off in admin (Settings → Sources), so a noisy or broken outlet stops being read
without a code change. Read at most every five minutes; when the store cannot be reached, nothing is switched off."""
from __future__ import annotations

import os
import time

import httpx

_TTL = 300.0
_cache: dict[str, tuple[float, frozenset[str]]] = {}


def disabled() -> frozenset[str]:
    hit = _cache.get("off")
    if hit and time.monotonic() - hit[0] < _TTL:
        return hit[1]
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
    off: frozenset[str] = frozenset()
    if url and key:
        try:
            r = httpx.post(f"{url}/rest/v1/rpc/disabled_sources", json={}, timeout=5,
                           headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            if r.status_code == 200 and isinstance(r.json(), list):
                off = frozenset(str(x) for x in r.json())
        except (httpx.HTTPError, ValueError):
            pass
    _cache["off"] = (time.monotonic(), off)
    return off


def is_on(name: str) -> bool:
    return name not in disabled()


def all_sources() -> list[dict]:
    """Every switchable source: the news outlets read for deals and events, and the private-capital pages."""
    from src.tools.africa_tool import AFRICAN_NEWS_FEEDS, PE_CAPITAL_SOURCES
    out = [{"name": name, "kind": "news", "url": url} for name, url in AFRICAN_NEWS_FEEDS.items()]
    seen = {s["name"] for s in out}
    out += [{"name": name, "kind": "private capital", "url": url} for name, url, _, _ in PE_CAPITAL_SOURCES
            if name not in seen]
    return out
