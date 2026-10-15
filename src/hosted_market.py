"""
Hosted API routes for market data (mounted by api/index.py):

  GET  /api/countries                  54 countries with risk score and coverage tier
  GET  /api/countries/{code}           country risk, currency risk, coverage, deals, events
  GET  /api/currencies                 currency risk for every currency
  GET  /api/coverage                   coverage and verification matrix
  GET  /api/deals                      deal search (q, country, type, sector, investor, since, until, min_usd)
  GET  /api/deals/{id}
  GET  /api/comparables                comparable deals (deal_id, or sector/country/type/amount_usd)
  GET  /api/investors                  leaderboard (role, kind)
  GET  /api/investors/{name}           investor profile
  GET  /api/funds                      fund raises and closes with LPs
  GET  /api/events                     corporate events (country, type, since, q)
  GET  /api/sectors/{sector}/risk      sector risk (country)
  GET  /api/companies/profile          company profile and financial statements (name, ticker, country, cik)
  GET  /api/valuation                  valuation view for a company
  POST /api/research                   source-grounded AI answer (rate-limited)
  POST /api/reports/country/{code}     country research report (rate-limited)
  POST /api/reports/sector/{sector}    sector research report (rate-limited)
  POST /api/watchlists                 create a watchlist; GET/DELETE /api/watchlists/{id}
  GET  /api/watchlists/{id}/feed.xml   RSS of matched events and deals
  GET  /api/evaluation                 historical backtest and live outcome statistics
  GET  /api/pulse                      live market summary for the site (deal flow, events, measured rates)
  GET  /api/cron/ingest                daily (Vercel Cron): feed -> deals and events, webhooks
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import socket
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from src.data import africa_countries as ac
from src.engines import company_profile, coverage, country_risk, deals as deals_mod, investors, market_risk
from src.engines import research as research_mod, watch

log = logging.getLogger("deal_intel.market")
router = APIRouter()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
API_SECRET = os.environ.get("DEAL_INTEL_API_SECRET", "")
CRON_SECRET = os.environ.get("CRON_SECRET", "")
PER_VISITOR_DAILY = int(os.environ.get("DEAL_INTEL_PER_VISITOR_DAILY", "10"))
GLOBAL_DAILY = int(os.environ.get("DEAL_INTEL_GLOBAL_DAILY", "300"))
APP_URL = os.environ.get("DEAL_INTEL_APP_URL", "").rstrip("/")
from src.engines.historical_backtest import SUMMARY_PATH as _BACKTEST_SUMMARY  # noqa: E402


def _configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY and API_SECRET)


def _headers() -> dict[str, str]:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}


def _rpc_sync(fn: str, args: dict, timeout: float = 30) -> httpx.Response:
    return httpx.post(f"{SUPABASE_URL}/rest/v1/rpc/{fn}", headers=_headers(), json={"secret": API_SECRET, **args},
                      timeout=timeout)


async def _rpc(client: httpx.AsyncClient, fn: str, args: dict) -> httpx.Response:
    return await client.post(f"{SUPABASE_URL}/rest/v1/rpc/{fn}", headers=_headers(), json={"secret": API_SECRET, **args})


def _client_hash(request: Request) -> str:
    import hashlib
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
    return hashlib.sha256(f"{API_SECRET}:{ip}".encode()).hexdigest()[:32]


# ── Data store (Supabase when configured, local files otherwise), cached per instance ──

_TTL = 300
_cache: dict[str, tuple[float, list]] = {}


def _load(kind: str) -> list[dict]:
    hit = _cache.get(kind)
    if hit and time.monotonic() - hit[0] < _TTL:
        return hit[1]
    rows: list[dict] = []
    if _configured():
        since = (date.today() - timedelta(days=3 * 365)).isoformat()
        try:
            r = _rpc_sync("list_deals" if kind == "deals" else "list_events", {"p_since": since})
            rows = r.json() if r.status_code == 200 else []
        except httpx.HTTPError as e:
            log.warning("loading %s failed: %s", kind, e)
            rows = hit[1] if hit else []
    else:
        if kind == "deals":
            rows = list(deals_mod.load_deals().values())
        else:
            from src.utils.paths import DATA_DIR
            from src.utils.storage import load_json
            rows = load_json(DATA_DIR / "events.json", list)
    _cache[kind] = (time.monotonic(), rows)
    return rows


def deals() -> list[dict]:
    return _load("deals")


def events() -> list[dict]:
    return _load("events")


def _country_or_404(code: str) -> ac.Country:
    c = ac.get(code)
    if c is None:
        raise HTTPException(404, "Unknown country code. Use an ISO code such as NG, KE or SN.")
    return c


# ── Countries, currencies, coverage ───────────────────────────────────────────

@router.get("/api/countries")
async def countries() -> dict:
    ds, es = deals(), events()
    rows = []
    for c in ac.COUNTRIES:
        risk = country_risk.assess(c, fx=lambda _: None)
        cov = coverage.country_row(c, ds, es)
        rows.append({"iso2": c.iso2, "name": c.name, "region": c.region, "currency": c.currency,
                     "exchange": c.exchange, "risk_score": risk["score"], "risk_tier": risk["tier"],
                     "risk_coverage": risk["coverage"], "coverage_tier": cov["tier"], "deals": cov["deals"],
                     "events": cov["events"]})
    return {"countries": rows, "data_as_of": country_risk.load_snapshot().get("retrieved")}


@router.get("/api/countries/{code}")
async def country(code: str) -> dict:
    c = _country_or_404(code)
    ds, es = deals(), events()
    return {
        "country": {k: getattr(c, k) for k in ("iso2", "iso3", "name", "region", "languages", "currency", "exchange",
                                               "yahoo_suffix", "central_bank", "securities_regulator")},
        "risk": await run_in_threadpool(country_risk.assess, c),
        "currency": await run_in_threadpool(market_risk.currency_risk, c.currency),
        "coverage": coverage.country_row(c, ds, es),
        "deals": deals_mod.search(ds, country=c.iso2, limit=25),
        "events": sorted([e for e in es if c.iso2 in (e.get("countries") or [e.get("country")])],
                         key=lambda e: e.get("day") or "", reverse=True)[:25],
        "investors": investors.leaderboard(deals_mod.search(ds, country=c.iso2, limit=5000), limit=10),
    }


@router.get("/api/currencies")
async def currencies() -> dict:
    return {"currencies": market_risk.all_currencies()}


@router.get("/api/coverage")
async def coverage_matrix() -> dict:
    return coverage.matrix(deals(), events())


# ── Deals, comparables, investors, funds, events ──────────────────────────────

@router.get("/api/deals")
async def deal_search(q: str = "", country: Optional[str] = None, type: Optional[str] = None,
                      sector: Optional[str] = None, investor: Optional[str] = None, since: Optional[str] = None,
                      until: Optional[str] = None, min_usd: Optional[float] = None,
                      limit: int = Query(50, ge=1, le=500)) -> dict:
    ds = deals()
    rows = deals_mod.search(ds, q=q, country=country, deal_type=type, sector=sector, since=since, until=until,
                            investor=investor, min_usd=min_usd, limit=limit)
    from src.engines import provenance
    out = []
    for d in rows:
        n = len(provenance.stories(d.get("sources") or []))
        out.append({**d, "independent_stories": n,
                    "verification": "corroborated" if n >= 2 else "single source"})
    return {"total_in_database": len(ds), "count": len(out), "deals": out}


_DEAL_EVAL = Path(__file__).resolve().parents[1] / "evaluation" / "deals" / "results.json"


def _field_accuracy() -> Optional[dict]:
    """Measured accuracy of each extracted field on the held-out evaluation set, shown next to the record."""
    try:
        r = json.loads(_DEAL_EVAL.read_text()).get("heldout_extraction") or {}
    except (OSError, ValueError):
        return None
    f = (r.get("fields") or {}).get("all") or {}
    return {"set": "held-out evaluation set", "fields": f, "fully_correct_record": (r.get("fields") or {}).get("fully_correct_record"),
            "detection": (r.get("detection") or {}).get("all")}


@router.get("/api/deals/{deal_id}")
async def deal(deal_id: str) -> dict:
    d = next((d for d in deals() if d.get("id") == deal_id), None)
    if d is None:
        raise HTTPException(404, "Deal not found.")
    from src.engines import provenance
    return {"deal": d, "verification": provenance.verify(d), "field_accuracy": _field_accuracy(),
            "parties": [{"name": n, "role": r} for n, r in investors.parties(d)],
            "comparables": deals_mod.comparables(deals(), sector=d.get("sector"), country=d.get("country"),
                                                 deal_type=d.get("deal_type"), amount_usd=d.get("amount_usd"),
                                                 exclude_id=d["id"], limit=10)}


@router.get("/api/comparables")
async def comparables(deal_id: Optional[str] = None, sector: Optional[str] = None, country: Optional[str] = None,
                      type: Optional[str] = None, amount_usd: Optional[float] = None,
                      limit: int = Query(15, ge=1, le=50)) -> dict:
    ds = deals()
    if deal_id:
        d = next((d for d in ds if d.get("id") == deal_id), None)
        if d is None:
            raise HTTPException(404, "Deal not found.")
        sector, country, type, amount_usd = d.get("sector"), d.get("country"), d.get("deal_type"), d.get("amount_usd")
    return deals_mod.comparables(ds, sector=sector, country=country, deal_type=type, amount_usd=amount_usd,
                                 exclude_id=deal_id, limit=limit)


@router.get("/api/investors")
async def investor_board(role: Optional[str] = None, kind: Optional[str] = None,
                         limit: int = Query(50, ge=1, le=200)) -> dict:
    return {"investors": investors.leaderboard(deals(), role=role, kind=kind, limit=limit),
            "registry": [{"name": i.name, "type": i.kind, "hq": i.hq, "aliases": list(i.aliases)}
                         for i in investors.REGISTRY]}


@router.get("/api/investors/{name}")
async def investor(name: str) -> dict:
    p = investors.profile(deals(), name)
    if p is None:
        entry = investors.registry_entry(name)
        if entry is None:
            raise HTTPException(404, "No deals found for this investor.")
        p = {"name": entry.name, "type": entry.kind, "hq": entry.hq, "in_registry": True, "deal_count": 0,
             "roles": {}, "recent": []}
    return p


@router.get("/api/funds")
async def funds(limit: int = Query(100, ge=1, le=500)) -> dict:
    return {"funds": investors.funds(deals())[:limit]}


@router.get("/api/events")
async def event_feed(country: Optional[str] = None, type: Optional[str] = None, since: Optional[str] = None,
                     q: str = "", limit: int = Query(100, ge=1, le=500)) -> dict:
    rows = events()
    c = ac.get(country) if country else None
    out = [e for e in rows
           if (not c or c.iso2 in (e.get("countries") or [e.get("country")]))
           and (not type or e.get("signal_type") == type)
           and (not since or (e.get("day") or "") >= since)
           and (not q or q.lower() in e.get("headline", "").lower())]
    out.sort(key=lambda e: e.get("day") or "", reverse=True)
    return {"count": len(out), "events": out[:limit]}


@router.get("/api/sectors/{sector}/risk")
async def sector_risk(sector: str, country: Optional[str] = None, days: int = Query(90, ge=7, le=730)) -> dict:
    if sector not in {s for s, _ in deals_mod.SECTORS}:
        raise HTTPException(404, f"Unknown sector. Choose from: {', '.join(s for s, _ in deals_mod.SECTORS)}.")
    return market_risk.sector_risk(sector, events(), deals(), country=country, days=days)


# ── Companies and valuation ───────────────────────────────────────────────────

_profile_cache: dict[tuple, tuple[float, dict]] = {}


@router.get("/api/companies/profile")
async def company(name: str = Query(..., min_length=1, max_length=120), ticker: Optional[str] = None,
                  country: Optional[str] = None, cik: Optional[int] = None) -> dict:
    key = (name.lower(), (ticker or "").upper(), (country or "").upper(), cik)
    hit = _profile_cache.get(key)
    if hit and time.monotonic() - hit[0] < 6 * 3600:
        return hit[1]
    profile = await run_in_threadpool(company_profile.build, name, ticker.upper() if ticker else None, country,
                                      deals(), cik)
    profile["valuation"] = market_risk.valuation_view(profile.get("name") or name, deals(), profile)
    _profile_cache[key] = (time.monotonic(), profile)
    return profile


@router.get("/api/valuation")
async def valuation(company: str = Query(..., min_length=1, max_length=120)) -> dict:
    return market_risk.valuation_view(company, deals())


# ── Research (rate-limited: shares the daily analysis allowance) ──────────────

class ResearchBody(BaseModel):
    question: str = Field(..., min_length=5, max_length=500)

    @field_validator("question")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()


async def _reserve(request: Request, label: str) -> int:
    if not _configured():
        raise HTTPException(503, "The API is not configured.")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{SUPABASE_URL}/rest/v1/rpc/start_run", headers=_headers(), json={
            "secret": API_SECRET, "p_client_hash": _client_hash(request), "p_company": label[:120], "p_ticker": None,
            "per_client_daily": PER_VISITOR_DAILY, "global_daily": GLOBAL_DAILY})
    if r.status_code != 200:
        if "client_limit" in r.text:
            raise HTTPException(429, f"You have used today's {PER_VISITOR_DAILY} free requests. The limit resets at 00:00 UTC.")
        if "global_limit" in r.text:
            raise HTTPException(429, "The free service has reached today's capacity. Try again tomorrow.")
        raise HTTPException(503, "The service is busy. Try again shortly.")
    return int(r.json())


async def _finish(run_id: int) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        await _rpc(client, "finish_research", {"p_run_id": run_id})


@router.post("/api/research")
async def research(body: ResearchBody, request: Request) -> dict:
    run_id = await _reserve(request, f"[research] {body.question}")
    result = await run_in_threadpool(research_mod.research, body.question, deals(), events())
    await _finish(run_id)
    return result


@router.post("/api/reports/country/{code}")
async def country_report(code: str, request: Request) -> dict:
    c = _country_or_404(code)
    run_id = await _reserve(request, f"[report] country {c.iso2}")
    result = await run_in_threadpool(research_mod.country_report, c.iso2, deals(), events())
    await _finish(run_id)
    return result


@router.post("/api/reports/sector/{sector}")
async def sector_report(sector: str, request: Request, country: Optional[str] = None) -> dict:
    if sector not in {s for s, _ in deals_mod.SECTORS}:
        raise HTTPException(404, "Unknown sector.")
    run_id = await _reserve(request, f"[report] sector {sector} {country or ''}")
    result = await run_in_threadpool(research_mod.sector_report, sector, deals(), events(), country)
    await _finish(run_id)
    return result


# ── Watchlists and alerts ─────────────────────────────────────────────────────

class WatchlistBody(BaseModel):
    name: str = Field("Watchlist", max_length=80)
    companies: list[str] = Field(default_factory=list, max_length=50)
    countries: list[str] = Field(default_factory=list, max_length=54)
    signal_types: list[str] = Field(default_factory=list, max_length=8)
    include_deals: bool = True
    webhook_url: Optional[str] = Field(None, max_length=500)

    @field_validator("companies")
    @classmethod
    def clean_companies(cls, v: list[str]) -> list[str]:
        return [c.strip()[:80] for c in v if c.strip()]

    @field_validator("countries")
    @classmethod
    def clean_countries(cls, v: list[str]) -> list[str]:
        out = []
        for code in v:
            c = ac.get(code)
            if c is None:
                raise ValueError(f"unknown country code {code}")
            out.append(c.iso2)
        return out


def _watch_link(wl_id: str) -> str:
    return f"{APP_URL}/app/watchlists/{wl_id}" if APP_URL else f"/app/watchlists/{wl_id}"


@router.post("/api/watchlists")
async def create_watchlist(body: WatchlistBody, request: Request) -> dict:
    if not _configured():
        raise HTTPException(503, "The API is not configured.")
    if not (body.companies or body.countries):
        raise HTTPException(422, "Add at least one company or country.")
    if not watch.valid_webhook(body.webhook_url) or (body.webhook_url and not _public_host(body.webhook_url)):
        raise HTTPException(422, "Webhooks must be https URLs on a public host.")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await _rpc(client, "create_watchlist", {
            "p_client_hash": _client_hash(request), "p_name": body.name, "p_companies": body.companies,
            "p_countries": body.countries, "p_signal_types": body.signal_types, "p_include_deals": body.include_deals,
            "p_webhook_url": body.webhook_url})
    if r.status_code != 200:
        if "watchlist_limit" in r.text:
            raise HTTPException(429, "You have created the maximum of 20 watchlists.")
        raise HTTPException(503, "The watchlist could not be saved.")
    wl_id = r.json()
    return {"id": wl_id, "url": _watch_link(wl_id), "feed": f"/api/watchlists/{wl_id}/feed.xml"}


async def _get_watchlist(wl_id: str) -> dict:
    try:
        uuid.UUID(wl_id)
    except ValueError:
        raise HTTPException(404, "Watchlist not found.")
    if not _configured():
        raise HTTPException(503, "The API is not configured.")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await _rpc(client, "get_watchlist", {"p_id": wl_id})
    rows = r.json() if r.status_code == 200 else []
    if not rows:
        raise HTTPException(404, "Watchlist not found.")
    wl = rows[0]
    wl.pop("client_hash", None)
    wl.pop("deleted_at", None)
    return wl


@router.get("/api/watchlists/{wl_id}")
async def get_watchlist(wl_id: str, since: Optional[str] = None) -> dict:
    wl = await _get_watchlist(wl_id)
    since = since or (date.today() - timedelta(days=90)).isoformat()
    return {"watchlist": wl, "alerts": watch.matches(wl, events(), deals(), since=since)}


@router.get("/api/watchlists/{wl_id}/feed.xml")
async def watchlist_feed(wl_id: str) -> Response:
    wl = await _get_watchlist(wl_id)
    since = (date.today() - timedelta(days=90)).isoformat()
    xml = watch.rss(wl, watch.matches(wl, events(), deals(), since=since), _watch_link(wl_id))
    return Response(xml, media_type="application/rss+xml")


@router.delete("/api/watchlists/{wl_id}")
async def delete_watchlist(wl_id: str) -> dict:
    await _get_watchlist(wl_id)
    async with httpx.AsyncClient(timeout=15) as client:
        await _rpc(client, "remove_watchlist", {"p_id": wl_id})
    return {"deleted": True}


def _public_host(url: str) -> bool:
    """Every address the webhook host resolves to is public (blocks DNS names pointing inside)."""
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


# ── Live measurements: outcome counts and observations, refreshed at most hourly ──

_LIVE_TTL = 3600
_live_loaded_at = 0.0
_live_stats: Optional[dict] = None


async def refresh_live(client: httpx.AsyncClient, force: bool = False) -> Optional[dict]:
    """Pull live outcome counts (per-market calibration) and observations (pooled into the measured
    tables) so confidence and expected moves follow what the market has done since the backtest."""
    global _live_loaded_at, _live_stats
    if not _configured() or (not force and _live_loaded_at and time.monotonic() - _live_loaded_at < _LIVE_TTL):
        return _live_stats
    from src.engines import measured
    from src.engines.adaptive_calibration import set_outcome_stats
    try:
        r1 = await _rpc(client, "outcome_stats", {})
        r2 = await _rpc(client, "outcome_rows", {})
    except httpx.HTTPError as e:
        log.warning("live outcomes unavailable: %s", e)
        return _live_stats
    if r1.status_code == 200:
        _live_stats = r1.json() or {}
        set_outcome_stats(_live_stats)
    if r2.status_code == 200:
        measured.set_live(r2.json() or [])
    if r1.status_code == 200 and r2.status_code == 200:
        _live_loaded_at = time.monotonic()
    return _live_stats


def _measured_summary() -> dict:
    from src.engines import measured
    t = measured.load()
    return {"source": t.get("source"), "period": t.get("period"), "overall_confirmation": t.get("overall_confirmation"),
            "backtest_observations": t.get("backtest_observations", 0), "live_observations": t.get("live_observations", 0),
            "live_updated_at": t.get("live_updated_at"), "backtest": _backtest_freshness()}


def _backtest_freshness() -> Optional[dict]:
    """When the backtest behind the measured figures ran, over what, and when it runs next."""
    from src.engines.evaluation_report import next_refresh
    r = _read_json(Path(__file__).resolve().parents[1] / "docs" / "evaluation_report.json") or {}
    d = r.get("design") or {}
    if not d:
        return None
    return {"generated_at": r.get("generated_at"), "start": d.get("start"), "end": d.get("end"),
            "companies": d.get("companies"), "universe_size": d.get("universe_size"),
            "not_yet_run": d.get("not_yet_run", 0),
            "schedule": (r.get("refresh") or {}).get("schedule", "monthly, on the 2nd (UTC)"),
            "next": next_refresh(datetime.now(timezone.utc).date()).isoformat()}


# ── Market pulse (public site) ───────────────────────────────────────────────

# ── Owner-only usage counts ──────────────────────────────────────────────────

ADMIN_KEY = os.environ.get("DEAL_INTEL_ADMIN_KEY", "")
_VISITOR = re.compile(r"^[a-z0-9]{8,40}$")


@router.post("/api/track")
async def track_visit(request: Request) -> dict:
    """One page view from the site's beacon (text/plain JSON: {"v": visitor id, "p": path}). Never fails loudly."""
    try:
        body = json.loads((await request.body())[:1000] or b"{}")
        visitor, path = str(body.get("v", "")), str(body.get("p", ""))
    except (ValueError, AttributeError):
        return {"ok": False}
    if not (_configured() and _VISITOR.match(visitor) and path.startswith("/") and len(path) <= 200):
        return {"ok": False}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await _rpc(client, "log_visit", {"p_visitor": visitor, "p_path": path.split("?")[0]})
    return {"ok": r.is_success}


@router.post("/api/admin/stats")
async def admin_stats(request: Request) -> dict:
    """Visits and product users for the owner's page; needs DEAL_INTEL_ADMIN_KEY in the JSON body."""
    import hmac
    try:
        body = await request.json()
    except ValueError:
        body = {}
    key = str(body.get("key", ""))
    if not (ADMIN_KEY and _configured() and hmac.compare_digest(key, ADMIN_KEY)):
        raise HTTPException(status_code=401, detail="Wrong key")
    days = max(1, min(int(body.get("days", 30) or 30), 365))
    async with httpx.AsyncClient(timeout=15) as client:
        r = await _rpc(client, "visit_stats", {"p_days": days})
    if not r.is_success:
        raise HTTPException(status_code=502, detail="Stats unavailable")
    return r.json()


@router.get("/api/pulse")
async def market_pulse() -> dict:
    from src.engines import pulse
    if _configured():
        async with httpx.AsyncClient(timeout=15) as client:
            await refresh_live(client)
    rows_d, rows_e = await run_in_threadpool(deals), await run_in_threadpool(events)
    summary = _measured_summary()
    try:
        backtest = json.loads(_BACKTEST_SUMMARY.read_text())
        summary["alpha_validation"] = backtest.get("alpha_validation")
    except (OSError, ValueError):
        pass
    return pulse.build(rows_d, rows_e, summary, today=datetime.now(timezone.utc).date())


# ── Evaluation ────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parents[1]
_DOWNLOADS = {
    "backtest_predictions.csv": ("docs/backtest_predictions.csv", "text/csv"),
    "deal_extraction_items.jsonl": ("evaluation/deals/extraction_items.jsonl", "application/x-ndjson"),
    "deal_extraction_labels.jsonl": ("evaluation/deals/extraction_labels.jsonl", "application/x-ndjson"),
    "deal_heldout_items.jsonl": ("evaluation/deals/heldout_extraction_items.jsonl", "application/x-ndjson"),
    "deal_heldout_labels.jsonl": ("evaluation/deals/heldout_extraction_labels.jsonl", "application/x-ndjson"),
    "dedup_items.jsonl": ("evaluation/deals/dedup_items.jsonl", "application/x-ndjson"),
    "dedup_labels.jsonl": ("evaluation/deals/dedup_labels.jsonl", "application/x-ndjson"),
    "identity_items.jsonl": ("evaluation/deals/identity_items.jsonl", "application/x-ndjson"),
    "identity_labels.jsonl": ("evaluation/deals/identity_labels.jsonl", "application/x-ndjson"),
    "names_heldout_items.jsonl": ("evaluation/deals/heldout_names_items.jsonl", "application/x-ndjson"),
    "names_heldout_labels.jsonl": ("evaluation/deals/heldout_names_labels.jsonl", "application/x-ndjson"),
    "deal_errors.jsonl": ("evaluation/deals/errors.jsonl", "application/x-ndjson"),
    "attribution_natural_items.jsonl": ("evaluation/attribution/natural_items.jsonl", "application/x-ndjson"),
    "attribution_natural_labels.jsonl": ("evaluation/attribution/natural_labels.jsonl", "application/x-ndjson"),
    "attribution_hard_items.jsonl": ("evaluation/attribution/hard_items.jsonl", "application/x-ndjson"),
    "attribution_hard_labels.jsonl": ("evaluation/attribution/hard_labels.jsonl", "application/x-ndjson"),
    "attribution_errors.jsonl": ("evaluation/attribution/errors.jsonl", "application/x-ndjson"),
}


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


@router.get("/api/evaluation/files")
async def evaluation_files() -> dict:
    return {"files": [{"name": k, "url": f"/api/evaluation/files/{k}", "available": (_ROOT / v[0]).exists()}
                      for k, v in _DOWNLOADS.items()]}


@router.get("/api/evaluation/files/{name}")
async def evaluation_file(name: str) -> Response:
    if name not in _DOWNLOADS:
        raise HTTPException(404, "Unknown file.")
    rel, media = _DOWNLOADS[name]
    try:
        body = (_ROOT / rel).read_text()
    except OSError:
        raise HTTPException(404, "File not published.")
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/api/evaluation")
async def evaluation() -> dict:
    try:
        backtest = json.loads(_BACKTEST_SUMMARY.read_text())
    except (OSError, ValueError):
        backtest = None
    live = None
    if _configured():
        async with httpx.AsyncClient(timeout=15) as client:
            live = await refresh_live(client)
    return {"historical_backtest": backtest, "live_outcomes": live, "measured_now": _measured_summary(),
            "signal_report": _read_json(_ROOT / "docs" / "evaluation_report.json"),
            "data_quality": _read_json(_ROOT / "evaluation" / "deals" / "results.json"),
            "data_quality_baseline": _read_json(_ROOT / "evaluation" / "deals" / "results_baseline.json"),
            "attribution": _read_json(_ROOT / "evaluation" / "attribution" / "results.json"),
            "attribution_before": _read_json(_ROOT / "evaluation" / "attribution" / "results_before_rule_changes.json"),
            "method": "Historical: walk-forward replay, 30-day lookback, 90-day horizon, confirmation strictly after "
                      "each as-of date. Live: every hosted brief's signals labelled daily against later filings, "
                      "credible news and abnormal price moves."}


# ── Daily ingestion ───────────────────────────────────────────────────────────

@router.get("/api/cron/ingest")
async def cron_ingest(request: Request) -> dict:
    """Daily: read every feed, extract deals and events, merge, store, deliver webhooks."""
    if not CRON_SECRET or request.headers.get("authorization") != f"Bearer {CRON_SECRET}":
        raise HTTPException(401, "Unauthorized")
    if not _configured():
        raise HTTPException(503, "The API is not configured.")
    from src.engines import market_feed
    items = await market_feed.collect("when:2d")
    new_deals, new_events = market_feed.to_deals(items), market_feed.to_events(items)
    _cache.clear()
    existing = {d["id"]: d for d in await run_in_threadpool(deals)}
    merged = deals_mod.merge_all(new_deals, into={k: existing[k] for k in {d["id"] for d in new_deals} if k in existing})
    async with httpx.AsyncClient(timeout=60) as client:
        r1 = await _rpc(client, "upsert_deals", {"p_rows": list(merged.values())})
        r2 = await _rpc(client, "upsert_events", {"p_rows": new_events})
        hooks = await _rpc(client, "webhook_watchlists", {})
    delivered = 0
    for wl in (hooks.json() if hooks.status_code == 200 else []):
        since = (wl.get("last_delivered_at") or (datetime.now(timezone.utc) - timedelta(days=2)).isoformat())[:10]
        alerts = watch.matches(wl, new_events, list(merged.values()), since=since)
        if not alerts or not _public_host(wl["webhook_url"]):
            continue
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                resp = await client.post(wl["webhook_url"], json=watch.webhook_payload(wl, alerts, _watch_link(wl["id"])))
                if resp.status_code < 300:
                    delivered += 1
                    await _rpc(client, "mark_delivered", {"p_id": wl["id"],
                                                          "p_at": datetime.now(timezone.utc).isoformat()})
        except httpx.HTTPError as e:
            log.info("webhook for %s failed: %s", wl["id"], e)
    _cache.clear()
    return {"headlines": len(items), "deals": len(merged), "deals_saved": r1.json() if r1.status_code == 200 else r1.text[:200],
            "events": len(new_events), "events_saved": r2.json() if r2.status_code == 200 else r2.text[:200],
            "webhooks_delivered": delivered}
