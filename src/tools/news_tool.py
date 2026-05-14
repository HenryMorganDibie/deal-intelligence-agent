"""
News Intelligence Tool.
Fetches financial news from Google News RSS (no API key required),
with relevance scoring and deduplication.
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

from src.schemas.models import NewsItem

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
YAHOO_FINANCE_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"

HIGH_SIGNAL_KEYWORDS = {
    "m_and_a": ["merger", "acquisition", "takeover", "buyout", "deal", "bid", "acquires", "acquired",
                "scheme of arrangement", "offer to acquire"],
    "credit_risk": ["downgrade", "default", "bankruptcy", "debt", "junk", "restructur", "covenant",
                    "GCR ratings", "moody's", "S&P", "fitch"],
    "distressed": ["distressed", "insolvency", "liquidation", "chapter 11", "chapter 7", "receivership",
                   "business rescue", "judicial management", "provisional liquidation"],
    "leadership": ["ceo resign", "cfo resign", "ceo depart", "cfo depart", "executive exit", "board resign",
                   "md resign", "managing director resign"],
    "regulatory": ["sec probe", "doj invest", "ftc", "antitrust", "fine", "penalty", "subpoena", "fraud",
                   "fsca action", "cma investigation", "cbn sanction", "licence revoked"],
    "earnings": ["miss", "warning", "guidance cut", "revenue decline", "profit warning", "restatement",
                 "trading statement", "headline earnings", "loss after tax"],
}


def _score_relevance(title: str, snippet: str, company_name: str) -> float:
    """Score a news item's relevance to deal intelligence (0.0–1.0)."""
    text = (title + " " + snippet).lower()
    company_lower = company_name.lower()

    score = 0.0

    # Company name mention
    if company_lower in text:
        score += 0.3
    elif any(part in text for part in company_lower.split() if len(part) > 3):
        score += 0.1

    # Signal keyword presence
    for category, keywords in HIGH_SIGNAL_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                score += 0.12
                break  # one hit per category max

    return min(score, 1.0)


def _parse_rss_date(date_str: str) -> str:
    """Parse RSS date format to ISO-8601 date string."""
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.utcnow().strftime("%Y-%m-%d")


class NewsTool:
    """Async news fetcher targeting financial/deal intelligence signals."""

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "NewsTool":
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DealIntelBot/1.0)"}
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("NewsTool must be used as async context manager")
        return self._client

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=4))
    async def _fetch_rss(self, url: str) -> list[dict[str, str]]:
        """Fetch and parse an RSS feed. Returns list of {title, link, pubDate, description}."""
        try:
            r = await self.client.get(url)
            r.raise_for_status()
            root = ET.fromstring(r.text)
        except Exception:
            return []

        items = []
        ns = {"media": "http://search.yahoo.com/mrss/"}
        for item in root.findall(".//item"):
            title = item.findtext("title") or ""
            link  = item.findtext("link") or ""
            pub   = item.findtext("pubDate") or ""
            desc  = item.findtext("description") or ""
            # strip HTML from description
            desc  = re.sub(r"<[^>]+>", " ", desc).strip()
            items.append({"title": title, "link": link, "pubDate": pub, "description": desc})

        return items

    async def fetch_company_news(
        self,
        company_name: str,
        ticker: Optional[str] = None,
        lookback_days: int = 90,
        max_items: int = 30,
    ) -> list[NewsItem]:
        """
        Fetch news for a company from multiple RSS sources.
        Deduplicates, scores relevance, and returns sorted list.
        """
        cutoff_date = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        queries = [
            f"{company_name} merger acquisition deal",
            f"{company_name} bankruptcy debt restructuring",
            f"{company_name} earnings revenue profit",
            f"{company_name} SEC investigation fraud",
            f"{company_name} CEO CFO executive",
        ]

        tasks = [
            self._fetch_rss(GOOGLE_NEWS_RSS.format(query=quote(q)))
            for q in queries
        ]
        if ticker:
            tasks.append(self._fetch_rss(YAHOO_FINANCE_RSS.format(ticker=ticker)))

        results = await asyncio.gather(*tasks, return_exceptions=True)

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

            snippet  = raw.get("description", "")[:400]
            url      = raw.get("link", "")
            source   = _extract_source(url)
            relevance = _score_relevance(title, snippet, company_name)

            if relevance < 0.1:
                continue  # filter out noise

            news_items.append(NewsItem(
                title=title,
                source=source,
                published_date=pub_date,
                url=url,
                snippet=snippet,
                relevance_score=relevance,
            ))

        # Sort by relevance descending, then recency
        news_items.sort(key=lambda n: (-n.relevance_score, n.published_date), reverse=False)
        news_items.sort(key=lambda n: n.relevance_score, reverse=True)

        return news_items[:max_items]


def _extract_source(url: str) -> str:
    """Extract readable source name from URL."""
    try:
        domain = re.search(r"https?://(?:www\.)?([^/]+)", url)
        if domain:
            host = domain.group(1)
            # Map common financial news domains
            mapping = {
                # US / Global
                "reuters.com": "Reuters",
                "bloomberg.com": "Bloomberg",
                "wsj.com": "Wall Street Journal",
                "ft.com": "Financial Times",
                "cnbc.com": "CNBC",
                "marketwatch.com": "MarketWatch",
                "seekingalpha.com": "Seeking Alpha",
                "finance.yahoo.com": "Yahoo Finance",
                "businesswire.com": "Business Wire",
                "prnewswire.com": "PR Newswire",
                "sec.gov": "SEC EDGAR",
                # Africa
                "businessday.ng": "BusinessDay Nigeria",
                "techcabal.com": "TechCabal",
                "theafricareport.com": "The Africa Report",
                "african.business": "African Business",
                "moneyweb.co.za": "Moneyweb",
                "businesslive.co.za": "BusinessLive SA",
                "stears.co": "Stears",
                "nation.africa": "Nation Africa",
                "nairametrics.com": "Nairametrics",
                "ngxgroup.com": "NGX Group",
                "jse.co.za": "JSE SENS",
                "nse.co.ke": "NSE Kenya",
                "gse.com.gh": "Ghana Stock Exchange",
                "vanguardngr.com": "Vanguard Nigeria",
                "thisdaylive.com": "ThisDay Nigeria",
                "premiumtimesng.com": "Premium Times Nigeria",
                "theeastafrican.co.ke": "The East African",
                "standardmedia.co.ke": "Standard Media Kenya",
                "disrupt-africa.com": "Disrupt Africa",
                "financialafrik.com": "Financial Afrik",
            }
            for key, name in mapping.items():
                if key in host:
                    return name
            return host.replace("www.", "").split(".")[0].capitalize()
    except Exception:
        pass
    return "Unknown"


async def fetch_market_news(company_name: str, ticker: Optional[str], lookback_days: int) -> list[NewsItem]:
    """Convenience wrapper."""
    async with NewsTool() as tool:
        return await tool.fetch_company_news(company_name, ticker, lookback_days)
