"""
Ground-truth events outside SEC EDGAR.

SEC filings confirm events for US companies. Everywhere else, events are taken
from:
  * official exchange disclosures: NGX (by symbol or name) and NSE Kenya,
  * credible publishers (credibility >= 0.70) reporting a completed event about
    the company: "completes acquisition", "appoints new CEO", "placed in
    business rescue", "fined by", ... in English or French.

Only completion language counts, never speculation ("talks", "considers",
"could"), and the company must be the subject (named before the event phrase).
Signal types the sources cannot evidence stay unknown, never "refuted".
"""
from __future__ import annotations

import html
import logging
import re
import time
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import quote

import httpx

from src.schemas.models import SignalType

log = logging.getLogger(__name__)

NGX_DISCLOSURES = "https://doclib.ngxgroup.com/_api/Web/Lists/GetByTitle('XFinancial_News')/items"
NSE_KENYA_MEDIA = "https://www.nse.co.ke/wp-json/wp/v2/media"
GOOGLE_NEWS = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{lang}"

MIN_NEWS_CREDIBILITY = 0.70

_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

# Completed events only. Matched case-insensitively against a headline or a
# disclosure title (underscores read as spaces).
CONFIRMATION_PATTERNS: dict[SignalType, list[str]] = {
    SignalType.MA_ACTIVITY: [
        r"\b(complet(es|ed|ion\s+of)|clos(es|ed)|finali[sz](es|ed))\b.{0,40}\b(acquisition|merger|takeover|purchase|sale|disposal)\b",
        r"\b(acquisition|merger|takeover|scheme\s+of\s+arrangement)\b.{0,30}\b(completed|closed|effective|sanctioned|approved\s+by\s+(the\s+)?(court|shareholders))\b",
        r"\b(finalise|finalis[eé]e?|a\s+finalis[eé]|conclut|a\s+conclu)\b.{0,40}\b(acquisition|fusion|cession|rachat)\b",
        r"\b(fusion|acquisition|rachat)\b.{0,30}\b(finalis[eé]e?|effective|approuv[eé]e)\b",
    ],
    SignalType.LEADERSHIP_CHANGE: [
        r"\b(appoints?|appointed|names|named|confirms)\b.{0,40}\b(ceo|cfo|chief\s+executive|chief\s+financial|managing\s+director|md|chairman|chairperson|president)\b",
        r"\b(resignation|retirement|exit|departure)\s+of\b.{0,40}\b(ceo|cfo|managing\s+director|md|chairman|director)\b",
        r"\b(ceo|cfo|chief|chief\s+executive|managing\s+director|chairman|president|head)\b.{0,30}\b(resigns|resigned|steps\s+down|stepped\s+down|retires|exits|departs|ousted|fired|replaced)\b",
        r"\bnew\s+(ceo|cfo|chief\s+executive|managing\s+director|chairman)\b.{0,40}\b(takes|took|starts|started|begins|named|appointed|takes\s+the\s+helm|takes\s+over)\b",
        r"\b(takes\s+the\s+helm|takes\s+over\s+as\s+(ceo|chief\s+executive|chairman|md))\b",
        r"\b(nomm[eé]e?|nomination|d[eé]mission|d[eé]part)\b.{0,40}\b(directeur\s+g[eé]n[eé]ral|directrice\s+g[eé]n[eé]rale|pdg|pr[eé]sident|dg)\b",
    ],
    SignalType.DISTRESSED_ASSET: [
        r"\b(placed|enters?|entered|files?|filed)\b.{0,30}\b(business\s+rescue|administration|liquidation|receivership|bankruptcy|chapter\s+11|insolvency)\b",
        r"\b(suspended|delisted|suspension\s+of\s+trading)\b",
        r"\b(plac[eé]e?\s+en|ouverture\s+d['’]une)\b.{0,30}\b(redressement|liquidation)\s+judiciaire\b",
    ],
    SignalType.CREDIT_RISK: [
        r"\b(downgrad(es|ed)|cuts?)\b.{0,40}\b(rating|outlook)\b",
        r"\b(defaults?|defaulted|missed)\b.{0,30}\b(payment|coupon|bond|loan|obligation)\b",
        r"\b(d[eé]grad[eé]e?|abaisse)\b.{0,30}\bnotation\b",
        r"\bd[eé]faut\s+de\s+paiement\b",
    ],
    SignalType.DEBT_RESTRUCTURE: [
        r"\b(creditors?|bondholders?|lenders?)\b.{0,30}\b(approve|approved|agree|agreed|sign|signed)\b.{0,30}\b(restructur\w*|extension|standstill)\b",
        r"\b(completes?|completed|concludes?|concluded|signs?|signed)\b.{0,30}\b(debt\s+restructur\w*|refinancing|restructuring\s+agreement)\b",
        r"\baccord\s+de\s+restructuration\b",
    ],
    SignalType.REGULATORY_ACTION: [
        r"\b(fined|sanctioned|penali[sz]ed|charged|licen[cs]e\s+(revoked|suspended))\b",
        r"\b(fine|penalty|sanction)\s+(of|on|against)\b",
        r"\b(sanctionn[eé]e?|amende|retrait\s+d['’]agr[eé]ment)\b",
    ],
    SignalType.INSIDER_ACTIVITY: [
        r"\b(director|insider)s?\s*dealings?\b",
        r"\b(acquires?|acquired|buys|bought|sells|sold)\b.{0,30}\b(stake|shares)\b",
        r"\bfranchissement\s+de\s+seuil\b",
    ],
    SignalType.EARNINGS_SURPRISE: [
        r"\bprofit\s+warning\b",
        r"\b(restates|restated|restatement\s+of)\b",
        r"\b(beats?|misses|missed|tops|topped)\b.{0,30}\b(estimates|expectations|forecasts?|consensus)\b",
        r"\bavertissement\s+sur\s+(les\s+)?r[eé]sultats\b",
    ],
}
_COMPILED = {t: [re.compile(p, re.IGNORECASE) for p in ps] for t, ps in CONFIRMATION_PATTERNS.items()}
_SPECULATIVE = re.compile(
    r"\b(talks?|considers?|considering|weighs?|weighing|explores?|exploring|could|may|might|plans?|planning|"
    r"eyes|eyeing|rumou?rs?|reportedly|proposed|potential|bid\s+for|envisage|pourrait|envisagerait)\b",
    re.IGNORECASE,
)
# NGX submission types that are the event itself.
NGX_TYPE_EVENTS = {"directorsdealings": {SignalType.INSIDER_ACTIVITY}}


def classify(text: str, matchers: Optional[list[re.Pattern]] = None) -> set[SignalType]:
    """Signal types whose completed event the text reports (about the company, if matchers given)."""
    text = " ".join(html.unescape(text or "").replace("_", " ").split())
    if not text or _SPECULATIVE.search(text):
        return set()
    mention = None
    if matchers:
        starts = [m.start() for p in matchers for m in [p.search(text)] if m]
        if not starts:
            return set()
        mention = min(starts)
    found = set()
    for sig_type, patterns in _COMPILED.items():
        for p in patterns:
            m = p.search(text)
            if m and (mention is None or mention <= m.start() + 5):
                found.add(sig_type)
                break
    return found


def _event(day: str, source: str, types: set[SignalType]) -> dict:
    return {"date": day[:10], "form": "", "items": set(), "source": source, "signal_types": {t.value for t in types}}


def ngx_events(client: httpx.Client, symbol: Optional[str], company: str, since: date, until: date) -> Optional[list[dict]]:
    """Events in NGX disclosures; None when the exchange could not be read."""
    code = symbol.upper().rsplit(".", 1)[0] if symbol else None
    who = (f"CompanySymbol eq '{code}'" if code
           else f"substringof('{company.replace(chr(39), chr(39) * 2).upper()}',CompanyName)")
    params = {
        "$select": "CompanySymbol,Type_of_Submission,Modified,URL",
        "$filter": f"{who} and Modified ge datetime'{since.isoformat()}T00:00:00Z' and Modified le datetime'{until.isoformat()}T23:59:59Z'",
        "$orderby": "Modified asc", "$top": "500",
    }
    try:
        r = client.get(NGX_DISCLOSURES, params=params, headers={"Accept": "application/json;odata=verbose"})
        r.raise_for_status()
        rows = r.json().get("d", {}).get("results", [])
    except Exception as e:
        log.warning("NGX disclosures unavailable for %s: %s", company, e)
        return None
    out = []
    for row in rows:
        url = (row.get("URL") or {}).get("Url", "")
        title = re.sub(r"^\d+_", "", url.rsplit("/", 1)[-1].rsplit(".", 1)[0])
        kind = (row.get("Type_of_Submission") or "").replace(" ", "").lower()
        types = classify(title) | NGX_TYPE_EVENTS.get(kind, set())
        if types:
            out.append(_event(row.get("Modified", ""), f"NGX disclosure: {title.replace('_', ' ')[:90]}", types))
    return out


def nse_events(client: httpx.Client, company: str, since: date, until: date) -> Optional[list[dict]]:
    params = {"search": company, "after": f"{since.isoformat()}T00:00:00", "before": f"{until.isoformat()}T23:59:59",
              "per_page": "100", "_fields": "date,title,mime_type"}
    try:
        r = client.get(NSE_KENYA_MEDIA, params=params)
        r.raise_for_status()
        rows = r.json()
    except Exception as e:
        log.warning("NSE Kenya documents unavailable for %s: %s", company, e)
        return None
    out = []
    for row in rows if isinstance(rows, list) else []:
        title = html.unescape((row.get("title") or {}).get("rendered", ""))
        types = classify(title)
        if types:
            out.append(_event(row.get("date", ""), f"NSE Kenya disclosure: {title[:90]}", types))
    return out


def news_events(
    client: httpx.Client, company: str, since: date, until: date, french: bool = False,
) -> Optional[list[dict]]:
    """
    Completed events about the company in credible outlets, from Google News
    restricted to [since, until]. None if the search returned nothing at all
    (no coverage: unknown, not 'no event').
    """
    from src.engines.deterministic_engine import _company_matchers, _source_credibility
    matchers = _company_matchers(company)
    window = f"after:{since.isoformat()} before:{until.isoformat()}"
    # A broad query returns at most 100 items, which one big story can fill, so
    # each event family also gets its own query.
    topics = ["", "CEO OR chairman OR appoints OR resigns", "acquisition OR merger OR completes OR takeover",
              "downgrade OR default OR restructuring OR administration", "fined OR penalty OR sanctioned OR regulator"]
    queries = [(f'"{company}" {t} {window}'.replace("  ", " "), ("en-US", "US", "en")) for t in topics]
    if french:
        queries += [(f'"{company}" {t} {window}'.replace("  ", " "), ("fr", "CI", "fr"))
                    for t in ("", "nomme OR démission OR acquisition OR fusion OR sanction")]
    items, seen = [], set()
    for q, (hl, gl, lang) in queries:
        try:
            r = client.get(GOOGLE_NEWS.format(q=quote(q), hl=hl, gl=gl, lang=lang))
            r.raise_for_status()
            for it in re.findall(r"<item>(.*?)</item>", r.text, re.S):
                key = (re.search(r"<title>(.*?)</title>", it, re.S) or [None, it])[1]
                if key not in seen:
                    seen.add(key)
                    items.append(it)
        except Exception as e:
            log.warning("news search failed for %s: %s", company, e)
        time.sleep(0.4)
    if not items:
        return None
    out = []
    for it in items:
        title = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(r"<title>(.*?)</title>", it, re.S) or [None, ""])[1]))
        publisher = html.unescape((re.search(r"<source[^>]*>(.*?)</source>", it, re.S) or [None, ""])[1])
        pub = (re.search(r"<pubDate>(.*?)</pubDate>", it) or [None, ""])[1]
        if not publisher or _source_credibility(publisher) < MIN_NEWS_CREDIBILITY:
            continue
        headline = title.rsplit(" - ", 1)[0] if publisher and title.endswith(publisher) else title
        try:
            day = parsedate_to_datetime(pub).date()
        except (TypeError, ValueError):
            continue
        if not (since <= day <= until):
            continue
        types = classify(headline, matchers)
        if types:
            out.append(_event(day.isoformat(), f"{publisher}: {headline[:90]}", types))
    return out


def collect_events(
    company: str, ticker: Optional[str], market: str, since: date, until: date,
    client: Optional[httpx.Client] = None,
) -> Optional[list[dict]]:
    """
    Non-SEC ground truth for one company over [since, until]: exchange
    disclosures for NGX / NSE Kenya listings, credible news for every company
    (listed or private). None when no source could be read.
    """
    own = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=True, headers=_HEADERS)
    try:
        results: list[Optional[list[dict]]] = []
        t = (ticker or "").upper()
        if t.endswith(".LG"):
            results.append(ngx_events(client, t, company, since, until))
        if t.endswith(".NR"):
            results.append(nse_events(client, company, since, until))
        french = t.endswith((".BV", ".CS", ".TN")) or market == "africa"
        results.append(news_events(client, company, since, until, french=french))
        got = [r for r in results if r is not None]
        return [e for r in got for e in r] if got else None
    finally:
        if own:
            client.close()
