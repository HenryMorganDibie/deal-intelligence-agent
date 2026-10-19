"""HTTP API for the hosted app (Vercel Python function).

Open access, no accounts:
  POST /api/analyse      run the pipeline, store the brief, return its id
  GET  /api/briefs/{id}  fetch a stored brief (ids are random UUIDs: share links)
  GET  /api/health
  GET  /api/cron/label   daily (Vercel Cron): label briefs' outcomes for calibration
  plus the market-data routes in src/hosted_market.py (countries, deals, investors,
  companies, research, watchlists, coverage, evaluation, daily ingestion)

Writes go through Supabase functions that require DEAL_INTEL_API_SECRET, which
only this function holds; the publishable key alone can read a brief by id and
nothing else. Each caller is identified by a salted hash of their IP, never the
IP itself, for a per-visitor daily limit and a global daily cap.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# The filesystem is read-only on Vercel apart from /tmp. Set before the
# pipeline modules import, since they resolve their store paths at import.
os.environ.setdefault("DEAL_INTEL_DATA_DIR", "/tmp/deal-intel-data")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hashlib  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402

import httpx  # noqa: E402
from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field, field_validator  # noqa: E402

log = logging.getLogger("deal_intel.api")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
API_SECRET = os.environ.get("DEAL_INTEL_API_SECRET", "")
PER_VISITOR_DAILY = int(os.environ.get("DEAL_INTEL_PER_VISITOR_DAILY", "1000"))
GLOBAL_DAILY = int(os.environ.get("DEAL_INTEL_GLOBAL_DAILY", "1000"))
CRON_SECRET = os.environ.get("CRON_SECRET", "")
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]

app = FastAPI(title="Deal Intelligence API", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["http://localhost:3000"],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
    max_age=600,
)


class AnalyseBody(BaseModel):
    company: str = Field(..., min_length=1, max_length=120)
    ticker: str | None = Field(None, max_length=20)
    country: str | None = Field(None, max_length=3)
    lookback_days: int = Field(90, ge=1, le=365)
    compliance: bool = False

    @field_validator("company", "ticker", "country")
    @classmethod
    def strip(cls, v: str | None) -> str | None:
        v = v.strip() if v else v
        return v or None


def _configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY and API_SECRET)


def _headers() -> dict[str, str]:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}


def _client_hash(request: Request) -> str:
    """Salted hash of the caller's IP (Vercel sets x-forwarded-for)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
    return hashlib.sha256(f"{API_SECRET}:{ip}".encode()).hexdigest()[:32]


async def _rpc(client: httpx.AsyncClient, fn: str, args: dict) -> httpx.Response:
    return await client.post(f"{SUPABASE_URL}/rest/v1/rpc/{fn}", headers=_headers(), json=args)


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "configured": _configured(),
        "llm": bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GROQ_API_KEY")),
        "daily_limit": PER_VISITOR_DAILY,
        "global_daily_limit": GLOBAL_DAILY,
    }


def _install_shared_llm_cache() -> None:
    """LLM replies cached in Supabase, so identical requests read the same text on every instance."""
    if not _configured():
        return
    from src.agents.signal_agent import set_shared_llm_cache

    def get(key: str):
        r = httpx.post(f"{SUPABASE_URL}/rest/v1/rpc/llm_cache_get", headers=_headers(),
                       json={"secret": API_SECRET, "p_key": key}, timeout=10)
        return r.json() if r.status_code == 200 else None

    def put(key: str, text: str) -> None:
        httpx.post(f"{SUPABASE_URL}/rest/v1/rpc/llm_cache_put", headers=_headers(),
                   json={"secret": API_SECRET, "p_key": key, "p_text": text}, timeout=10)

    set_shared_llm_cache(get, put)


_install_shared_llm_cache()

from src.hosted_market import router as market_router  # noqa: E402

app.include_router(market_router)


async def _refresh_outcome_stats(client: httpx.AsyncClient) -> None:
    """Live outcome counts and observations for calibration, refreshed at most hourly per instance."""
    from src.hosted_market import refresh_live
    await refresh_live(client)


@app.post("/api/analyse")
async def analyse(body: AnalyseBody, request: Request) -> dict:
    if not _configured():
        raise HTTPException(503, "The API is not configured.")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await _rpc(client, "start_run", {
            "secret": API_SECRET, "p_client_hash": _client_hash(request),
            "p_company": body.company, "p_ticker": body.ticker,
            "per_client_daily": PER_VISITOR_DAILY, "global_daily": GLOBAL_DAILY,
        })
    if resp.status_code != 200:
        message = resp.text
        if "client_limit" in message:
            raise HTTPException(429, f"You have run {PER_VISITOR_DAILY} analyses today. The limit resets at 00:00 UTC.")
        if "global_limit" in message:
            raise HTTPException(429, "The free service has reached today's capacity. Try again tomorrow.")
        log.error("start_run failed: %s %s", resp.status_code, message[:300])
        raise HTTPException(503, "The service is busy. Try again shortly.")
    run_id = int(resp.json())
    async with httpx.AsyncClient(timeout=10) as client:
        await _refresh_outcome_stats(client)

    from src.agents.graph import run_analysis
    from src.schemas.models import AnalysisRequest
    from src.utils.formatter import brief_to_markdown

    try:
        request_model = AnalysisRequest(company_name=body.company, ticker=body.ticker, country=body.country,
                                        lookback_days=body.lookback_days)
    except ValueError as e:
        async with httpx.AsyncClient(timeout=15) as client:
            await _rpc(client, "fail_run", {"secret": API_SECRET, "p_run_id": run_id})
        raise HTTPException(422, str(e).splitlines()[-1][:200])
    try:
        brief = await run_analysis(request_model, compliance_mode=body.compliance)
    except Exception:
        log.exception("analysis failed for %r", body.company)
        async with httpx.AsyncClient(timeout=15) as client:
            await _rpc(client, "fail_run", {"secret": API_SECRET, "p_run_id": run_id})
        raise HTTPException(502, "The analysis failed. The data sources may be unavailable; try again in a minute.")

    brief_json = json.loads(brief.model_dump_json())
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await _rpc(client, "finish_run", {
            "secret": API_SECRET, "p_run_id": run_id,
            "p_company": brief.company_name, "p_ticker": body.ticker,
            "p_severity": brief_json.get("overall_severity"),
            "p_signal_count": len(brief.detected_signals),
            "p_llm_used": "LLM unavailable" not in (brief_json.get("analyst_model") or ""),
            "p_brief": brief_json, "p_markdown": brief_to_markdown(brief),
        })
    if resp.status_code != 200:
        log.error("finish_run failed: %s %s", resp.status_code, resp.text[:300])
        raise HTTPException(502, "The brief was generated but could not be saved.")
    return {
        "id": resp.json(), "company": brief.company_name, "ticker": body.ticker,
        "severity": brief_json.get("overall_severity"), "signal_count": len(brief.detected_signals),
    }


# ── Showcase: daily briefs on a fixed company list, for the public site ─────────

async def _showcase_one(company: str, ticker: str, market: str) -> dict:
    from src.agents.graph import run_analysis
    from src.engines import showcase
    from src.schemas.models import AnalysisRequest
    from src.utils.formatter import brief_to_markdown

    brief = await run_analysis(AnalysisRequest(company_name=company, ticker=ticker,
                                               lookback_days=showcase.LOOKBACK_DAYS))
    brief_json = json.loads(brief.model_dump_json())
    summary = showcase.summarise(brief_json, market=market)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await _rpc(client, "save_showcase", {
            "secret": API_SECRET, "p_company": company, "p_ticker": ticker, "p_market": market,
            "p_summary": summary, "p_brief": brief_json, "p_markdown": brief_to_markdown(brief),
        })
    if r.status_code != 200:
        raise RuntimeError(f"save_showcase failed: {r.status_code} {r.text[:200]}")
    return {"company": company, "signals": summary["signal_count"], "severity": summary["severity"]}


@app.get("/api/cron/showcase")
async def cron_showcase(request: Request, shift: int = 0) -> dict:
    """Daily: run the pipeline on today's showcase companies (half the list, rotating)."""
    if not CRON_SECRET or request.headers.get("authorization") != f"Bearer {CRON_SECRET}":
        raise HTTPException(401, "Unauthorized")
    if not _configured():
        raise HTTPException(503, "The API is not configured.")
    import asyncio
    from src.engines import showcase

    async with httpx.AsyncClient(timeout=10) as client:
        await _refresh_outcome_stats(client)
    day = datetime.now(timezone.utc).date() + timedelta(days=shift)
    batch = showcase.todays_batch(day)
    sem = asyncio.Semaphore(2)

    async def run(c: tuple[str, str, str]) -> dict:
        async with sem:
            try:
                return await asyncio.wait_for(_showcase_one(*c), timeout=130)
            except Exception as e:
                log.warning("showcase run for %s failed: %r", c[0], e)
                return {"company": c[0], "error": type(e).__name__}

    return {"runs": await asyncio.gather(*(run(c) for c in batch))}


_showcase_cache: tuple[float, dict] | None = None


@app.get("/api/showcase")
async def get_showcase() -> dict:
    """The strongest recent showcase brief (hero) and the strongest from another company (example)."""
    global _showcase_cache
    if _showcase_cache and time.monotonic() - _showcase_cache[0] < 300:
        return _showcase_cache[1]
    if not _configured():
        raise HTTPException(503, "The API is not configured.")
    from src.engines import showcase
    async with httpx.AsyncClient(timeout=15) as client:
        recent = []
        for days in (3, 14, 60):
            r = await _rpc(client, "recent_showcase", {"p_days": days})
            recent = r.json() if r.status_code == 200 else []
            if any(s.get("signal_count") for s in recent):
                break
    recent = showcase.latest_per_company(recent)
    hero = showcase.pick(recent)
    others = [s for s in recent if hero and s.get("company") != hero.get("company")]
    out = {"hero": hero, "example": showcase.pick(others),
           "companies": [{"company": c, "ticker": t, "market": m} for c, t, m in showcase.COMPANIES]}
    if hero:
        _showcase_cache = (time.monotonic(), out)
    return out



class MarketBriefBody(BaseModel):
    lookback_days: int = Field(30, ge=7, le=365)
    country: str | None = Field(None, max_length=3)
    sector: str | None = Field(None, max_length=60)
    deal_type: str | None = Field(None, max_length=60)
    audience: str = Field("Investment banking analyst", min_length=1, max_length=100)
    research_question: str | None = Field(None, max_length=500)

    @field_validator("country", "sector", "deal_type", "audience", "research_question")
    @classmethod
    def market_brief_strip(cls, value: str | None) -> str | None:
        value = value.strip() if value else value
        return value or None


class NewsletterBody(BaseModel):
    source_brief_id: str = Field(..., min_length=1, max_length=64)
    briefing_type: str = Field("both", pattern="^(deal|advisory|both)$")
    selected_items: list[str] = Field(..., min_length=1, max_length=40)
    audience: str = Field("Investment banking analyst", min_length=1, max_length=100)
    instructions: str | None = Field(None, max_length=1000)

    @field_validator("source_brief_id", "audience", "instructions")
    @classmethod
    def newsletter_strip(cls, value: str | None) -> str | None:
        value = value.strip() if value else value
        return value or None


def _market_brief_markdown(report: dict) -> str:
    lines = [
        f"# {report['title']}", "",
        f"**Period:** {report['period_start']} to {report['period_end']}  ",
        f"**Generated:** {report['generated_at']}  ",
        f"**Scope:** {report['scope_label']}  ",
        f"**Audience:** {report['audience']}", "",
        "## Executive snapshot", "",
        f"- **{report['metrics']['transaction_count']}** dated transaction records in the selected window.",
        f"- **{report['metrics']['disclosed_value_count']}** records disclose an amount; disclosed value totals **{report['metrics']['disclosed_value_usd_label']}**.",
        f"- **{report['metrics']['countries_represented']}** countries represented in the records.", "",
        "> These figures describe records currently held by Deal Intelligence, not a complete census of all transactions. Undisclosed amounts are not estimated.", "",
        "## Key transactions", "",
    ]
    for d in report["key_transactions"]:
        parties = " — ".join(x for x in [d.get("buyer"), d.get("target"), d.get("seller")] if x)
        lines += [
            f"### {d.get('headline') or d.get('target') or 'Transaction'}",
            f"- **Date:** {d.get('announced') or 'Not dated'}",
            f"- **Type / stage:** {d.get('deal_type') or 'Unclassified'} / {d.get('stage') or 'Not stated'}",
            f"- **Parties:** {parties or 'Not fully identified'}",
            f"- **Country / sector:** {', '.join(d.get('countries') or ([d.get('country')] if d.get('country') else [])) or 'Not identified'} / {d.get('sector') or 'Not classified'}",
            f"- **Disclosed amount:** {d.get('amount_usd_label') or 'Not disclosed'}",
            f"- **Evidence status:** {d.get('verification') or 'Unassessed'}; {d.get('independent_stories', 0)} independent story group(s)",
        ]
        for source in (d.get("sources") or [])[:3]:
            if source.get("url"):
                lines.append(f"- **Source:** [{source.get('publisher') or source.get('title') or 'Open source'}]({source['url']})")
        lines.append("")
    lines += ["## Observed patterns", ""]
    lines += [f"- {x}" for x in report["observed_patterns"]] or ["- The current filtered sample is too small to support a meaningful pattern."]
    lines += ["", "## Potential advisory research leads", ""]
    for signal in report["advisory_signals"]:
        lines.append(f"- **{signal['title']}** — {signal['rationale']}")
        lines.append(f"  - Evidence in this sample: {signal['evidence_count']} transaction record(s). This is a research lead, not evidence of an active mandate.")
        for source in signal["evidence"][:2]:
            if source.get("url"):
                lines.append(f"  - [{source.get('headline') or 'Supporting transaction'}]({source['url']})")
    if not report["advisory_signals"]:
        lines.append("- The current sample does not support a sufficiently repeated pattern to generate a research lead.")
    lines += ["", "## Comparable activity", ""]
    for item in report["comparables"]:
        lines.append(f"- **{item.get('headline') or item.get('target') or 'Transaction'}** — {item.get('announced') or 'date unknown'}; {item.get('deal_type') or 'type unknown'}; {item.get('amount_usd_label') or 'amount undisclosed'}.")
    if not report["comparables"]:
        lines.append("- No comparable records met the current similarity criteria.")
    lines += ["", "## Method and limitations", "", report["methodology"], "", report["coverage_note"], ""]
    web_research = report.get("web_research") or {}
    lines += ["", "## Hybrid web research", ""]
    if web_research.get("answer"):
        lines += [f"**Synthesis mode:** {web_research.get('mode', 'unknown')}"
                  + (f" · {web_research['model']}" if web_research.get("model") else ""), "",
                  web_research["answer"], ""]
        if web_research.get("validation"):
            validation = web_research["validation"]
            lines.append(f"**Citation check:** {validation.get('grounded_share', 0):.0%} grounded sentences; "
                         f"{validation.get('invalid_citations_removed', 0)} invalid citation(s) removed.")
            lines.append("")
    else:
        lines += ["Live web search did not return enough evidence for a narrative synthesis. The database-backed "
                  "transaction analysis above remains available; no external facts have been inferred.", ""]
    lines += ["### Retrieved web and database evidence", ""]
    evidence = web_research.get("evidence") or []
    for item in evidence:
        url = item.get("url")
        citation = f"[{item.get('n')}]"
        title = item.get("title") or "Evidence item"
        details = " · ".join(str(x) for x in (item.get("source"), item.get("date"), item.get("kind")) if x)
        lines.append(f"- {citation} " + (f"[{title}]({url})" if url else title)
                     + (f" — {details}" if details else ""))
    if not evidence:
        lines.append("- No additional live web evidence was returned for this query.")
    lines.append("")
    return "\n".join(lines)


@app.get("/api/market-briefs")
async def list_market_briefs() -> dict:
    """Return a small public index of market briefs, never company-analysis history."""
    if not _configured():
        raise HTTPException(503, "The API is not configured.")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await _rpc(client, "list_market_briefs", {"p_limit": 20})
    if resp.status_code != 200:
        log.error("list_market_briefs failed: %s %s", resp.status_code, resp.text[:300])
        raise HTTPException(502, "Could not load recent market briefs.")
    rows = resp.json() or []
    return {"briefs": rows}


@app.post("/api/market-briefs")
async def create_market_brief(body: MarketBriefBody) -> dict:
    """Build and persist a public, source-linked market brief from the existing deal store."""
    if not _configured():
        raise HTTPException(503, "The API is not configured for saving market briefs.")
    from src.hosted_market import deals as market_deals, events as market_events, _country_or_404
    from src.engines import deals as deals_engine, provenance
    from src.data import africa_countries as ac

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=body.lookback_days - 1)
    country_code = None
    country_name = None
    if body.country:
        country_obj = _country_or_404(body.country.upper())
        country_code, country_name = country_obj.iso2, country_obj.name
    all_deals = market_deals()
    selected = deals_engine.search(
        all_deals, country=country_code, deal_type=body.deal_type,
        sector=body.sector, since=start.isoformat(),
        limit=max(len(all_deals), 1),
    )
    # Compare ISO date prefixes so same-day timestamps are not accidentally excluded
    # by a lexical comparison against a date-only upper bound.
    selected = [d for d in selected if d.get("announced") and start.isoformat() <= str(d["announced"])[:10] <= today.isoformat()]
    selected.sort(key=lambda d: d.get("announced") or "", reverse=True)
    disclosed = [float(d.get("amount_usd")) for d in selected if d.get("amount_usd") is not None and float(d.get("amount_usd") or 0) > 0]
    country_codes = set()
    for d in selected:
        for code in (d.get("countries") or []) + ([d.get("country")] if d.get("country") else []):
            resolved = ac.resolve(country=code)
            if resolved:
                country_codes.add(resolved.iso2)
    by_type: dict[str, int] = {}
    by_sector: dict[str, int] = {}
    by_country: dict[str, int] = {}
    for d in selected:
        kind = str(d.get("deal_type") or "unclassified")
        by_type[kind] = by_type.get(kind, 0) + 1
        sector_name = str(d.get("sector") or "unclassified")
        by_sector[sector_name] = by_sector.get(sector_name, 0) + 1
        resolved = ac.resolve(country=d.get("country")) if d.get("country") else None
        if resolved:
            by_country[resolved.name] = by_country.get(resolved.name, 0) + 1
    def top_labels(counts: dict[str, int], n: int = 3) -> str:
        return ", ".join(f"{name.replace('_', ' ')} ({count})" for name, count in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:n])
    patterns = []
    if by_type:
        patterns.append(f"Most represented transaction categories in this sample: {top_labels(by_type)}.")
    if by_sector:
        patterns.append(f"Most represented sectors in this sample: {top_labels(by_sector)}.")
    if by_country:
        patterns.append(f"Most represented countries in this sample: {top_labels(by_country)}.")
    if len(selected) < 5:
        patterns.append("The filtered sample contains fewer than five records; treat apparent concentrations as descriptive, not market-wide trends.")
    if not selected:
        patterns.append("No records in the current database match every selected filter and announcement-date constraint.")
    key_transactions = []
    for d in selected[:15]:
        independent = len(provenance.stories(d.get("sources") or []))
        amount = d.get("amount_usd")
        country_list = d.get("countries") or ([d.get("country")] if d.get("country") else [])
        key_transactions.append({
            **d,
            "amount_usd_label": (f"${float(amount):,.0f}" if amount is not None and float(amount) > 0 else None),
            "verification": "corroborated" if independent >= 2 else "single source",
            "independent_stories": independent,
            "countries": country_list,
        })
    comparable_pool = []
    for d in selected[:5]:
        result = deals_engine.comparables(all_deals, sector=d.get("sector"), country=d.get("country"),
                                          deal_type=d.get("deal_type"), amount_usd=d.get("amount_usd"),
                                          exclude_id=d.get("id"), limit=3)
        for comparable in result.get("deals", []):
            if comparable.get("announced") and start.isoformat() <= comparable["announced"][:10] <= today.isoformat():
                comparable_pool.append(comparable)
    seen = set()
    comparables = []
    selected_ids = {d.get("id") for d in selected}
    for d in comparable_pool:
        if d.get("id") in seen or d.get("id") in selected_ids:
            continue
        seen.add(d.get("id"))
        amount = d.get("amount_usd")
        comparables.append({**d, "amount_usd_label": f"${float(amount):,.0f}" if amount is not None and float(amount) > 0 else None})
        if len(comparables) >= 8:
            break
    advisory_signals = []
    signal_specs = [
        ({"debt_financing"}, "Debt and refinancing activity", "Repeated debt-financing records may justify checking refinancing calendars, lender exposure and restructuring disclosures."),
        ({"acquisition", "merger"}, "Consolidation activity", "Repeated acquisition/merger records may justify mapping active buyers, potential targets and sector consolidation."),
        ({"fund_raise"}, "Fundraising activity", "Repeated fund-raise records may justify reviewing capital-raising momentum and investor allocation patterns."),
        ({"exit"}, "Exit and liquidity activity", "Repeated exit records may justify examining exit routes, buyer appetite and portfolio liquidity."),
        ({"equity_funding"}, "Equity funding activity", "Repeated equity-funding records may justify comparing active investors, funding stages and sector capital formation."),
    ]
    for kinds, title, rationale in signal_specs:
        evidence_rows = [d for d in selected if d.get("deal_type") in kinds]
        if len(evidence_rows) >= 2:
            advisory_signals.append({
                "title": title,
                "rationale": rationale,
                "evidence_count": len(evidence_rows),
                "evidence": [
                    {"headline": d.get("headline") or d.get("target"), "url": next((s.get("url") for s in (d.get("sources") or []) if s.get("url")), None)}
                    for d in evidence_rows[:5]
                ],
            })
    # Hybrid retrieval: use the same evidence-grounded research engine as the Research page.
    # It combines stored deal/event records with live news search, then asks the configured
    # LLM to synthesize only from numbered evidence and validates its citations.
    from src.engines import research as research_engine
    scope_parts = [
        country_name or "Africa",
        body.sector.replace("_", " ") if body.sector else "all sectors",
        body.deal_type.replace("_", " ") if body.deal_type else "all transaction types",
    ]
    focus = body.research_question or (
        "Summarize the latest material transactions, capital flows, notable market shifts, "
        "and implications for the selected audience."
    )
    research_question = (
        f"Research {'; '.join(scope_parts)} private-market transactions and M&A for the "
        f"the last {body.lookback_days} days. "
        f"Audience: {body.audience}. Analyst focus: {focus}. "
        "Use hybrid research: compare the structured transaction database with live web/news results. "
        "Prioritize official company announcements, regulator/exchange filings, and reputable financial press. "
        "Separate confirmed reported facts from interpretation, identify conflicts and unknowns, and cite every material claim."
    )
    try:
        web_research = await run_in_threadpool(
            research_engine.research, research_question, selected, market_events()
        )
    except Exception as exc:
        log.warning("market brief hybrid research failed: %s", exc)
        web_research = {
            "question": research_question,
            "answer": "",
            "mode": "unavailable",
            "model": None,
            "evidence": [],
            "validation": {"grounded_share": 0, "invalid_citations_removed": 0},
            "error": "Hybrid web research was unavailable during this run.",
        }

    report = {
        "brief_type": "market_deals",
        "title": f"{country_name or 'Africa'} Deals & M&A Intelligence Brief",
        "audience": body.audience,
        "research_question": focus,
        "period_start": start.isoformat(),
        "period_end": today.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope_label": f"{country_name or 'Africa'} · {body.sector.replace('_', ' ') if body.sector else 'All sectors'} · {body.deal_type.replace('_', ' ') if body.deal_type else 'All transaction types'} · {body.lookback_days} days",
        "filters": {"lookback_days": body.lookback_days, "country": country_code, "sector": body.sector, "deal_type": body.deal_type},
        "metrics": {
            "transaction_count": len(selected),
            "disclosed_value_count": len(disclosed),
            "disclosed_value_usd": round(sum(disclosed)),
            "disclosed_value_usd_label": f"${sum(disclosed):,.0f}" if disclosed else "not available",
            "countries_represented": len(country_codes),
            "by_type": by_type, "by_sector": by_sector, "by_country": by_country,
        },
        "key_transactions": key_transactions,
        "comparables": comparables,
        "observed_patterns": patterns,
        "advisory_signals": advisory_signals,
        "web_research": web_research,
        "methodology": "Transactions are selected by the record's announcement date within the stated window, then filtered by country, sector and type. Amount totals include only positive disclosed/normalized USD amounts in the selected records. Comparable records are selected using the existing transparent sector/country/type/size similarity logic and then constrained to the same date window. Reported publication dates and transaction announcement dates are not interchangeable.",
        "coverage_note": "Coverage is limited to transactions discovered and retained by this product's sources and extraction pipeline. A missing record does not mean no transaction occurred. Syndicated copies are not treated as independent corroboration. Source counts indicate independent story groups where the provenance engine can resolve them; they do not certify every transaction field. This brief is a research aid, not a confirmation of mandates or investment advice.",
    }
    report["markdown"] = _market_brief_markdown(report)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await _rpc(client, "save_market_brief", {
            "secret": API_SECRET, "p_title": report["title"], "p_report": report, "p_markdown": report["markdown"],
        })
    if resp.status_code != 200:
        log.error("save_market_brief failed: %s %s", resp.status_code, resp.text[:300])
        raise HTTPException(502, "The report was generated but could not be saved.")
    return {"id": str(resp.json()), "title": report["title"], "transaction_count": len(selected), "period_start": report["period_start"], "period_end": report["period_end"]}


@app.get("/api/market-briefs/{brief_id}")
async def get_market_brief(brief_id: str) -> dict:
    try:
        uuid.UUID(brief_id)
    except ValueError:
        raise HTTPException(404, "Market brief not found.")
    if not _configured():
        raise HTTPException(503, "The API is not configured.")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await _rpc(client, "get_market_brief", {"p_id": brief_id})
    rows = resp.json() if resp.status_code == 200 else []
    if not rows:
        raise HTTPException(404, "Market brief not found.")
    row = rows[0]
    return {"id": row["id"], "title": row["title"], "report": row["report"], "markdown": row["markdown"], "created_at": row["created_at"]}


@app.post("/api/market-briefs/newsletter")
async def create_market_newsletter(body: NewsletterBody) -> dict:
    """Turn analyst-selected market-brief evidence into a saved deal/advisory newsletter."""
    if not _configured():
        raise HTTPException(503, "The API is not configured for saving newsletters.")
    try:
        source_id = str(uuid.UUID(body.source_brief_id))
    except ValueError:
        raise HTTPException(404, "Source market brief not found.")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await _rpc(client, "get_market_brief", {"p_id": source_id})
    rows = resp.json() if resp.status_code == 200 else []
    if not rows:
        raise HTTPException(404, "Source market brief not found.")
    source_row = rows[0]
    source_report = source_row.get("report") or {}
    source_deals = source_report.get("key_transactions") or []
    web_evidence = (source_report.get("web_research") or {}).get("evidence") or []
    selected_deals = []
    selected_web = []
    for key in body.selected_items:
        try:
            kind, raw_index = key.split(":", 1)
            idx = int(raw_index)
        except (ValueError, AttributeError):
            continue
        if kind == "deal" and 0 <= idx < len(source_deals):
            selected_deals.append(source_deals[idx])
        elif kind == "web":
            item = next((item for item in web_evidence if str(item.get("n")) == str(raw_index)), None)
            if item:
                selected_web.append(item)
    # Deduplicate in the order selected by the analyst.
    seen_deals = set()
    selected_deals = [d for d in selected_deals if not (
        str(d.get("id") or d.get("headline") or d.get("target")) in seen_deals
        or seen_deals.add(str(d.get("id") or d.get("headline") or d.get("target")))
    )]
    seen_web = set()
    selected_web = [e for e in selected_web if not (
        str(e.get("url") or e.get("title")) in seen_web
        or seen_web.add(str(e.get("url") or e.get("title")))
    )]
    if not selected_deals and not selected_web:
        raise HTTPException(422, "Select at least one valid deal or web evidence item.")

    from src.hosted_market import events as market_events
    from src.engines import research as research_engine
    kind_label = {"deal": "Deal briefing newsletter", "advisory": "Advisory briefing newsletter", "both": "Deal and advisory briefing newsletter"}[body.briefing_type]
    chosen_context = []
    for idx, deal in enumerate(selected_deals, 1):
        chosen_context.append(
            f"SELECTED DEAL {idx}: {deal.get('headline') or deal.get('target') or 'Transaction'}; "
            f"date={deal.get('announced') or 'unknown'}; country={deal.get('country') or 'unknown'}; "
            f"sector={deal.get('sector') or 'unknown'}; type={deal.get('deal_type') or 'unknown'}; "
            f"amount={deal.get('amount_usd_label') or 'undisclosed'}; parties="
            f"{', '.join(str(deal.get(k)) for k in ('buyer', 'target', 'seller') if deal.get(k)) or 'unknown'}."
        )
    for idx, item in enumerate(selected_web, 1):
        chosen_context.append(
            f"SELECTED WEB EVIDENCE {idx}: {item.get('title') or 'Untitled source'}; "
            f"publisher={item.get('source') or 'unknown'}; date={item.get('date') or 'unknown'}; "
            f"URL={item.get('url') or 'not available'}; excerpt={str(item.get('text') or '')[:900]}"
        )
    instructions = body.instructions or "Write a clear, decision-useful briefing with no generic filler."
    prompt = (
        f"Create a professional {kind_label.lower()} based on the analyst-selected items below. "
        f"Audience: {body.audience}. Source brief: {source_row.get('title')}. "
        f"Scope: {source_report.get('scope_label') or 'not specified'}. "
        f"Period: {source_report.get('period_start') or 'unknown'} to {source_report.get('period_end') or 'unknown'}. "
        f"Analyst instructions: {instructions}.\n\n"
        "Write a polished, publication-quality financial intelligence newsletter in NORMAL PROSE, not Markdown. "
        "Put a compelling headline on its own line, then a concise executive-summary paragraph, followed by short titled sections "
        "on material transactions, market implications, advisory considerations where requested, and what to watch next. "
        "Use complete natural-language paragraphs with clear transitions. Do not use Markdown syntax, hash-prefixed headings, "
        "asterisk emphasis, Markdown tables, or Markdown bullet lists. If a short list is essential, write it as plain numbered "
        "sentences, not Markdown. Keep the tone suitable for investment bankers, private equity and corporate strategy teams. "
        "Explain what matters and why; avoid generic filler and unsupported predictions. "
        "For advisory content, identify potential client needs and research angles only as hypotheses supported by evidence; "
        "never claim a company has an active mandate or fabricate client relationships. "
        "Separate reported facts from analysis, state when values are undisclosed, and do not infer missing figures. "
        "Cite factual claims with inline numbered citations like [1] only when those evidence items exist. Do not invent sources or citations. "
        "If evidence is thin or conflicting, say so explicitly. End with a concise conclusion and source-aware disclaimer.\n\n"
        + "\n".join(chosen_context)
    )
    try:
        research_result = await run_in_threadpool(
            research_engine.research, prompt, selected_deals, market_events()
        )
    except Exception:
        log.exception("market newsletter research failed")
        raise HTTPException(502, "The research service could not generate this newsletter. Please try again.")
    if research_result.get("mode") != "llm":
        raise HTTPException(502, "The LLM was unavailable for this run, so no newsletter was saved. Please retry when LLM research is available.")
    answer = str(research_result.get("answer") or "").strip()
    # Present newsletter copy as readable prose, not Markdown source.
    answer = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", answer)
    answer = re.sub(r"(?m)^\s*[-*+]\s+", "", answer)
    answer = re.sub(r"\*\*(.*?)\*\*", r"\1", answer)
    answer = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", answer)
    answer = re.sub(r"`{1,3}", "", answer)
    answer = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", answer)
    answer = re.sub(r"(?m)^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$", "", answer)
    answer = re.sub(r"\n{3,}", "\n\n", answer).strip()
    research_result["answer"] = answer
    if not answer:
        raise HTTPException(502, "The research engine returned no briefing text. Try again with a different selection.")

    now = datetime.now(timezone.utc).isoformat()
    title_prefix = {
        "deal": "Deal Intelligence Newsletter",
        "advisory": "Advisory Intelligence Newsletter",
        "both": "Deal & Advisory Intelligence Newsletter",
    }[body.briefing_type]
    title = f"{title_prefix}: {source_report.get('scope_label') or 'Selected research'}"
    report = {
        **source_report,
        "brief_type": "research_newsletter",
        "newsletter_type": body.briefing_type,
        "title": title,
        "audience": body.audience,
        "generated_at": now,
        "parent_brief_id": source_id,
        "parent_brief_title": source_row.get("title"),
        "selected_deal_count": len(selected_deals),
        "selected_web_evidence_count": len(selected_web),
        "key_transactions": selected_deals,
        "comparables": [],
        "advisory_signals": source_report.get("advisory_signals", []) if body.briefing_type in ("advisory", "both") else [],
        "newsletter_instructions": body.instructions,
        "newsletter_selected_evidence": selected_web,
        "research_question": prompt,
        "web_research": research_result,
        "methodology": "Generated from analyst-selected records and evidence using hybrid database/live-web research and the configured LLM. Review source links and verify material claims before external distribution.",
        "coverage_note": "This is analyst-drafted newsletter copy, not investment, legal, tax, or transaction advice. Advisory opportunities are research hypotheses, not confirmed mandates.",
    }
    lines = [
        f"# {title}", "",
        f"**Audience:** {body.audience}  ",
        f"**Source brief:** [{source_row.get('title')}](/app/market-briefs/{source_id})  ",
        f"**Generated:** {now}  ",
        f"**Selected deal records:** {len(selected_deals)} · **Selected web evidence items:** {len(selected_web)}", "",
        "---", "", answer, "",
        "## Analyst-selected source trail", "",
    ]
    for item in selected_deals:
        lines.append(f"- **{item.get('headline') or item.get('target') or 'Transaction'}** — {item.get('announced') or 'date unknown'}; {item.get('country') or 'country unknown'}; {item.get('amount_usd_label') or 'amount undisclosed'}.")
        for source in (item.get("sources") or [])[:3]:
            if source.get("url"):
                lines.append(f"  - [{source.get('publisher') or source.get('title') or 'Source'}]({source['url']})")
    for item in selected_web:
        title_text = item.get("title") or "Web evidence"
        if item.get("url"):
            lines.append(f"- [{title_text}]({item['url']}) — {item.get('source') or 'publisher unknown'}; {item.get('date') or 'date unknown'}.")
        else:
            lines.append(f"- {title_text} — source URL unavailable.")
    lines += ["", "## Research engine evidence", ""]
    for item in (research_result.get("evidence") or []):
        url = item.get("url")
        label = item.get("title") or "Evidence"
        lines.append(f"- [{label}]({url})" if url else f"- {label}")
    lines += ["", "## Review note", "", report["coverage_note"], ""]
    markdown = "\n".join(lines)
    report["markdown"] = markdown
    async with httpx.AsyncClient(timeout=20) as client:
        saved = await _rpc(client, "save_market_brief", {
            "secret": API_SECRET, "p_title": title, "p_report": report, "p_markdown": markdown,
        })
    if saved.status_code != 200:
        log.error("save_market_brief newsletter failed: %s %s", saved.status_code, saved.text[:300])
        raise HTTPException(502, "The newsletter was generated but could not be saved. Please retry.")
    new_id = saved.json()
    return {"id": str(new_id), "title": title, "markdown": markdown, "mode": research_result.get("mode"), "evidence_count": len(research_result.get("evidence") or [])}


@app.get("/api/briefs/{brief_id}")
async def get_brief(brief_id: str) -> dict:
    try:
        uuid.UUID(brief_id)
    except ValueError:
        raise HTTPException(404, "Brief not found.")
    if not _configured():
        raise HTTPException(503, "The API is not configured.")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await _rpc(client, "get_brief", {"p_id": brief_id})
    rows = resp.json() if resp.status_code == 200 else []
    if not rows:
        raise HTTPException(404, "Brief not found.")
    return rows[0]


def _label_brief(row: dict, today: date) -> tuple[int, list[dict], list[dict]]:
    """Outcomes for one stored brief's signals, plus ground truth for its company."""
    from src.engines.outcome_labeller import CONFIRMATION_WINDOW_DAYS, fetch_events, ground_truth, label_prediction
    from src.schemas.models import SignalType

    created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")).astimezone(timezone.utc).date()
    stage = 2 if (today - created).days >= CONFIRMATION_WINDOW_DAYS + 5 else 1
    ticker = row.get("ticker")
    events = fetch_events(row["company"], ticker, created, today)
    outcomes = []
    for sig in (row.get("brief") or {}).get("detected_signals", []):
        alpha = sig.get("alpha_score") or {}
        try:
            signal_type = SignalType(sig["signal_type"])
        except (KeyError, ValueError):
            continue
        o = label_prediction(
            company_name=row["company"], ticker=ticker, signal_type=signal_type,
            severity=sig.get("severity", "low"), detection_date=created, alpha_score=alpha.get("score"),
            expected_direction=alpha.get("expected_direction"),
            expected_low=alpha.get("expected_magnitude_pct_low"),
            expected_high=alpha.get("expected_magnitude_pct_high"),
            events=events, today=today,
        )
        if o:
            outcomes.append(o)
    truth = ground_truth(row["company"], events, created, today) if events else []
    return stage, outcomes, truth


@app.get("/api/cron/label")
async def cron_label(request: Request) -> dict:
    """Daily: label due briefs (price reaction at 12+ days, confirmation at 95+)."""
    if not CRON_SECRET or request.headers.get("authorization") != f"Bearer {CRON_SECRET}":
        raise HTTPException(401, "Unauthorized")
    if not _configured():
        raise HTTPException(503, "The API is not configured.")
    deadline = time.monotonic() + 240
    today = datetime.now(timezone.utc).date()
    done = outcomes_written = 0
    from src.tools.african_prices import set_snapshot, snapshot_rows
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Snapshot today's NGX / NSE closes: the only way to build their price history.
        try:
            price_rows = await run_in_threadpool(snapshot_rows)
            r = await _rpc(client, "save_prices", {"secret": API_SECRET, "p_rows": price_rows})
            prices_saved = int(r.json()) if r.status_code == 200 else 0
        except Exception:
            log.exception("price snapshot failed")
            prices_saved = 0
        # 2. Price history for labelling African briefs.
        r = await _rpc(client, "get_prices", {"secret": API_SECRET, "p_since": (today - timedelta(days=140)).isoformat()})
        if r.status_code != 200:
            log.error("get_prices failed: %s %s", r.status_code, r.text[:300])
            raise HTTPException(502, "Could not load price history for daily outcome labelling.")
        set_snapshot(r.json())
        resp = await _rpc(client, "briefs_to_label", {"secret": API_SECRET, "max_n": 60})
        if resp.status_code != 200:
            log.error("briefs_to_label failed: %s %s", resp.status_code, resp.text[:300])
            raise HTTPException(502, "Could not load briefs due for daily outcome labelling.")
        rows = resp.json()
        label_errors = 0
        for row in rows:
            if time.monotonic() > deadline:
                break
            try:
                stage, outcomes, truth = await run_in_threadpool(_label_brief, row, today)
            except Exception:
                log.exception("labelling failed for brief %s", row.get("id"))
                continue
            r = await _rpc(client, "save_labels", {
                "secret": API_SECRET, "p_brief_id": row["id"], "p_stage": stage,
                "p_outcomes": outcomes, "p_events": truth,
            })
            if r.status_code == 200:
                done += 1
                outcomes_written += len(outcomes)
            else:
                label_errors += 1
                log.error("save_labels failed for brief %s: %s %s", row.get("id"), r.status_code, r.text[:300])
    set_snapshot(None)
    from src.hosted_market import refresh_live
    async with httpx.AsyncClient(timeout=30) as client:
        await refresh_live(client, force=True)
    if label_errors:
        raise HTTPException(502, f"Daily labelling only partially completed: {label_errors} label writes failed. The scheduled run must be retried.")
    return {"status": "ok", "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "prices_saved": prices_saved, "due": len(rows), "labelled": done, "outcomes": outcomes_written}
