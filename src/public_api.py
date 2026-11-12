"""
Public, key-authenticated API: /v1.

The /api/* routes serve the web app and may change with it; /v1 is the stable contract for customers'
own code, Slack and Teams bots, spreadsheets, Zapier and the like. Every request carries an account's API
key (Authorization: Bearer di_live_..., or X-API-Key) and counts against the account's monthly allowance
(Free 30, Pro 3,000, Team 15,000, Institutional 100,000; set in the api_plans table).

Metering happens in the database in one statement (api_key_consume), so concurrent requests cannot overrun
an allowance, and a request is refused (429) rather than served uncounted if the database cannot be reached.
Keys are stored only as SHA-256 hashes. Responses are never cached at the edge: a cached copy would be
served to callers without a key and without counting.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Awaitable, Callable, Literal, Optional

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from src import hosted_market as hm

log = logging.getLogger("deal_intel.public_api")

router = APIRouter(prefix="/v1")

KEY_PATTERN = re.compile(r"^di_live_[0-9a-f]{48}$")
DOCS_URL = "https://deal-intelligence.app/developers"


class PublicApiError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: Optional[dict] = None):
        super().__init__(message)
        self.status, self.code, self.message, self.headers = status, code, message, headers or {}


async def _error_response(request: Request, exc: PublicApiError) -> JSONResponse:
    # A request that passed the key check was counted, so its error still reports the remaining allowance.
    counted = getattr(request.state, "quota", None)
    headers = {**(quota_headers(counted) if counted else {}), "Cache-Control": "no-store", **exc.headers}
    return JSONResponse({"error": {"code": exc.code, "message": exc.message, "docs": DOCS_URL}},
                        status_code=exc.status, headers=headers)


def install(app: FastAPI) -> None:
    app.include_router(router)
    app.add_exception_handler(PublicApiError, _error_response)


def presented_key(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return (request.headers.get("x-api-key") or "").strip() or None


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _epoch(iso: Optional[str]) -> Optional[int]:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int((dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp())


def quota_headers(status: dict) -> dict:
    out = {"X-RateLimit-Limit": str(status.get("limit", 0)), "X-RateLimit-Remaining": str(status.get("remaining", 0))}
    reset = _epoch(status.get("resets_at"))
    if reset:
        out["X-RateLimit-Reset"] = str(reset)
    return out


async def authorize(request: Request, response: Response, count: bool = True) -> dict:
    """Check the key and count the request. Raises PublicApiError (401, 429 or 503)."""
    key = presented_key(request)
    if not key:
        raise PublicApiError(401, "missing_key", "Send your API key as 'Authorization: Bearer <key>'.",
                             {"WWW-Authenticate": "Bearer"})
    if not KEY_PATTERN.match(key):
        raise PublicApiError(401, "invalid_key", "That is not a valid API key.", {"WWW-Authenticate": "Bearer"})
    if not hm._configured():
        raise PublicApiError(503, "unavailable", "The API is not configured.")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await hm._rpc(client, "api_key_consume", {"p_hash": key_hash(key), "p_count": count})
    except httpx.HTTPError as exc:
        log.warning("api_key_consume unreachable: %r", exc)
        raise PublicApiError(503, "unavailable", "Usage could not be checked. Try again shortly.", {"Retry-After": "30"})
    if r.status_code != 200:
        log.error("api_key_consume failed: %s %s", r.status_code, r.text[:200])
        raise PublicApiError(503, "unavailable", "Usage could not be checked. Try again shortly.", {"Retry-After": "30"})
    status = r.json() or {}
    if not status.get("ok"):
        if status.get("reason") == "quota_exceeded":
            headers = quota_headers(status)
            reset = _epoch(status.get("resets_at"))
            if reset:
                headers["Retry-After"] = str(max(reset - int(datetime.now(timezone.utc).timestamp()), 60))
            raise PublicApiError(429, "quota_exceeded",
                                 f"Your {status.get('plan', 'free')} plan's {status.get('limit')} requests this month "
                                 "are used up. Upgrade, or wait for the allowance to reset.", headers)
        raise PublicApiError(401, "invalid_key", "That API key does not exist or has been revoked.",
                             {"WWW-Authenticate": "Bearer"})
    request.state.quota = status
    response.headers.update(quota_headers(status))
    response.headers["Cache-Control"] = "no-store"
    return status


def _country(value: Optional[str]) -> Optional[str]:
    """An ISO code or a country name ("Kenya", "Ivory Coast") as the ISO code the data uses; unknown values pass
    through so the handler can answer with its own 404."""
    if not value:
        return None
    from src.data import africa_countries as ac
    hit = ac.get(value) or next(iter(ac.countries_in_text(value)), None)
    return hit.iso2 if hit else value


async def _call(fn: Callable[[], Awaitable]) -> object:
    """Run an underlying handler, turning its errors into the public error shape."""
    try:
        return await fn()
    except HTTPException as exc:
        code = {400: "bad_request", 404: "not_found", 422: "invalid_request", 503: "unavailable"}.get(exc.status_code, "error")
        raise PublicApiError(exc.status_code, code, str(exc.detail)) from None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("")
async def index() -> JSONResponse:
    """What the API offers. Needs no key and is not counted."""
    return JSONResponse({"name": "Deal Intelligence API", "version": "v1", "docs": DOCS_URL,
                         "auth": "Authorization: Bearer <your key>", "endpoints": [
                             f"GET /v1/{p}" for p in (
                                 "usage", "deals", "deals/{id}", "events", "investors", "investors/{name}",
                                 "countries", "countries/{code}", "markets/overview", "markets/screener",
                                 "markets/search", "markets/quote", "elections/news", "elections/summary",
                                 "elections/areas", "elections/polling-units", "elections/polling-units/{code}")]},
                        headers={"Cache-Control": "public, max-age=3600"})


@router.get("/usage")
async def usage(request: Request, response: Response) -> dict:
    """This month's allowance and use for the key's account. Not counted."""
    s = await authorize(request, response, count=False)
    return {"plan": s.get("plan"), "limit": s.get("limit"), "used": s.get("used"),
            "remaining": s.get("remaining"), "resets_at": s.get("resets_at")}


@router.get("/deals")
async def deals(request: Request, response: Response, q: str = Query("", max_length=120),
                country: Optional[str] = Query(None, max_length=60), type: Optional[str] = Query(None, max_length=40),
                sector: Optional[str] = Query(None, max_length=60), investor: Optional[str] = Query(None, max_length=120),
                since: Optional[str] = Query(None, max_length=10), until: Optional[str] = Query(None, max_length=10),
                min_usd: Optional[float] = Query(None, ge=0), limit: int = Query(25, ge=1, le=100),
                offset: int = Query(0, ge=0, le=100_000)) -> dict:
    await authorize(request, response)
    return await _call(lambda: hm.deal_search(q=q, country=_country(country), type=type, sector=sector, investor=investor,
                                              since=since, until=until, min_usd=min_usd, limit=limit, offset=offset))


@router.get("/deals/{deal_id}")
async def deal(deal_id: str, request: Request, response: Response) -> dict:
    await authorize(request, response)
    return await _call(lambda: hm.deal(deal_id))


@router.get("/events")
async def events(request: Request, response: Response, country: Optional[str] = Query(None, max_length=60),
                 type: Optional[str] = Query(None, max_length=40), since: Optional[str] = Query(None, max_length=10),
                 q: str = Query("", max_length=120), limit: int = Query(50, ge=1, le=200),
                 offset: int = Query(0, ge=0, le=100_000)) -> dict:
    await authorize(request, response)
    return await _call(lambda: hm.event_feed(country=_country(country), type=type, since=since, q=q, limit=limit, offset=offset))


@router.get("/investors")
async def investors(request: Request, response: Response, role: Optional[str] = Query(None, max_length=20),
                    kind: Optional[str] = Query(None, max_length=40), sector: Optional[str] = Query(None, max_length=60),
                    country: Optional[str] = Query(None, max_length=60), stage: Optional[str] = Query(None, max_length=40),
                    type: Optional[str] = Query(None, max_length=40), since: Optional[str] = Query(None, max_length=10),
                    until: Optional[str] = Query(None, max_length=10), min_usd: Optional[float] = Query(None, ge=0),
                    max_usd: Optional[float] = Query(None, ge=0), lead_only: bool = False,
                    limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=100_000)) -> dict:
    await authorize(request, response)
    out = await _call(lambda: hm.investor_board(role=role, kind=kind, sector=sector, country=country, stage=stage,
                                                type=type, since=since, until=until, min_usd=min_usd, max_usd=max_usd,
                                                lead_only=lead_only, limit=limit, offset=offset))
    out.pop("registry", None)          # the full investor registry is large and belongs to the app's filters
    return out


@router.get("/investors/{name}")
async def investor(name: str, request: Request, response: Response) -> dict:
    await authorize(request, response)
    return await _call(lambda: hm.investor(name))


@router.get("/countries")
async def countries(request: Request, response: Response) -> dict:
    await authorize(request, response)
    return await _call(hm.countries)


@router.get("/countries/{code}")
async def country(code: str, request: Request, response: Response) -> dict:
    await authorize(request, response)
    return await _call(lambda: hm.country(_country(code)))


@router.get("/elections/news")
async def election_news(request: Request, response: Response, candidate: Optional[str] = Query(None, max_length=80),
                        party: Optional[str] = Query(None, max_length=10), state: Optional[str] = Query(None, max_length=30),
                        topic: Optional[str] = Query(None, max_length=30), race: Optional[str] = Query(None, max_length=30),
                        q: str = Query("", max_length=120), since: Optional[str] = Query(None, max_length=10),
                        limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=100_000)) -> dict:
    """Nigeria 2027 election coverage: one record per story, every outlet's report attached, tagged by candidate,
    party, state, topic and race."""
    from src import election_feed
    await authorize(request, response)

    async def run():
        return await run_in_threadpool(election_feed.search, candidate=candidate, party=party, state=state,
                                       topic=topic, race=race, q=q, since=since, limit=limit, offset=offset)
    return await _call(run)


@router.get("/elections/summary")
async def election_summary(request: Request, response: Response, days: int = Query(7, ge=1, le=90)) -> dict:
    """Coverage counts per candidate, party, state, topic and race over the last `days` days."""
    from src import election_feed
    await authorize(request, response)

    async def run():
        return await run_in_threadpool(election_feed.summary, days)
    return await _call(run)


@router.get("/elections/areas")
async def election_areas(request: Request, response: Response, state: Optional[str] = Query(None, max_length=40),
                         lga: Optional[str] = Query(None, max_length=3)) -> dict:
    """INEC's delimitation one level at a time: the states; a state's LGAs; an LGA's wards, with polling-unit counts."""
    from src import polling_units
    await authorize(request, response)

    async def run():
        rows = await run_in_threadpool(polling_units.areas, state, lga)
        level = "wards" if lga else "lgas" if state else "states"
        return {"level": level, "count": len(rows), level: rows}
    return await _call(run)


@router.get("/elections/polling-units")
async def election_polling_units(request: Request, response: Response, state: Optional[str] = Query(None, max_length=40),
                                 lga: Optional[str] = Query(None, max_length=3), ward: Optional[str] = Query(None, max_length=3),
                                 q: str = Query("", max_length=80), limit: int = Query(100, ge=1, le=500),
                                 offset: int = Query(0, ge=0, le=200_000)) -> dict:
    """Polling units in a ward (state, lga and ward codes), or matching a name (q), optionally within a state."""
    from src import polling_units
    await authorize(request, response)

    async def run():
        return await run_in_threadpool(polling_units.units, state, lga, ward, q, limit, offset)
    return await _call(run)


@router.get("/elections/polling-units/{code:path}")
async def election_polling_unit(code: str, request: Request, response: Response) -> dict:
    """One polling unit by INEC code, SS/LL/WW/UUU (slashes or hyphens)."""
    from src import polling_units
    await authorize(request, response)

    async def run():
        return await run_in_threadpool(polling_units.unit, code)
    return await _call(run)


@router.get("/markets/overview")
async def markets_overview(request: Request, response: Response) -> dict:
    await authorize(request, response)
    return await _call(hm.markets_overview)


@router.get("/markets/screener")
async def markets_screener(
    request: Request, response: Response, exchange: Optional[str] = Query(None, max_length=8),
    sector: Optional[str] = Query(None, max_length=60), min_mcap_usd: Optional[float] = Query(None, ge=0),
    q: Optional[str] = Query(None, max_length=80),
    sort: Literal["mcap", "chg_1d", "ytd", "value", "name", "pe", "dividend"] = "mcap",
    include_stale: bool = False, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=100_000),
) -> dict:
    await authorize(request, response)
    return await _call(lambda: hm.markets_screener(exchange=exchange, sector=sector, min_mcap_usd=min_mcap_usd, q=q,
                                                   sort=sort, include_stale=include_stale, limit=limit, offset=offset))


@router.get("/markets/search")
async def markets_search(request: Request, response: Response, q: str = Query(..., min_length=2, max_length=80),
                         limit: int = Query(10, ge=1, le=25)) -> dict:
    await authorize(request, response)
    return await _call(lambda: hm.markets_search(q=q, limit=limit))


@router.get("/markets/quote")
async def markets_quote(request: Request, response: Response, exchange: str = Query(..., max_length=8),
                        symbol: str = Query(..., max_length=20)) -> dict:
    await authorize(request, response)
    return await _call(lambda: hm.markets_quote(exchange=exchange, symbol=symbol))
