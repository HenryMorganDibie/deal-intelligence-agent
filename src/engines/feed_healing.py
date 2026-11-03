"""Self-healing outlet feeds.

Every outlet in AFRICAN_NEWS_FEEDS has a preferred feed. When it fails, returns nothing, or stops updating, the
outlet's replacement is found from the outlet itself, in this order:

  1. the feed its homepage advertises (<link rel="alternate" type="application/rss+xml">),
  2. the usual feed addresses on the same site (/feed/, /rss.xml, ...),
  3. Google News limited to the outlet's own site.

Every candidate belongs to the same outlet, so a replacement can never bring in another publisher's headlines.

Collection runs switch to a replacement on the spot (no headlines are lost while a feed is down). The daily
health job saves replacements to src/data/feed_overrides.json, so later runs go straight to them, and drops an
override as soon as the preferred feed works again.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, quote, urljoin, urlparse

import httpx

log = logging.getLogger(__name__)

OVERRIDES_PATH = Path(__file__).resolve().parents[1] / "data" / "feed_overrides.json"
COMMON_FEED_PATHS = ("/feed/", "/rss/", "/rss.xml", "/feed.xml", "/index.xml", "/atom.xml", "/rss",
                     "/arc/outboundfeeds/rss/", "/feeds/posts/default")
STALE_AFTER_DAYS = 45                 # a feed whose newest item is older than this has stopped updating
_ALTERNATE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)

# Country and language used for an outlet's Google News fallback (outlets already read through Google News carry
# theirs in the URL). Pan-African English outlets use the UK edition.
REGION: dict[str, tuple[str, str]] = {
    "BusinessDay Nigeria": ("NG", "en"), "TechCabal": ("NG", "en"), "Nairametrics": ("NG", "en"),
    "Vanguard Nigeria": ("NG", "en"), "ThisDay Nigeria": ("NG", "en"), "Premium Times Nigeria": ("NG", "en"),
    "Punch Nigeria": ("NG", "en"), "Channels TV Business": ("NG", "en"),
    "Moneyweb": ("ZA", "en"), "BusinessDay SA": ("ZA", "en"), "Daily Maverick Business": ("ZA", "en"),
    "IOL": ("ZA", "en"),
    "Nation Africa": ("KE", "en"), "The East African": ("KE", "en"), "Standard Media Kenya": ("KE", "en"),
    "Business Daily Africa": ("KE", "en"),
    "The Africa Report": ("GB", "en"), "African Business": ("GB", "en"), "Disrupt Africa": ("GB", "en"),
    "Ventureburn": ("ZA", "en"), "WeeTracker": ("GB", "en"),
    "Financial Afrik": ("SN", "fr"), "Jeune Afrique": ("FR", "fr"), "SenePlus": ("SN", "fr"),
    "BRVM Actualites": ("CI", "fr"),
    "Graphic Business Ghana": ("GH", "en"),
    "Daily News Egypt": ("EG", "en"), "Egypt Independent": ("EG", "en"),
    "Addis Fortune": ("ET", "en"), "The Reporter Ethiopia": ("ET", "en"),
    "Zimbabwe Independent": ("ZW", "en"), "Zambia Daily Mail": ("ZM", "en"),
}


def site_news_url(site: str, country: str, lang: str = "en", extra: str = "", window: str = "when:2d") -> str:
    query = quote(" ".join(part for part in (f"site:{site}", extra, window) if part))
    return f"https://news.google.com/rss/search?q={query}&hl={lang}-{country}&gl={country}&ceid={country}:{lang}"


def is_site_news(url: str) -> bool:
    return urlparse(url).netloc == "news.google.com"


def outlet_site(url: str) -> tuple[str, str, str, str]:
    """(site, country, lang, extra) recovered from a Google News site query, or ("", "", "", "") otherwise."""
    parsed = urlparse(url)
    if not is_site_news(url):
        return "", "", "", ""
    q = parse_qs(parsed.query)
    words = (q.get("q") or [""])[0].split()
    site = next((w[5:] for w in words if w.startswith("site:")), "")
    extra = " ".join(w for w in words if not w.startswith(("site:", "when:")))
    country = (q.get("gl") or ["GB"])[0]
    lang = (q.get("hl") or ["en"])[0].split("-")[0]
    return site, country, lang, extra


def load_overrides(path: Path = OVERRIDES_PATH) -> dict[str, dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if isinstance(v, dict) and str(v.get("url", "")).startswith("https://")}
    except (OSError, ValueError):
        return {}


def save_overrides(overrides: dict[str, dict], path: Path = OVERRIDES_PATH) -> None:
    path.write_text(json.dumps(dict(sorted(overrides.items())), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def effective_feeds(feeds: Optional[dict[str, str]] = None, overrides: Optional[dict[str, dict]] = None) -> dict[str, str]:
    """The feed to read for each outlet: its saved replacement if it has one, otherwise its preferred feed."""
    if feeds is None:
        from src.tools.africa_tool import AFRICAN_NEWS_FEEDS
        feeds = AFRICAN_NEWS_FEEDS
    overrides = load_overrides() if overrides is None else overrides
    return {name: (overrides.get(name) or {}).get("url") or url for name, url in feeds.items()}


def _host_root(host: str) -> str:
    """example.co.za for www.example.co.za; enough to keep candidates on the outlet's own site."""
    parts = host.lower().split(".")
    if parts and parts[0] == "www":
        parts = parts[1:]
    return ".".join(parts)


def _same_site(url: str, root: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host == root or host.endswith("." + root)


def _newest(items: list[dict]) -> Optional[date]:
    days = []
    for it in items:
        try:
            days.append(date.fromisoformat(str(it.get("date") or "")[:10]))
        except ValueError:
            continue
    return max(days) if days else None


async def probe(client: httpx.AsyncClient, url: str, require_fresh: bool = True) -> tuple[bool, list[dict], str]:
    """(usable, items, reason). Usable means the URL answers with feed items that are not all stale."""
    from src.engines.market_feed import parse_feed
    try:
        response = await client.get(url)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - any failure makes the candidate unusable
        status = getattr(getattr(exc, "response", None), "status_code", "")
        return False, [], f"{type(exc).__name__} {status}".strip()
    items = parse_feed(response.text, default_publisher="" if is_site_news(url) else "")
    if not items:
        return False, [], "no items"
    newest = _newest(items)
    if require_fresh and newest and newest < date.today() - timedelta(days=STALE_AFTER_DAYS):
        return False, items, f"stale since {newest.isoformat()}"
    return True, items, "ok"


async def candidates(client: httpx.AsyncClient, name: str, preferred: str) -> list[str]:
    """Replacement feeds for one outlet, most direct first."""
    site, country, lang, extra = outlet_site(preferred)
    if site:
        host = site.split("/", 1)[0]
    else:
        host = urlparse(preferred).netloc
        country, lang = REGION.get(name, ("GB", "en"))
    root = _host_root(host)
    home = f"https://{host}/"
    found: list[str] = []
    try:
        page = await client.get(home)
        if page.status_code == 200 and "html" in page.headers.get("content-type", ""):
            for tag in _ALTERNATE.findall(page.text[:200_000]):
                if re.search(r"rel=['\"]?alternate", tag, re.I) and re.search(r"(rss|atom)\+xml", tag, re.I):
                    href = re.search(r"href=['\"]([^'\"]+)['\"]", tag, re.I)
                    if href:
                        url = urljoin(home, href.group(1).strip())
                        if url.startswith("https://") and _same_site(url, root) and "comments" not in url:
                            found.append(url)
    except httpx.HTTPError:
        pass
    found += [urljoin(home, path) for path in COMMON_FEED_PATHS]
    found.append(site_news_url(site or root, country, lang, extra))
    out, seen = [], {preferred}
    for url in found:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


async def find_replacement(client: httpx.AsyncClient, name: str, preferred: str,
                           exclude: tuple[str, ...] = ()) -> tuple[Optional[str], list[dict]]:
    """The first working replacement for an outlet and the items it returned, or (None, [])."""
    for url in await candidates(client, name, preferred):
        if url in exclude:
            continue
        if is_site_news(url):
            # A quiet outlet can have nothing in two days; check a fortnight to confirm it is indexed at all.
            wide = url.replace("when%3A2d", "when%3A14d")
            ok, _, _ = await probe(client, wide, require_fresh=False)
            if ok:
                _, items, _ = await probe(client, url, require_fresh=False)
                return url, items
            continue
        ok, items, _ = await probe(client, url)
        if ok:
            return url, items
    return None, []


async def heal_all(feeds: Optional[dict[str, str]] = None, overrides: Optional[dict[str, dict]] = None,
                   concurrency: int = 6, timeout: float = 20
                   ) -> tuple[dict[str, dict], list[str], list[str], list[str]]:
    """Check every outlet and work out the overrides to keep.

    Returns (overrides, changes, unresolved, dormant): unresolved outlets cannot be reached at all; dormant ones
    answer but have published nothing recently anywhere, so there is nothing to replace."""
    if feeds is None:
        from src.tools.africa_tool import AFRICAN_NEWS_FEEDS
        feeds = AFRICAN_NEWS_FEEDS
    current = load_overrides() if overrides is None else dict(overrides)
    updated: dict[str, dict] = {}
    changes: list[str] = []
    unresolved: list[str] = []
    dormant: list[str] = []
    sem = asyncio.Semaphore(concurrency)
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) deal-intelligence-agent/1.0"}
    today = datetime.now(timezone.utc).date().isoformat()

    async def one(client: httpx.AsyncClient, name: str, preferred: str) -> None:
        async with sem:
            ok, items, reason = await probe(client, preferred, require_fresh=not is_site_news(preferred))
            if is_site_news(preferred) and not ok and reason == "no items":
                ok, _, _ = await probe(client, preferred.replace("when%3A2d", "when%3A14d"), require_fresh=False)
            if ok:
                if name in current:
                    changes.append(f"{name}: preferred feed works again, override removed")
                return
            saved = current.get(name)
            if saved:
                good, _, _ = await probe(client, saved["url"], require_fresh=not is_site_news(saved["url"]))
                if good or is_site_news(saved["url"]):
                    updated[name] = saved
                    return
            url, _ = await find_replacement(client, name, preferred, exclude=tuple(filter(None, [(saved or {}).get("url")])))
            if url:
                updated[name] = {"url": url, "since": today, "reason": f"preferred feed: {reason}"}
                changes.append(f"{name}: {reason}; now reading {url}")
            elif reason.startswith("stale since") or reason == "no items":
                dormant.append(f"{name}: {reason}; the outlet has published nothing recent anywhere")
            else:
                unresolved.append(f"{name}: {reason}; no working replacement found")

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        await asyncio.gather(*(one(client, n, u) for n, u in feeds.items()))
    return updated, sorted(changes), sorted(unresolved), sorted(dormant)
