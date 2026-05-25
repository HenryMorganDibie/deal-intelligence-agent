"""
SEC EDGAR Full-Text Search & EDGAR REST API integration.
Uses the official EDGAR APIs (no auth required, rate-limited to 10 req/s).
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import quote

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.schemas.models import SECFiling, FilingType

EDGAR_BASE       = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SEARCH     = "https://efts.sec.gov/LATEST/search-index?q={query}&dateRange=custom&startdt={start}&enddt={end}&forms={forms}"
EDGAR_COMPANY    = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_FULL_TEXT  = "https://efts.sec.gov/LATEST/search-index?q=%22{query}%22&forms={forms}&dateRange=custom&startdt={start}&enddt={end}"
EDGAR_SEARCH_API = "https://efts.sec.gov/LATEST/search-index"

# The public EDGAR full-text search endpoint
EDGAR_EFTS = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_COMPANY_SEARCH = "https://www.sec.gov/cgi-bin/browse-edgar?company={name}&CIK=&type=&dateb=&owner=include&count=10&search_text=&action=getcompany&output=atom"
EDGAR_FULL_SEARCH = "https://efts.sec.gov/LATEST/search-index?q={q}&forms={forms}&dateRange=custom&startdt={start}&enddt={end}&_source=period_of_report,file_date,form_type,entity_name,file_num,period_of_report,biz_location,inc_states"

# New EDGAR search endpoint
EDGAR_SEARCH_V2 = "https://efts.sec.gov/LATEST/search-index?q={q}&dateRange=custom&startdt={start}&enddt={end}&forms={forms}"

HEADERS = {
    "User-Agent": "DealIntelligenceAgent henry@dealintel.ai",
    "Accept-Encoding": "gzip, deflate",
    "Host": "efts.sec.gov"
}

SIGNAL_FORMS = ["8-K", "10-K", "10-Q", "SC 13D", "SC 13G", "Form 4", "DEF 14A"]
MA_KEYWORDS  = ["merger", "acquisition", "takeover", "tender offer", "going private", "buyout"]
DISTRESS_KW  = ["bankruptcy", "default", "restructuring", "going concern", "liquidity", "covenant breach"]
CREDIT_KW    = ["credit facility", "debt", "leverage", "impairment", "write-down", "goodwill"]


class EdgarTool:
    """
    Async tool for querying SEC EDGAR.
    Provides company resolution, filing retrieval, and full-text search.
    """

    def __init__(self, timeout: float = 20.0):
        self._client: Optional[httpx.AsyncClient] = None
        self.timeout = timeout

    async def __aenter__(self) -> "EdgarTool":
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "DealIntelligenceAgent research@dealintel.ai"},
            timeout=self.timeout,
            follow_redirects=True
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("EdgarTool must be used as async context manager")
        return self._client

    # ── Company Resolution ──────────────────────────────────────────────

    async def resolve_company(self, name: str, ticker: Optional[str] = None) -> dict[str, Any]:
        """
        Resolve company to CIK using EDGAR company search.
        Returns dict with cik, name, ticker, exchange, sic info.
        """
        # Try ticker first (more precise)
        if ticker:
            result = await self._resolve_by_ticker(ticker)
            if result:
                return result

        # Fall back to name search
        return await self._resolve_by_name(name)

    async def _resolve_by_ticker(self, ticker: str) -> Optional[dict[str, Any]]:
        try:
            url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=&CIK={ticker}&type=10-K&dateb=&owner=include&count=5&search_text=&output=atom"
            r = await self.client.get(url)
            r.raise_for_status()
            # Parse atom/XML for CIK
            text = r.text
            cik_match = re.search(r'CIK=(\d+)', text)
            name_match = re.search(r'<company-name>([^<]+)</company-name>', text)
            if cik_match:
                return {
                    "cik": cik_match.group(1).zfill(10),
                    "name": name_match.group(1) if name_match else ticker,
                    "ticker": ticker
                }
        except Exception:
            pass
        return None

    async def _resolve_by_name(self, name: str) -> dict[str, Any]:
        try:
            url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={quote(name)}&CIK=&type=10-K&dateb=&owner=include&count=5&search_text=&action=getcompany&output=atom"
            r = await self.client.get(url)
            r.raise_for_status()
            text = r.text
            cik_match = re.search(r'CIK=(\d+)', text)
            name_match = re.search(r'<company-name>([^<]+)</company-name>', text)
            return {
                "cik": cik_match.group(1).zfill(10) if cik_match else None,
                "name": name_match.group(1) if name_match else name,
                "ticker": None
            }
        except Exception:
            return {"cik": None, "name": name, "ticker": None}

    # ── Filing Retrieval ────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def get_recent_filings(
        self,
        cik: str,
        forms: list[str] | None = None,
        lookback_days: int = 90
    ) -> list[SECFiling]:
        """
        Fetch recent filings for a company via EDGAR submissions API.
        """
        if not cik:
            return []

        padded_cik = cik.zfill(10)
        url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"

        try:
            r = await self.client.get(url)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return []

        cutoff = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        target_forms = set(forms or SIGNAL_FORMS)
        filings: list[SECFiling] = []

        recent = data.get("filings", {}).get("recent", {})
        form_types  = recent.get("form", [])
        filed_dates = recent.get("filingDate", [])
        accessions  = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        descriptions = recent.get("primaryDocDescription", [])

        for i, form_type in enumerate(form_types):
            if form_type not in target_forms:
                continue
            if i >= len(filed_dates):
                continue
            filing_date = filed_dates[i]
            if filing_date < cutoff:
                continue  # outside lookback window

            accession = accessions[i] if i < len(accessions) else ""
            acc_nodash = accession.replace("-", "")
            doc = primary_docs[i] if i < len(primary_docs) else ""
            desc = descriptions[i] if i < len(descriptions) else ""

            doc_url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash}/{doc}"
                if doc else
                f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form_type}&dateb=&owner=include&count=5"
            )

            filings.append(SECFiling(
                accession_number=accession,
                form_type=form_type,
                filing_date=filing_date,
                company_name=data.get("name", ""),
                cik=cik,
                document_url=doc_url,
                description=desc
            ))

            if len(filings) >= 20:  # cap per company
                break

        return filings

    # ── Full-Text Search ────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def fulltext_search(
        self,
        query: str,
        forms: list[str] | None = None,
        lookback_days: int = 90,
        max_results: int = 10
    ) -> list[SECFiling]:
        """
        Full-text search across all EDGAR filings using EFTS endpoint.
        """
        end_date   = datetime.utcnow().strftime("%Y-%m-%d")
        start_date = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        forms_str  = ",".join(forms or ["8-K", "10-K", "10-Q"])

        url = "https://efts.sec.gov/LATEST/search-index"
        params = {
            "q": f'"{query}"',
            "dateRange": "custom",
            "startdt": start_date,
            "enddt": end_date,
            "forms": forms_str,
        }

        try:
            r = await self.client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return []

        hits = data.get("hits", {}).get("hits", [])[:max_results]
        filings: list[SECFiling] = []

        for hit in hits:
            src = hit.get("_source", {})
            entity = src.get("entity_name", "Unknown")
            cik_raw = src.get("file_num", "") or src.get("period_of_report", "")
            accession = hit.get("_id", "")
            form_type = src.get("form_type", "")
            file_date = src.get("file_date", "")

            # Build document URL from accession
            acc_clean = accession.replace("-", "")
            cik_num = src.get("_ciks", ["0"])[0] if src.get("_ciks") else "0"
            doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_clean}/"

            filings.append(SECFiling(
                accession_number=accession,
                form_type=form_type,
                filing_date=file_date,
                company_name=entity,
                cik=str(cik_num),
                document_url=doc_url,
                description=src.get("period_of_report", ""),
                raw_excerpt=hit.get("highlight", {}).get("file_date", [""])[0] if hit.get("highlight") else None
            ))

        return filings

    # ── Document Extraction ─────────────────────────────────────────────

    async def extract_filing_text(self, filing: SECFiling, max_chars: int = 4000) -> str:
        """
        Attempt to fetch and extract key text from a filing document.
        Returns truncated plain text for LLM consumption.
        """
        if not filing.document_url:
            return ""
        try:
            r = await self.client.get(filing.document_url)
            r.raise_for_status()
            text = r.text
            # Strip HTML tags
            text = re.sub(r'<[^>]+>', ' ', text)
            # Normalise whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:max_chars]
        except Exception:
            return ""


async def search_company_filings(
    company_name: str,
    ticker: Optional[str],
    cik: Optional[str],
    lookback_days: int = 90
) -> tuple[dict[str, Any], list[SECFiling]]:
    """
    Convenience wrapper: resolve company + fetch filings in one call.
    Returns (profile_dict, filings_list).
    """
    async with EdgarTool() as edgar:
        profile = await edgar.resolve_company(company_name, ticker)
        resolved_cik = cik or profile.get("cik")

        filings: list[SECFiling] = []
        if resolved_cik:
            filings = await edgar.get_recent_filings(resolved_cik, lookback_days=lookback_days)

        # Also run keyword searches for high-value signals
        kw_results: list[SECFiling] = []
        if company_name:
            for kw in MA_KEYWORDS[:2]:  # limit to avoid rate limits
                hits = await edgar.fulltext_search(
                    f"{company_name} {kw}",
                    forms=["8-K"],
                    lookback_days=lookback_days,
                    max_results=3
                )
                kw_results.extend(hits)
                await asyncio.sleep(0.12)  # respect 10 req/s limit

        # Deduplicate by accession number
        seen = set()
        all_filings: list[SECFiling] = []
        for f in filings + kw_results:
            key = f.accession_number or f.document_url
            if key not in seen:
                seen.add(key)
                all_filings.append(f)

        return profile, all_filings
