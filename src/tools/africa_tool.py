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
    # ── Nigeria ──────────────────────────────────────────────────────────
    "BusinessDay Nigeria":      "https://businessday.ng/feed/",
    "TechCabal":                "https://techcabal.com/feed/",
    "Stears":                   "https://stears.co/feed/",
    "Nairametrics":             "https://nairametrics.com/feed/",
    "Vanguard Nigeria":         "https://www.vanguardngr.com/feed/",
    "ThisDay Nigeria":          "https://www.thisdaylive.com/feed/",
    "Premium Times Nigeria":    "https://www.premiumtimesng.com/feed",
    "The Guardian Nigeria":     "https://guardian.ng/feed/",
    "Punch Nigeria":            "https://punchng.com/feed/",
    "Channels TV Business":     "https://www.channelstv.com/feed/",
    # ── South Africa ─────────────────────────────────────────────────────
    "Moneyweb":                 "https://www.moneyweb.co.za/feed/",
    "BusinessLive SA":          "https://www.businesslive.co.za/rss/",
    "Daily Maverick Business":  "https://www.dailymaverick.co.za/rss/",
    "Fin24":                    "https://www.news24.com/fin24/rss",
    "IOL Business Report":      "https://www.iol.co.za/business-report/rss",
    "Mail & Guardian Business": "https://mg.co.za/feed/",
    # ── East Africa ──────────────────────────────────────────────────────
    "Nation Africa":            "https://nation.africa/rss/",
    "Daily Monitor Uganda":     "https://www.monitor.co.ug/Uganda/Business/rss/",
    "The East African":         "https://www.theeastafrican.co.ke/rss/",
    "Standard Media Kenya":     "https://www.standardmedia.co.ke/rss/business.php",
    "Business Daily Africa":    "https://www.businessdailyafrica.com/rss/",
    "Rwanda New Times":         "https://www.newtimes.co.rw/rss.xml",
    "The Citizen Tanzania":     "https://www.thecitizen.co.tz/tanzania/rss/",
    # ── Pan-African / Tech ────────────────────────────────────────────────
    "The Africa Report":        "https://www.theafricareport.com/feed/",
    "African Business":         "https://african.business/feed",
    "Financial Afrik":          "https://www.financialafrik.com/feed/",
    "Disrupt Africa":           "https://disrupt-africa.com/feed/",
    "Ventureburn":              "https://ventureburn.com/feed/",
    "WeeTracker":               "https://weetracker.com/feed/",
    "TechPoint Africa":         "https://techpoint.africa/feed/",
    "Quartz Africa":            "https://qz.com/africa/rss",
    # ── Ghana ─────────────────────────────────────────────────────────────
    "Graphic Business Ghana":   "https://www.graphic.com.gh/business/feed",
    "Citi Business Ghana":      "https://citinewsroom.com/category/business/feed/",
    "GhanaWeb Business":        "https://www.ghanaweb.com/GhanaHomePage/business/rss.xml",
    # ── Francophone Africa ────────────────────────────────────────────────
    "Jeune Afrique Economie":   "https://www.jeuneafrique.com/sections/economie/feed/",
    # ── Egypt / North Africa ──────────────────────────────────────────────
    "Daily News Egypt":         "https://dailynewsegypt.com/feed/",
    "Egypt Today Business":     "https://www.egypttoday.com/rss/Category/54",
    # ── Ethiopia / Horn of Africa ─────────────────────────────────────────
    "Addis Fortune":            "https://addisfortune.news/feed/",
    "The Reporter Ethiopia":    "https://www.thereporterethiopia.com/rss.xml",
}

# ─── Private Capital & Institutional Sources (HTML scraping) ─────────────────
# These sites don't provide RSS feeds. We scrape their public listing pages
# for headlines, links, and dates. Each entry is:
#   (source_name, url, article_link_pattern, title_tag_hint)
PE_CAPITAL_SOURCES: list[tuple[str, str, str, str]] = [
    # ── Original user-specified sources ──────────────────────────────────
    ("Global Private Capital",        "https://www.globalprivatecapital.org/industry-news/",                    "globalprivatecapital.org",    "h2,h3,h4"),
    ("PSG Capital",                   "https://psgcapital.com/news-insights/latest-transactions/",              "psgcapital.com",              "h2,h3,h4"),
    ("IFC Press Room",                "https://www.ifc.org/en/pressroom",                                       "ifc.org",                     "h3,h4"),
    ("Bayport Finance",               "https://www.bayportfinance.com/latest-investor-news/",                   "bayportfinance.com",           "h2,h3,h4"),
    ("Zawya",                         "https://www.zawya.com/en/news/latest",                                   "zawya.com",                   "h3,h4"),
    ("Africa PE News Deals",          "https://www.africaprivateequitynews.com/t/deals",                        "africaprivateequitynews.com",  "h2,h3"),
    ("Africa PE News Exits",          "https://www.africaprivateequitynews.com/t/exits",                        "africaprivateequitynews.com",  "h2,h3"),
    ("Africa PE News Debt Mezz",      "https://www.africaprivateequitynews.com/t/debt-and-mez",                 "africaprivateequitynews.com",  "h2,h3"),
    ("Africa PE News VC",             "https://www.africaprivateequitynews.com/t/venture-capital",              "africaprivateequitynews.com",  "h2,h3"),
    ("AVCA",                          "https://www.avca.africa/news-insights/industry-news/",                   "avca.africa",                 "h2,h3,h4"),
    # ── Development Finance Institutions ──────────────────────────────────
    ("African Development Bank",      "https://www.afdb.org/en/news-and-events/press-releases",                 "afdb.org",                    "h3,h4"),
    ("Proparco",                      "https://www.proparco.fr/en/actualites",                                  "proparco.fr",                 "h3,h4"),
    ("DBSA News",                     "https://www.dbsa.org/news",                                              "dbsa.org",                    "h3,h4"),
    ("Afreximbank",                   "https://www.afreximbank.com/news/",                                      "afreximbank.com",             "h3,h4"),
    ("CDC Group / BII",               "https://www.bii.co.uk/en/news-insight/news/",                            "bii.co.uk",                   "h3,h4"),
    ("FMO Netherlands",               "https://www.fmo.nl/news",                                                "fmo.nl",                      "h3,h4"),
    # ── VC / Startup Deal Flow ────────────────────────────────────────────
    ("Partech Africa",                "https://partechpartners.com/news/",                                      "partechpartners.com",         "h3,h4"),
    ("Novastar Ventures",             "https://novastarventures.com/news/",                                     "novastarventures.com",        "h3,h4"),
    ("Kepple Africa",                 "https://kepple-africa.com/news/",                                        "kepple-africa.com",           "h3,h4"),
    ("TLcom Capital",                 "https://www.tlcomcapital.com/blog",                                      "tlcomcapital.com",            "h3,h4"),
    ("Catalyst Fund",                 "https://thecatalystfund.com/news/",                                      "thecatalystfund.com",         "h3,h4"),
    # ── Credit / Debt Markets ─────────────────────────────────────────────
    ("Rand Merchant Bank",            "https://www.rmb.co.za/page/news-and-insights",                           "rmb.co.za",                   "h3,h4"),
    ("Standard Bank Research",        "https://www.standardbank.com/sbg/standard-bank-group/media/news-and-media-releases", "standardbank.com", "h3,h4"),
    # ── Regulatory Bodies ─────────────────────────────────────────────────
    ("SEC Nigeria",                   "https://sec.gov.ng/news/",                                               "sec.gov.ng",                  "h3,h4"),
    ("FSCA South Africa",             "https://www.fsca.co.za/Regulatory%20Frameworks/Pages/Press-Releases-and-Notices.aspx", "fsca.co.za", "h3,h4"),
    ("CMA Kenya",                     "https://www.cma.or.ke/media-centre/press-releases/",                     "cma.or.ke",                   "h3,h4"),
    ("CBN Press Releases",            "https://www.cbn.gov.ng/Mediaroom/pressreleases.asp",                     "cbn.gov.ng",                  "h3,h4"),
    ("SARB Press",                    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/media-releases/media-releases-search", "resbank.co.za", "h3,h4"),
]

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
    # Nigeria
    "businessday.ng":              "BusinessDay Nigeria",
    "techcabal.com":               "TechCabal",
    "stears.co":                   "Stears",
    "nairametrics.com":            "Nairametrics",
    "vanguardngr.com":             "Vanguard Nigeria",
    "thisdaylive.com":             "ThisDay Nigeria",
    "premiumtimesng.com":          "Premium Times Nigeria",
    "guardian.ng":                 "The Guardian Nigeria",
    "punchng.com":                 "Punch Nigeria",
    "channelstv.com":              "Channels TV Business",
    # South Africa
    "moneyweb.co.za":              "Moneyweb",
    "businesslive.co.za":          "BusinessLive SA",
    "dailymaverick.co.za":         "Daily Maverick Business",
    "news24.com":                  "Fin24",
    "iol.co.za":                   "IOL Business Report",
    "mg.co.za":                    "Mail & Guardian Business",
    # East Africa
    "nation.africa":               "Nation Africa",
    "monitor.co.ug":               "Daily Monitor Uganda",
    "theeastafrican.co.ke":        "The East African",
    "standardmedia.co.ke":         "Standard Media Kenya",
    "businessdailyafrica.com":     "Business Daily Africa",
    "newtimes.co.rw":              "Rwanda New Times",
    "thecitizen.co.tz":            "The Citizen Tanzania",
    # Pan-African
    "theafricareport.com":         "The Africa Report",
    "african.business":            "African Business",
    "financialafrik.com":          "Financial Afrik",
    "disrupt-africa.com":          "Disrupt Africa",
    "ventureburn.com":             "Ventureburn",
    "weetracker.com":              "WeeTracker",
    "techpoint.africa":            "TechPoint Africa",
    "qz.com":                      "Quartz Africa",
    # Ghana
    "graphic.com.gh":              "Graphic Business Ghana",
    "citinewsroom.com":            "Citi Business Ghana",
    "ghanaweb.com":                "GhanaWeb Business",
    # Exchanges
    "ngxgroup.com":                "NGX Group",
    "jse.co.za":                   "JSE SENS",
    "nse.co.ke":                   "NSE Kenya",
    "gse.com.gh":                  "Ghana Stock Exchange",
    "dse.co.tz":                   "Dar es Salaam Stock Exchange",
    "use.or.ug":                   "Uganda Securities Exchange",
    "rse.rw":                      "Rwanda Stock Exchange",
    "casablanca-bourse.com":       "Casablanca Stock Exchange",
    "egyptianexchange.com":        "Egyptian Exchange",
    # Francophone / North Africa
    "jeuneafrique.com":            "Jeune Afrique Economie",
    "dailynewsegypt.com":          "Daily News Egypt",
    "egypttoday.com":              "Egypt Today Business",
    "addisfortune.news":           "Addis Fortune",
    "thereporterethiopia.com":     "The Reporter Ethiopia",
    # Private capital & institutional
    "globalprivatecapital.org":    "Global Private Capital",
    "psgcapital.com":              "PSG Capital",
    "ifc.org":                     "IFC Press Room",
    "bayportfinance.com":          "Bayport Finance",
    "zawya.com":                   "Zawya",
    "africaprivateequitynews.com": "Africa PE News",
    "avca.africa":                 "AVCA",
    "proparco.fr":                 "Proparco",
    "dbsa.org":                    "DBSA",
    "afreximbank.com":             "Afreximbank",
    "afdb.org":                    "African Development Bank",
    # Regulatory bodies
    "cma.or.ke":                   "CMA Kenya",
    "cbn.gov.ng":                  "CBN Nigeria",
    "sec.gov.ng":                  "SEC Nigeria",
    "fsca.co.za":                  "FSCA South Africa",
    "resbank.co.za":               "SARB South Africa",
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

    # ── HTML Scraping for PE/Capital Sources ───────────────────────────

    async def _scrape_pe_source(
        self,
        source_name: str,
        url: str,
        company_name: str,
        cutoff_date: str,
    ) -> list[dict[str, str]]:
        """
        Scrape a PE/capital site that doesn't have an RSS feed.
        Extracts article links and titles from the listing page HTML.
        Falls back gracefully on any error — these sites can be flaky.
        """
        try:
            r = await self.client.get(url)
            r.raise_for_status()
            html = r.text
        except Exception:
            return []

        items: list[dict[str, str]] = []
        company_lower = company_name.lower()

        # Extract <a> tags whose href looks like an article link
        # and whose text/surrounding context contains the company name or signal keywords
        link_pattern = re.compile(
            r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL
        )
        for match in link_pattern.finditer(html):
            href = match.group(1).strip()
            link_text = re.sub(r"<[^>]+>", " ", match.group(2)).strip()

            if len(link_text) < 15 or len(link_text) > 300:
                continue
            if not any(c.isalpha() for c in link_text):
                continue

            # Make relative URLs absolute
            if href.startswith("/"):
                base = re.match(r"(https?://[^/]+)", url)
                href = base.group(1) + href if base else href
            elif not href.startswith("http"):
                continue

            # Score relevance: company name mention OR strong signal keyword
            text_lower = link_text.lower()
            has_company = company_lower in text_lower or any(
                part in text_lower for part in company_lower.split() if len(part) > 3
            )
            has_signal = any(
                kw in text_lower
                for kws in AFRICAN_SIGNAL_KEYWORDS.values()
                for kw in kws
            )

            if not (has_company or has_signal):
                continue

            items.append({
                "title": link_text,
                "link": href,
                "pubDate": datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT"),
                "description": f"[{source_name}] {link_text}",
                "source_override": source_name,
            })

            if len(items) >= 8:
                break

        return items

    async def fetch_pe_capital_news(
        self,
        company_name: str,
        lookback_days: int = 90,
    ) -> list[NewsItem]:
        """
        Scrape private capital and institutional sources for deal intelligence.
        Covers: GPCA, PSG Capital, IFC, Bayport, Zawya, Africa PE News, AVCA.
        """
        cutoff_date = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        tasks = [
            self._scrape_pe_source(name, url, company_name, cutoff_date)
            for name, url, _, _ in PE_CAPITAL_SOURCES
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        seen_titles: set[str] = set()
        news_items: list[NewsItem] = []

        for batch in results:
            if not isinstance(batch, list):
                continue
            for raw in batch:
                title = raw.get("title", "").strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                snippet   = raw.get("description", "")[:400]
                url       = raw.get("link", "")
                source    = raw.get("source_override") or _extract_african_source(url)
                relevance = _score_african_relevance(title, snippet, company_name)
                # PE sources are high-signal by nature — lower threshold
                if relevance < 0.05:
                    relevance = max(relevance, 0.25)  # floor for PE sources

                news_items.append(NewsItem(
                    title=title,
                    source=source,
                    published_date=datetime.utcnow().strftime("%Y-%m-%d"),
                    url=url,
                    snippet=snippet,
                    relevance_score=min(relevance, 1.0),
                ))

        news_items.sort(key=lambda n: n.relevance_score, reverse=True)
        return news_items

    async def fetch_african_news(
        self,
        company_name: str,
        lookback_days: int = 90,
        max_items: int = 40,
    ) -> list[NewsItem]:
        """
        Fetch company-relevant news from:
          - African financial media RSS feeds (BusinessDay, TechCabal, Moneyweb, etc.)
          - Geo-scoped Google News (NG / ZA / KE)
          - Private capital & institutional sources: GPCA, PSG Capital, IFC,
            Bayport Finance, Zawya, Africa PE News (deals/exits/debt/VC), AVCA
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
            f"{company_name} private equity venture capital Africa",
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

        # Merge PE/capital results — run concurrently, deduplicate by title
        pe_items = await self.fetch_pe_capital_news(company_name, lookback_days)
        for pe_item in pe_items:
            if pe_item.title not in seen_titles:
                seen_titles.add(pe_item.title)
                news_items.append(pe_item)

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
