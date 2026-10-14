"""
SEC EDGAR Full-Text Search & EDGAR REST API integration.
Uses the official EDGAR APIs (no auth required, rate-limited to 10 req/s).
"""
from __future__ import annotations

import asyncio
import html
import json
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import quote

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.schemas.models import SECFiling, FilingType
from src.utils.clock import utcnow

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

# EDGAR renamed "SC 13D" to "SCHEDULE 13D" in December 2024; both spellings are kept.
SIGNAL_FORMS = ["8-K", "10-K", "10-Q", "SC 13D", "SCHEDULE 13D", "SC 13G", "4", "DEF 14A"]

# Form 4 filings are only signals when they show discretionary open-market trades.
# Grants (A), option exercises (M), tax withholding (F), gifts (G) and sales under a
# pre-arranged Rule 10b5-1 plan are routine and are dropped.
FORM4_MIN_SALE_USD = 1_000_000

# SEC fair-access policy: at most 10 requests per second per client.
SEC_MAX_REQUESTS_PER_SECOND = 8
MA_KEYWORDS  = ["merger", "acquisition", "takeover", "tender offer", "going private", "buyout"]
DISTRESS_KW  = ["bankruptcy", "default", "restructuring", "going concern", "liquidity", "covenant breach"]
CREDIT_KW    = ["credit facility", "debt", "leverage", "impairment", "write-down", "goodwill"]


# Form 8-K item titles (17 CFR 249.308). The submissions API gives only the codes.
EIGHT_K_ITEMS = {
    "1.01": "Entry into a Material Definitive Agreement",
    "1.02": "Termination of a Material Definitive Agreement",
    "1.03": "Bankruptcy or Receivership",
    "1.05": "Material Cybersecurity Incidents",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of a Direct Financial Obligation",
    "2.04": "Triggering Events That Accelerate or Increase a Direct Financial Obligation",
    "2.05": "Costs Associated with Exit or Disposal Activities",
    "2.06": "Material Impairments",
    "3.01": "Notice of Delisting or Failure to Satisfy a Continued Listing Rule",
    "3.02": "Unregistered Sales of Equity Securities",
    "3.03": "Material Modification to Rights of Security Holders",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements",
    "5.01": "Changes in Control of Registrant",
    "5.02": "Departure or Appointment of Directors or Certain Officers",
    "5.03": "Amendments to Articles of Incorporation or Bylaws",
    "5.07": "Submission of Matters to a Vote of Security Holders",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}


class _RateLimiter:
    """Spaces request start times so at most `per_second` begin in any second."""

    def __init__(self, per_second: float):
        self._interval = 1.0 / per_second
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            start = max(now, self._next)
            self._next = start + self._interval
        if start > now:
            await asyncio.sleep(start - now)


def _xml_value(block: str, tag: str) -> str:
    """Text of <tag>...</tag>, or of its nested <value>, within an ownership XML block."""
    m = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.S)
    if not m:
        return ""
    inner = m.group(1)
    v = re.search(r"<value>(.*?)</value>", inner, re.S)
    return html.unescape((v.group(1) if v else inner).strip())


def form4_owner(xml: str) -> Optional[dict[str, str]]:
    """The reporting owner of a Form 4 and their role, for the entity graph."""
    name = _xml_value(xml, "rptOwnerName")
    if not name:
        return None
    roles = []
    if _xml_value(xml, "isDirector") in ("1", "true"):
        roles.append("Director")
    if _xml_value(xml, "officerTitle"):
        roles.append(_xml_value(xml, "officerTitle"))
    if _xml_value(xml, "isTenPercentOwner") in ("1", "true"):
        roles.append("10% owner")
    return {"name": name, "role": ", ".join(roles) or "Insider", "cik": _xml_value(xml, "rptOwnerCik")}


def describe_form4(xml: str) -> Optional[str]:
    """
    Summarise the discretionary open-market trades in a Form 4 ownership document.
    Returns None when the filing holds no such trade (grants, exercises, withholding,
    small sales, or sales under a Rule 10b5-1 plan).
    """
    if _xml_value(xml, "aff10b5One").lower() in ("1", "true"):
        planned_sale = True
    else:
        planned_sale = False
    owner = _xml_value(xml, "rptOwnerName") or "an insider"
    title = _xml_value(xml, "officerTitle") or ("Director" if _xml_value(xml, "isDirector") in ("1", "true") else "")
    who = f"{owner} ({title})" if title else owner

    totals = {"P": [0.0, 0.0], "S": [0.0, 0.0]}   # code -> [shares, value]
    for tx in re.findall(r"<nonDerivativeTransaction>(.*?)</nonDerivativeTransaction>", xml, re.S):
        code = _xml_value(tx, "transactionCode")
        if code not in totals:
            continue
        try:
            shares = float(_xml_value(tx, "transactionShares") or 0)
            price = float(_xml_value(tx, "transactionPricePerShare") or 0)
        except ValueError:
            continue
        totals[code][0] += shares
        totals[code][1] += shares * price

    parts = []
    if totals["P"][0] > 0:
        parts.append(f"open-market purchase of {totals['P'][0]:,.0f} shares (${totals['P'][1]:,.0f})")
    if totals["S"][0] > 0 and not planned_sale and totals["S"][1] >= FORM4_MIN_SALE_USD:
        parts.append(f"open-market sale of {totals['S'][0]:,.0f} shares (${totals['S'][1]:,.0f}), not under a 10b5-1 plan")
    if not parts:
        return None
    return f"Form 4 filed: {' and '.join(parts)} by {who}"


def _describe_8k_items(items: str) -> str:
    """'2.02,9.01' -> 'Item 2.02: Results of Operations ...; Item 9.01: ...'"""
    parts = []
    for code in (c.strip() for c in items.split(",")):
        if code:
            parts.append(f"Item {code}: {EIGHT_K_ITEMS.get(code, 'Unlisted item')}")
    return "; ".join(parts)


class EdgarTool:
    """
    Async tool for querying SEC EDGAR.
    Provides company resolution, filing retrieval, and full-text search.
    """

    def __init__(self, timeout: float = 20.0):
        self._client: Optional[httpx.AsyncClient] = None
        self.timeout = timeout
        # Reporting owners seen in every Form 4 read, routine ones included.
        self.insiders: dict[str, dict[str, str]] = {}

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
            name_match = re.search(r'<(?:conformed-name|company-name)>([^<]+)</', text)
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
            name_match = re.search(r'<(?:conformed-name|company-name)>([^<]+)</', text)
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

        cutoff = (utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        target_forms = set(forms or SIGNAL_FORMS)
        filings: list[SECFiling] = []

        recent = data.get("filings", {}).get("recent", {})
        form_types  = recent.get("form", [])
        filed_dates = recent.get("filingDate", [])
        accessions  = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        descriptions = recent.get("primaryDocDescription", [])
        item_codes   = recent.get("items", [])

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
            items = item_codes[i] if i < len(item_codes) else ""
            if form_type == "8-K" and items:
                desc = _describe_8k_items(items)

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

        return await self._enrich_form4(filings)

    async def _enrich_form4(self, filings: list[SECFiling]) -> list[SECFiling]:
        """Replace Form 4 entries with a description of their open-market trades, dropping routine ones."""
        limiter = _RateLimiter(SEC_MAX_REQUESTS_PER_SECOND)

        async def enrich(f: SECFiling) -> Optional[SECFiling]:
            if f.form_type != "4":
                return f
            # primaryDocument is the XSL-rendered view (xslF345X06/form4.xml); the raw XML drops that prefix.
            xml_url = re.sub(r"/xslF345X\d+/", "/", f.document_url)
            await limiter.wait()
            try:
                r = await self.client.get(xml_url)
                r.raise_for_status()
                summary = describe_form4(r.text)
                owner = form4_owner(r.text)
                if owner:
                    self.insiders.setdefault(owner["cik"] or owner["name"], owner)
            except Exception:
                summary = None
            return f.model_copy(update={"description": summary, "document_url": xml_url}) if summary else None

        # Every Form 4 in the lookback window is read, paced to SEC's request limit.
        results = await asyncio.gather(*(enrich(f) for f in filings))
        return [f for f in results if f is not None]

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
        end_date   = utcnow().strftime("%Y-%m-%d")
        start_date = (utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
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

        profile = {**profile, "insiders": list(edgar.insiders.values())}
        return profile, all_filings
