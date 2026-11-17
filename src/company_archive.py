"""
A company's own pages from the Common Crawl archive, for sites that refuse automated readers.

Common Crawl is a public web archive whose crawler (CCBot) obeys robots.txt when it collects. When a company's
site answers us with a bot challenge, its About, Team and Leadership pages are looked up in the two latest crawls
and read from the archived copy, so the profile is built from the company's own words rather than only from what
others wrote about it. Each page keeps its original address and the date it was archived.

The owner's wishes are respected: the archive is used only when the site's robots.txt allows CCBot, or cannot be
read at all (the archive's crawler checked it when it collected the page); never when robots.txt forbids CCBot.

Best effort by design: the index is often slow or down, so lookups are exact addresses (not whole-site queries), a
few at a time, under a short overall deadline, and any failure simply yields no pages.
"""
from __future__ import annotations

import gzip
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from urllib import robotparser
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

INDEX = "https://index.commoncrawl.org"
DATA = "https://data.commoncrawl.org"
CRAWLS_FALLBACK = ("CC-MAIN-2026-43", "CC-MAIN-2026-39")
PATHS = ("", "about", "about-us", "who-we-are", "company", "our-team", "team", "leadership", "management",
         "board-of-directors")
DEADLINE_SECONDS = 10
USER_AGENT = "Mozilla/5.0 (compatible; DealIntelligence/1.0; +https://deal-intelligence.app)"

_crawls: tuple[float, tuple[str, ...]] | None = None


def latest_crawls(client: httpx.Client, n: int = 2) -> tuple[str, ...]:
    """The newest crawl ids, from the index's list (cached a day), or known recent ones if it cannot be read."""
    global _crawls
    if _crawls and time.monotonic() - _crawls[0] < 86400:
        return _crawls[1]
    try:
        r = client.get(f"{INDEX}/collinfo.json", timeout=6)
        ids = tuple(c["id"] for c in r.json()[:n]) if r.status_code == 200 else ()
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        ids = ()
    _crawls = (time.monotonic(), ids or CRAWLS_FALLBACK)
    return _crawls[1]


def ccbot_allowed(robots_txt: Optional[str], url: str) -> bool:
    """True when the archive may be used for this page: robots.txt allows CCBot, or was not readable (None)."""
    if robots_txt is None:
        return True
    rp = robotparser.RobotFileParser()
    rp.parse(robots_txt.splitlines())
    return rp.can_fetch("CCBot", url)


def parse_record(gz: bytes) -> Optional[tuple[str, str]]:
    """(archived date, HTML) from one gzipped WARC response record; None if it is not a 200 HTML response."""
    try:
        raw = gzip.decompress(gz)
    except (OSError, EOFError):
        return None
    parts = raw.split(b"\r\n\r\n", 2)
    if len(parts) < 3:
        return None
    warc_head, http_head, body = parts
    if b" 200 " not in http_head.split(b"\r\n", 1)[0] or b"html" not in http_head.lower():
        return None
    date = ""
    for line in warc_head.split(b"\r\n"):
        if line.lower().startswith(b"warc-date:"):
            date = line.split(b":", 1)[1].strip().decode("ascii", "ignore")[:10]
    return date, body.decode("utf-8", "replace")


def _lookup(client: httpx.Client, crawl: str, url: str) -> Optional[dict]:
    try:
        r = client.get(f"{INDEX}/{crawl}-index", params={"url": url, "output": "json"}, timeout=4)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    import json
    rows = []
    for line in r.text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("status") == "200" and "html" in (row.get("mime") or row.get("mime-detected") or ""):
            rows.append(row)
    return rows[-1] if rows else None                   # the latest capture in this crawl


def _fetch(client: httpx.Client, row: dict) -> Optional[tuple[str, str]]:
    try:
        offset, length = int(row["offset"]), int(row["length"])
        r = client.get(f"{DATA}/{row['filename']}", headers={"Range": f"bytes={offset}-{offset + length - 1}"}, timeout=5)
    except (httpx.HTTPError, KeyError, ValueError):
        return None
    return parse_record(r.content) if r.status_code in (200, 206) else None


def archived_pages(site: str, robots_txt: Optional[str], client: Optional[httpx.Client] = None,
                   deadline: float = DEADLINE_SECONDS) -> list[dict]:
    """The site's About, Team and Leadership pages from the archive, as pages the site reader can read."""
    from src.company_live import _Page
    host = urlparse(site).netloc or site
    bare = host[4:] if host.startswith("www.") else host
    if not ccbot_allowed(robots_txt, f"https://{bare}/about"):
        return []
    own = client is None
    c = client or httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    start = time.monotonic()
    pages: list[dict] = []
    try:
        crawls = latest_crawls(c)
        targets = [f"{h}/{p}" for p in PATHS for h in dict.fromkeys((bare, f"www.{bare}"))]

        def one(target: str) -> Optional[dict]:
            for crawl in crawls:
                if time.monotonic() - start > deadline:
                    return None
                row = _lookup(c, crawl, target)
                if row:
                    got = _fetch(c, row)
                    if got:
                        archived_at, html = got
                        page = _Page(row.get("url") or f"https://{target}")
                        try:
                            page.feed(html[:2_000_000])
                        except Exception:       # noqa: BLE001 - a malformed archived page is skipped
                            return None
                        return {"url": row.get("url") or f"https://{target}", "final_url": row.get("url"),
                                "status_code": 200, "title": page.title.strip()[:200], "text": page.text()[:20000],
                                "links": page.links, "depth": 1, "archived_at": archived_at}
            return None

        # Three at a time: the index asks to be queried gently. At the deadline, lookups still queued are cancelled
        # and those in flight are left to finish on their own, so a slow archive never holds up the profile.
        pool = ThreadPoolExecutor(max_workers=3)
        try:
            futures = [pool.submit(one, t) for t in targets]
            for f in as_completed(futures, timeout=deadline):
                try:
                    page = f.result()
                except Exception:               # noqa: BLE001 - one lookup failing never stops the others
                    page = None
                if page and page["text"] and all(p["url"] != page["url"] for p in pages):
                    pages.append(page)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
    except Exception as e:                      # noqa: BLE001 - the archive being down yields no pages
        log.info("archive lookup for %s failed: %r", site, e)
    finally:
        if own:
            c.close()                           # a lookup still in flight then fails inside its abandoned thread
    return pages
