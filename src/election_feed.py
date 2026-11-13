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
from src.data.election_profiles import PROFILES
from src.engines import election_country as ec
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


def _fetch_sources() -> tuple[list[tuple[str, str]], list[tuple[str, str, str]], dict[str, str]]:
    """Nigeria's outlet feeds as (outlet, text), the other elections' feeds as (election, outlet, text) (outlet ""
    for the Google News search), and the status of every fetch."""
    texts, country_texts, status = [], [], {}
    with httpx.Client(headers={"User-Agent": en.USER_AGENT}, timeout=25, follow_redirects=True) as client:
        def get(label: str, url: str) -> Optional[str]:
            try:
                resp = client.get(url)
                status[label] = str(resp.status_code)
                return resp.text if resp.status_code == 200 else None
            except httpx.HTTPError as e:
                status[label] = type(e).__name__
                return None
        for outlet, url in en.all_sources():
            text = get(f"{outlet} (Google News)" if "news.google.com" in url else outlet, url)
            if text is not None:
                texts.append((outlet, text))
        for key, outlet, url in ec.sources():
            text = get(f"{PROFILES[key]['country']}: {outlet or 'Google News'}", url)
            if text is not None:
                country_texts.append((key, outlet, text))
    return texts, country_texts, status


def collect_once(today: Optional[date] = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    texts, country_texts, status = _fetch_sources()
    since = (today - timedelta(days=5)).isoformat()
    _cache.pop(since, None)
    stored = ec.split(dict(s) for s in (_load(since) if hm._configured() else []))
    items_by = {ec.NIGERIA: en.collect(texts, today)}
    for key, outlet, text in country_texts:
        items_by.setdefault(key, []).extend(ec.collect(key, text, today, outlet=outlet))
    rows, counts = [], {}
    for key, items in items_by.items():
        nigeria = key == ec.NIGERIA
        stories, changed = en.merge(stored.get(key, []), items, None if nigeria else ec.tagger(key), key)
        if nigeria:
            changed |= en.retag_missing(stories)      # stories stored before a newer tag existed get it now
        changed |= en.assign_events(stories, keys_fn=None if nigeria else ec.headline_keys(key))
        rows += [s for s in stories if s["id"] in changed]
        counts[key] = len(items)
    written = _write(rows)
    from src import election_alerts
    return {"sources": status, "items": sum(counts.values()), "items_by_election": counts,
            "stories_changed": len(rows), "written": written, "alerts": election_alerts.deliver(rows)}


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
        # A slow site must not hold up the hourly run: a page that does not answer in 15 seconds is marked
        # unreadable (its headline tags stand) rather than retried.
        "concurrency": 2, "max_retries": 0, "request_timeout": "15s",
        "rate_per_host_rps": 0.5, "rate_burst": 1, "adaptive_rate": True,   # one page every two seconds per site
        "sink_backend": "jsonl", "output_path": output_path, "report_interval": "30s",
        "targets": _crawl_targets(_load(since), limit),
    }


def _crawl_targets(stories: list[dict], limit: int) -> list[dict]:
    """Nigeria's outlets first (up to `limit` pages), then each other election's readable outlets (up to 20 pages
    each), so a country's backlog never crowds out another's."""
    by = ec.split(stories)
    targets = en.crawl_targets(by.get(ec.NIGERIA, []), limit)
    for key, p in PROFILES.items():
        if p.get("article_selectors"):
            targets += en.crawl_targets(by.get(key, []), 20, 10, p["article_selectors"], p.get("slow_outlets", {}))
    return targets


def apply_crawl(pages: list[dict], today: Optional[date] = None) -> dict:
    """Re-tag recent stories from the article pages web-harvester fetched, and store what changed."""
    today = today or datetime.now(timezone.utc).date()
    since = (today - timedelta(days=5)).isoformat()
    _cache.pop(since, None)
    by = ec.split(dict(s, reports=[dict(r) for r in s.get("reports") or []]) for s in _load(since))
    rows = []
    for key, stories in by.items():
        nigeria = key == ec.NIGERIA
        if not nigeria and key not in PROFILES:
            continue
        changed = en.apply_articles(stories, pages, None if nigeria else ec.body_tags(key))
        changed |= en.assign_events(stories, keys_fn=None if nigeria else ec.headline_keys(key))
        rows += [s for s in stories if s["id"] in changed]
    read = sum(1 for p in pages if p.get("status_code") == 200 and (p.get("fields") or {}).get("body"))
    written = _write(rows)
    from src import election_alerts                  # an article can reveal an incident the headline did not
    return {"pages": len(pages), "articles_read": read, "stories_changed": len(rows), "written": written,
            "alerts": election_alerts.deliver(rows)}


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
           limit: int = 50, offset: int = 0, lga: Optional[str] = None, election: Optional[str] = None) -> dict:
    _check_election(election)
    since = since or (datetime.now(timezone.utc).date() - timedelta(days=30)).isoformat()
    try:
        date.fromisoformat(since)
    except ValueError:
        raise HTTPException(400, "since must be a date, YYYY-MM-DD.")
    rows = [s for s in _load(since) if _in_election(s, election)
            and _matches(s, "candidates", candidate) and _matches(s, "parties", party) and _matches(s, "states", state)
            and _matches(s, "topics", topic) and _matches(s, "races", race)
            and (not lga or any(lga.strip().lower() == x.split(",")[0].lower() for x in s.get("lgas") or []))
            and (not q or q.lower() in (s.get("title", "") + " " + s.get("snippet", "")).lower())]
    sources = sorted({o for o, _ in en.all_sources()}) if (election or ec.NIGERIA) == ec.NIGERIA \
        else sorted({o for s in rows for o in s.get("outlets") or []})
    return {"election": election, "since": since, "total": len(rows), "offset": offset,
            "stories": rows[offset:offset + limit], "sources": sources}


_SEVERITY = {"low": 1, "medium": 2, "high": 3}


def elections() -> list[dict]:
    """Every monitored election: key, country, label, dates, regions and what is covered."""
    from src.data import elections_ng_2027 as ng
    out = [{"key": ec.NIGERIA, "country": "Nigeria", "iso": "NG", "label": "Nigeria: 2027 general elections",
            "dates": [{"date": str(ng.PRESIDENTIAL_DAY), "name": "Presidential and National Assembly"},
                      {"date": str(ng.GOVERNORSHIP_DAY), "name": "Governorship and State Assembly"}],
            "body": "INEC", "region_word": "State", "regions": list(ng.STATES),
            "coverage": ["news", "incidents", "full_articles", "candidates", "lgas", "polling_units", "results"],
            "candidates": [{"name": c, "party": acr, "status": "on INEC's final list"} for acr, _, c, _ in ng.TICKETS],
            "outlets": sorted({o for o, _ in en.all_sources()}), "full_text_outlets": sorted(en.ARTICLE_SELECTORS)}]
    for key, p in PROFILES.items():
        out.append({"key": key, "country": p["country"], "iso": p["iso"], "label": p["label"],
                    "dates": [{"date": d, "name": n} for d, n in p["dates"]], "body": p["body"][0],
                    "region_word": p["region_word"], "regions": list(p["regions"]),
                    "coverage": ["news", "incidents", "candidates", "people"] +
                                (["full_articles"] if p.get("article_selectors") else []),
                    "candidates": [{k: c.get(k) for k in ("name", "party", "status")} for c in p.get("candidates", ())],
                    "candidates_checked": p.get("candidates_checked"), "people": list(p.get("people", {})),
                    "outlets": sorted(o for o, _ in p.get("sources", ())) + ["Google News search"],
                    "full_text_outlets": sorted(p.get("article_selectors", {}))})
    return sorted(out, key=lambda e: e["dates"][0]["date"])


def _check_election(election: Optional[str]) -> None:
    if election and election != ec.NIGERIA and election not in PROFILES:
        raise HTTPException(400, f"election must be one of: {', '.join(sorted([ec.NIGERIA, *PROFILES]))}.")


def _in_election(s: dict, election: Optional[str]) -> bool:
    return not election or ec.election_of(s) == election


def incident_feed(state: Optional[str] = None, lga: Optional[str] = None, type: Optional[str] = None,
                  severity: Optional[str] = None, since: Optional[str] = None, limit: int = 50, offset: int = 0,
                  group: bool = False, election: Optional[str] = None) -> dict:
    """Stories reporting election incidents, newest first, optionally by election, region, LGA, type and minimum
    severity."""
    _check_election(election)
    if severity and severity not in _SEVERITY:
        raise HTTPException(400, "severity must be low, medium or high.")
    since = since or (datetime.now(timezone.utc).date() - timedelta(days=30)).isoformat()
    try:
        date.fromisoformat(since)
    except ValueError:
        raise HTTPException(400, "since must be a date, YYYY-MM-DD.")
    floor = _SEVERITY.get(severity or "low", 1)
    rows = [s for s in _load(since) if s.get("incident_types") and _in_election(s, election)
            and _SEVERITY.get(s.get("severity") or "low", 1) >= floor
            and _matches(s, "states", state) and _matches(s, "incident_types", type)
            and (not lga or any(lga.strip().lower() == x.split(",")[0].lower() for x in s.get("lgas") or []))]
    by_type: dict[str, int] = {}
    for s in rows:
        for t in s["incident_types"]:
            by_type[t] = by_type.get(t, 0) + 1
    events = {}
    for s in rows:
        events.setdefault(s.get("event_id") or s["id"], []).append(s)
    if group:                                  # one entry per event: its most severe story, with the rest listed
        grouped = []
        for ev, members in events.items():
            lead = max(members, key=lambda s: (_SEVERITY.get(s.get("severity") or "low", 1), -len(s.get("title", ""))))
            grouped.append(dict(lead, event_id=ev, event_size=len(members),
                                event_reports=[{"title": m["title"], "url": m.get("url"), "outlets": m.get("outlets"),
                                                "day": m.get("day")} for m in members if m is not lead]))
        rows = sorted(grouped, key=lambda s: (s.get("day") or "", _SEVERITY.get(s.get("severity") or "low", 1)), reverse=True)
    return {"election": election, "since": since, "total": len(rows), "events": len(events),
            "by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
            "by_severity": {k: sum(1 for s in rows if s.get("severity") == k) for k in ("high", "medium", "low")},
            "offset": offset, "incidents": rows[offset:offset + limit]}


def summary(days: int = 7, election: Optional[str] = None) -> dict:
    _check_election(election)
    since = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    rows = [s for s in _load(since) if _in_election(s, election)]
    by_election: dict[str, int] = {}
    for s in rows:
        by_election[ec.election_of(s)] = by_election.get(ec.election_of(s), 0) + 1
    out = {"election": election, "since": since, "days": days, "by_election": by_election, **en.summary(rows, since)}
    if election and election in PROFILES:           # names the coverage is about that the profile does not track
        out["untracked_names"] = ec.untracked_names(election, rows)
    return out
