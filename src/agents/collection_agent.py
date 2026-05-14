"""
Data Collection Agent.
LangGraph node that resolves the company profile, fetches SEC filings,
African exchange disclosures, and news — populating AgentState for downstream agents.
"""
from __future__ import annotations

import asyncio

from src.schemas.models import AgentState, CompanyProfile
from src.tools.edgar_tool import search_company_filings
from src.tools.news_tool import fetch_market_news
from src.tools.africa_tool import fetch_african_intelligence


class DataCollectionAgent:
    """
    Runs three concurrent pipelines:
      1. SEC EDGAR — US company resolution + filing retrieval
      2. African exchanges — NGX / JSE SENS / NSE Kenya disclosures + African news
      3. Global financial news — RSS feeds with relevance scoring

    All three run in parallel. Each fails independently without blocking the others.
    Populates state.company_profile, state.filings, state.news_items.
    """

    async def run(self, state: AgentState) -> AgentState:
        state.log("data_collection", "Starting data collection (US + Africa)")

        req = state.request

        # ── Three concurrent pipelines ──────────────────────────────────
        edgar_task  = asyncio.create_task(
            search_company_filings(
                company_name=req.company_name,
                ticker=req.ticker,
                cik=req.cik,
                lookback_days=req.lookback_days
            )
        )
        africa_task = asyncio.create_task(
            fetch_african_intelligence(
                company_name=req.company_name,
                ticker=req.ticker,
                lookback_days=req.lookback_days
            )
        )
        news_task   = asyncio.create_task(
            fetch_market_news(
                company_name=req.company_name,
                ticker=req.ticker,
                lookback_days=req.lookback_days
            )
        )

        edgar_result, africa_result, news_result = await asyncio.gather(
            edgar_task, africa_task, news_task, return_exceptions=True
        )

        # ── Process EDGAR (US) ──────────────────────────────────────────
        if isinstance(edgar_result, Exception):
            state.errors.append(f"EDGAR collection failed: {edgar_result}")
            profile_dict: dict = {"name": req.company_name, "cik": req.cik, "ticker": req.ticker}
            us_filings = []
        else:
            profile_dict, us_filings = edgar_result

        state.company_profile = CompanyProfile(
            name=profile_dict.get("name") or req.company_name,
            ticker=profile_dict.get("ticker") or req.ticker,
            cik=profile_dict.get("cik") or req.cik,
            exchange=profile_dict.get("exchange"),
            sector=profile_dict.get("sector"),
            description=profile_dict.get("description"),
        )

        # ── Process African exchange disclosures ────────────────────────
        african_filings = []
        african_news    = []
        if isinstance(africa_result, Exception):
            state.errors.append(f"Africa collection failed: {africa_result}")
        else:
            african_filings, african_news = africa_result

        # ── Merge filings (US + Africa), deduplicate ────────────────────
        seen_keys: set[str] = set()
        all_filings = []
        for f in us_filings + african_filings:
            key = f.accession_number or f.document_url
            if key not in seen_keys:
                seen_keys.add(key)
                all_filings.append(f)
        state.filings = all_filings

        # ── Process global news ─────────────────────────────────────────
        global_news: list = []
        if isinstance(news_result, Exception):
            state.errors.append(f"News collection failed: {news_result}")
        else:
            global_news = news_result

        # ── Merge news (global + African), deduplicate by title ─────────
        seen_titles: set[str] = set()
        all_news = []
        for n in global_news + african_news:
            if n.title not in seen_titles:
                seen_titles.add(n.title)
                all_news.append(n)
        # Re-sort merged list by relevance
        all_news.sort(key=lambda n: n.relevance_score, reverse=True)
        state.news_items = all_news

        # ── Log summary ─────────────────────────────────────────────────
        filing_types = list({f.form_type for f in state.filings})
        african_filing_count = len(african_filings)
        us_filing_count      = len(us_filings)

        state.log(
            "data_collection",
            (
                f"Collected {len(state.filings)} filings "
                f"(US: {us_filing_count}, Africa: {african_filing_count}), "
                f"{len(state.news_items)} news items "
                f"(global: {len(global_news)}, Africa: {len(african_news)})"
            ),
            {
                "company_resolved": state.company_profile.name,
                "cik": state.company_profile.cik,
                "filing_types": filing_types,
                "african_sources": [f.cik for f in african_filings if f.cik in ("NGX", "JSE", "NSE-KE")],
            }
        )

        return state
