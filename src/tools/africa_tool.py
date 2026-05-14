"""
African Markets Intelligence Tool.
Pulls regulatory filings and financial news from African exchanges and media:

Exchanges (public disclosure portals):
  - NGX (Nigerian Exchange Group) — ngxgroup.com
  - JSE (Johannesburg Stock Exchange) — jse.co.za
  - NSE Kenya (Nairobi Securities Exchange) — nse.co.ke
  - GSE (Ghana Stock Exchange) — gse.com.gh

News sources (RSS + structured scraping):
  - BusinessDay Nigeria
  - TechCabal
  - African Business Magazine
  - The Africa Report
  - Stears (public RSS)
  - Moneyweb (South Africa)
  - BusinessLive (South Africa)
  - BD Africa / Nation Media (Kenya/East Africa)

No API keys required — all public sources.
"""
from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import quote

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.schemas.models import SECFiling, NewsItem

# ─── African Exchange Disclosure Portals ─────────────────────────────────────
# These are the public company announcement/disclosure feeds where listed
# companies file material information (equivalent to SEC EDGAR for Africa).

NGX_ANNOUNCEMENTS  = "https://ngxgroup.com/exchange/data/company-announcements/?download=rss"
NGX_SEARCH         = "https://ngxgroup.com/exchange/data/company-announcements/?q={query}"
JSE_SENS           = "https://senssearch.co.za/articles.rss?q={query}"           # SENS = Stock Exchange News Service
NSE_KENYA_DISC     = "https://www.nse.co.ke/regulatory-framework/announcements/company-announcements.html"
GSE_ANNOUNCEMENTS  = "https://gse.com.gh/listed-companies/company-news/"

# ─── African Financial News RSS Feeds ────────────────────────────────────────
AFRICAN_NEWS_FEEDS = {
    "BusinessDay Nigeria":    "https://businessday.ng/feed/",
    "TechCabal":              "https://techcabal.com/feed/",
    "The Africa Report":      "https://www.theafricareport.com/feed/",
    "African Business":       "https://african.business/feed",
    "Moneyweb":               "https://www.moneyweb.co.za/feed/",
    "BusinessLive SA":        "https://www.businesslive.co.za/rss/",
    "Stears":                 "https://stears.co/feed/",
    "Nation Africa":          "https://nation.africa/rss/",
    "Daily Monitor Uganda":   "https://www.monitor.co.ug/Uganda/Business/rss/",
}

# Google News Africa-scoped queries
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-NG&gl=NG&ceid=NG:en"
GOOGLE_NEWS_SA  = "https://news.google.com/rss/search?q={query}&hl=en-ZA&gl=ZA&ceid=ZA:en"
GOOGLE_NEWS_KE  = "https://news.google.com/rss/search?q={query}&hl=en-KE&gl=KE&ceid=KE:en"

# African regulatory bodies (for regulatory signal queries)
AFRICAN_REGULATORS = ["SEC Nigeria", "FSCA", "CMA Kenya", "SEC Ghana", "CBN", "SARB", "CBK"]

AFRICAN_SIGNAL_KEYWORDS = {
    "m_and_a": ["merger", "acquisition", "takeover", "scheme of arrangement", "offer to acquire",
                "definitive agreement", "strategic partnership", "buyout", "acquires"],
    "credit_risk": ["credit downgrade", "default", "debt restructur", "going concern",
                    "liquidity crisis", "covenant breach", "impairment", "write-down",
                    "Moody's", "S&P", "Fitch", "GCR Ratings"],
    "distressed": ["business rescue", "liquidation", "provisional liquidation", "judicial management",
                   "administration", "receivership", "insolvency", "voluntary winding up"],
    "regulatory": ["SEC probe", "FSCA action", "CMA investigation", "CBN sanction",
                   "regulatory fine", "licence revoked", "enforcement action", "fraud investigation"],
    "leadership": ["ceo resign", "ceo depart", "cfo resign", "cfo depart", "md resign",
                   "board chairman resign", "executive director resign", "management change"],
    "earnings": ["profit warning", "revenue decline", "earnings miss", "below guidance",
                 "trading statement", "headline earnings", "loss after tax"],
}

AFRICAN_SOURCE_MAP = {
    "businessday.ng":        "BusinessDay Nigeria",
    "techcabal.com":         "TechCabal",
    "theafricareport.com":   "The Africa Report",
    "african.business":      "African Business",
    "moneyweb.co.za":        "Moneyweb",
    "businesslive.co.za":    "BusinessLive SA",
    "stears.co":             "Stears",
    "nation.africa":         "Nation Africa",
    "monitor.co.ug":         "Daily Monitor Uganda",
    "ngxgroup.com":          "NGX Group",
    "jse.co.za":             "JSE SENS",
    "nse.co.ke":             "NSE Kenya",
    "gse.com.gh":            "Ghana Stock Exchange",
    "vanguardngr.com":       "Vanguard Nigeria",
    "thisdaylive.com":       "ThisDay Nigeria",
    "guardian.ng":           "The Guardian Nigeria",
    "premiumtimesng.com":    "Premium Times Nigeria",
    "nairametrics.com":      "Nairametrics",
    "disrupt-africa.com":    "Disrupt Africa",
    "ventureburn.com":       "Ventureburn",
    "financialafrik.com":    "Financial Afrik",
    "standardmedia.co.ke":   "Standard Media Kenya",
    "theeastafrican.co.ke":  "The East African",
}

AFRICAN_COUNTRIES = [
    "Nigeria", "South Africa", "Kenya", "Ghana", "Egypt", "Ethiopia",
    "Tanzania", "Uganda", "Rwanda", "Senegal", "Côte d'Ivoire", "Morocco",
    "Zambia", "Zimbabwe", "Mozambique", "Angola", "Cameroon"
]


def _is_africa_focused(title: str, snippet: str) -> bool:
    """Heuristic: does this article have African market relevance?"""
    text = (title + " " + snippet).lower()
    return any(c.lower() in text for c in AFRICAN_COUNTRIES) or \
           any(kw in text for kw in ["africa", "nairobi", "lagos", "johannesburg",
                                      "accra", "cairo", "ngx", "jse", "nse kenya"])


def _score_african_relevance(title: str, snippet: str, company_name: str) -> float:
    """Score relevance combining company mention + African signal keywords."""
    text = (title + " " + snippet).lower()
    company_lower = company_name.lower()

    score = 0.0
    if company_lower in text:
        score += 0.3
    elif any(part in text for part in company_lower.split() if len(part) > 3):
        score += 0.1

    for category, keywords in AFRICAN_SIGNAL_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                score += 0.12
                break

    return min(score, 1.0)


def _extract_african_source(url: str) -> str:
    """Map URL to readable African source name."""
    try:
        domain_match = re.search(r"https?://(?:www\.)?([^/]+)", url)
        if domain_match:
            host = domain_match.group(1)
            for key, name in AFRICAN_SOURCE_MAP.items():
                if key in host:
                    return name
            return host.replace("www.", "").split(".")[0].capitalize()
    except Exception:
        pass
    return "Unknown"


def _parse_rss_date(date_str: str) -> str:
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.utcnow().strftime("%Y-%m-%d")


class AfricaTool:
    """
    Async tool for African market intelligence.
    Fetches from African exchange disclosure portals + African financial news RSS feeds.
    """

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "AfricaTool":
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DealIntelBot/1.0; Africa)"}
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("AfricaTool must be used as async context manager")
        return self._client

    # ── RSS Fetching ────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=3))
    async def _fetch_rss(self, url: str, source_name: str = "") -> list[dict[str, str]]:
        """Fetch and parse an RSS feed into raw item dicts."""
        try:
            r = await self.client.get(url)
            r.raise_for_status()
            # Handle encoding issues common in African news sites
            content = r.content.decode(r.encoding or "utf-8", errors="replace")
            root = ET.fromstring(content)
        except Exception:
            return []

        items = []
        for item in root.findall(".//item"):
            title = item.findtext("title") or ""
            link  = item.findtext("link") or ""
            pub   = item.findtext("pubDate") or ""
            desc  = item.findtext("description") or ""
            desc  = re.sub(r"<[^>]+>", " ", desc).strip()
            items.append({
                "title": title,
                "link": link,
                "pubDate": pub,
                "description": desc,
                "source_override": source_name
            })
        return items

    # ── Exchange Disclosure Feeds ───────────────────────────────────────

    async def fetch_ngx_announcements(self, company_name: str) -> list[SECFiling]:
        """
        Fetch NGX (Nigerian Exchange) company announcements via Google News
        scoped to NGX disclosure language.
        """
        filings: list[SECFiling] = []
        queries = [
            f'"{company_name}" NGX announcement',
            f'"{company_name}" Nigerian Exchange disclosure',
            f'"{company_name}" site:ngxgroup.com',
        ]
        for q in queries[:2]:
            url = GOOGLE_NEWS_RSS.format(query=quote(q))
            items = await self._fetch_rss(url, "NGX Group")
            for item in items[:3]:
                title = item.get("title", "")
                if not title:
                    continue
                filings.append(SECFiling(
                    accession_number=f"NGX-{hash(title) % 999999:06d}",
                    form_type="NGX Announcement",
                    filing_date=_parse_rss_date(item.get("pubDate", "")),
                    company_name=company_name,
                    cik="NGX",
                    document_url=item.get("link", ""),
                    description=title,
                    raw_excerpt=item.get("description", "")[:300]
                ))
            await asyncio.sleep(0.1)
        return filings

    async def fetch_jse_sens(self, company_name: str) -> list[SECFiling]:
        """
        Fetch JSE SENS (Stock Exchange News Service) announcements.
        SENS is the JSE's mandatory disclosure platform — equivalent to 8-K filings.
        """
        filings: list[SECFiling] = []
        # SENS RSS via senssearch.co.za
        url = JSE_SENS.format(query=quote(company_name))
        items = await self._fetch_rss(url, "JSE SENS")

        for item in items[:8]:
            title = item.get("title", "")
            if not title:
                continue
            filings.append(SECFiling(
                accession_number=f"SENS-{hash(title) % 999999:06d}",
                form_type="JSE SENS",
                filing_date=_parse_rss_date(item.get("pubDate", "")),
                company_name=company_name,
                cik="JSE",
                document_url=item.get("link", ""),
                description=title,
                raw_excerpt=item.get("description", "")[:300]
            ))

        # Fallback: Google News scoped to JSE/SENS language
        if not filings:
            fallback_url = GOOGLE_NEWS_SA.format(
                query=quote(f"{company_name} JSE SENS announcement")
            )
            items = await self._fetch_rss(fallback_url, "JSE SENS")
            for item in items[:4]:
                title = item.get("title", "")
                if not title:
                    continue
                filings.append(SECFiling(
                    accession_number=f"JSE-{hash(title) % 999999:06d}",
                    form_type="JSE Announcement",
                    filing_date=_parse_rss_date(item.get("pubDate", "")),
                    company_name=company_name,
                    cik="JSE",
                    document_url=item.get("link", ""),
                    description=title,
                    raw_excerpt=item.get("description", "")[:300]
                ))

        return filings

    async def fetch_nse_kenya_disclosures(self, company_name: str) -> list[SECFiling]:
        """Fetch NSE Kenya company disclosures via Google News Kenya."""
        url = GOOGLE_NEWS_KE.format(
            query=quote(f"{company_name} NSE Kenya disclosure announcement")
        )
        items = await self._fetch_rss(url, "NSE Kenya")
        filings = []
        for item in items[:4]:
            title = item.get("title", "")
            if not title:
                continue
            filings.append(SECFiling(
                accession_number=f"NSE-{hash(title) % 999999:06d}",
                form_type="NSE Kenya Disclosure",
                filing_date=_parse_rss_date(item.get("pubDate", "")),
                company_name=company_name,
                cik="NSE-KE",
                document_url=item.get("link", ""),
                description=title,
                raw_excerpt=item.get("description", "")[:300]
            ))
        return filings

    # ── African News Fetching ───────────────────────────────────────────

    async def fetch_african_news(
        self,
        company_name: str,
        lookback_days: int = 90,
        max_items: int = 30,
    ) -> list[NewsItem]:
        """
        Fetch company-relevant news from African financial media sources.
        Combines direct RSS feeds + geo-scoped Google News queries.
        """
        cutoff_date = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        # African news RSS feeds
        rss_tasks = [
            self._fetch_rss(url, name)
            for name, url in AFRICAN_NEWS_FEEDS.items()
        ]

        # Geo-scoped Google News queries
        africa_queries = [
            f"{company_name} merger acquisition Africa",
            f"{company_name} restructuring debt default Africa",
            f"{company_name} earnings revenue Africa",
            f"{company_name} CEO resignation Africa",
            f"{company_name} regulatory investigation Africa",
            f"{company_name} NGX JSE NSE",
        ]
        google_tasks = [
            self._fetch_rss(GOOGLE_NEWS_RSS.format(query=quote(q)), "Google News Africa")
            for q in africa_queries
        ] + [
            self._fetch_rss(GOOGLE_NEWS_SA.format(query=quote(f"{company_name} JSE merger acquisition")), "Google News SA"),
            self._fetch_rss(GOOGLE_NEWS_KE.format(query=quote(f"{company_name} NSE Kenya deal")), "Google News Kenya"),
        ]

        all_tasks = rss_tasks + google_tasks
        results = await asyncio.gather(*all_tasks, return_exceptions=True)

        seen_titles: set[str] = set()
        raw_items: list[dict[str, str]] = []
        for batch in results:
            if isinstance(batch, list):
                raw_items.extend(batch)

        news_items: list[NewsItem] = []
        for raw in raw_items:
            title = raw.get("title", "").strip()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)

            pub_date = _parse_rss_date(raw.get("pubDate", ""))
            if pub_date < cutoff_date:
                continue

            snippet   = raw.get("description", "")[:400]
            url       = raw.get("link", "")
            source    = raw.get("source_override") or _extract_african_source(url)
            relevance = _score_african_relevance(title, snippet, company_name)

            # Lower threshold for African sources — any mention is worth capturing
            if relevance < 0.08:
                continue

            news_items.append(NewsItem(
                title=title,
                source=source,
                published_date=pub_date,
                url=url,
                snippet=snippet,
                relevance_score=relevance,
            ))

        news_items.sort(key=lambda n: n.relevance_score, reverse=True)
        return news_items[:max_items]


async def fetch_african_intelligence(
    company_name: str,
    ticker: Optional[str],
    lookback_days: int = 90,
) -> tuple[list[SECFiling], list[NewsItem]]:
    """
    Convenience wrapper: fetch African exchange filings + African news concurrently.
    Returns (exchange_filings, african_news_items).
    """
    async with AfricaTool() as tool:
        # Run exchange disclosure fetches + news concurrently
        ngx_task   = asyncio.create_task(tool.fetch_ngx_announcements(company_name))
        jse_task   = asyncio.create_task(tool.fetch_jse_sens(company_name))
        nse_task   = asyncio.create_task(tool.fetch_nse_kenya_disclosures(company_name))
        news_task  = asyncio.create_task(tool.fetch_african_news(company_name, lookback_days))

        results = await asyncio.gather(
            ngx_task, jse_task, nse_task, news_task,
            return_exceptions=True
        )

    filings: list[SECFiling] = []
    for r in results[:3]:  # first 3 are filing tasks
        if isinstance(r, list):
            filings.extend(r)

    news: list[NewsItem] = results[3] if isinstance(results[3], list) else []

    # Deduplicate filings by accession number
    seen: set[str] = set()
    deduped_filings: list[SECFiling] = []
    for f in filings:
        key = f.accession_number or f.document_url
        if key not in seen:
            seen.add(key)
            deduped_filings.append(f)

    return deduped_filings, news
