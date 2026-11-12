"""
Election news, served: the scheduled collection job and the queries behind /v1/elections.

The job reads each source's feed, keeps election coverage from the last three days, merges it into the stories
already stored for that window (so a second outlet's report joins the first), and writes only what changed. Reads
are cached per instance for ten minutes; the table holds a few hundred small rows a week, so a read is cheap.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from src import hosted_market as hm
from src.engines import election_news as en

log = logging.getLogger("deal_intel.election_feed")
router = APIRouter()

_TTL = 600
_cache: dict[str, tuple[float, list[dict]]] = {}


def _load(since: str) -> list[dict]:
    hit = _cache.get(since)
    if hit and time.monotonic() - hit[0] < _TTL:
        return hit[1]
    r = hm._rpc_sync("list_election_news", {"p_since": since, "p_limit": 20000})
    if r.status_code != 200:
        log.error("election news read failed: %s %s", r.status_code, r.text[:300])
        raise HTTPException(503, "Election news is unavailable.")
    rows = r.json() or []
    _cache[since] = (time.monotonic(), rows)
    return rows


def _fetch_sources() -> tuple[list[tuple[str, str]], dict[str, str]]:
    texts, status = [], {}
    with httpx.Client(headers={"User-Agent": en.USER_AGENT}, timeout=25, follow_redirects=True) as client:
        for outlet, url in en.all_sources():
            label = f"{outlet} (Google News)" if "news.google.com" in url else outlet
            try:
                resp = client.get(url)
                status[label] = str(resp.status_code)
                if resp.status_code == 200:
                    texts.append((outlet, resp.text))
            except httpx.HTTPError as e:
                status[label] = type(e).__name__
    return texts, status


def collect_once(today: Optional[date] = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    texts, status = _fetch_sources()
    items = en.collect(texts, today)
    since = (today - timedelta(days=5)).isoformat()
    _cache.pop(since, None)
    stored = _load(since) if hm._configured() else []
    stories, changed = en.merge([dict(s) for s in stored], items)
    rows = [s for s in stories if s["id"] in changed]
    return {"sources": status, "items": len(items), "stories_changed": len(rows), "written": _write(rows)}


def _write(rows: list[dict]) -> int:
    written = 0
    for i in range(0, len(rows), 200):
        r = hm._rpc_sync("upsert_election_news", {"p_rows": rows[i:i + 200]})
        if r.status_code != 200:
            raise HTTPException(503, f"Election news write failed: {r.status_code}")
        written += int(r.json() or 0)
    _cache.clear()
    return written


def crawl_config(output_path: str, limit: int = 150, today: Optional[date] = None) -> dict:
    """A web-harvester crawl config (cmd/crawl) for the articles of recent stories not read yet."""
    today = today or datetime.now(timezone.utc).date()
    since = (today - timedelta(days=5)).isoformat()
    _cache.pop(since, None)
    return {
        "user_agent": en.USER_AGENT, "robots_agent": "web-harvester",
        "concurrency": 2, "max_retries": 1, "request_timeout": "25s",
        "rate_per_host_rps": 0.5, "rate_burst": 1, "adaptive_rate": True,   # one page every two seconds per site
        "sink_backend": "jsonl", "output_path": output_path, "report_interval": "30s",
        "targets": en.crawl_targets(_load(since), limit),
    }


def apply_crawl(pages: list[dict], today: Optional[date] = None) -> dict:
    """Re-tag recent stories from the article pages web-harvester fetched, and store what changed."""
    today = today or datetime.now(timezone.utc).date()
    since = (today - timedelta(days=5)).isoformat()
    _cache.pop(since, None)
    stories = [dict(s, reports=[dict(r) for r in s.get("reports") or []]) for s in _load(since)]
    changed = en.apply_articles(stories, pages)
    rows = [s for s in stories if s["id"] in changed]
    read = sum(1 for p in pages if p.get("status_code") == 200 and (p.get("fields") or {}).get("body"))
    return {"pages": len(pages), "articles_read": read, "stories_changed": len(rows), "written": _write(rows)}


@router.get("/api/cron/election-news")
async def cron_election_news(request: Request) -> dict:
    """Collect election coverage from the sources' feeds and store new and updated stories."""
    if not hm._authorized_cron(request):
        raise HTTPException(status_code=401, detail="Scheduled workflow authorization required.")
    return await run_in_threadpool(collect_once)


def _matches(s: dict, field: str, value: Optional[str]) -> bool:
    if not value:
        return True
    v = value.strip().lower()
    return any(v == x.lower() or (field == "candidates" and v in x.lower()) for x in s.get(field) or [])


def search(candidate: Optional[str] = None, party: Optional[str] = None, state: Optional[str] = None,
           topic: Optional[str] = None, race: Optional[str] = None, q: str = "", since: Optional[str] = None,
           limit: int = 50, offset: int = 0) -> dict:
    since = since or (datetime.now(timezone.utc).date() - timedelta(days=30)).isoformat()
    try:
        date.fromisoformat(since)
    except ValueError:
        raise HTTPException(400, "since must be a date, YYYY-MM-DD.")
    rows = [s for s in _load(since)
            if _matches(s, "candidates", candidate) and _matches(s, "parties", party) and _matches(s, "states", state)
            and _matches(s, "topics", topic) and _matches(s, "races", race)
            and (not q or q.lower() in (s.get("title", "") + " " + s.get("snippet", "")).lower())]
    return {"since": since, "total": len(rows), "offset": offset, "stories": rows[offset:offset + limit],
            "sources": sorted({o for o, _ in en.all_sources()})}


def summary(days: int = 7) -> dict:
    since = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    return {"since": since, "days": days, **en.summary(_load(since), since)}
