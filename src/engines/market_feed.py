"""
Daily market feed: African business headlines turned into deals and corporate events.

Sources, every run:
  * the African business and private-capital RSS feeds in africa_tool;
  * Google News deal searches in every one of the 54 countries' editions, in
    each country's working languages;
  * pan-African deal searches (venture, private equity, DFI lending, fund closes).

Each headline goes through two deterministic extractors:
  * deals.extract_deal: transactions for the deals database;
  * the signal rules: corporate events (M&A, credit, distress, leadership,
    regulatory, earnings, restructuring, insider) for monitoring and alerts.

Historical backfill uses Google News date-restricted searches (after:/before:).
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable, Optional
from urllib.parse import quote

import httpx

from src.data.africa_countries import COUNTRIES, Country, countries_in_text
from src.engines import deals as deals_mod
from src.engines.alpha_scorer import evidence_direction
from src.engines.deterministic_engine import _match_rules, _source_credibility

log = logging.getLogger(__name__)

# Query words per language: any of them makes a headline worth reading.
DEAL_TERMS = {
    "en": '(acquires OR acquisition OR raises OR invests OR "stake in" OR loan OR "fund close" OR merger)',
    "fr": '(rachat OR acquisition OR "lève" OR "levée de fonds" OR investit OR "prise de participation" OR "prêt")',
    "pt": '(aquisição OR adquire OR investimento OR financiamento OR "capta")',
    "ar": '(استحواذ OR تمويل OR صفقة OR اندماج)',
    "es": '(adquisición OR inversión OR financiación)',
}
EVENT_TERMS = {
    "en": '(default OR downgrade OR resigns OR fine OR suspended OR restructuring OR "profit warning" OR probe)',
    "fr": '(défaut OR dégradation OR démission OR sanction OR restructuration OR "avertissement sur résultats")',
    "pt": '(incumprimento OR rebaixamento OR demissão OR multa OR reestruturação)',
}
PAN_AFRICAN_QUERIES = (
    "Africa startup raises", "African fintech raises Series", "Africa private equity acquires",
    "Africa fund final close", "Africa fund first close", "IFC invests Africa", "British International Investment Africa",
    "Proparco Africa investment", "Afreximbank facility", "AfDB loan approves", "Africa acquisition completes",
    "Africa exits stake", "Africa venture debt", "Africa IPO listing", "Africa joint venture",
)

_ITEM = re.compile(r"<item>(.*?)</item>", re.S)
_ENTRY = re.compile(r"<entry>(.*?)</entry>", re.S)


def _tag(block: str, name: str) -> str:
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, re.S)
    if not m:
        return ""
    return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip()


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def parse_feed(text: str, default_publisher: str = "") -> list[dict]:
    """RSS or Atom items as {title, publisher, url, date, snippet}."""
    out = []
    for block in _ITEM.findall(text) or _ENTRY.findall(text):
        title = _strip_html(_tag(block, "title"))
        if not title:
            continue
        publisher = _strip_html(_tag(block, "source")) or default_publisher
        if publisher and title.endswith(" - " + publisher):
            title = title[: -len(publisher) - 3]
        source_tag = re.search(r"<source\b[^>]*>", block, re.IGNORECASE)
        source_url = ""
        if source_tag:
            url_attribute = re.search(r"\burl\s*=\s*(['\"])(.*?)\1", source_tag.group(0), re.IGNORECASE)
            if url_attribute:
                source_url = html.unescape(url_attribute.group(2)).strip()
        link = _tag(block, "link") or (re.search(r'<link[^>]+href="([^"]+)"', block) or [None, ""])[1]
        raw_date = _tag(block, "pubDate") or _tag(block, "published") or _tag(block, "updated") or _tag(block, "dc:date")
        day = None
        try:
            day = parsedate_to_datetime(raw_date).date().isoformat()
        except (TypeError, ValueError):
            m = re.match(r"\d{4}-\d{2}-\d{2}", raw_date)
            day = m.group(0) if m else None
        out.append({"title": title, "publisher": publisher, "url": link.strip(), "publisher_url": source_url,
                    "date": day, "snippet": _strip_html(_tag(block, "description"))[:400]})
    return out


def country_queries(window: str = "when:2d", events: bool = True) -> list[tuple[str, str, Country]]:
    """(url, label, country) Google News searches: deal terms (and event terms) per country and language."""
    urls = []
    for c in COUNTRIES:
        for lang in c.languages[:2]:
            terms = DEAL_TERMS.get(lang)
            if terms:
                urls.append((c.news_url(f"{_query_name(c, lang)} {terms} {window}", lang), f"{c.name} deals ({lang})", c))
            if events and lang in EVENT_TERMS:
                urls.append((c.news_url(f"{_query_name(c, lang)} {EVENT_TERMS[lang]} {window}", lang),
                             f"{c.name} events ({lang})", c))
    return urls


_LOCAL_NAMES = {"fr": {"Côte d'Ivoire": "Côte d'Ivoire", "Senegal": "Sénégal", "Cameroon": "Cameroun", "Chad": "Tchad",
                       "Guinea": "Guinée", "Morocco": "Maroc", "Algeria": "Algérie", "Tunisia": "Tunisie",
                       "Mauritania": "Mauritanie", "Benin": "Bénin", "Comoros": "Comores",
                       "Democratic Republic of the Congo": "RDC", "Republic of the Congo": "Congo-Brazzaville",
                       "Central African Republic": "Centrafrique", "Equatorial Guinea": "Guinée équatoriale",
                       "Mauritius": "Maurice"},
                "pt": {"Mozambique": "Moçambique", "Cabo Verde": "Cabo Verde", "Guinea-Bissau": "Guiné-Bissau",
                       "São Tomé and Príncipe": "São Tomé"},
                "ar": {"Egypt": "مصر", "Morocco": "المغرب", "Algeria": "الجزائر", "Tunisia": "تونس", "Libya": "ليبيا",
                       "Sudan": "السودان", "Mauritania": "موريتانيا"}}


def _query_name(c: Country, lang: str) -> str:
    name = _LOCAL_NAMES.get(lang, {}).get(c.name, c.name)
    return f'"{name}"' if " " in name or "'" in name else name


def pan_african_queries(window: str = "when:2d") -> list[tuple[str, str, Optional[Country]]]:
    return [(f"https://news.google.com/rss/search?q={quote(q + ' ' + window)}&hl=en-GB&gl=GB&ceid=GB:en", q, None)
            for q in PAN_AFRICAN_QUERIES]


async def _fetch(client: httpx.AsyncClient, sem: asyncio.Semaphore, url: str, label: str,
                 country: Optional[Country], africa_source: bool) -> list[dict]:
    async with sem:
        try:
            r = await client.get(url)
            r.raise_for_status()
        except Exception as e:
            log.info("feed %s unavailable: %s", label, e)
            return []
    items = parse_feed(r.text, default_publisher=label if "news.google" not in url else "")
    for it in items:
        it["country_hint"] = country.iso2 if country else None
        it["africa_source"] = africa_source or is_africa_outlet(it.get("publisher", ""))
        it["feed"] = label
    return items


# Outlets that publish only African business and deal news: their headlines need no country named.
AFRICA_ONLY_OUTLETS = {"africa private equity news", "disrupt africa", "agence ecofin", "financial afrik",
                       "financial afrik (fr)"}


def is_africa_outlet(publisher: str) -> bool:
    return (publisher or "").strip().lower() in AFRICA_ONLY_OUTLETS


async def collect(window: str = "when:2d", include_feeds: bool = True, include_countries: bool = True,
                  concurrency: int = 12, timeout: float = 20) -> list[dict]:
    """Headlines from every source for the window, de-duplicated by title."""
    from src.tools.africa_tool import AFRICAN_NEWS_FEEDS
    jobs: list[tuple[str, str, Optional[Country], bool]] = []
    if include_feeds:
        jobs += [(url, name, None, is_africa_outlet(name)) for name, url in AFRICAN_NEWS_FEEDS.items()]
    jobs += [(u, label, c, False) for u, label, c in pan_african_queries(window)]
    if include_countries:
        jobs += [(u, label, c, False) for u, label, c in country_queries(window)]
    sem = asyncio.Semaphore(concurrency)
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) deal-intelligence-agent/1.0"}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        batches = await asyncio.gather(*(_fetch(client, sem, u, label, c, a) for u, label, c, a in jobs))
    seen, out = set(), []
    for batch in batches:
        for it in batch:
            key = re.sub(r"\W+", " ", it["title"].lower()).strip()
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
    return out


def historical_queries(since: date, until: date) -> list[tuple[str, str, Optional[Country]]]:
    """Date-restricted deal searches for a backfill window (pan-African plus every country, primary language)."""
    window = f"after:{since.isoformat()} before:{(until + timedelta(days=1)).isoformat()}"
    urls = pan_african_queries(window)
    for c in COUNTRIES:
        lang = c.languages[0]
        if lang in DEAL_TERMS:
            urls.append((c.news_url(f"{_query_name(c, lang)} {DEAL_TERMS[lang]} {window}", lang), f"{c.name} deals", c))
    return urls


async def collect_historical(since: date, until: date, concurrency: int = 6) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        batches = await asyncio.gather(*(_fetch(client, sem, u, label, c, False)
                                         for u, label, c in historical_queries(since, until)))
    seen, out = set(), []
    for batch in batches:
        for it in batch:
            if it["title"] not in seen and (not it.get("date") or since.isoformat() <= it["date"] <= until.isoformat()):
                seen.add(it["title"])
                out.append(it)
    return out


# ── Extraction ────────────────────────────────────────────────────────────────

def to_deals(items: Iterable[dict]) -> list[dict]:
    out = []
    for it in items:
        d = deals_mod.extract_deal(it["title"], it.get("snippet", ""), published=it.get("date"),
                                   publisher=it.get("publisher", ""), url=it.get("url", ""),
                                   country_hint=it.get("country_hint"), africa_source=it.get("africa_source", False))
        if d:
            out.append(d)
    return out


def event_id(title: str) -> str:
    return hashlib.sha1(re.sub(r"\W+", " ", title.lower()).strip().encode()).hexdigest()[:16]


def to_events(items: Iterable[dict], min_score: float = 0.7) -> list[dict]:
    """Corporate events: headlines that match a signal rule at min_score or above."""
    out = []
    for it in items:
        title = it["title"]
        hits = [(t, s) for t, _, s in _match_rules(title) if s >= min_score]
        if not hits:
            continue
        signal_type, score = max(hits, key=lambda h: h[1])
        countries = [c.iso2 for c in countries_in_text(f"{title} {it.get('snippet', '')}")]
        if not countries and it.get("country_hint"):
            countries.append(it["country_hint"])
        out.append({
            "id": event_id(title),
            "day": it.get("date"),
            "headline": title,
            "publisher": it.get("publisher", ""),
            "url": it.get("url", ""),
            "signal_type": signal_type.value,
            "rule_score": score,
            "direction": evidence_direction(signal_type, title),
            "credibility": _source_credibility(it.get("publisher", "")),
            "country": countries[0] if countries else None,
            "countries": countries,
            "sector": deals_mod.classify_sector(f"{title} {it.get('snippet', '')}"),
        })
    return out


def run(window: str = "when:2d", **kw) -> tuple[list[dict], list[dict], int]:
    """(deals, events, headline count) for the window."""
    items = asyncio.run(collect(window, **kw))
    return to_deals(items), to_events(items), len(items)


def today_utc() -> date:
    return datetime.now(timezone.utc).date()
