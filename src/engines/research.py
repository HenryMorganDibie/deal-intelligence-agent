"""
Source-grounded research: AI search and research reports.

Retrieval first, generation second:
  1. The question is parsed for countries, sectors, deal types, investors,
     companies and a time window.
  2. Evidence is retrieved from the deals database, the corporate-event feed,
     country and currency risk, investor profiles, and a live news search.
     Every item gets a number.
  3. The LLM (Claude or Groq) writes the answer using only those items and
     cites them as [n]. Citations are then checked: a number that does not
     match an item is removed, and every sentence without a valid citation is
     reported, so the reader sees exactly how much of the answer is grounded.
  4. With no LLM configured, the answer is a deterministic summary of the
     same evidence.

Country and sector research reports assemble the same evidence into
fixed sections; the LLM only writes the executive summary, under the same
citation rules.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
from collections import Counter
from datetime import date, timedelta
from typing import Callable, Iterable, Optional
from urllib.parse import quote, urlparse

import httpx

from src.data.africa_countries import COUNTRIES, countries_in_text, get as get_country
from src.engines import country_risk as cr
from src.engines import deals as deals_mod
from src.engines import investors as inv
from src.engines import market_risk as mr

log = logging.getLogger(__name__)
_NEWS_EVIDENCE_LIMIT = 8

_TYPE_WORDS = {
    "acquisition": r"acqui\w*|buyout|takeover|m&a|mergers?",
    "equity_funding": r"fund(ing|raise)|raised?|rounds?|venture|vc|series\s+[a-h]|seed|equity|startups?",
    "debt_financing": r"debt|loans?|credit|facilit\w+|bonds?|lend\w*|financing",
    "fund_raise": r"fund\s+close|first\s+close|final\s+close|fund\s+raising|lps?|limited\s+partners?|gps?|fund\s+managers?",
    "exit": r"exits?|divest\w*|sold",
    "ipo": r"ipos?|listings?|initial\s+public",
}
_SECTOR_WORDS = {name: rx for name, rx in deals_mod._SECTOR_RE}
_STOP = set("""a an and are as at be by for from has have how in is it its of on or that the this to was were what which
who when will with about across between during over into than then there these those why where most more many much
any all show list give tell me us our latest recent top biggest largest deals deal companies company africa african
dfi dfis series seed private markets market risk investment investments development finance url urls source sources
evidence cite citations link links provide include distinguish confirmed facts figures publicly disclosed reported
transaction value did last past month months day days year years audit separate amount raised valuation cite each
field""".split())
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
_NEWS_ACTIONS = {
    "acquisition": re.compile(
        r"\b(?:acquir\w*|buy|buys|bought|takeover|rachat\w*|rachet\w*|acquisition\w*|adquir\w*|"
        r"compra\w*|comprou|aquisiç\w*|prise\s+de\s+participation|"
        r"استحواذ\w*|اشتر\w*)\b|(?:prend|prendre)\s+le\s+contrôle", re.IGNORECASE),
    "funding": re.compile(
        r"\b(?:fund\w*|rais\w*|invest\w*|financ\w*|lèv\w*|lev\w*|finance\w*|investit\w*|"
        r"capta\w*|arrecad\w*|levant\w*|receb\w*|investimento\w*|financiamento\w*|"
        r"تمويل\w*|استثمار\w*|جمع\w*)\b", re.IGNORECASE),
}
_FUNDING_ANNOUNCEMENT = re.compile(
    r"\b(?:raises?|raised|secures?|secured|closes?|closed|lands?|announces?|announced|receives?|received)\b"
    r".{0,100}\b(?:funding|investment|round|series|capital|financing|million|billion)\b"
    r"|\b(?:funding|investment)\s+round\b|\bseries\s+[a-g]\b"
    r"|\b(?:lève|levée|lever|lanc\w*|obtient|sécurise|annonce)\b.{0,100}"
    r"\b(?:fonds?|financement|investissement|millions?|milliards?|série|tour)\b"
    r"|\b(?:capta|arrecada|levanta|recebe|anuncia|fecha)\w*\b.{0,100}"
    r"\b(?:fundos?|financiamento|investimento|milhões?|bilhões?|série|rodada|capital)\b"
    r"|\b(?:تمويل|استثمار|جمع|أعلن)\b",
    re.IGNORECASE,
)
_FUNDING_NEGATION = re.compile(
    r"\b(?:denies?|denied|not\s+raised|failed\s+to\s+raise|démenti|infructueuse?|"
    r"n['’]a\s+pas\s+levé|não\s+conseguiu\s+captar|não\s+captou)\b",
    re.IGNORECASE,
)
_NON_EQUITY_FUNDING = re.compile(
    r"\b(?:eurobonds?|bonds?|bond\s+issuance|treasury|government|sovereign|state\s+budget|"
    r"political\s+part(?:y|ies)|loan|loans|car\s+finance|auto\s+loan|public\s+debt|"
    r"obligations?|emprunt(?:s)?|emprunt\s+obligataire|trésor|budget|état|etat|"
    r"l['’](?:é)?tat|fmi|imf|parti\s+politique|prêt|"
    r"títulos?|tesouro|orçamento|partido\s+político|empréstimo|"
    r"allocat\w*|alocad\w*|allou\w*|allocation|"
    r"projets?|project(?:s)?|projetos?|projeto|power\s+plant|centrale|micro[-\s]?projects?|"
    r"travaux|infrastructure|port|marché\s+(?:financier|régional|international)|"
    r"agricultur\w*|ag\s+development|sector\s+agricole|secteur\s+agricole|"
    r"سندات|خزينة|حكومة|ميزانية|الأحزاب|أحزاب|حزب|سيارات|شراء سيارات|"
    r"القطاع الزراعي|زراعي|الزراعة)\b",
    re.IGNORECASE,
)
_EQUITY_FUNDING_MARKER = re.compile(
    r"\b(?:startup|start-up|fintech|venture|seed|series\s+[a-g]|equity|funding\s+round|"
    r"pre[-\s]?seed|série\s+[a-g]|tour\s+de\s+financement|rodada|ronda)\b",
    re.IGNORECASE,
)
_NON_CORPORATE_ACQUISITION = re.compile(
    r"\b(?:awards?\s+contender|film\s+rights|movie\s+rights|screen\s+rights)\b",
    re.IGNORECASE,
)
_LOCAL_SEARCH_TERMS = {
    "fr": {
        "acquisition": "(rachat OR acquisition OR acquiert)",
        "equity_funding": "(lève OR levée OR financement OR investissement OR série)",
        "debt_financing": "(prêt OR dette OR crédit OR financement)",
        "fund_raise": "(clôture OR fonds OR levée)",
        "corporate": "(entreprise OR sociétés OR actualités OR événement)",
    },
    "pt": {
        "acquisition": "(aquisição OR adquire OR compra)",
        "equity_funding": "(capta OR rodada OR financiamento OR investimento OR série)",
        "debt_financing": "(empréstimo OR dívida OR financiamento OR crédito)",
        "fund_raise": "(fechamento OR fundo OR captação)",
        "corporate": "(empresa OR companhias OR notícias OR evento)",
    },
    "ar": {
        "acquisition": "(استحواذ OR شراء OR استحوذت)",
        "equity_funding": "(تمويل OR استثمار OR جولة تمويل)",
        "debt_financing": "(قرض OR ديون OR تمويل OR ائتمان)",
        "fund_raise": "(إغلاق OR صندوق OR جمع التمويل)",
        "corporate": "(شركة OR شركات OR أخبار OR أحداث)",
    },
    "es": {
        "acquisition": "(adquisición OR compra OR adquiere)",
        "equity_funding": "(financiación OR inversión OR ronda OR capta)",
        "debt_financing": "(préstamo OR deuda OR financiación OR crédito)",
        "fund_raise": "(cierre OR fondo OR captación)",
        "corporate": "(empresa OR compañías OR noticias OR evento)",
    },
}
_ARABIC_COUNTRY_NAMES = {
    "DZ": "الجزائر",
    "EG": "مصر",
    "LY": "ليبيا",
    "SD": "السودان",
    "MA": "المغرب",
    "TN": "تونس",
}
_REGION_ALIASES = {
    "Northern Africa": r"\b(?:north|northern)\s+africa\b",
    "Western Africa": r"\b(?:west|western)\s+africa\b",
    "Middle Africa": r"\b(?:middle|central)\s+africa\b",
    "Eastern Africa": r"\b(?:east|eastern)\s+africa\b",
    "Southern Africa": r"\bsouthern\s+africa\b",
}


def _terms(q: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9&'-]{3,}", q.lower()) if t not in _STOP]


def parse_question(q: str, today: Optional[date] = None) -> dict:
    today = today or date.today()
    regions = [region for region, pattern in _REGION_ALIASES.items() if re.search(pattern, q, re.IGNORECASE)]
    countries = [c.iso2 for c in countries_in_text(q)]
    countries.extend(c.iso2 for c in COUNTRIES if c.region in regions and c.iso2 not in countries)
    types = [t for t, rx in _TYPE_WORDS.items() if re.search(rf"\b(?:{rx})\b", q, re.IGNORECASE)]
    sectors = [s for s, rx in _SECTOR_WORDS.items() if rx.search(q)]
    investors = []
    for entry in inv.REGISTRY:
        for n in (entry.name, *entry.aliases):
            if re.search(rf"(?<![\w]){re.escape(n)}(?![\w])", q, 0 if n.isupper() else re.IGNORECASE):
                investors.append(entry.name)
                break
    since = until = None
    years = re.findall(r"\b(20\d{2})\b", q)
    if years:
        since, until = date(int(min(years)), 1, 1), date(int(max(years)), 12, 31)
    else:
        number_pattern = r"(\d+|" + "|".join(_NUMBER_WORDS) + r")"
        m = re.search(rf"\b(?:last|past)\s+{number_pattern}\s+(day|week|month|year)s?\b", q, re.IGNORECASE)
        if m:
            count = m.group(1).lower()
            n = int(count) if count.isdigit() else _NUMBER_WORDS[count]
            unit = m.group(2).lower()
            since = today - timedelta(days=n * {"day": 1, "week": 7, "month": 30, "year": 365}[unit])
        elif re.search(r"\bthis\s+year\b", q, re.IGNORECASE):
            since, until = date(today.year, 1, 1), today
        elif re.search(r"\blast\s+year\b", q, re.IGNORECASE):
            since, until = date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
        elif re.search(r"\bpast\s+year\b", q, re.IGNORECASE):
            since = today - timedelta(days=365)
    # Keep explicit company names even at the start of a question, while ignoring
    # interrogatives and generic market vocabulary that is capitalised by title case.
    company_question = q.replace("’", "'")
    for country in countries_in_text(company_question):
        for country_name in sorted((country.name, *country.aliases), key=len, reverse=True):
            company_question = re.sub(rf"(?<![\w]){re.escape(country_name)}(?![\w])", " ",
                                      company_question, flags=re.IGNORECASE)
    companies = []
    for phrase in re.findall(r"(?<![.?!]\s)\b([A-Z][\w&'-]+(?:\s+[A-Z][\w&'-]+){0,3})", company_question):
        phrase = re.sub(r"'s$", "", phrase)
        phrase_words = phrase.split()
        while phrase_words and phrase_words[0].lower() in _STOP:
            phrase_words.pop(0)
        phrase = " ".join(phrase_words)
        if not phrase:
            continue
        words = re.findall(r"[a-z0-9]+", phrase.lower())
        if (inv.canonical(phrase) in investors or not words
                or all(word in _STOP for word in words)
                or any(pattern.search(phrase) for pattern in _SECTOR_WORDS.values())
                or any(re.fullmatch(pattern, phrase, re.IGNORECASE) for pattern in _REGION_ALIASES.values())):
            continue
        companies.append(phrase)
    kinds = [k for k, rx in (("dfi", r"\b(dfis?|development\s+finance)\b"), ("multilateral", r"\bmultilateral"),
                             ("private_equity", r"\bprivate\s+equity\b|\bpe\s+firms?\b"),
                             ("venture_capital", r"\bventure\s+capital|\bvcs?\b"), ("sovereign", r"\bsovereign\s+wealth"))
             if re.search(rx, q, re.IGNORECASE)]
    return {"countries": countries, "regions": regions, "deal_types": types, "sectors": sectors,
            "investors": investors, "investor_kinds": kinds,
            "companies": companies[:4], "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None, "terms": _terms(q)}


def _score(text: str, terms: list[str]) -> int:
    t = text.lower()
    return sum(1 for w in terms if w in t)


def _date_in_scope(value: Optional[str], parsed: dict) -> bool:
    if not parsed["since"] and not parsed["until"]:
        return True
    try:
        day = date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return False
    return (not parsed["since"] or day.isoformat() >= parsed["since"]) and (
        not parsed["until"] or day.isoformat() <= parsed["until"]
    )


def _matches_company(name: str, deal: dict) -> bool:
    tokens = deals_mod.normalise_name(name).split()
    if not tokens:
        return False
    fields = [deal.get("target"), deal.get("buyer"), deal.get("seller"), deal.get("headline"),
              *(deal.get("investors") or [])]
    return any(all(token in deals_mod.normalise_name(str(field)).split() for token in tokens)
               for field in fields if field)


def _fmt_usd(v: Optional[float]) -> str:
    if not v:
        return "undisclosed"
    for unit, div in (("bn", 1e9), ("m", 1e6), ("k", 1e3)):
        if abs(v) >= div:
            return f"${v / div:.1f}{unit}".replace(".0" + unit, unit)
    return f"${v:,.0f}"


_KIND_LABEL = {"dfi": "development finance institution", "multilateral": "multilateral development bank",
               "private_equity": "private equity firm", "venture_capital": "venture capital firm", "growth": "growth investor",
               "sovereign": "sovereign wealth fund", "pension": "pension fund", "accelerator": "accelerator"}


def _who(name: str) -> str:
    """Name with its registry type, so the model need not know who a DFI is."""
    entry = inv.registry_entry(name)
    return f"{name} ({_KIND_LABEL.get(entry.kind, entry.kind)})" if entry else name


def _deal_text(d: dict) -> str:
    parts = [f"{d['deal_type'].replace('_', ' ')} ({d.get('stage')})", f"target: {d.get('target') or 'n/a'}"]
    if d.get("buyer"):
        parts.append(f"buyer/lead/lender: {_who(d['buyer'])}")
    if d.get("investors"):
        parts.append(f"investors: {', '.join(_who(n) for n in d['investors'][:6])}")
    parts.append(f"amount: {_fmt_usd(d.get('amount_usd'))}")
    if d.get("round"):
        parts.append(f"round: {d['round']}")
    if d.get("stake_pct"):
        parts.append(f"stake: {d['stake_pct']}%")
    val = d.get("reported_valuation_usd") or d.get("implied_valuation_usd")
    if val:
        parts.append(f"valuation: {_fmt_usd(val)}")
    parts.append(f"country: {d.get('country') or 'Africa'}; sector: {d.get('sector') or 'n/a'}")
    tier = d.get("verification")
    if tier:
        parts.append(f"record verification tier: {tier}")
    independent = d.get("independent_stories")
    if independent is not None:
        parts.append(f"independent reported stories: {independent}")
    sources = d.get("sources") or []
    if sources:
        parts.append(f"linked source records: {len(sources)}")
    return "; ".join(parts) + f". Headline: {d.get('headline')}"


def _news_items(query: str, country: Optional[str], limit: int = 8, client: Optional[httpx.Client] = None,
                since: Optional[str] = None, until: Optional[str] = None) -> list[dict]:
    c = get_country(country) if country else None
    query_variants: list[tuple[str, Optional[str]]] = [(query, None)]
    if c:
        from src.engines.market_feed import localized_country_name

        action = next((kind for kind, pattern in _NEWS_ACTIONS.items() if pattern.search(query)), None)
        if re.search(r"\b(?:fund\s+close|first\s+close|final\s+close|fund\s+raising)\b", query, re.IGNORECASE):
            action = "fund_raise"
        elif re.search(r"\b(?:debt|loan|credit|bond|lending|financing)\b", query, re.IGNORECASE):
            action = "debt_financing"
        english_terms = {
            "acquisition": "(acquisition OR acquired OR takeover)",
            "funding": "(funding OR raises OR financing OR investment OR round)",
            "debt_financing": "(debt OR loan OR credit OR bond OR financing)",
            "fund_raise": "(fund close OR fundraise OR closes OR capital)",
            None: "(company OR business OR corporate OR event)",
        }.get(action)
        if action == "funding":
            english_terms = "(funding OR investment OR round OR series)"

        query_variants = [(query, c.languages[0])]
        for language in c.languages[:2]:
            local_label = localized_country_name(c, language)
            labels = list(dict.fromkeys((local_label, c.name, *c.aliases)))
            if c.iso2 in _ARABIC_COUNTRY_NAMES:
                labels.append(_ARABIC_COUNTRY_NAMES[c.iso2])
            country_query = "(" + " OR ".join(f'"{label}"' for label in dict.fromkeys(labels)) + ")"
            local_action = "equity_funding" if action == "funding" else action or "corporate"
            localized_terms = _LOCAL_SEARCH_TERMS.get(language, {}).get(local_action, "")
            if localized_terms:
                query_variants.append((f"{country_query} {localized_terms}", language))
        if c.languages[0] != "en" and english_terms:
            labels = list(dict.fromkeys((c.name, *c.aliases)))
            country_query = "(" + " OR ".join(f'"{label}"' for label in labels) + ")"
            query_variants.append((f"{country_query} {english_terms}", "en"))
        if not any(label.lower() in query.lower() for label in (c.name, *c.aliases)):
            labels = list(dict.fromkeys((c.name, *c.aliases)))
            country_query = "(" + " OR ".join(f'"{label}"' for label in labels) + ")"
            query_variants[0] = (f"{country_query} {query}", c.languages[0])
    query_variants = list(dict.fromkeys(query_variants))

    from src.engines.market_feed import parse_feed
    request_client = client or httpx.Client(timeout=15, follow_redirects=True)

    def fetch(url: str) -> list[dict]:
        r = request_client.get(url)
        r.raise_for_status()
        return parse_feed(r.text)

    def fetch_variants(date_scope: Optional[str]) -> list[dict]:
        results = []
        successful_queries = 0
        errors = []
        for variant, language in query_variants:
            try:
                results.extend(fetch(search_url_for(variant, language, date_scope)))
                successful_queries += 1
            except Exception as e:
                errors.append(e)
                log.warning("research news RSS query failed for %r: %s", variant, e)
        if not successful_queries and errors:
            log.error("research news RSS fetch or parse failed: %s", errors[-1])
        return _rank_news(query, results)

    def search_url_for(variant: str, language: Optional[str], date_scope: Optional[str]) -> str:
        search_query = " ".join(filter(None, (variant, date_scope)))
        return (c.news_url(search_query, language) if c else
                f"https://news.google.com/rss/search?q={quote(search_query)}&hl=en-GB&gl=US&ceid=US:en")

    def resolve_article(item: dict) -> dict:
        item_url = item.get("url") or ""
        publisher_url = item.get("publisher_url") or ""
        publisher_host = (urlparse(publisher_url).hostname or "").lower()
        article_host = (urlparse(item_url).hostname or "").lower()
        if not item_url or not publisher_host or article_host != "news.google.com":
            return item
        try:
            response = request_client.get(item_url)
            response.raise_for_status()
            destination = str(response.url)
        except httpx.HTTPError as e:
            log.info("could not resolve Google News article link for %s: %s", item.get("title"), e)
            return item
        parsed = urlparse(destination)
        destination_host = (parsed.hostname or "").lower()
        normalized_publisher_host = publisher_host.removeprefix("www.")
        normalized_destination_host = destination_host.removeprefix("www.")
        same_publisher = normalized_destination_host == normalized_publisher_host
        if (parsed.scheme == "https" and same_publisher and parsed.path not in {"", "/", "/home", "/homepage"}
                and destination_host not in {"news.google.com", "consent.google.com"}):
            item["url"] = destination
        else:
            log.info("Google News article link did not resolve to a publisher article for %s; retaining RSS URL",
                     item.get("title"))
        return item

    def resolve_articles(items: list[dict]) -> list[dict]:
        return [resolve_article(item) for item in items[:limit]]

    date_scope = " ".join(filter(None, (
        f"after:{since}" if since else None,
        f"before:{until}" if until else None,
    )))
    recent = fetch_variants(date_scope or "when:90d")
    if not recent:
        log.info("research news RSS search completed with no feed items")
    if (since or until) and not recent:
        log.info("date-restricted research search returned no items; retrying without RSS date operators")
        recent = fetch_variants(None)
    if recent and (since or until or _has_relevant_news(query, recent)):
        return resolve_articles(recent)
    log.info("recent research news did not match the question well; retrying without a date restriction")
    broader = fetch_variants(date_scope or None)
    items = _rank_news(query, recent + broader)
    if not items:
        log.info("research broad news RSS search completed with no feed items")
    return resolve_articles(items)


def _news_tokens(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    folded = re.sub(r"\s+", " ", text.lower())
    if (tokens & {"acquire", "acquires", "acquired", "acquiring", "acquisition", "buy", "buys", "bought"}
            or re.search(r"\b(?:rachat|acquisition|acquiert|acheté|aquisição|adquire|comprou)\b", folded)
            or re.search(r"(?:استحواذ|اشتر)", folded)):
        tokens.add("acquisition")
    if (tokens & {"fund", "funds", "funded", "funding", "raise", "raises", "raised", "investment", "invests"}
            or re.search(r"\b(?:lève|levée|lever|financement|investissement|capta|arrecada|"
                         r"levanta|recebe|financiamento|investimento|ronda|rodada)\b", folded)
            or re.search(r"(?:تمويل|استثمار|جمع)", folded)):
        tokens.add("funding")
    for country in countries_in_text(text):
        tokens.add(country.name.lower())
        tokens.add(country.iso2.lower())
    return tokens


def _news_matches_country(item: dict, code: str) -> bool:
    country = get_country(code)
    if not country:
        return False
    text = f"{item.get('title', '')} {item.get('snippet', '')}"
    from src.engines.market_feed import localized_country_name

    labels = [country.name, *(localized_country_name(country, language) for language in country.languages[:2])]
    labels.extend(country.aliases)
    for name in dict.fromkeys(labels):
        final_word = name.split()[-1].lower()
        if name not in {country.name, localized_country_name(country, country.languages[0])} and re.search(
                r"(?:ian|ean|ese|ish|ien|ienne|ais|aise|ain|aine|ois|oise|an|ano|ana|ense|er)$",
                final_word, re.IGNORECASE):
            continue
        if re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", text, re.IGNORECASE):
            return True
    mentioned_countries = {found.iso2 for found in countries_in_text(text)}
    return code in mentioned_countries and len(mentioned_countries) == 1


def _is_equity_funding_announcement(text: str) -> bool:
    return bool(_FUNDING_ANNOUNCEMENT.search(text)
                and not _FUNDING_NEGATION.search(text)
                and (not _NON_EQUITY_FUNDING.search(text) or _EQUITY_FUNDING_MARKER.search(text)))


def _is_acquisition_announcement(text: str) -> bool:
    return bool(_NEWS_ACTIONS["acquisition"].search(text)
                and not _NON_CORPORATE_ACQUISITION.search(text))


def _has_relevant_news(query: str, items: list[dict]) -> bool:
    query_tokens = _news_tokens(query) - _STOP
    if not query_tokens or not items:
        return False
    requested_series = re.search(r"\bseries\s+([a-g])\b", query, re.IGNORECASE)
    action_groups = [kind for kind, pattern in _NEWS_ACTIONS.items() if pattern.search(query)]
    for item in items:
        title = item.get("title", "")
        title_tokens = _news_tokens(f"{title} {item.get('snippet', '')}")
        if requested_series and not re.search(
                rf"\bseries\s+{requested_series.group(1)}\b", f"{title} {item.get('snippet', '')}", re.IGNORECASE):
            continue
        if requested_series and len((query_tokens - {"funding", "acquisition"}) & title_tokens) >= 1:
            return True
        if action_groups:
            other_terms = query_tokens - {"acquisition", "funding"}
            if len(other_terms & title_tokens) < 1:
                continue
            if "funding" in action_groups and _is_equity_funding_announcement(
                    f"{title} {item.get('snippet', '')}"):
                return True
            if "acquisition" in action_groups:
                words = re.findall(r"[a-z0-9]+", title.lower())
                target_terms = other_terms
                passive = re.search(r"\bacquired\s+by\b", title, re.IGNORECASE)
                if passive:
                    before_action = set(words[:len(re.findall(r"[a-z0-9]+", title[:passive.start()].lower()))])
                    if target_terms & before_action:
                        return True
                    tail = title[passive.end():]
                    buyer_end = re.search(r",", tail)
                    if buyer_end and target_terms & _news_tokens(tail[buyer_end.end():]):
                        return True
                else:
                    active = re.search(r"\b(?:acquir\w*|buys|bought)\b", title, re.IGNORECASE)
                    if active:
                        action_position = len(re.findall(r"[a-z0-9]+", title[:active.start()].lower()))
                        if any(term in words[action_position + 1:] for term in target_terms):
                            return True
                if re.search(r"\bacquisition\s+of\s+", title, re.IGNORECASE):
                    acquisition = re.search(r"\bacquisition\s+of\s+", title, re.IGNORECASE)
                    if acquisition and target_terms & _news_tokens(title[acquisition.end():]):
                        return True
        elif len(query_tokens & title_tokens) >= min(2, len(query_tokens)):
            return True
    return False


def _rank_news(query: str, items: list[dict]) -> list[dict]:
    query_tokens = _news_tokens(query) - _STOP
    series = re.search(r"\bseries\s+([a-g])\b", query, re.IGNORECASE)
    requested_actions = [kind for kind, pattern in _NEWS_ACTIONS.items() if pattern.search(query)]
    unique = {}
    for item in items:
        key = item.get("url") or item.get("title")
        if key and key not in unique:
            unique[key] = item
    return sorted(unique.values(), key=lambda item: (
        any(
            _is_acquisition_announcement(f"{item.get('title', '')} {item.get('snippet', '')}")
            if action == "acquisition" else
            _is_equity_funding_announcement(f"{item.get('title', '')} {item.get('snippet', '')}")
            for action in requested_actions
        ),
        bool(series and re.search(
            rf"\bseries\s+{series.group(1)}\b", f"{item.get('title', '')} {item.get('snippet', '')}", re.IGNORECASE)),
        len(query_tokens & _news_tokens(f"{item.get('title', '')} {item.get('snippet', '')}")),
        {"Official / primary": 3, "Established publisher": 2, "Unrated publisher": 1}.get(
            _source_assessment("news", item.get("url"), item.get("publisher"))[0], 0),
        item.get("date") or "",
    ), reverse=True)


def _source_assessment(kind: str, url: Optional[str], source: Optional[str]) -> tuple[str, str]:
    """Conservative, transparent source classification; this is not a truth guarantee."""
    publisher = (source or "").strip().lower()
    host = (urlparse(url).hostname or "").lower().removeprefix("www.") if url else ""
    primary_hosts = {
        "sec.gov", "edgar.sec.gov", "ngxgroup.com", "nse.co.ke", "jse.co.za",
        "worldbank.org", "data.worldbank.org", "imf.org", "afdb.org", "ifc.org",
        "cbn.gov.ng", "sec.gov.ng", "fsca.co.za", "cma.or.ke", "bankofengland.co.uk",
        "ecb.europa.eu", "federalreserve.gov", "federalreserve.gov", "bis.org",
    }
    if host and (host.endswith(".gov") or host.endswith(".gov.ng") or host.endswith(".gov.za")
                 or host in primary_hosts or any(host.endswith("." + d) for d in primary_hosts)):
        return "Official / primary", "Official filing, regulator, exchange, central-bank or institutional domain."
    primary_publishers = ("world bank", "international monetary fund", "imf", "african development bank",
                          "ifc", "securities and exchange commission", "central bank", "stock exchange",
                          "national statistics", "ministry of finance", "company announcement", "investor relations")
    if any(term in publisher for term in primary_publishers):
        return "Official / primary", "Identified as an official institution or company source; check the linked document."
    established = ("reuters", "associated press", "ap news", "bloomberg", "financial times",
                   "wall street journal", "the economist", "bbc", "cnbc", "africa report",
                   "businessday", "techcabal", "techcrunch", "disrupt africa", "ventureburn",
                   "financial afric", "moneyweb", "business daily africa", "the east african")
    if any(term in publisher or term in host for term in established):
        return "Established publisher", "Recognised news publisher; secondary reporting, not an official filing."
    if not url:
        if kind in {"statistics", "investor", "country_risk", "currency_risk"}:
            return "Database-derived", "Computed from the product's structured data or stated methodology; inspect its underlying inputs."
        return "No direct source link", "The claim cannot be independently checked from a direct link in this result."
    if host in {"news.google.com", "consent.google.com"}:
        return "Aggregator / unresolved", "Search aggregator link; publisher-level verification is still needed."
    return "Unrated publisher", "A link is present, but this system has not independently rated the publisher or verified claim support."


def retrieve(question: str, deals: Iterable[dict] = (), events: Iterable[dict] = (), briefs: Iterable[dict] = (),
             live_news: bool = True, news: Optional[Callable[[str, Optional[str]], list[dict]]] = None,
             today: Optional[date] = None, max_items: int = 30) -> tuple[dict, list[dict]]:
    """(parsed question, numbered evidence items)."""
    max_items = max(0, max_items)
    p = parse_question(question, today)
    deals, events = list(deals), list(events)
    items: list[dict] = []

    def add(kind: str, title: str, text: str, url: Optional[str] = None, day: Optional[str] = None,
            source: Optional[str] = None) -> None:
        source_quality, source_quality_note = _source_assessment(kind, url, source)
        items.append({"n": len(items) + 1, "kind": kind, "title": title, "text": text, "url": url, "date": day,
                      "source": source, "source_quality": source_quality,
                      "source_quality_note": source_quality_note})

    # Deals: filtered by the parsed scope, ranked by term overlap then recency.
    scope = []
    for d in deals:
        if p["countries"] and not set(p["countries"]) & set(d.get("countries") or [d.get("country")]):
            continue
        if p["deal_types"] and d.get("deal_type") not in p["deal_types"]:
            continue
        if p["sectors"] and d.get("sector") not in p["sectors"]:
            continue
        if not _date_in_scope(d.get("announced"), p):
            continue
        if p["investors"] and not set(p["investors"]) & {n for n, _ in inv.parties(d)}:
            continue
        if p["investor_kinds"]:
            kinds = set(p["investor_kinds"]) | ({"multilateral"} if "dfi" in p["investor_kinds"] else set())
            if not any((inv.registry_entry(n) or inv.Investor("", "", "")).kind in kinds for n, _ in inv.parties(d)):
                continue
        if p["companies"] and not any(_matches_company(c, d) for c in p["companies"]):
            continue
        scope.append(d)
    scope.sort(key=lambda d: (_score(_deal_text(d), p["terms"]), d.get("announced") or ""), reverse=True)
    if scope:
        total = sum(d.get("amount_usd") or 0 for d in scope)
        by_type = Counter(d["deal_type"] for d in scope)
        by_country = Counter(d.get("country") or "pan-African" for d in scope)
        add("statistics", "Deals in scope (computed from the deals database)",
            f"{len(scope)} deals; disclosed value {_fmt_usd(total)} across {sum(1 for d in scope if d.get('amount_usd'))} "
            f"with amounts; by type: {dict(by_type)}; by country: {dict(by_country.most_common(8))}; "
            f"period: {min(d.get('announced') or '' for d in scope)} to {max(d.get('announced') or '' for d in scope)}.",
            source="Deals database")
    for d in scope[:12]:
        src = (d.get("sources") or [{}])[0]
        add("deal", d.get("headline") or d.get("target") or "deal", _deal_text(d), src.get("url"), d.get("announced"),
            src.get("publisher") or "news")

    # Corporate events.
    ev = [e for e in events
          if (not p["countries"] or set(p["countries"]) & set(e.get("countries") or [e.get("country")]))
          and (not p["sectors"] or e.get("sector") in p["sectors"])
          and _date_in_scope(e.get("day"), p)]
    ev.sort(key=lambda e: (_score(e["headline"], p["terms"]), e.get("day") or ""), reverse=True)
    for e in ev[:8]:
        add("event", e["headline"], f"{e['signal_type'].replace('_', ' ')} event"
            + (f", direction {e['direction']}" if e.get("direction") else "") + f"; country {e.get('country') or 'n/a'}",
            e.get("url"), e.get("day"), e.get("publisher"))

    # Country and currency risk.
    for code in ([] if p["regions"] else p["countries"][:3]):
        c = get_country(code)
        risk = cr.assess(c, fx=lambda _: None)
        comps = ", ".join(f"{x['name'].replace('_', ' ')} risk {x['risk']}" for x in risk["components"] if x["risk"] is not None)
        add("country_risk", f"{c.name} country risk", f"score {risk['score']}/100 ({risk['tier']}), coverage "
            f"{risk['coverage']:.0%}; component risk scores (0 = lowest risk, 100 = highest): {comps}. "
            f"World Bank data retrieved {risk['data_as_of']}.",
            "https://data.worldbank.org/country/" + c.iso2, risk["data_as_of"], "World Bank WGI/WDI")
        cur = mr.currency_risk(c.currency, fx=lambda _: None)
        add("currency_risk", f"{c.currency} currency risk", f"regime: {cur['regime']}; depreciation against the US "
            f"dollar last year {cur['last_year_depreciation_pct']}% (negative means the currency strengthened); five-year "
            f"annualised depreciation {cur['five_year_annualised_depreciation_pct']}%; currency risk score {cur['score']}/100 "
            f"({cur['tier']}).", None, None, "World Bank official exchange rates")

    # Investor profiles.
    investor_profiles = [inv.profile(scope, name) for name in p["investors"][:3]]
    kinds = set(p["investor_kinds"])
    if "dfi" in kinds:
        kinds.add("multilateral")
    for kind in sorted(kinds):
        investor_profiles.extend(inv.leaderboard(scope, kind=kind, limit=6))
    unique_profiles = {profile["name"]: profile for profile in investor_profiles if profile}
    ranked_profiles = sorted(unique_profiles.values(), key=lambda profile: profile["deal_count"], reverse=True)
    for prof in ranked_profiles[:6]:
        add("investor", f"{prof['name']} activity", f"{prof['deal_count']} deals; roles {prof['roles']}; disclosed "
            f"{_fmt_usd(prof['disclosed_usd'])}; countries {prof['countries']}; last seen {prof['last_seen']}.",
            source="Deals database")

    # Company briefs (signal analysis) that match the question.
    for b in briefs:
        if p["companies"] and any(deals_mod.normalise_name(c) in deals_mod.normalise_name(b.get("company", ""))
                                  for c in p["companies"]):
            sigs = (b.get("brief") or {}).get("detected_signals", [])
            add("brief", f"Signal brief: {b.get('company')}", f"severity {b.get('severity')}; signals: "
                + "; ".join(f"{s.get('signal_type')} ({s.get('severity')})" for s in sigs[:6]),
                None, (b.get("created_at") or "")[:10], "Deal Intelligence brief")

    # Live news is attempted even when local evidence is full; valid results displace
    # the least-prioritised local items so they survive the final evidence cap.
    if live_news:
        company_terms = p["companies"][:2]
        company_tokens = {token.lower() for name in company_terms
                          for token in re.findall(r"[a-z0-9]+", name, re.IGNORECASE)}
        country_tokens = {token.lower() for code in p["countries"]
                          for name in ((get_country(code).name, *get_country(code).aliases)
                                       if get_country(code) else ())
                          for token in re.findall(r"[a-z0-9]+", name, re.IGNORECASE)}
        query_terms = company_terms + [
            term for term in p["terms"]
            if not set(re.findall(r"[a-z0-9]+", term.lower())).issubset(company_tokens | country_tokens)
            and not re.fullmatch(r"20\d{2}", term)
        ][:3]
        series = re.search(r"\bseries\s+([a-g])\b", question, re.IGNORECASE)
        if series:
            query_terms.append(f"Series {series.group(1).upper()}")
        amount = re.search(r"(?<!\w)(?:[$€£]\s*)?\d+(?:\.\d+)?\s*(?:million|billion|m|bn)(?!\w)",
                           question, re.IGNORECASE)
        if amount:
            query_terms.append(amount.group(0))
        country_context = [get_country(code).name for code in p["countries"][:1] if get_country(code)]
        query = " ".join([*p["regions"][:1], *country_context, *query_terms]) or question[:80]
        news_country = p["countries"][0] if len(p["countries"]) == 1 and not p["regions"] else None
        news_search = news or (lambda q, c: _news_items(q, c, since=p["since"], until=p["until"]))
        try:
            fetched_news = news_search(query, news_country)
        except Exception as e:
            log.error("research news search failed: %s", e)
            fetched_news = []
        if len(p["countries"]) == 1 and not p["regions"]:
            code = p["countries"][0]
            company_tokens = [deals_mod.normalise_name(name) for name in p["companies"]]
            fetched_news = [
                item for item in fetched_news
                if (_news_matches_country(item, code)
                    or any(token and token in deals_mod.normalise_name(
                        f"{item.get('title', '')} {item.get('snippet', '')}") for token in company_tokens))
            ]
        if "acquisition" in p["deal_types"]:
            if p["companies"]:
                fetched_news = [it for it in fetched_news if _has_relevant_news(query, [it])]
            else:
                fetched_news = [it for it in fetched_news if _is_acquisition_announcement(
                    f"{it.get('title', '')} {it.get('snippet', '')}")]
        elif "equity_funding" in p["deal_types"]:
            requested_series = re.search(r"\bseries\s+([a-g])\b", question, re.IGNORECASE)
            fetched_news = [it for it in fetched_news
                            if (_has_relevant_news(query, [it]) if requested_series else
                                _is_equity_funding_announcement(
                                    f"{it.get('title', '')} {it.get('snippet', '')}"))]
        valid_news = []
        news_limit = min(_NEWS_EVIDENCE_LIMIT, max_items)
        if news_limit:
            for it in fetched_news:
                if not _date_in_scope(it.get("date"), p):
                    continue
                valid_news.append(it)
                if len(valid_news) >= news_limit:
                    break
        if fetched_news and not valid_news:
            log.info("research news RSS search returned no date-valid results (%d fetched)", len(fetched_news))
        elif valid_news:
            log.debug("research news RSS search returned %d date-valid results", len(valid_news))
            items = items[:max_items - len(valid_news)]
            for it in valid_news:
                add("news", it["title"], it.get("snippet") or it["title"],
                    it.get("url"),
                    it.get("date"), it.get("publisher"))
    return p, items[:max_items]


SYSTEM = """You are a research analyst covering African companies, private markets and country risk.
Answer the question using ONLY the numbered evidence items provided. Rules:
- Every factual sentence must end with one or more citations like [3] or [2][5] pointing at the items it relies on.
- Do not use outside knowledge, do not estimate figures that are not in the items, and do not invent names.
- If the items do not answer the question, say so plainly and state what evidence is missing.
- Cite with square brackets only, e.g. [4], never other bracket styles.
- Be concise: a short direct answer, then the key supporting points. Use US dollars as given in the items."""


def _evidence_block(items: list[dict]) -> str:
    return "\n".join(f"[{i['n']}] ({i['kind']}; {i.get('source') or ''}; {i.get('date') or 'undated'}) "
                     f"{i['title']} | {i['text']}" for i in items)


_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\-*•])")
_CITE = re.compile(r"\[(\d{1,3})\]")


def normalise_citations(text: str) -> str:
    """【3】, [2, 5], [2-4] and (3) styles -> [3], [2][5], [2][3][4]."""
    text = re.sub(r"【\s*(\d{1,3})\s*】", r"[\1]", text)

    def expand(m: re.Match) -> str:
        nums: list[int] = []
        for part in re.split(r"\s*,\s*", m.group(1)):
            if "-" in part or "–" in part:
                a, b = re.split(r"[-–]", part)
                nums += list(range(int(a), int(b) + 1)) if int(b) - int(a) < 10 else [int(a), int(b)]
            else:
                nums.append(int(part))
        return "".join(f"[{n}]" for n in nums)
    return re.sub(r"\[(\d{1,3}(?:\s*[,\-–]\s*\d{1,3})+)\]", expand, text)


_NO_CLAIM = re.compile(r"(?i)\b(no|not)\b.{0,80}\b(evidence|items?|provided|available|listed|recorded)\b"
                       r"|\b(evidence|items?)\b.{0,40}\b(do|does)\s+not\b")


def _segments(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = re.sub(r"^[-*•\s]+", "", line.strip())
        if not line or line.startswith("#") or re.fullmatch(r"[*_]{1,3}[^*_]+[*_]{1,3}:?", line) or line.endswith(":"):
            continue
        out += [s.strip() for s in _SENTENCE.split(line) if len(s.strip()) > 25]
    return out


def validate_citations(text: str, n_items: int) -> dict:
    """Remove citations to items that do not exist; report factual sentences without a valid citation."""
    text = normalise_citations(text)
    invalid = sorted({int(n) for n in _CITE.findall(text) if not 1 <= int(n) <= n_items})
    clean = _CITE.sub(lambda m: m.group(0) if 1 <= int(m.group(1)) <= n_items else "", text)
    factual = [s for s in _segments(clean) if not _NO_CLAIM.search(s)]
    uncited = [s for s in factual if not _CITE.search(s)]
    cited = sorted({int(n) for n in _CITE.findall(clean)})
    return {"text": clean, "invalid_citations_removed": invalid, "cited_items": cited,
            "sentences": len(factual), "uncited_sentences": uncited,
            "grounded_share": round(1 - len(uncited) / len(factual), 2) if factual else 1.0}


def _acquisition_summary(parsed: dict, items: list[dict], question: str) -> Optional[str]:
    if "acquisition" not in parsed["deal_types"] or not parsed["companies"]:
        return None
    target = parsed["companies"][0]
    target_tokens = set(re.findall(r"[a-z0-9]+", deals_mod.normalise_name(target)))
    descriptors = {"us", "silicon", "valley", "payments", "payment", "giant", "nigerian", "nigeria",
                   "startup", "african", "fintech", "online", "commerce", "processor", "firm", "company"}
    matches = []

    def buyer_name(segment: str) -> str:
        capitalized = re.findall(r"\b[A-Z][A-Za-z0-9&.'’-]*\b", segment)
        buyer_parts = [part for part in capitalized
                       if part.lower() not in descriptors
                       and not target_tokens.intersection(re.findall(r"[a-z0-9]+", part.lower()))]
        return " ".join(buyer_parts[-2:])

    for item in items:
        if item["kind"] not in {"news", "deal"}:
            continue
        title = item["title"]
        words = re.findall(r"[a-z0-9]+", title.lower())
        if not target_tokens or not target_tokens.issubset(set(words)):
            continue
        passive = re.search(r"\bacquired\s+by\s+(.+?)(?:,|\s+(?:for|in|as)\b|$)", title, re.IGNORECASE)
        active = re.search(r"\b(?:acquir\w*|buys|bought)\b", title, re.IGNORECASE)
        nominal = re.search(r"\bacquisition\s+of\s+", title, re.IGNORECASE)
        if passive:
            buyer = buyer_name(passive.group(1))
        elif active:
            action_word = active.group(0).lower()
            target_positions = [index for index, word in enumerate(words) if word in target_tokens]
            action_position = next((index for index, word in enumerate(words)
                                    if word in {action_word, "acquire", "acquires", "acquired",
                                                "acquiring", "buys", "bought"}), -1)
            buyer = buyer_name(title[:active.start()]) if any(pos > action_position for pos in target_positions) else ""
        elif nominal:
            buyer = buyer_name(title[:nominal.start()])
        else:
            buyer = ""
        if buyer:
            matches.append((buyer, item))
    if not matches:
        return None
    buyers = Counter(buyer for buyer, _ in matches)
    buyer = buyers.most_common(1)[0][0]
    corroborating = [item for candidate, item in matches if candidate == buyer]
    dates = sorted({item["date"] for item in corroborating if item.get("date")})
    if dates:
        earliest = dates[0]
        corroborating = [item for item in corroborating if item.get("date") == earliest]
    corroborating = corroborating[:4]
    citations = "".join(f"[{item['n']}]" for item in corroborating)
    dates = sorted({item["date"] for item in corroborating if item.get("date")})
    date_text = f" in reports dated {', '.join(dates)}" if dates else ""
    summary = f"Reports identify {buyer} as the acquirer of {target}{date_text} {citations}."
    if re.search(r"\b(?:value|amount|price|transaction)\b", question, re.IGNORECASE):
        amount_reports = [
            item for _, item in matches
            if re.search(r"(?:\$|€|£|USD|EUR|GBP)\s?[\d,.]+\s?(?:million|billion|m|bn)?\+?"
                         r"|\b[\d,.]+\s?(?:million|billion|m|bn)\b",
                         f"{item['title']} {item['text']}", re.IGNORECASE)
        ]
        if amount_reports:
            report = amount_reports[0]
            figure = re.search(r"(?:\$|€|£|USD|EUR|GBP)\s?[\d,.]+\s?(?:million|billion|m|bn)?\+?"
                               r"|\b[\d,.]+\s?(?:million|billion|m|bn)\b",
                               report["title"], re.IGNORECASE)
            reported = figure.group(0) if figure else "an amount"
            summary += (f" A separate headline reports {reported}, but the retrieved evidence does not confirm "
                        f"it as the publicly disclosed deal value [{report['n']}].")
        else:
            summary += (" The transaction value and whether it was publicly disclosed are not established "
                        f"by the retrieved evidence {citations}.")
    return summary


def _funding_summary(parsed: dict, items: list[dict]) -> Optional[str]:
    if "equity_funding" not in parsed["deal_types"]:
        return None
    reports = [item for item in items if item["kind"] in {"news", "deal"}
               and _is_equity_funding_announcement(f"{item['title']} {item['text']}")]
    if not reports:
        return ("The retrieved evidence does not identify a specific funding announcement or disclosed amount "
                "in the requested period.")
    citations = "".join(f"[{item['n']}]" for item in reports[:6])
    return f"Funding-related reports in the requested period include the announcements listed below {citations}."


def _funding_audit_summary(parsed: dict, items: list[dict], question: str) -> Optional[str]:
    if not parsed["companies"] or not re.search(
            r"\b(?:audit|separate|amount raised|valuation|series\s+[a-g])\b", question, re.IGNORECASE):
        return None
    company = parsed["companies"][0]
    company_tokens = set(re.findall(r"[a-z0-9]+", deals_mod.normalise_name(company)))
    evidence = []
    for item in items:
        if item["kind"] not in {"news", "deal"}:
            continue
        title, body = item.get("title", ""), item.get("text", "")
        text = title if body == title else f"{title} {body}"
        text_tokens = set(re.findall(r"[a-z0-9]+", deals_mod.normalise_name(text)))
        if company_tokens and company_tokens.issubset(text_tokens):
            evidence.append((item, text))
    if not evidence:
        return ("Amount raised: unknown; valuation: unknown. The retrieved evidence does not establish either "
                "field.")

    def amount(pattern: str, exclude_valuation_context: bool = False) -> list[tuple[str, dict]]:
        found = []
        seen: set[tuple[str, int]] = set()
        for item, text in evidence:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = match.group(1).strip()
                key = (value.lower(), item["n"])
                if key in seen:
                    continue
                nearby = text[max(0, match.start() - 32):match.end() + 32]
                if exclude_valuation_context and re.search(r"\b(?:valuation|valued)\b", nearby, re.IGNORECASE):
                    continue
                seen.add(key)
                found.append((value, item))
        return found

    amount_raised = amount(
        r"\b(?:raised|raises|secured|secures|received|receives|closed|closes)\b"
        r".{0,80}?((?:\$|€|£|USD|EUR|GBP)\s?[\d,.]+\s?(?:million|billion|m|bn)?\+?)",
        exclude_valuation_context=True,
    )
    valuation = amount(
        r"\b(?:valuation|valued)\b.{0,50}?"
        r"((?:\$|€|£|USD|EUR|GBP)\s?[\d,.]+\s?(?:million|billion|m|bn)?\+?)"
    )
    if not valuation:
        valuation = amount(
            r"((?:\$|€|£|USD|EUR|GBP)\s?[\d,.]+\s?(?:million|billion|m|bn)?\+?)"
            r".{0,15}\b(?:valuation|valued)\b"
        )
    citations_by_type = {
        "amount": "".join(f"[{item['n']}]" for _, item in amount_raised[:4]),
        "valuation": "".join(f"[{item['n']}]" for _, item in valuation[:4]),
    }
    cited = "".join(f"[{item['n']}]" for item, _ in evidence[:4])
    raised_text = (f"{amount_raised[0][0]} {citations_by_type['amount']}" if amount_raised else
                   f"unknown (not explicitly established by these reports) {cited}")
    valuation_text = (f"{valuation[0][0]} {citations_by_type['valuation']}" if valuation else
                      f"unknown (not explicitly established by these reports) {cited}")
    return f"Amount raised: {raised_text}. Valuation: {valuation_text}."


def deterministic_answer(question: str, parsed: dict, items: list[dict]) -> str:
    if not items:
        return "No evidence in the deals database, event feed or news matched this question."
    lines = []
    acquisition_summary = _acquisition_summary(parsed, items, question)
    if acquisition_summary:
        lines.append(acquisition_summary)
    audit_summary = _funding_audit_summary(parsed, items, question)
    if audit_summary:
        lines.append(audit_summary)
    funding_summary = _funding_summary(parsed, items) if not audit_summary else None
    if funding_summary:
        lines.append(funding_summary)
    stats = next((i for i in items if i["kind"] == "statistics"), None)
    if stats:
        lines.append(f"{stats['text']} [{stats['n']}]")
    for kind, label in (("deal", "Relevant deals"), ("investor", "Investors"), ("country_risk", "Country risk"),
                        ("currency_risk", "Currency risk"), ("event", "Corporate events"), ("news", "News reports")):
        rows = [i for i in items if i["kind"] == kind]
        if rows:
            lines.append(f"\n{label}:")
            lines += [f"- {i['title']}" + (f" ({i['date']})" if i.get("date") else "") + f" [{i['n']}]" for i in rows[:8]]
    return "\n".join(lines)


def evidence_coverage(items: list[dict]) -> list[dict]:
    """Summarise retrieved evidence and its newest source date without implying completeness."""
    kinds = sorted({item["kind"] for item in items})
    return [
        {
            "kind": kind,
            "items": sum(1 for item in items if item["kind"] == kind),
            "latest_source_date": max(
                (str(item["date"])[:10] for item in items if item["kind"] == kind and item.get("date")),
                default=None,
            ),
        }
        for kind in kinds
    ]


def answer(question: str, items: list[dict], parsed: Optional[dict] = None, llm: Optional[Callable] = None) -> dict:
    """Grounded answer. llm(system, user, max_tokens) -> text; None uses the configured router or falls back."""
    parsed = parsed or parse_question(question)
    model = None
    if llm is None:
        try:
            from src.agents.signal_agent import _call_llm, _get_llm_client, _model_label
            client, provider = _get_llm_client()

            def llm(system: str, user: str, max_tokens: int) -> str:     # noqa: E306
                return _call_llm(client, provider, system, user, max_tokens)
            model_of = lambda: _model_label(client, provider)            # noqa: E731
        except Exception as e:
            log.info("research without LLM: %s", e)
            llm, model_of = None, None
    else:
        model_of = lambda: "custom"                                       # noqa: E731
    if llm is None or not items:
        text = deterministic_answer(question, parsed, items)
        return {"answer": text, "mode": "deterministic", "model": None, **_validation_summary(text, items)}
    user = f"Question: {question}\n\nEvidence items:\n{_evidence_block(items)}\n\nAnswer with citations."
    try:
        text = llm(SYSTEM, user, 1200)
        model = model_of() if model_of else None
    except Exception as e:
        log.warning("research LLM call failed: %s", e)
        text = deterministic_answer(question, parsed, items)
        return {"answer": text, "mode": "deterministic", "model": None, **_validation_summary(text, items)}
    v = validate_citations(text, len(items))
    return {"answer": v["text"], "mode": "llm", "model": model, "validation": v}


def _validation_summary(text: str, items: list[dict]) -> dict:
    return {"validation": validate_citations(text, len(items))}


def research(question: str, deals: Iterable[dict] = (), events: Iterable[dict] = (), briefs: Iterable[dict] = (),
             live_news: bool = True, llm: Optional[Callable] = None, news=None, today: Optional[date] = None) -> dict:
    parsed, items = retrieve(question, deals, events, briefs, live_news=live_news, news=news, today=today)
    result = answer(question, items, parsed, llm)
    return {"question": question, "parsed": parsed, "evidence": items,
            "evidence_coverage": evidence_coverage(items), **result}


# ── Research reports ──────────────────────────────────────────────────────────

def _section(title: str, rows: list[str]) -> str:
    return f"## {title}\n\n" + ("\n".join(rows) if rows else "_No evidence in the sources for this section._") + "\n"


def country_report(code: str, deals: Iterable[dict] = (), events: Iterable[dict] = (),
                   llm: Optional[Callable] = None, live_news: bool = True, news=None) -> dict:
    c = get_country(code)
    if c is None:
        raise ValueError(f"unknown country {code}")
    deals, events = list(deals), list(events)
    q = f"Private markets, deals and risk in {c.name}"
    parsed, items = retrieve(q, deals, events, live_news=live_news, news=news)
    risk = cr.assess(c, fx=lambda _: None)
    cur = mr.currency_risk(c.currency, fx=lambda _: None)
    cdeals = deals_mod.search(deals, country=c.iso2, limit=500)
    top_inv = inv.leaderboard(cdeals, limit=8)
    md = [f"# {c.name}: private markets and risk\n",
          f"Region: {c.region}. Currency: {c.currency} ({cur['regime']}). Exchange: {c.exchange or 'none'}. "
          f"Central bank: {c.central_bank}. Securities regulator: {c.securities_regulator or 'n/a'}.\n"]
    summary = answer(f"Summarise the investment environment in {c.name}: deal activity, investors, and risks.",
                     items, parsed, llm)
    md.append(_section("Executive summary", [summary["answer"]]))
    md.append(_section("Country risk", [f"Score **{risk['score']}** ({risk['tier']}), data coverage {risk['coverage']:.0%}."]
                       + [f"- {x['name'].replace('_', ' ')}: {x['risk']} (weight {x['weight']}; {x['formula']})"
                          for x in risk["components"]]))
    md.append(_section("Currency", [f"Regime: {cur['regime']} ({cur['regime_note']}). Last-year depreciation vs USD: "
                                    f"{cur['last_year_depreciation_pct']}%; five-year annualised: "
                                    f"{cur['five_year_annualised_depreciation_pct']}%. Score {cur['score']} ({cur['tier']})."]))
    by_type = Counter(d["deal_type"] for d in cdeals)
    md.append(_section("Deal activity", [f"{len(cdeals)} deals recorded; disclosed value "
                                         f"{_fmt_usd(sum(d.get('amount_usd') or 0 for d in cdeals))}; by type {dict(by_type)}."]
                       + [f"- {d.get('announced')}: {d.get('headline')}" for d in cdeals[:15]]))
    md.append(_section("Most active investors", [f"- {r['name']}: {r['deal_count']} deals, roles {r['roles']}" for r in top_inv]))
    md.append(_section("Sources", [f"[{i['n']}] {i['title']} {i.get('url') or ''}" for i in items]))
    return {"title": f"{c.name}: private markets and risk", "markdown": "\n".join(md), "evidence": items,
            "summary": summary, "country_risk": risk, "currency_risk": cur}


def sector_report(sector: str, deals: Iterable[dict] = (), events: Iterable[dict] = (), country: Optional[str] = None,
                  llm: Optional[Callable] = None, live_news: bool = True, news=None) -> dict:
    deals, events = list(deals), list(events)
    where = get_country(country).name if country and get_country(country) else "Africa"
    q = f"{sector.replace('_', ' ')} deals and risk in {where}"
    parsed, items = retrieve(q, deals, events, live_news=live_news, news=news)
    srisk = mr.sector_risk(sector, events, deals, country=country)
    sdeals = deals_mod.search(deals, sector=sector, country=country, limit=500)
    comps = deals_mod.comparables(sdeals, sector=sector, country=country, deal_type="equity_funding")
    summary = answer(f"Summarise {sector.replace('_', ' ')} activity in {where}: deals, investors, valuations and risks.",
                     items, parsed, llm)
    md = [f"# {sector.replace('_', ' ').title()} in {where}\n",
          _section("Executive summary", [summary["answer"]]),
          _section("Sector risk", [f"Score **{srisk['score']}** ({srisk['tier']}) from {srisk['adverse_events']} adverse "
                                   f"events, {srisk['other_events']} other events and {srisk['deals']} deals in "
                                   f"{srisk['window_days']} days" + (" (low sample)" if srisk["low_sample"] else "") + "."]),
          _section("Deals", [f"- {d.get('announced')}: {d.get('headline')}" for d in sdeals[:20]]),
          _section("Funding round sizes", [f"{comps['size_usd']}" if comps["size_usd"] else ""]),
          _section("Most active investors", [f"- {r['name']}: {r['deal_count']} deals" for r in inv.leaderboard(sdeals, limit=8)]),
          _section("Sources", [f"[{i['n']}] {i['title']} {i.get('url') or ''}" for i in items])]
    return {"title": f"{sector} in {where}", "markdown": "\n".join(md), "evidence": items, "summary": summary,
            "sector_risk": srisk}
