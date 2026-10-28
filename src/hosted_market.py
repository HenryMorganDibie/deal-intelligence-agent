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
  GET  /api/valuation/cost-of-equity   country cost of equity (dollar and local currency) with its build-up
  POST /api/valuation/evidence         each valuation input checked against exchange data, the filing and the source
  POST /api/research                   source-grounded AI answer (rate-limited)
  POST /api/reports/country/{code}     country research report (rate-limited)
  POST /api/reports/sector/{sector}    sector research report (rate-limited)
  POST /api/watchlists                 create a watchlist; GET/DELETE /api/watchlists/{id}
  GET  /api/watchlists/{id}/feed.xml   RSS of matched events and deals
  GET  /api/evaluation                 historical backtest and live outcome statistics
  GET  /api/pulse                      live market summary for the site (deal flow, events, measured rates)
  GET  /api/markets/overview           exchange tiles, movers, most traded, sectors, currencies (16 exchanges)
  GET  /api/markets/screener           shares across every exchange (exchange, sector, min_mcap_usd, q, sort)
  GET  /api/markets/search             listed shares matching a name or ticker
  GET  /api/markets/quote              one listing's latest quote (exchange, symbol)
  GET  /api/companies/directory        every company: listed shares and private companies (q, kind, country, sector)
  POST /api/markets/prices             latest closes for a list of holdings, and dollar rates
  GET  /api/cron/ingest                scheduled rolling feed -> deals and events, webhooks
  GET  /api/cron/market-snapshot       scheduled daily quotes, indices and FX
  GET  /api/cron/market-intraday       delayed intraday quotes during trading hours (JSE, NGX)
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import socket
import statistics
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from src.data import africa_countries as ac
from src.engines import company_profile, country_profile, coverage, country_risk, deals as deals_mod, investors, market_risk
from src.engines import research as research_mod, watch, official_sources

log = logging.getLogger("deal_intel.market")
router = APIRouter()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
API_SECRET = os.environ.get("DEAL_INTEL_API_SECRET", "")
CRON_SECRET = os.environ.get("CRON_SECRET", "")
PER_VISITOR_DAILY = int(os.environ.get("DEAL_INTEL_PER_VISITOR_DAILY", "1000"))
GLOBAL_DAILY = int(os.environ.get("DEAL_INTEL_GLOBAL_DAILY", "1000"))
APP_URL = os.environ.get("DEAL_INTEL_APP_URL", "").rstrip("/")
from src.engines.historical_backtest import SUMMARY_PATH as _BACKTEST_SUMMARY  # noqa: E402


def _configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY and API_SECRET)


def _authorized_cron(request: Request) -> bool:
    authorization = request.headers.get("authorization", "")
    if CRON_SECRET and authorization == f"Bearer {CRON_SECRET}":
        return True
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    try:
        import jwt
        from jwt import PyJWKClient
        client = PyJWKClient("https://token.actions.githubusercontent.com/.well-known/jwks")
        key = client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience="deal-intelligence-api", issuer="https://token.actions.githubusercontent.com")
        allowed_workflows = {
            "HenryMorganDibie/deal-intelligence-agent/.github/workflows/live-deal-ingestion.yml@refs/heads/main",
            "HenryMorganDibie/deal-intelligence-agent/.github/workflows/historical-backfill.yml@refs/heads/main",
            "HenryMorganDibie/deal-intelligence-agent/.github/workflows/review-labels-import.yml@refs/heads/main",
            "HenryMorganDibie/deal-intelligence-agent/.github/workflows/enrich-round-investors.yml@refs/heads/main",
            "HenryMorganDibie/deal-intelligence-agent/.github/workflows/market-snapshot.yml@refs/heads/main",
            "HenryMorganDibie/deal-intelligence-agent/.github/workflows/market-intraday.yml@refs/heads/main",
        }
        return (
            claims.get("repository") == "HenryMorganDibie/deal-intelligence-agent"
            and claims.get("ref") == "refs/heads/main"
            and claims.get("workflow_ref") in allowed_workflows
        )
    except Exception as exc:
        log.info("Cron OIDC token rejected: %s", type(exc).__name__)
        return False



def _headers() -> dict[str, str]:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}


def _rpc_sync(fn: str, args: dict, timeout: float = 30) -> httpx.Response:
    return httpx.post(f"{SUPABASE_URL}/rest/v1/rpc/{fn}", headers=_headers(), json={"secret": API_SECRET, **args},
                      timeout=timeout)


async def _rpc(client: httpx.AsyncClient, fn: str, args: dict) -> httpx.Response:
    return await client.post(f"{SUPABASE_URL}/rest/v1/rpc/{fn}", headers=_headers(), json={"secret": API_SECRET, **args})


_behavioral_interest_cache: tuple[float, dict[str, float]] | None = None


def _behavioral_interest_scores_from_stats(stats: dict) -> dict[str, float]:
    """Build conservative, smoothed interest scores; engagement never means factual verification."""
    scores: dict[str, float] = {}
    rows = stats.get("top_deals", []) if isinstance(stats, dict) else []
    if not isinstance(rows, list):
        return scores
    for row in rows:
        if not isinstance(row, dict):
            continue
        deal_id = str(row.get("deal_id") or "")
        try:
            impressions = max(0, int(row.get("impressions", 0)))
            unique_impression_visitors = max(0, int(row.get("unique_impression_visitors", 0)))
            unique_openers = max(0, int(row.get("unique_openers", 0)))
            int(row.get("opens", 0))  # a malformed row is skipped even though raw opens do not score
        except (TypeError, ValueError):
            continue
        # Require a small independent audience before engagement can influence ranking.
        if not deal_id or impressions < 5 or unique_impression_visitors < 3 or unique_openers < 2:
            continue
        # Use distinct visitors/openers so repeat clicks cannot masquerade as
        # independent votes; smoothing dampens small-audience CTR spikes.
        posterior_ctr = (min(unique_openers, unique_impression_visitors) + 1.0) / (unique_impression_visitors + 20.0)
        scores[deal_id] = min(1.0, posterior_ctr / 0.20)
    return scores


def _rerank_with_behavioral_interest(items: list[dict], interest: dict[str, float]) -> list[dict]:
    """Apply at most a 3% tie-breaking-style adjustment to existing relevance order."""
    if len(items) < 2 or not interest:
        return items
    denominator = max(1, len(items) - 1)
    ranked = sorted(
        enumerate(items),
        key=lambda pair: (
            0.97 * (1.0 - pair[0] / denominator)
            + 0.03 * interest.get(str(pair[1].get("id") or ""), 0.0),
            -pair[0],
        ),
        reverse=True,
    )
    return [item for _, item in ranked]


def _behavioral_interest_scores() -> dict[str, float]:
    """Read cached aggregate engagement through the existing Supabase RPC; fail open."""
    global _behavioral_interest_cache
    if not _configured():
        return {}
    now = time.monotonic()
    if _behavioral_interest_cache and now - _behavioral_interest_cache[0] < 300:
        return _behavioral_interest_cache[1]
    try:
        response = _rpc_sync("behavioral_signal_stats", {"p_days": 30}, timeout=4)
        if response.status_code != 200:
            raise RuntimeError(f"behavioural stats returned HTTP {response.status_code}")
        scores = _behavioral_interest_scores_from_stats(response.json())
        _behavioral_interest_cache = (now, scores)
        return scores
    except (httpx.HTTPError, ValueError, RuntimeError, TypeError) as exc:
        log.info("Behavioural ranking signals unavailable; retaining baseline order (%s)", type(exc).__name__)
        return {}


def _client_hash(request: Request) -> str:
    import hashlib
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
    return hashlib.sha256(f"{API_SECRET}:{ip}".encode()).hexdigest()[:32]


# ── Data store (Supabase when configured, local files otherwise), cached per instance ──

_TTL = 900  # Reduce repeated full-history RPC reads that can time out under load.
_cache: dict[str, tuple[float, list]] = {}


# Earliest month the store keeps and the product shows; backfills may reach back this far.
HISTORY_START = date(2010, 1, 1)


_RPC_PAGE_SIZE = 500
_RPC_MAX_PAGES = 100  # Safety stop: at most 50,000 records per full refresh.


def _load_rpc_pages(kind: str, since: str) -> list[dict]:
    """Load complete history with bounded keyset pages and a fixed ID upper bound."""
    function = "list_deals_page" if kind == "deals" else "list_events_page"
    rows: list[dict] = []
    after_id: str | None = None
    max_id: str | None = None
    for page in range(_RPC_MAX_PAGES):
        response = _rpc_sync(function, {
            "p_since": since,
            "p_limit": _RPC_PAGE_SIZE,
            "p_after_id": after_id,
            "p_max_id": max_id,
        })
        if response.status_code != 200:
            log.error("loading %s page %s failed: status=%s body=%s",
                      kind, page, response.status_code, response.text[:300])
            raise RuntimeError(f"{kind} page {page} returned HTTP {response.status_code}")
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
            raise ValueError(f"{kind} page {page} did not return a paginated object")
        page_max_id = payload.get("max_id")
        if page == 0:
            if page_max_id is not None and not isinstance(page_max_id, str):
                raise ValueError(f"{kind} page {page} returned an invalid max_id")
            max_id = page_max_id
        elif page_max_id != max_id:
            raise ValueError(f"{kind} page {page} changed the pagination upper bound")
        batch = payload["rows"]
        rows.extend(batch)
        if len(batch) < _RPC_PAGE_SIZE:
            date_key = "announced" if kind == "deals" else "day"
            # Preserve the API's historical newest-first ordering after fetching by stable ID.
            rows.sort(key=lambda row: (row.get(date_key) is not None, row.get(date_key) or ""), reverse=True)
            return rows
        last_id = batch[-1].get("id")
        if not isinstance(last_id, str) or (after_id is not None and last_id <= after_id):
            raise ValueError(f"{kind} page {page} did not advance the pagination cursor")
        after_id = last_id
    raise RuntimeError(f"{kind} exceeded the {_RPC_MAX_PAGES}-page safety limit")


def _load(kind: str) -> list[dict]:
    hit = _cache.get(kind)
    if hit and time.monotonic() - hit[0] < _TTL:
        return hit[1]
    rows: list[dict] = []
    if _configured():
        since = HISTORY_START.isoformat()
        try:
            rows = _load_rpc_pages(kind, since)
        except (httpx.HTTPError, ValueError, RuntimeError) as e:
            log.error("loading %s failed: %s", kind, e)
            if hit:
                return hit[1]
            raise HTTPException(503, f"Market data store is unavailable for {kind}.")
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
    """Deals the product shows; merged duplicates and excluded non-transactions stay stored for audit."""
    return [d for d in _load("deals") if deals_mod.is_visible(d)]


def _visible_events(rows: list[dict]) -> list[dict]:
    """Events the product shows: placed in an African market, not reviewed out of scope, and about a company
    (event_filters). Events with no country are mostly foreign stories the news search returned, and political
    or personal stories matched by a signal rule; both stay stored for audit."""
    from src.engines import headline_translate
    from src.engines.event_filters import is_corporate_event
    return [e for e in rows if not e.get("excluded") and not e.get("merged_into")
            and (e.get("country") or e.get("countries"))
            # An Arabic headline is judged by its English rendering; untranslated, only by a transaction rule.
            and is_corporate_event(e.get("headline_en") or e.get("headline") or "", e.get("signal_type"))
            and (e.get("headline_en") or not headline_translate.is_arabic(e.get("headline"))
                 or e.get("signal_type") in {"m_and_a_activity", "insider_activity"})]


def events() -> list[dict]:
    return _visible_events(_load("events"))


def _country_or_404(code: str) -> ac.Country:
    c = ac.get(code)
    if c is None:
        raise HTTPException(404, "Unknown country code. Use an ISO code such as NG, KE or SN.")
    return c


# ── Countries, currencies, coverage ───────────────────────────────────────────

_countries_cache: dict = {"key": None, "value": None}


@router.get("/api/countries")
async def countries() -> dict:
    ds, es = deals(), events()
    today = datetime.now(timezone.utc).date()
    # The table is a pass over every record for 54 countries; it is recomputed when the data or the day changes.
    key = (id(ds), len(ds), id(es), len(es), today)
    if _countries_cache["key"] == key:
        return _countries_cache["value"]
    first_year: dict[str, int] = {}
    recent: dict[str, int] = {}
    amounts: dict[str, list[float]] = {}
    unassigned = 0
    for d in ds:
        year = (d.get("announced") or "")[:4]
        isos = [i for i in (d.get("countries") or [d.get("country")]) if i]
        unassigned += not isos
        for iso in isos:
            if year.isdigit():
                first_year[iso] = min(first_year.get(iso, 9999), int(year))
            if country_profile.in_last_12_months(d.get("announced"), today):
                recent[iso] = recent.get(iso, 0) + 1
            if (d.get("amount_usd") or 0) > 0:
                amounts.setdefault(iso, []).append(float(d["amount_usd"]))
    rows = []
    for c in ac.COUNTRIES:
        risk = country_risk.assess(c, fx=lambda _: None)
        cov = coverage.country_row(c, ds, es)
        source_quality = official_sources.audit_country(c.iso2, ds, es)
        rows.append({"iso2": c.iso2, "name": c.name, "region": c.region, "currency": c.currency,
                     "exchange": c.exchange, "risk_score": risk["score"], "risk_tier": risk["tier"],
                     "risk_coverage": risk["coverage"], "coverage_tier": cov["tier"], "deals": cov["deals"],
                     "events": cov["events"], "deal_value_usd": cov["deal_value_usd"],
                     "first_year": first_year.get(c.iso2), "deals_last_12m": recent.get(c.iso2, 0),
                     "deals_with_amount": len(amounts.get(c.iso2, [])),
                     "median_disclosed_usd": round(statistics.median(amounts[c.iso2])) if amounts.get(c.iso2) else None,
                     "largest_disclosed_usd": round(max(amounts[c.iso2])) if amounts.get(c.iso2) else None,
                     "risk_partial": risk["partial"],
                     "source_quality": source_quality})
    value = {"countries": rows, "data_as_of": country_risk.load_snapshot().get("retrieved"),
             "history_start": f"{country_profile.HISTORY_START_YEAR}-01-01", "unassigned_deals": unassigned,
             "total_deals": len(ds),
             "notes": ["Deal value is the sum of disclosed amounts; a deal naming several countries counts in full "
                       "for each.", "Last 12 months is the current calendar month and the 11 before it."]}
    _countries_cache.update(key=key, value=value)
    return value


@router.get("/api/countries/{code}/history")
async def country_history(code: str, since: int = Query(1960, ge=1960, le=2100),
                          until: Optional[int] = Query(None, ge=1960, le=2100),
                          snapshots: int = Query(30, ge=1, le=365)) -> dict:
    """Annual reconstructed history plus archived daily snapshots where configured."""
    c = _country_or_404(code)
    history = country_risk.historical_scores(c, since=since, until=until)
    # Deal/event history begins with the earliest dated record currently held in the dataset,
    # not a claim that this is the earliest transaction that occurred in the country.
    all_deals, all_events = deals(), events()
    def belongs_to_country(record: dict) -> bool:
        raw = ([record.get("country")] if record.get("country") else []) + (record.get("countries") or [])
        for value in raw:
            resolved = ac.resolve(country=value)
            if resolved and resolved.iso2 == c.iso2:
                return True
        return False
    country_deals = [d for d in all_deals if belongs_to_country(d)]
    country_events = [e for e in all_events if belongs_to_country(e)]
    def _record_year(record: dict, keys: tuple[str, ...]) -> Optional[int]:
        for key in keys:
            value = record.get(key)
            if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
                year = int(value[:4])
                if 1900 <= year <= 2100:
                    return year
        return None
    deal_years = {id(d): _record_year(d, ("announced", "date", "published")) for d in country_deals}
    event_years = {id(e): _record_year(e, ("day", "date", "announced", "published", "timestamp")) for e in country_events}
    first_years = [y for y in [*deal_years.values(), *event_years.values()] if y is not None]
    activity_start = min(first_years) if first_years else None
    activity_end = max(first_years) if first_years else None
    activity = []
    # Return only years with dated records. An absent year is unknown coverage, not zero activity.
    activity_years = sorted({y for y in [*deal_years.values(), *event_years.values()] if y is not None})
    if activity_years:
        for year in activity_years:
            yd = [d for d in country_deals if deal_years[id(d)] == year]
            ye = [e for e in country_events if event_years[id(e)] == year]
            audit = official_sources.audit_country(c.iso2, yd, ye)
            activity.append({
                "year": year,
                "deal_records": len(yd),
                "event_records": len(ye),
                "disclosed_deal_value_usd": round(sum(float(d.get("amount_usd") or 0) for d in yd)),
                "deals_with_official_host": audit["deal_records_with_official_host"],
                "events_with_official_host": audit["event_records_with_official_host"],
                "source_links_checked": audit["source_links_checked"],
                "official_host_matched_links": audit["official_host_matched_links"],
                "dated_records": len(yd) + len(ye),
            })
    archived = []
    if _configured():
        try:
            r = _rpc_sync("list_country_risk_snapshots", {"p_iso2": c.iso2, "p_limit": 1})
            if r.status_code == 200:
                archived = r.json() or []
            else:
                log.warning("country snapshot history unavailable: %s %s", r.status_code, r.text[:200])
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("country snapshot history unavailable: %s", type(exc).__name__)
    return {**history, "archived_snapshots": archived,
            "market_activity": activity,
            "market_activity_start_year": activity_start,
            "market_activity_end_year": activity_end,
            "market_activity_note": "Counts reflect dated records currently present in the product database, not a complete census of transactions. Earlier years with no row may reflect missing historical coverage rather than zero activity. Amounts include disclosed/normalized values only and do not estimate undisclosed deals.",
            "snapshot_note": "No archived snapshots have been captured yet. The annual series is a reconstruction from currently available historical source observations, not a stored history of what the product knew at each past date."}


@router.get("/api/countries/{code}")
async def country(code: str) -> dict:
    c = _country_or_404(code)
    ds, es = deals(), events()
    return {
        "country": {k: getattr(c, k) for k in ("iso2", "iso3", "name", "region", "languages", "currency", "exchange",
                                               "yahoo_suffix", "central_bank", "securities_regulator")},
        "risk": await run_in_threadpool(country_risk.assess, c),
        "current_signals": await run_in_threadpool(country_risk.current_macro_signals, c),
        "currency": await run_in_threadpool(market_risk.currency_risk, c.currency),
        "coverage": coverage.country_row(c, ds, es),
        "source_quality": official_sources.audit_country(c.iso2, ds, es),
        "deals": deals_mod.search(ds, country=c.iso2, limit=25),
        "deals_total": len(deals_mod.search(ds, country=c.iso2, limit=max(len(ds), 1))),
        "events": sorted([e for e in es if c.iso2 in (e.get("countries") or [e.get("country")])],
                         key=lambda e: e.get("day") or "", reverse=True)[:25],
        "events_total": sum(1 for e in es if c.iso2 in (e.get("countries") or [e.get("country")])),
        "investors": investors.leaderboard(deals_mod.search(ds, country=c.iso2, limit=5000), limit=10),
        "profile": country_profile.build(c.iso2, ds, es, today=datetime.now(timezone.utc).date()),
        "history_start": HISTORY_START.isoformat(),
    }


@router.get("/api/currencies")
async def currencies() -> dict:
    return {"currencies": market_risk.all_currencies()}


@router.get("/api/coverage")
async def coverage_matrix() -> dict:
    return {**coverage.matrix(deals(), events()), "history_start": HISTORY_START.isoformat()}


# ── Deals, comparables, investors, funds, events ──────────────────────────────

@router.get("/api/deals")
async def deal_search(q: str = "", country: Optional[str] = None, type: Optional[str] = None,
                      sector: Optional[str] = None, investor: Optional[str] = None, since: Optional[str] = None,
                      until: Optional[str] = None, min_usd: Optional[float] = None,
                      limit: int = Query(50, ge=1, le=100),
                      offset: int = Query(0, ge=0, le=100000)) -> dict:
    country = _country_or_404(country).iso2 if country else None
    ds = deals()
    # The store is already cached in memory. Filter before slicing so pagination
    # covers the complete matching result set rather than only the first page.
    matching = deals_mod.search(ds, q=q, country=country, deal_type=type, sector=sector, since=since, until=until,
                                investor=investor, min_usd=min_usd, limit=max(len(ds), 1))
    # Engagement may make only a small, evidence-gated adjustment to the existing
    # relevance order. It never changes deal facts or verification labels.
    interest = await run_in_threadpool(_behavioral_interest_scores)
    matching = _rerank_with_behavioral_interest(matching, interest)
    total_matching = len(matching)
    rows = matching[offset:offset + limit]
    from src.engines import provenance
    out = []
    for d in rows:
        n = len(provenance.stories(d.get("sources") or []))
        out.append({**d, "independent_stories": n,
                    "verification": "corroborated" if n >= 2 else "single source"})
    return {"total_in_database": len(ds), "total_matching": total_matching, "offset": offset,
            "limit": limit, "count": len(out), "deals": out}


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
    stored = {d.get("id"): d for d in _load("deals")}
    d = stored.get(deals_mod.canonical_id(deal_id, stored))
    if d is None or not deals_mod.is_visible(d):
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
    country = _country_or_404(country).iso2 if country else None
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
                         sector: Optional[str] = None, country: Optional[str] = None, stage: Optional[str] = None,
                         type: Optional[str] = None, since: Optional[str] = None, until: Optional[str] = None,
                         min_usd: Optional[float] = Query(None, ge=0), max_usd: Optional[float] = Query(None, ge=0),
                         lead_only: bool = False,
                         limit: int = Query(50, ge=1, le=100),
                         offset: int = Query(0, ge=0, le=100000)) -> dict:
    """Investor screener: parties ranked on the deals that match the filters (sector, country, round stage,
    deal type, dates, round size), optionally only those that led a round."""
    if country:
        # The screener accepts a name ("Kenya", "Ivory Coast") as well as an ISO code.
        named = ac.get(country) or next(iter(ac.countries_in_text(country)), None)
        country = (named or _country_or_404(country)).iso2
    scope = investors.filter_deals(deals(), sector=sector, country=country, stage=stage, deal_type=type,
                                   since=since, until=until, min_usd=min_usd, max_usd=max_usd)
    matching = investors.leaderboard(scope, role=role, kind=kind, lead_only=lead_only,
                                     limit=max(len(scope) * 2, 1000))
    total_matching = len(matching)
    return {"investors": matching[offset:offset + limit], "total_matching": total_matching,
            "offset": offset, "limit": limit, "deals_in_scope": len(scope),
            "registry": [{"name": i.name, "type": i.kind, "hq": i.hq, "aliases": list(i.aliases)}
                         for i in investors.REGISTRY]}


@router.get("/api/investors/{name}")
async def investor(name: str) -> dict:
    ds = deals()
    p = investors.profile(ds, name)
    if p is not None:
        p = {**p, "portfolio": investors.portfolio(ds, p["name"])[:40],
             "fund_lifecycle": investors.fund_lifecycle(ds, p["name"])}
    if p is None:
        entry = investors.registry_entry(name)
        if entry is None:
            raise HTTPException(404, "No deals found for this investor.")
        p = {"name": entry.name, "type": entry.kind, "hq": entry.hq, "in_registry": True, "deal_count": 0,
             "roles": {}, "recent": []}
    return p


@router.get("/api/funds")
async def funds(limit: int = Query(50, ge=1, le=100),
                     offset: int = Query(0, ge=0, le=100000)) -> dict:
    matching = investors.funds(deals())
    return {"funds": matching[offset:offset + limit], "total_matching": len(matching),
            "offset": offset, "limit": limit}


@router.get("/api/events")
async def event_feed(country: Optional[str] = None, type: Optional[str] = None, since: Optional[str] = None,
                     q: str = "", limit: int = Query(100, ge=1, le=500),
                     offset: int = Query(0, ge=0, le=100000)) -> dict:
    rows = events()
    c = _country_or_404(country) if country else None
    out = [e for e in rows
           if (not c or c.iso2 in (e.get("countries") or [e.get("country")]))
           and (not type or e.get("signal_type") == type)
           and (not since or (e.get("day") or "") >= since)
           and (not q or q.lower() in f'{e.get("headline", "")} {e.get("headline_en") or ""}'.lower())]
    out.sort(key=lambda e: e.get("day") or "", reverse=True)
    page = [{**e, "measured": event_measures(e.get("signal_type"))} for e in out[offset:offset + limit]]
    return {"count": len(out), "offset": offset, "limit": limit, "events": page}


_measures_cache: dict[str, tuple[float, Optional[dict]]] = {}


def event_measures(signal_type: Optional[str]) -> Optional[dict]:
    """How this kind of event has played out: its graded track record in African markets (how often such a flag
    was followed by confirmation, against the base rate) and the measured market-adjusted 10-day share-price
    move after it. Graded on the type, since stored events carry no severity."""
    if not signal_type:
        return None
    hit = _measures_cache.get(signal_type)
    if hit and time.monotonic() - hit[0] < _LIVE_TTL:
        return hit[1]
    from src.engines import measured
    try:
        record = measured.track_record(signal_type, "", None, "africa")
        move = measured.expected_move(signal_type, "")
    except Exception:
        log.exception("measured lookup failed for %s", signal_type)
        return None
    out = {"grade": record.get("grade"), "label": record.get("label"), "lift": record.get("lift"),
           "n": record.get("n"), "basis": record.get("basis"), "graded_on": record.get("graded_on"),
           "move_10d": move and {k: move.get(k) for k in ("median", "p25", "p75", "n", "share_negative")}}
    _measures_cache[signal_type] = (time.monotonic(), out)
    return out


@router.get("/api/sectors/{sector}/risk")
async def sector_risk(sector: str, country: Optional[str] = None, days: int = Query(90, ge=7, le=730)) -> dict:
    if sector not in {s for s, _ in deals_mod.SECTORS}:
        raise HTTPException(404, f"Unknown sector. Choose from: {', '.join(s for s, _ in deals_mod.SECTORS)}.")
    country = _country_or_404(country).iso2 if country else None
    return market_risk.sector_risk(sector, events(), deals(), country=country, days=days)


# ── Companies and valuation ───────────────────────────────────────────────────

_profile_cache: dict[tuple, tuple[float, dict]] = {}


def _listing_for(name: str, ticker: Optional[str], country: Optional[str]) -> Optional[dict]:
    """The company's quote in the latest market snapshot: by ticker when one is given, else by name."""
    from src.engines import markets
    try:
        snap = _market_snapshot()
    except HTTPException:
        return None
    if ticker:
        exchange = company_profile.exchange_of(ticker)
        hit = markets.quote(snap, exchange, ticker) if exchange else None
        if hit or exchange:
            return hit
        # A bare symbol: the country's exchange, if the symbol is listed there.
        return next((r for r in markets.search(snap, ticker, limit=5)
                     if r["symbol"] == ticker.upper() and (not country or r["country"] == country.upper())), None)
    return markets.resolve(snap, name, country)


@router.get("/api/companies/profile")
async def company(name: str = Query(..., min_length=1, max_length=120), ticker: Optional[str] = None,
                  country: Optional[str] = None, cik: Optional[int] = None,
                  exchange: Optional[str] = Query(None, max_length=8), symbol: Optional[str] = Query(None, max_length=20)) -> dict:
    """A company's profile. `exchange` and `symbol` name a listing in the market snapshot exactly (the markets
    pages link this way); otherwise a ticker or the name is resolved against it."""
    if country:                                      # an ISO code or a country name ("Kenya")
        found = ac.get(country) or next(iter(ac.countries_in_text(country)), None)
        # A market outside Africa (e.g. "United States") is not an error: the listing is found from the ticker.
        country = found.iso2 if found else None
    key = (name.lower(), (ticker or "").upper(), (country or "").upper(), cik, (exchange or "").lower(),
           (symbol or "").upper())
    hit = _profile_cache.get(key)
    if hit and time.monotonic() - hit[0] < 6 * 3600:
        return hit[1]
    if exchange and symbol:
        from src.engines import markets
        snap = await run_in_threadpool(_market_snapshot)
        listing = markets.quote(snap, exchange.lower(), symbol)
    else:
        listing = await run_in_threadpool(_listing_for, name, ticker, country)
    profile = await run_in_threadpool(company_profile.build, name, ticker.upper() if ticker else None, country,
                                      deals(), cik, None, listing)
    profile["valuation"] = market_risk.valuation_view(profile.get("name") or name, deals(), profile)
    mark = profile["valuation"].get("latest_mark")
    if mark and not profile.get("listing"):
        from src.engines import markets
        own = [d for d in deals() if deals_mod.normalise_name(d.get("target")) == deals_mod.normalise_name(profile.get("name") or name)]
        sector = next((d.get("sector") for d in sorted(own, key=lambda d: d.get("announced") or "", reverse=True)
                       if d.get("sector")), None)
        try:
            snap = await run_in_threadpool(_market_snapshot)
            profile["valuation"]["public_bridge"] = markets.valuation_bridge(
                snap, mark.get("valuation_usd"), sector, profile.get("country") or next((d.get("country") for d in own if d.get("country")), None),
                mark.get("announced"))
        except HTTPException:
            pass
    _profile_cache[key] = (time.monotonic(), profile)
    return profile


@router.get("/api/valuation/cost-of-equity")
async def valuation_cost_of_equity(country: str = Query(..., min_length=2, max_length=60)) -> dict:
    """A transparent cost of equity for valuing a company in this country (dollar and local currency)."""
    return market_risk.cost_of_equity(_country_or_404(country))


class EvidenceBody(BaseModel):
    company: str = Field(..., min_length=1, max_length=120)
    ticker: str = Field("", max_length=24)
    country: str = Field("", max_length=60)
    exchange: str = Field("", max_length=8)
    symbol: str = Field("", max_length=20)
    method: Literal["dcf", "ddm"] = "dcf"
    currency: str = Field("", max_length=3)
    period: str = Field("", max_length=10)
    source: str = Field("", max_length=1000)
    price: Optional[float] = None
    price_date: str = Field("", max_length=10)
    price_source: str = Field("", max_length=1000)
    shares: Optional[float] = None
    fcf: Optional[float] = None
    cash: Optional[float] = None
    debt: Optional[float] = None
    dividend_per_share: Optional[float] = None


@router.post("/api/valuation/evidence")
async def valuation_evidence(body: EvidenceBody) -> dict:
    """Checks each valuation input against the exchange's data, the parsed filing and the cited document."""
    import asyncio
    from src.engines import markets, valuation_evidence as ve
    if body.exchange and body.symbol:
        listing = markets.quote(await run_in_threadpool(_market_snapshot), body.exchange.lower(), body.symbol)
    else:
        listing = await run_in_threadpool(_listing_for, body.company, body.ticker or None, body.country or None)
    profile: dict = {}
    try:                                                # usually cached: the page has just loaded this profile
        profile = await asyncio.wait_for(company(name=body.company, ticker=body.ticker or None,
                                                 country=body.country or None, cik=None,
                                                 exchange=body.exchange or None, symbol=body.symbol or None), timeout=40)
    except (asyncio.TimeoutError, HTTPException):
        pass
    inputs = body.model_dump()
    return await run_in_threadpool(lambda: ve.check(inputs, listing, profile.get("financials"),
                                                    (profile.get("identity") or {}).get("website")))


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


class ResultFeedbackBody(BaseModel):
    result_type: Literal["brief", "research", "country_report", "sector_report"]
    result_id: uuid.UUID
    category: Literal[
        "incorrect_signal", "wrong_company", "missed_event",
        "unsupported_claim", "outdated_data", "other",
    ]
    note: str = Field("", max_length=1000)

    @field_validator("note")
    @classmethod
    def strip_note(cls, value: str) -> str:
        return value.strip()


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
    try:
        result = await run_in_threadpool(research_mod.research, body.question, deals(), events())
    finally:
        await _finish(run_id)
    return {**result, "result_id": str(uuid.uuid4())}


@router.post("/api/reports/country/{code}")
async def country_report(code: str, request: Request) -> dict:
    c = _country_or_404(code)
    run_id = await _reserve(request, f"[report] country {c.iso2}")
    try:
        result = await run_in_threadpool(research_mod.country_report, c.iso2, deals(), events())
    finally:
        await _finish(run_id)
    return {**result, "result_id": str(uuid.uuid4())}


@router.post("/api/reports/sector/{sector}")
async def sector_report(sector: str, request: Request, country: Optional[str] = None) -> dict:
    if sector not in {s for s, _ in deals_mod.SECTORS}:
        raise HTTPException(404, "Unknown sector.")
    country = _country_or_404(country).iso2 if country else None
    run_id = await _reserve(request, f"[report] sector {sector} {country or ''}")
    try:
        result = await run_in_threadpool(research_mod.sector_report, sector, deals(), events(), country)
    finally:
        await _finish(run_id)
    return {**result, "result_id": str(uuid.uuid4())}


@router.post("/api/feedback", status_code=201)
async def submit_result_feedback(body: ResultFeedbackBody, request: Request) -> dict:
    if not _configured():
        raise HTTPException(503, "Feedback is not configured.")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await _rpc(client, "submit_result_feedback", {
            "p_client_hash": _client_hash(request),
            "p_result_type": body.result_type,
            "p_result_id": str(body.result_id),
            "p_category": body.category,
            "p_note": body.note,
        })
    if not r.is_success:
        if "feedback_limit" in r.text:
            raise HTTPException(429, "Feedback limit reached. Please try again tomorrow.")
        log.error("submit_result_feedback failed: %s %s", r.status_code, r.text[:300])
        raise HTTPException(502, "Feedback could not be saved.")
    return {"id": r.json(), "status": "received"}


@router.post("/api/admin/feedback")
async def admin_feedback(request: Request) -> dict:
    import hmac
    try:
        body = await request.json()
    except ValueError:
        body = {}
    key = str(body.get("key", ""))
    if not (ADMIN_KEY and _configured() and hmac.compare_digest(key, ADMIN_KEY)):
        raise HTTPException(status_code=401, detail="Wrong key")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await _rpc(client, "list_result_feedback", {"p_limit": 100})
    if not r.is_success:
        log.error("list_result_feedback failed: %s %s", r.status_code, r.text[:300])
        raise HTTPException(502, "Feedback is unavailable.")
    return {"items": r.json()}


@router.post("/api/admin/feedback/{feedback_id}/review")
async def review_result_feedback(feedback_id: str, request: Request) -> dict:
    import hmac
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request body.")
    try:
        parsed_id = uuid.UUID(feedback_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Feedback not found.")
    key = str(body.get("key", ""))
    if not (ADMIN_KEY and _configured() and hmac.compare_digest(key, ADMIN_KEY)):
        raise HTTPException(status_code=401, detail="Wrong key")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await _rpc(client, "review_result_feedback", {"p_feedback_id": str(parsed_id)})
    if not r.is_success:
        log.error("review_result_feedback failed: %s %s", r.status_code, r.text[:300])
        raise HTTPException(502, "Feedback could not be updated.")
    return {"reviewed": r.json() is True}


# ── Watchlists and alerts ─────────────────────────────────────────────────────

class WatchlistBody(BaseModel):
    name: str = Field("Watchlist", max_length=80)
    companies: list[str] = Field(default_factory=list, max_length=50)
    countries: list[str] = Field(default_factory=list, max_length=54)
    signal_types: list[str] = Field(default_factory=list, max_length=8)
    include_deals: bool = True
    webhook_url: Optional[str] = Field(None, max_length=500)
    delivery_frequency: Literal["daily", "weekly"] = "daily"

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



class AlertReviewBody(BaseModel):
    alert_key: str = Field(..., min_length=3, max_length=300)
    state: Literal["unreviewed", "reviewed", "dismissed"]

    @field_validator("alert_key")
    @classmethod
    def validate_alert_key(cls, value: str) -> str:
        if not re.match(r"^(event|deal):.+$", value):
            raise ValueError("alert_key must start with event: or deal:")
        return value


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
            "p_webhook_url": body.webhook_url, "p_delivery_frequency": body.delivery_frequency})
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
    if not r.is_success:
        log.error("get_watchlist failed: %s %s", r.status_code, r.text[:300])
        raise HTTPException(502, "The watchlist could not be loaded.")
    rows = r.json()
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
    alerts = watch.matches(wl, events(), deals(), since=since)
    return {"watchlist": wl, "alerts": alerts, "quality": watch.quality_metrics(alerts)}


@router.get("/api/watchlists/{wl_id}/reviews")
async def list_watchlist_reviews(wl_id: str) -> dict:
    await _get_watchlist(wl_id)
    async with httpx.AsyncClient(timeout=15) as client:
        response = await _rpc(client, "list_watchlist_reviews", {"p_id": wl_id})
    if not response.is_success:
        log.warning("list_watchlist_reviews failed: %s %s", response.status_code, response.text[:300])
        raise HTTPException(502, "Alert review state could not be loaded.")
    return {"reviews": response.json() or []}


@router.post("/api/watchlists/{wl_id}/reviews")
async def save_watchlist_review(wl_id: str, body: AlertReviewBody) -> dict:
    await _get_watchlist(wl_id)
    async with httpx.AsyncClient(timeout=15) as client:
        response = await _rpc(client, "upsert_watchlist_review", {
            "p_id": wl_id, "p_alert_key": body.alert_key, "p_state": body.state
        })
    if not response.is_success:
        log.warning("upsert_watchlist_review failed: %s %s", response.status_code, response.text[:300])
        raise HTTPException(502, "Alert review state could not be saved.")
    return {"saved": True, "alert_key": body.alert_key, "state": body.state}


@router.get("/api/watchlists/{wl_id}/feed.xml")
async def watchlist_feed(wl_id: str) -> Response:
    wl = await _get_watchlist(wl_id)
    since = (date.today() - timedelta(days=90)).isoformat()
    xml = watch.rss(wl, watch.matches(wl, events(), deals(), since=since), _watch_link(wl_id))
    return Response(xml, media_type="application/rss+xml")


@router.get("/api/watchlists/{wl_id}/delivery")
async def watchlist_delivery_history(wl_id: str) -> dict:
    await _get_watchlist(wl_id)
    async with httpx.AsyncClient(timeout=15) as client:
        response = await _rpc(client, "latest_watchlist_delivery", {"p_id": wl_id})
    if not response.is_success:
        log.warning("latest_watchlist_delivery failed: %s %s", response.status_code, response.text[:300])
        raise HTTPException(502, "Webhook delivery history could not be loaded.")
    return {"deliveries": response.json() or []}


@router.delete("/api/watchlists/{wl_id}")
async def delete_watchlist(wl_id: str) -> dict:
    await _get_watchlist(wl_id)
    async with httpx.AsyncClient(timeout=15) as client:
        r = await _rpc(client, "remove_watchlist", {"p_id": wl_id})
    if not r.is_success:
        log.error("remove_watchlist failed: %s %s", r.status_code, r.text[:300])
        raise HTTPException(502, "The watchlist could not be deleted.")
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
# Where a session landed from: the referring site's host (never a full URL) and campaign tags.
_REFERRER_HOST = re.compile(r"^[a-z0-9.-]{1,100}$")
_UTM_VALUE = re.compile(r"^[A-Za-z0-9._+-]{1,60}$")
_EVENT_ID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_PRODUCT_ACTIONS = {
    "deals_loaded", "investors_loaded", "events_loaded", "risk_data_loaded",
    "company_data_loaded", "watchlists_used", "brief_opened", "performance_data_loaded",
    "deal_search_submitted", "deal_opened", "research_submitted", "market_brief_opened", "deal_impression",
}


@router.post("/api/track")
async def track_visit(request: Request) -> dict:
    """Record a page view or successful app feature response from the site's beacon."""
    try:
        body = json.loads((await request.body())[:1000] or b"{}")
        visitor = str(body.get("v", ""))
        path = str(body.get("p", ""))
        action = str(body.get("a", ""))
        target_id = str(body.get("t", ""))[:160]
        event_id = str(body.get("e", ""))
        source = {k: str(body.get(k) or "") for k in ("r", "us", "um", "uc")}
        context_raw = body.get("c", "{}")
        context = json.loads(context_raw) if isinstance(context_raw, str) else context_raw
    except (ValueError, AttributeError):
        return {"ok": False}
    if not (_configured() and _VISITOR.fullmatch(visitor)):
        return {"ok": False}
    if path and not (path.startswith("/") and len(path) <= 200):
        return {"ok": False}
    if action and action not in _PRODUCT_ACTIONS:
        return {"ok": False}
    if not path and not action:
        return {"ok": False}
    if context is None or not isinstance(context, dict) or len(json.dumps(context)) > 1200:
        return {"ok": False}
    if target_id and any(ord(ch) < 32 for ch in target_id):
        return {"ok": False}
    async with httpx.AsyncClient(timeout=10) as client:
        if path:
            r = await _rpc(client, "log_visit_with_source", {
                "p_visitor": visitor, "p_path": path.split("?")[0],
                "p_referrer": source["r"].lower() if _REFERRER_HOST.fullmatch(source["r"].lower()) else None,
                **{f"p_utm_{name}": source[k] if _UTM_VALUE.fullmatch(source[k]) else None
                   for k, name in (("us", "source"), ("um", "medium"), ("uc", "campaign"))},
            })
            if not r.is_success:
                return {"ok": False}
        if action:
            r = await _rpc(client, "log_product_action", {"p_visitor": visitor, "p_action": action})
            if not r.is_success:
                return {"ok": False}
            if action in {"deal_search_submitted", "deal_opened", "research_submitted", "market_brief_opened", "deal_impression"}:
                r = await _rpc(client, "log_behavioral_event", {
                    "p_event_type": action,
                    "p_visitor": visitor,
                    "p_target_id": target_id or None,
                    "p_context": context,
                    # A malformed id from an old or misbehaving client must not reject the event.
                    "p_event_id": event_id if _EVENT_ID.fullmatch(event_id) else None,
                })
                if not r.is_success:
                    return {"ok": False}
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
    visitor = body.get("visitor")
    if visitor is not None and (not isinstance(visitor, str) or not _VISITOR.fullmatch(visitor)):
        raise HTTPException(status_code=422, detail="Invalid browser ID")
    days = max(1, min(int(body.get("days", 30) or 30), 365))
    async with httpx.AsyncClient(timeout=15) as client:
        r = await _rpc(client, "visit_stats", {
            "p_days": days, "p_excluded_visitor": visitor,
            "p_excluded_client_hash": _client_hash(request),
        })
        if not r.is_success:
            raise HTTPException(status_code=502, detail="Stats unavailable")
        stats = r.json()
        behavioral = await _rpc(client, "behavioral_signal_stats", {"p_days": days})
        stats["behavioral_signals"] = behavioral.json() if behavioral.is_success else {"status": "unavailable"}
        return stats


# ── Independent review labelling ─────────────────────────────────────────────

def _review_token_hash(token: str) -> str:
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


def _admin_key_ok(body: dict) -> bool:
    import hmac
    return bool(ADMIN_KEY and _configured() and hmac.compare_digest(str(body.get("key", "")), ADMIN_KEY))


def _review_sample(year: int) -> tuple[list[dict], list[dict]]:
    folder = _REVIEW / str(year)
    read = lambda name: [json.loads(line) for line in (folder / name).read_text().splitlines() if line.strip()]  # noqa: E731
    try:
        return read("items.jsonl"), read("pairs.jsonl")
    except OSError:
        raise HTTPException(status_code=404, detail="No review sample for that year.")


async def _review_body(request: Request) -> dict:
    try:
        body = json.loads((await request.body())[:20000] or b"{}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request body.")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid request body.")
    return body


@router.post("/api/admin/review/annotators")
async def review_create_link(request: Request) -> dict:
    """Create a private labelling link for annotator A, annotator B or the adjudicator (owner only)."""
    import secrets
    body = await _review_body(request)
    if not _admin_key_ok(body):
        raise HTTPException(status_code=401, detail="Wrong key")
    role, name = str(body.get("role", "")), " ".join(str(body.get("name", "")).split())[:80]
    year = int(body.get("year") or (_review_years() or [0])[0])
    if role not in ("a", "b", "adjudicator") or not name or year not in _review_years():
        raise HTTPException(status_code=422, detail="Choose a role, a name and a year with a drawn sample.")
    token = secrets.token_urlsafe(24)
    async with httpx.AsyncClient(timeout=15) as client:
        r = await _rpc(client, "review_create_annotator", {"p_token_hash": _review_token_hash(token), "p_year": year,
                                                          "p_role": role, "p_name": name})
    if not r.is_success:
        raise HTTPException(status_code=502, detail="The link could not be created.")
    return {"token": token, "year": year, "role": role, "name": name, "path": f"/review?t={token}"}


@router.post("/api/review/session")
async def review_session(request: Request) -> dict:
    """What a labelling link may see: the blind sample, the guide and the holder's own labels.
    The adjudicator also receives both annotators' labels. Never the system's decisions."""
    body = await _review_body(request)
    token = str(body.get("token", ""))
    if not (_configured() and 20 <= len(token) <= 64):
        raise HTTPException(status_code=401, detail="This labelling link is not valid.")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await _rpc(client, "review_session", {"p_token_hash": _review_token_hash(token)})
    session = r.json() if r.is_success else None
    if not session:
        raise HTTPException(status_code=401, detail="This labelling link is not valid or has been withdrawn.")
    items, pairs = _review_sample(session["year"])
    manifest = _read_json(_REVIEW / str(session["year"]) / "manifest.json") or {}
    return {**session, "items": items, "pairs": pairs, "guidelines_md": manifest.get("guidelines_md")}


@router.post("/api/review/label")
async def review_save(request: Request) -> dict:
    from src.engines import review_labels
    body = await _review_body(request)
    token, kind, item_id = str(body.get("token", "")), str(body.get("kind", "")), str(body.get("item_id", ""))
    pattern = review_labels.ITEM_ID if kind == "item" else review_labels.PAIR_ID if kind == "pair" else None
    if not (_configured() and 20 <= len(token) <= 64 and pattern and pattern.fullmatch(item_id)):
        raise HTTPException(status_code=422, detail="Invalid label request.")
    try:
        label = (review_labels.clean_item if kind == "item" else review_labels.clean_pair)(body.get("label") or {})
    except review_labels.LabelError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    async with httpx.AsyncClient(timeout=15) as client:
        r = await _rpc(client, "review_save_label", {"p_token_hash": _review_token_hash(token), "p_kind": kind,
                                                    "p_item_id": item_id, "p_label": label})
    if not r.is_success:
        raise HTTPException(status_code=502, detail="The label could not be saved; try again.")
    if r.json() is not True:
        raise HTTPException(status_code=401, detail="This labelling link is not valid or has been withdrawn.")
    return {"saved": True, "label": label}


def _review_export_files(year: int) -> dict[str, str]:
    from src.engines import review_labels
    items, pairs = _review_sample(year)
    r = _rpc_sync("review_export", {"p_year": year}, timeout=30)
    if not r.is_success:
        raise HTTPException(status_code=502, detail="Labels unavailable.")
    files = review_labels.to_files(r.json() or [], [i["item_id"] for i in items], [p["item_id"] for p in pairs])
    return {name: "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows) for name, rows in files.items()}


@router.post("/api/admin/review/export")
async def review_export_admin(request: Request) -> dict:
    body = await _review_body(request)
    if not _admin_key_ok(body):
        raise HTTPException(status_code=401, detail="Wrong key")
    year = int(body.get("year") or (_review_years() or [0])[0])
    return {"year": year, "files": await run_in_threadpool(_review_export_files, year)}


@router.get("/api/cron/review-export")
async def review_export_cron(request: Request, year: Optional[int] = Query(None, ge=2020, le=2100)) -> dict:
    """The scheduled import workflow pulls the labels here and commits them next to the sample."""
    if not _authorized_cron(request):
        raise HTTPException(status_code=401, detail="Scheduled workflow authorization required.")
    year = year or (_review_years() or [0])[0]
    return {"year": year, "files": await run_in_threadpool(_review_export_files, year)}


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
    out = pulse.build(rows_d, rows_e, summary, today=datetime.now(timezone.utc).date())
    for card in out["events"]["latest"]:
        card["measured"] = event_measures(card.get("signal_type"))
    return out


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
_REVIEW = _ROOT / "evaluation" / "review"
_REVIEW_FILES = {
    "items.jsonl": "items.jsonl", "pairs.jsonl": "pairs.jsonl",
    "labels_template.jsonl": "labels_a.jsonl", "pair_labels_template.jsonl": "pair_labels_a.jsonl",
}


def _review_years() -> list[int]:
    """Years with a drawn review sample, newest first; a new year appears once its folder is committed."""
    try:
        return sorted((int(p.name) for p in _REVIEW.iterdir() if p.name.isdigit() and (p / "manifest.json").exists()),
                      reverse=True)
    except OSError:
        return []


def _review_downloads() -> dict[str, tuple[str, str]]:
    out = {}
    for year in _review_years():
        for public, local in _REVIEW_FILES.items():
            out[f"review_{year}_{public}"] = (f"evaluation/review/{year}/{local}", "application/x-ndjson")
        out[f"review_{year}_guidelines.md"] = ("evaluation/review/GUIDELINES.md", "text/markdown")
    return out


def _filled(path: Path, key: str) -> int:
    """Rows an annotator has completed: signed and with the main judgement made."""
    try:
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    except (OSError, ValueError):
        return 0
    return sum(1 for r in rows if r.get("annotator") and r.get(key) is not None)


_review_progress_cache: dict[int, tuple[float, dict]] = {}


def _review_live_progress(year: int) -> dict:
    cached = _review_progress_cache.get(year)
    if cached and time.time() - cached[0] < 120:
        return cached[1]
    live: dict = {}
    if _configured():
        try:
            r = _rpc_sync("review_progress", {"p_year": year}, timeout=8)
            live = r.json() if r.is_success and isinstance(r.json(), dict) else {}
        except (httpx.HTTPError, ValueError):
            live = {}
    _review_progress_cache[year] = (time.time(), live)
    return live


def _review_status(year: int) -> Optional[dict]:
    """Progress of one year's independent review; scores are published only once it is complete."""
    folder = _REVIEW / str(year)
    manifest = _read_json(folder / "manifest.json")
    if not manifest:
        return None
    live = _review_live_progress(year)
    progress = {
        "labels_a": _filled(folder / "labels_a.jsonl", "is_transaction"),
        "labels_b": _filled(folder / "labels_b.jsonl", "is_transaction"),
        "pair_labels_a": _filled(folder / "pair_labels_a.jsonl", "same_transaction"),
        "pair_labels_b": _filled(folder / "pair_labels_b.jsonl", "same_transaction"),
        "adjudicated": _filled(folder / "adjudicated_labels.jsonl", "is_transaction"),
        "adjudicated_pairs": _filled(folder / "adjudicated_pair_labels.jsonl", "same_transaction"),
    }
    # Labels entered on the labelling page count as soon as they are saved, before the import commits them.
    for key, live_key in (("labels_a", "a:item"), ("labels_b", "b:item"), ("pair_labels_a", "a:pair"),
                          ("pair_labels_b", "b:pair")):
        progress[key] = max(progress[key], int(live.get(live_key) or 0))
    labelled = (progress["labels_a"] == progress["labels_b"] == manifest["items"]
                and progress["pair_labels_a"] == progress["pair_labels_b"] == manifest["pairs"])
    resolved = progress["adjudicated"] == manifest["items"] and progress["adjudicated_pairs"] == manifest["pairs"]
    status = ("complete" if labelled and resolved else
              "labelled, awaiting adjudication" if labelled else "awaiting independent labels")
    manifest = {k: v for k, v in manifest.items() if k != "guidelines_md"}
    results = {}
    for source in ("independent", "automated"):
        scored = _read_json(folder / f"results_{source}.json")
        if scored:
            errors = scored.get("errors") or []
            results[source] = {**{k: v for k, v in scored.items() if k != "errors"},
                               "error_count": len(errors), "errors_sample": errors[:25]}
    return {**manifest, "year": year, "progress": progress, "status": status, "results": results,
            "downloads": [f"review_{year}_{f}" for f in [*_REVIEW_FILES, "guidelines.md"]]}


def _independent_review() -> Optional[dict]:
    years = _review_years()
    if not years:
        return None
    return {"current": _review_status(years[0]), "previous": [_review_status(y) for y in years[1:]]}


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


@router.get("/api/evaluation/files")
async def evaluation_files() -> dict:
    return {"files": [{"name": k, "url": f"/api/evaluation/files/{k}", "available": _download_body(k) is not None}
                      for k in _all_downloads()]}


def _all_downloads() -> dict[str, tuple[str, str]]:
    return {**_DOWNLOADS, **_review_downloads()}


def _download_body(name: str) -> Optional[str]:
    downloads = _all_downloads()
    if name not in downloads:
        return None
    try:
        return (_ROOT / downloads[name][0]).read_text()
    except OSError:
        year = re.fullmatch(r"review_(\d{4})_guidelines\.md", name)
        if year:                                         # the hosted runtime drops Markdown; the manifest carries it
            return (_read_json(_REVIEW / year.group(1) / "manifest.json") or {}).get("guidelines_md")
        return None


@router.get("/api/evaluation/files/{name}")
async def evaluation_file(name: str) -> Response:
    downloads = _all_downloads()
    if name not in downloads:
        raise HTTPException(404, "Unknown file.")
    media = downloads[name][1]
    body = _download_body(name)
    if body is None:
        raise HTTPException(404, "File not published.")
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _return_forecast_status() -> Optional[dict]:
    from src.engines import return_forecast
    return return_forecast.current_status(_read_json(_ROOT / "docs" / "return_forecast_validation.json"))


@router.get("/api/return-forecast")
async def return_forecast_estimate(market: str = Query(..., pattern="^(us|africa)$"),
                                   signal_type: str = Query(..., max_length=40),
                                   severity: str = Query(..., pattern="^(low|medium|high|critical)$")) -> dict:
    """A 10-day market-adjusted return estimate for a flag, issued only while the validation gates pass today."""
    from src.engines import return_forecast
    return return_forecast.estimate(_read_json(_ROOT / "docs" / "return_forecast_validation.json"),
                                    market, signal_type, severity)


def signal_track_records() -> list[dict]:
    """Every signal type at every severity, graded against how often its event happens with no flag."""
    from src.engines import measured
    from src.schemas.models import Severity, SignalType
    return [measured.track_record(t.value, sev.value) for t in SignalType for sev in (Severity.LOW, Severity.MEDIUM, Severity.HIGH)]


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
            "return_forecast_validation": _return_forecast_status(),
            "data_quality": _read_json(_ROOT / "evaluation" / "deals" / "results.json"),
            "data_quality_baseline": _read_json(_ROOT / "evaluation" / "deals" / "results_baseline.json"),
            "attribution": _read_json(_ROOT / "evaluation" / "attribution" / "results.json"),
            "attribution_before": _read_json(_ROOT / "evaluation" / "attribution" / "results_before_rule_changes.json"),
            "independent_review": _independent_review(),
            "track_records": signal_track_records(),
            "method": "Historical: walk-forward replay, 30-day lookback, 90-day horizon, confirmation strictly after "
                      "each as-of date. Live: every hosted brief's signals labelled daily against later filings, "
                      "credible news and abnormal price moves."}


# ── Scheduled rolling ingestion ──────────────────────────────────────────────

@router.get("/api/cron/country-snapshot")
async def cron_country_snapshot(request: Request) -> dict:
    """Capture an auditable risk-score snapshot for each of the 54 countries."""
    if not _authorized_cron(request):
        raise HTTPException(status_code=401, detail="Scheduled workflow authorization required.")
    captured_at = datetime.now(timezone.utc)
    data_as_of = country_risk.load_snapshot().get("retrieved")
    rows = []
    for c in ac.COUNTRIES:
        risk = country_risk.assess(c, fx=lambda _: None)
        rows.append({
            "iso2": c.iso2, "iso3": c.iso3, "country_name": c.name,
            "snapshot_date": captured_at.date().isoformat(), "score": risk["score"],
            "tier": risk["tier"], "coverage": risk["coverage"], "data_as_of": data_as_of,
            "captured_at": captured_at.isoformat(),
            "source": "World Bank WDI/WGI; source dataset date recorded separately",
            "source_url": f"https://api.worldbank.org/v2/country/{c.iso2.lower()}/indicator/FP.CPI.TOTL.ZG?format=json", "method": risk["method"],
            "components": risk["components"], "indicators": risk["indicators"],
            "snapshot_kind": "observed_at_capture",
        })
    if not _configured():
        raise HTTPException(status_code=503, detail="Country snapshot storage is not configured.")
    r = _rpc_sync("upsert_country_risk_snapshots", {"p_rows": rows}, timeout=45)
    if not r.is_success:
        log.error("country risk snapshot write failed: %s %s", r.status_code, r.text[:300])
        raise HTTPException(status_code=502, detail="Could not persist country risk snapshots.")
    return {"status": "ok", "captured_at": captured_at.isoformat(), "countries_submitted": len(rows),
            "rows_written": r.json(), "data_as_of": data_as_of,
            "note": "This captures the current score and inputs; it does not imply the underlying annual indicators were published on the capture date."}


def _needs_round_parties(d: dict) -> bool:
    """A visible equity round that names no investor, whose articles have not been read yet, or were read
    without a result before other reports were searched or by an older version of the extractor."""
    from src.engines import round_parties
    checked = d.get("parties_checked")
    unread = not checked or (checked.get("status") != "investors_found" and (
        not checked.get("searched") or (checked.get("v") or 1) < round_parties.EXTRACTOR_VERSION))
    return d.get("deal_type") == "equity_funding" and deals_mod.is_visible(d) and unread and not investors.parties(d)


@router.get("/api/cron/enrich-rounds")
async def cron_enrich_rounds(request: Request, limit: int = Query(40, ge=1, le=80)) -> dict:
    """Read the articles of funding rounds that name no investor and record the investors they name, each
    with the sentence that names it. Every round tried is marked, so none is read twice."""
    if not _authorized_cron(request):
        raise HTTPException(401, "Unauthorized")
    if not _configured():
        raise HTTPException(503, "The API is not configured.")
    import asyncio
    from src.engines import round_parties
    _cache.clear()
    pending = sorted((d for d in await run_in_threadpool(_load, "deals") if _needs_round_parties(d)),
                     key=lambda d: d.get("announced") or "", reverse=True)
    batch = pending[:limit]
    deadline = time.monotonic() + 200
    sem = asyncio.Semaphore(4)

    def work(deal: dict) -> tuple[dict, str]:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            return round_parties.enrich(deal, client)

    async def one(deal: dict) -> Optional[tuple[dict, str]]:
        async with sem:
            if time.monotonic() > deadline:
                return None                     # left for the next call
            try:
                return await asyncio.wait_for(run_in_threadpool(work, deal), timeout=80)
            except Exception as e:
                log.info("round enrichment failed for %s: %r", deal.get("id"), e)
                return None
    results = [r for r in await asyncio.gather(*(one(d) for d in batch)) if r]
    if results:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await _rpc(client, "upsert_deals", {"p_rows": [deal for deal, _ in results]})
        if r.status_code != 200:
            log.error("round enrichment write failed: status=%s body=%s", r.status_code, r.text[:300])
            raise HTTPException(502, "Round enrichment could not be saved; the run can be retried.")
        _cache.clear()
    statuses: dict[str, int] = {}
    for _, status in results:
        statuses[status] = statuses.get(status, 0) + 1
    return {"processed": len(results), "statuses": statuses, "remaining": len(pending) - len(results)}


def _reclassify_stored(existing: dict[str, dict], merged: dict[str, dict]) -> dict[str, dict]:
    """Stored records the current rules correct (deals.reclassify): a roundup or a non-company target is
    excluded, a bond or loan stored as an equity round gets its type, and a record whose new type matches another
    stored record of the same transaction is merged into it."""
    visible = [d for d in existing.values() if deals_mod.is_visible(d)]
    out: dict[str, dict] = {}
    for d in visible:
        current = merged.get(d["id"], d)
        if current.get("reviewed_on"):
            continue                                    # a reviewer's decision stands
        change = deals_mod.reclassify(current)
        if not change:
            continue
        fixed = {**current, **change}
        if "deal_type" in change:
            twin = next((o for o in visible if o["id"] != d["id"] and o["id"] not in out
                         and deals_mod.same_transaction(fixed, o)), None)
            if twin:
                fixed["merged_into"] = twin["id"]
        out[d["id"]] = fixed
    return out


@router.get("/api/cron/ingest")
async def cron_ingest(
    request: Request,
    month: Optional[str] = Query(default=None, pattern=r"^20[1-9][0-9]-(0[1-9]|1[0-2])$"),
) -> dict:
    """Refresh recent news, or backfill one bounded calendar month (from 2010) without sending stale alerts."""
    if not _authorized_cron(request):
        raise HTTPException(401, "Unauthorized")
    if not _configured():
        raise HTTPException(503, "The API is not configured.")
    from src.engines import market_feed
    if month:
        month_start = datetime.strptime(month, "%Y-%m").date()
        if month_start < HISTORY_START:
            raise HTTPException(400, f"History starts in {HISTORY_START:%B %Y}.")
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = min(next_month - timedelta(days=1), datetime.now(timezone.utc).date())
        if month_start > month_end:
            raise HTTPException(400, "That month has not started yet.")
        try:
            items = await market_feed.collect_historical(month_start, month_end)
        except (RuntimeError, ValueError) as exc:
            log.error("historical deal collection failed for %s: %s", month, exc)
            raise HTTPException(502, f"Historical collection failed for {month}; the backfill can be retried.")
    else:
        # Re-scan a rolling week because news sources can index stories late.
        items = await market_feed.collect("when:7d")
    new_deals, new_events = market_feed.to_deals(items), market_feed.to_events(items)
    _cache.clear()
    existing = {d["id"]: d for d in await run_in_threadpool(_load, "deals")}
    new_deals = deals_mod.resolve_duplicates(new_deals, existing)
    if month:
        # Backfilled history clears a stricter bar; held-back records are kept, marked, for audit.
        for d in new_deals:
            if d["id"] not in existing:
                reason = deals_mod.history_exclusion(d.get("headline", ""),
                                                     [d.get("target"), d.get("buyer"), *(d.get("investors") or [])],
                                                     [s.get("publisher") for s in d.get("sources") or []])
                if reason:
                    d["excluded"] = reason
        for e in new_events:
            reason = deals_mod.history_exclusion(e.get("headline", ""), [e.get("company")],
                                                 [e.get("publisher"), *(s.get("publisher") for s in e.get("sources") or [])])
            if reason:
                e["excluded"] = reason
    merged = deals_mod.merge_all(new_deals, into={k: existing[k] for k in {d["id"] for d in new_deals} if k in existing})
    reclassified = _reclassify_stored(existing, merged)
    merged.update(reclassified)
    # Each publisher's wording of a story is one event: later reports point at the first.
    from src.engines import event_dedup
    stored_events = {e["id"]: e for e in await run_in_threadpool(_load, "events")}
    new_events = await run_in_threadpool(event_dedup.resolve, new_events, stored_events)
    # Arabic headlines get an English rendering: today's first, then a batch of stored ones each run.
    from src.engines import headline_translate
    queued = {e["id"]: e for e in new_events}
    backlog = [e for e in stored_events.values() if e["id"] not in queued and not e.get("merged_into")
               and not e.get("excluded")]
    import asyncio
    try:
        translated = await asyncio.wait_for(
            run_in_threadpool(headline_translate.add_translations, [*new_events, *backlog]), timeout=60)
    except asyncio.TimeoutError:
        translated = []                                 # left for the next run
    for e in translated:
        queued[e["id"]] = e
    new_events = list(queued.values())
    async with httpx.AsyncClient(timeout=60) as client:
        r1 = await _rpc(client, "upsert_deals", {"p_rows": list(merged.values())})
        if r1.status_code != 200:
            log.error("deal ingestion write failed: status=%s body=%s", r1.status_code, r1.text[:300])
            raise HTTPException(502, "Deal ingestion failed while saving records. The scheduled run must be retried.")
        r2 = await _rpc(client, "upsert_events", {"p_rows": new_events})
        if r2.status_code != 200:
            log.error("event ingestion write failed: status=%s body=%s", r2.status_code, r2.text[:300])
            raise HTTPException(502, "Event ingestion failed while saving records. The scheduled run must be retried.")
        hooks = await _rpc(client, "webhook_watchlists", {})
    if hooks.status_code != 200:
        log.warning("watchlist webhook lookup failed after successful ingestion: status=%s body=%s",
                    hooks.status_code, hooks.text[:300])
    delivered = 0
    # Historical backfills populate the database silently; never send stale alerts.
    for wl in (hooks.json() if hooks.status_code == 200 and not month else []):
        if not watch.delivery_due(wl.get("delivery_frequency", "daily"), last_delivered_at=wl.get("last_delivered_at")):
            continue
        if not _public_host(wl["webhook_url"]):
            continue
        if wl.get("delivery_frequency") == "weekly" and wl.get("last_delivered_at"):
            last_delivery = datetime.fromisoformat(wl["last_delivered_at"].replace("Z", "+00:00"))
            baseline_since = (last_delivery - timedelta(days=7)).date().isoformat()
        else:
            baseline_since = (wl.get("last_delivered_at") or
                              (datetime.now(timezone.utc) - timedelta(days=7)).isoformat())[:10]
        # Re-check a rolling 90-day window so material corrections to an older record
        # can be surfaced without re-sending every unchanged alert each day.
        candidates_alerts = watch.matches(
            wl, new_events, list(merged.values()),
            since=(date.today() - timedelta(days=90)).isoformat(),
        )
        if not candidates_alerts:
            continue
        candidates = [
            {"alert_key": f"{a['kind']}:{a['id']}", "fingerprint": watch.alert_fingerprint(a)}
            for a in candidates_alerts
        ]
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                unseen_response = await _rpc(client, "unseen_watchlist_alerts", {
                    "p_id": wl["id"], "p_candidates": candidates,
                })
            if not unseen_response.is_success:
                log.warning("watchlist duplicate-suppression lookup failed for %s: %s",
                            wl["id"], unseen_response.status_code)
                continue
            unseen_rows = unseen_response.json() or []
        except httpx.HTTPError as exc:
            log.warning("watchlist duplicate-suppression lookup failed for %s: %s",
                        wl["id"], type(exc).__name__)
            continue
        changes = {row["alert_key"]: bool(row.get("is_update")) for row in unseen_rows}
        alerts = []
        for alert in candidates_alerts:
            key = f"{alert['kind']}:{alert['id']}"
            if key not in changes:
                continue
            # On first rollout, don't blast the full 90-day history. Existing alert
            # identities can still reappear if their material fingerprint changed.
            if not changes[key] and (alert.get("day") or "") < baseline_since:
                continue
            alerts.append({**alert, "change_type": "updated" if changes[key] else "new"})
        if not alerts:
            continue
        candidates_to_record = [
            {"alert_key": f"{a['kind']}:{a['id']}", "fingerprint": watch.alert_fingerprint(a)}
            for a in alerts
        ]
        result = await watch.deliver_webhook(
            wl["webhook_url"],
            watch.webhook_payload(wl, alerts, _watch_link(wl["id"])),
            watch.delivery_idempotency_key(wl["id"], alerts),
        )
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                saved = await _rpc(client, "record_watchlist_delivery", {
                    "p_id": wl["id"], "p_delivered": result["delivered"],
                    "p_attempt_count": result["attempts"], "p_http_status": result["status_code"],
                    "p_alert_count": len(alerts), "p_error_code": result["error"],
                })
                if not saved.is_success:
                    log.warning("watchlist delivery outcome could not be recorded: %s", saved.status_code)
                if result["delivered"]:
                    recorded = await _rpc(client, "record_watchlist_alerts_delivered", {
                        "p_id": wl["id"], "p_candidates": candidates_to_record,
                    })
                    if not recorded.is_success:
                        log.warning("delivered alert fingerprints could not be recorded: %s", recorded.status_code)
        except httpx.HTTPError as exc:
            log.warning("watchlist delivery outcome logging failed for %s: %s", wl["id"], type(exc).__name__)
        if result["delivered"]:
            delivered += 1
    _cache.clear()
    return {"status": "ok", "mode": f"backfill:{month}" if month else "rolling-7d",
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "headlines": len(items), "deals_detected": len(new_deals), "deals_saved": r1.json(),
            "events_detected": len(new_events), "events_saved": r2.json(), "deals_reclassified": len(reclassified),
            "headlines_translated": len(translated),
            "webhooks_delivered": delivered, "webhook_lookup_ok": hooks.status_code == 200,
            "alerts_suppressed": bool(month)}


# ── African equity markets ───────────────────────────────────────────────────

_markets_cache: dict[str, tuple[float, dict]] = {}
_MARKETS_TTL = 600


def _market_snapshot() -> dict:
    """The latest stored snapshot of every exchange's quotes, the indices and FX."""
    from src.engines import markets
    hit = _markets_cache.get("snapshot")
    if hit and time.monotonic() - hit[0] < _MARKETS_TTL:
        return hit[1]
    if not _configured():
        snap = markets.load_local()
    else:
        parts = {}
        for kind in ("quotes", "indices", "fx"):
            r = _rpc_sync("list_market_snapshots", {"p_kind": kind})
            if r.status_code != 200:
                log.error("market snapshot read failed: %s %s", r.status_code, r.text[:300])
                if hit:
                    return hit[1]
                raise HTTPException(503, "Market data store is unavailable.")
            parts[kind] = r.json() or []
        snap = markets.from_rows(parts["quotes"], parts["indices"], parts["fx"])
        today = datetime.now(timezone.utc).date().isoformat()
        r = _rpc_sync("list_market_snapshots", {"p_kind": "intraday"})
        if r.status_code == 200:
            snap["intraday"] = {row["scope"]: row.get("payload") or {} for row in r.json() or []
                                if str(row.get("snapshot_date")) == today}
    markets.apply_intraday(snap, snap.get("intraday") or {})
    _markets_cache["snapshot"] = (time.monotonic(), snap)
    return snap


@router.get("/api/cron/market-snapshot")
async def cron_market_snapshot(request: Request) -> dict:
    """Record today's quotes for every exchange, the benchmark indices and dollar exchange rates."""
    if not _authorized_cron(request):
        raise HTTPException(401, "Unauthorized")
    from src.engines import markets
    try:
        previous = await run_in_threadpool(_market_snapshot)
    except HTTPException:
        previous = {}                                   # no earlier snapshot to compare with
    snap = await run_in_threadpool(lambda: markets.build_snapshot(previous=previous))
    markets.fill_daily_change(snap, previous)
    rows = markets.snapshot_rows(snap)
    if not rows:
        raise HTTPException(502, "No market source answered; nothing was recorded.")
    if not _configured():
        markets.save_local(snap)
        written = len(rows)
    else:
        r = await run_in_threadpool(_rpc_sync, "upsert_market_snapshots", {"p_rows": rows}, 60)
        if not r.is_success:
            log.error("market snapshot write failed: %s %s", r.status_code, r.text[:300])
            raise HTTPException(502, "Could not persist the market snapshot.")
        written = r.json()
    _markets_cache.clear()
    _directory_cache.clear()
    return {"status": "ok", "rows_written": written, "exchanges": {k: len(v) for k, v in snap["quotes"].items()},
            "indices": len(snap["indices"]), "currencies": len(snap["fx"].get("rates") or {}),
            "failed": snap["errors"]}


@router.get("/api/cron/market-intraday")
async def cron_market_intraday(request: Request) -> dict:
    """Delayed intraday quotes for the exchanges with a free intraday source, during trading hours."""
    if not _authorized_cron(request):
        raise HTTPException(401, "Unauthorized")
    from src.engines import markets
    snap = await run_in_threadpool(_market_snapshot)
    intraday = await run_in_threadpool(markets.build_intraday, snap)
    if not intraday:
        return {"status": "ok", "rows_written": 0, "note": "no exchange has quotes from today's session yet"}
    rows = markets.intraday_rows(intraday)
    if not _configured():
        markets.save_local_intraday(intraday)
        written = len(rows)
    else:
        r = await run_in_threadpool(_rpc_sync, "upsert_market_snapshots", {"p_rows": rows}, 60)
        if not r.is_success:
            log.error("intraday write failed: %s %s", r.status_code, r.text[:300])
            raise HTTPException(502, "Could not persist intraday quotes.")
        written = r.json()
    _markets_cache.clear()
    _directory_cache.clear()
    return {"status": "ok", "rows_written": written, "exchanges": {k: len(v["rows"]) for k, v in intraday.items()}}


@router.get("/api/markets/overview")
async def markets_overview() -> dict:
    """Exchange tiles, movers, most traded, sector moves and currency moves across 16 African exchanges."""
    from src.engines import markets
    return markets.overview(await run_in_threadpool(_market_snapshot))


@router.get("/api/markets/screener")
async def markets_screener(
    exchange: Optional[str] = Query(None, max_length=8), sector: Optional[str] = Query(None, max_length=60),
    min_mcap_usd: Optional[float] = Query(None, ge=0), q: Optional[str] = Query(None, max_length=80),
    sort: Literal["mcap", "chg_1d", "ytd", "value", "name", "pe", "dividend"] = "mcap",
    include_stale: bool = False, limit: int = Query(100, ge=1, le=500),
) -> dict:
    """Shares across every exchange, filtered and sorted."""
    from src.engines import markets
    snap = await run_in_threadpool(_market_snapshot)
    return markets.screener(snap, exchange=exchange, sector=sector, min_mcap_usd=min_mcap_usd, q=q, sort=sort,
                            include_stale=include_stale, limit=limit)


@router.get("/api/markets/search")
async def markets_search(q: str = Query(..., min_length=2, max_length=80), limit: int = Query(10, ge=1, le=25)) -> dict:
    """Listed shares matching a company name or ticker."""
    from src.engines import markets
    return {"results": markets.search(await run_in_threadpool(_market_snapshot), q, limit=limit)}


class PriceItem(BaseModel):
    name: str = Field("", max_length=120)
    ticker: str = Field("", max_length=24)
    country: str = Field("", max_length=60)
    currency: str = Field("", max_length=3)


class PriceRequest(BaseModel):
    items: list[PriceItem] = Field(..., min_length=1, max_length=200)


@router.post("/api/markets/prices")
async def markets_prices(body: PriceRequest) -> dict:
    """Latest close for each holding (by ticker, else by name) and dollar rates, for pricing a portfolio."""
    from src.engines import markets
    snap = await run_in_threadpool(_market_snapshot)

    def one(item: PriceItem) -> Optional[dict]:
        country = None
        if item.country:
            found = ac.get(item.country) or next(iter(ac.countries_in_text(item.country)), None)
            country = found.iso2 if found else None
        ticker = item.ticker.strip().upper()
        exchange = company_profile.exchange_of(ticker)
        hit = None
        if exchange:
            hit = markets.quote(snap, exchange, ticker)
        elif ticker:
            hit = next((r for r in markets.search(snap, ticker, limit=10)
                        if r["symbol"] == ticker and (not country or r["country"] == country)), None)
        if not hit and item.name.strip():
            hit = markets.resolve(snap, item.name, country)
        # A quote in another currency than the holding's is a different line (a cross-listing): not used.
        if hit and item.currency and hit["currency"] != item.currency.upper():
            return None
        return hit and {k: hit.get(k) for k in ("exchange", "exchange_name", "symbol", "name", "price", "currency",
                                                  "chg_1d", "date", "stale", "age_days")}
    results = await run_in_threadpool(lambda: [one(i) for i in body.items])
    fx = snap.get("fx") or {}
    return {"results": results, "fx": {"usd_rates": {**(fx.get("rates") or {}), "USD": 1.0}, "as_of": fx.get("as_of")}}


_directory_cache: dict[str, tuple[float, list]] = {}


def _directory() -> list[dict]:
    from src.engines import company_directory
    hit = _directory_cache.get("rows")
    if hit and time.monotonic() - hit[0] < _MARKETS_TTL:
        return hit[1]
    rows = company_directory.directory(_market_snapshot(), deals(), events=events())
    _directory_cache["rows"] = (time.monotonic(), rows)
    return rows


@router.get("/api/companies/directory")
async def companies_directory(
    q: Optional[str] = Query(None, max_length=80), kind: Literal["all", "listed", "private"] = "all",
    country: Optional[str] = Query(None, max_length=60), sector: Optional[str] = Query(None, max_length=60),
    sort: Literal["recent", "raised", "size", "deals", "name"] = "recent",
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=100000),
) -> dict:
    """Every company on record: listed shares on 17 exchanges and private companies from the deals database."""
    from src.engines import company_directory
    code = _country_or_404(country).iso2 if country else None
    rows = await run_in_threadpool(_directory)
    return company_directory.query(rows, q=q, kind=kind, country=code, sector=sector, sort=sort, limit=limit,
                                   offset=offset)


@router.get("/api/markets/quote")
async def markets_quote(exchange: str = Query(..., max_length=8), symbol: str = Query(..., max_length=20)) -> dict:
    from src.engines import markets
    hit = markets.quote(await run_in_threadpool(_market_snapshot), exchange.lower(), symbol)
    if not hit:
        raise HTTPException(404, "No quote for that listing in the latest snapshot.")
    return hit
