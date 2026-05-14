"""
Data Collection Agent.
LangGraph node that resolves the company profile, fetches SEC filings,
and retrieves news items — populating AgentState for downstream agents.
"""
from __future__ import annotations

import asyncio

from src.schemas.models import AgentState, CompanyProfile
from src.tools.edgar_tool import search_company_filings
from src.tools.news_tool import fetch_market_news


class DataCollectionAgent:
    """
    Runs concurrently:
      1. SEC EDGAR company resolution + filing retrieval
      2. Financial news collection
    Populates state.company_profile, state.filings, state.news_items.
    """

    async def run(self, state: AgentState) -> AgentState:
        state.log("data_collection", "Starting data collection")

        req = state.request

        # Run EDGAR + news concurrently
        edgar_task = asyncio.create_task(
            search_company_filings(
                company_name=req.company_name,
                ticker=req.ticker,
                cik=req.cik,
                lookback_days=req.lookback_days
            )
        )
        news_task = asyncio.create_task(
            fetch_market_news(
                company_name=req.company_name,
                ticker=req.ticker,
                lookback_days=req.lookback_days
            )
        )

        # Gather with error isolation
        edgar_result, news_result = await asyncio.gather(
            edgar_task, news_task, return_exceptions=True
        )

        # Process EDGAR result
        if isinstance(edgar_result, Exception):
            state.errors.append(f"EDGAR collection failed: {edgar_result}")
            profile_dict = {"name": req.company_name, "cik": req.cik, "ticker": req.ticker}
            filings = []
        else:
            profile_dict, filings = edgar_result

        state.company_profile = CompanyProfile(
            name=profile_dict.get("name") or req.company_name,
            ticker=profile_dict.get("ticker") or req.ticker,
            cik=profile_dict.get("cik") or req.cik,
            exchange=profile_dict.get("exchange"),
            sector=profile_dict.get("sector"),
            description=profile_dict.get("description"),
        )
        state.filings = filings

        # Process news result
        if isinstance(news_result, Exception):
            state.errors.append(f"News collection failed: {news_result}")
            state.news_items = []
        else:
            state.news_items = news_result

        state.log(
            "data_collection",
            f"Collected {len(state.filings)} filings, {len(state.news_items)} news items",
            {
                "company_resolved": state.company_profile.name,
                "cik": state.company_profile.cik,
                "filing_types": list({f.form_type for f in state.filings}),
            }
        )

        return state
