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
import threading
import os
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
        r"\b(conclui|concluiu|concluída|finaliza|finalizou)\b.{0,40}\b(aquisi[cç][aã]o|fus[aã]o|compra|venda)\b",
        r"(إتمام|اتمام|استكمال|أتمت|اتمت|أكملت)\s+.{0,30}(استحواذ|اندماج|صفقة)",
        r"\b(complet(es|ed|ion\s+of)|clos(es|ed)|finali[sz](es|ed))\b.{0,40}\b(acquisition|merger|takeover|purchase|sale|disposal)\b",
        r"\b(acquisition|merger|takeover|scheme\s+of\s+arrangement)\b.{0,30}\b(completed|closed|effective|sanctioned|approved\s+by\s+(the\s+)?(court|shareholders))\b",
        r"\b(finalise|finalis[eé]e?|a\s+finalis[eé]|conclut|a\s+conclu)\b.{0,40}\b(acquisition|fusion|cession|rachat)\b",
        r"\b(fusion|acquisition|rachat)\b.{0,30}\b(finalis[eé]e?|effective|approuv[eé]e)\b",
        # Milestones of a live deal: definitive agreement, shareholder and regulatory approval.
        r"\b(signs?|signed|enters?\s+into|entered\s+into)\s+(a\s+)?definitive\s+(merger\s+)?agreement\b",
        r"\bshareholders?\s+(approve[sd]?|back(s|ed)?|vote\s+(for|in\s+favou?r\s+of))\b.{0,40}\b(merger|acquisition|takeover|scheme|deal|sale)\b",
        r"\b(approves?|approved|clears?|cleared|green[-\s]?lights?)\b.{0,40}\b(merger|acquisition|takeover|deal)\b",
        r"\b(merger|acquisition|takeover|deal)\b.{0,30}\b(wins?|receives?|gets?|secures?)\s+(regulatory\s+|antitrust\s+|competition\s+|shareholder\s+)?(approval|clearance)\b",
    ],
    SignalType.LEADERSHIP_CHANGE: [
        r"\b(nomeia|nomeou|nomeado|nomeada|renuncia|renunciou|demite|demitiu)\b.{0,40}\b(presidente|ceo|director[a]?\s+geral|administrador)\b",
        r"(تعيين|استقالة|إقالة|اقالة)\s+.{0,30}(رئيس\s+(ال)?تنفيذي|عضو\s+(ال)?منتدب|رئيس\s+مجلس)",
        r"\b(appoints?|appointed|names|named|confirms)\b.{0,40}\b(ceo|cfo|chief\s+executive|chief\s+financial|managing\s+director|md|chairman|chairperson|president)\b",
        r"\b(resignation|retirement|exit|departure)\s+of\b.{0,40}\b(ceo|cfo|managing\s+director|md|chairman|director)\b",
        r"\b(ceo|cfo|chief|chief\s+executive|managing\s+director|chairman|president|head)\b.{0,30}\b(resigns|resigned|steps\s+down|stepped\s+down|retires|exits|departs|ousted|fired|replaced)\b",
        r"\bnew\s+(ceo|cfo|chief\s+executive|managing\s+director|chairman)\b.{0,40}\b(takes|took|starts|started|begins|named|appointed|takes\s+the\s+helm|takes\s+over)\b",
        r"\b(takes\s+the\s+helm|takes\s+over\s+as\s+(ceo|chief\s+executive|chairman|md))\b",
        r"\b(nomm[eé]e?|nomination|d[eé]mission|d[eé]part)\b.{0,40}\b(directeur\s+g[eé]n[eé]ral|directrice\s+g[eé]n[eé]rale|pdg|pr[eé]sident|dg)\b",
    ],
    SignalType.DISTRESSED_ASSET: [
        r"\b(fal[eê]ncia|insolv[eê]ncia|recupera[cç][aã]o\s+judicial)\b.{0,20}\b(decretada|declarada|pedido|requer)\b",
        r"(إشهار\s+(ال)?إفلاس|تصفية|شطب\s+(ال)?سهم|إيقاف\s+(ال)?تداول)",
        r"\b(placed|enters?|entered|files?|filed)\b.{0,30}\b(business\s+rescue|administration|liquidation|receivership|bankruptcy|chapter\s+11|insolvency)\b",
        r"\b(suspended|delisted|suspension\s+of\s+trading)\b",
        r"\b(plac[eé]e?\s+en|ouverture\s+d['’]une)\b.{0,30}\b(redressement|liquidation)\s+judiciaire\b",
    ],
    SignalType.CREDIT_RISK: [
        r"\b(rebaixa|rebaixou|corta|cortou)\b.{0,30}\b(rating|nota[cç][aã]o)\b",
        r"(خفض|تخفيض|خفضت)\s+.{0,20}(ال)?تصنيف",
        r"\b(downgrad(es|ed)|cuts?)\b.{0,40}\b(rating|outlook)\b",
        r"\b(defaults?|defaulted|missed)\b.{0,30}\b(payment|coupon|bond|loan|obligation)\b",
        r"\b(d[eé]grad[eé]e?|abaisse)\b.{0,30}\bnotation\b",
        r"\bd[eé]faut\s+de\s+paiement\b",
    ],
    SignalType.DEBT_RESTRUCTURE: [
        r"\b(acordo|conclui|concluiu)\b.{0,30}\breestrutura[cç][aã]o\s+(da|de)\s+d[ií]vida\b",
        r"(اتفاق|توقيع)\s+.{0,20}(إعادة|اعادة)\s+(ال)?هيكلة\s+(ال)?(ديون|مديونية)",
        r"\b(creditors?|bondholders?|lenders?)\b.{0,30}\b(approve|approved|agree|agreed|sign|signed)\b.{0,30}\b(restructur\w*|extension|standstill)\b",
        r"\b(completes?|completed|concludes?|concluded|signs?|signed)\b.{0,30}\b(debt\s+restructur\w*|refinancing|restructuring\s+agreement)\b",
        r"\baccord\s+de\s+restructuration\b",
    ],
    SignalType.REGULATORY_ACTION: [
        r"\b(multad[oa]|multa\s+de|sancionad[oa])\b",
        r"(فرض|فرضت|توقيع)\s+(ال)?(غرامة|عقوبة)",
        r"\b(fined|sanctioned|penali[sz]ed|charged|licen[cs]e\s+(revoked|suspended))\b",
        r"\b(pleads?|pleaded|pled|agrees?\s+to\s+plead)\s+guilty\b|\bguilty\s+plea\b",
        r"\b(settles?|settled|agrees?\s+to\s+pay)\b.{0,50}\b(sec|doj|ftc|regulator|authorit\w+|commission|charges?|fine|penalty|probe)\b",
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
    r"eyes|eyeing|rumou?rs?|reportedly|proposed|potential|bid\s+for|envisage|pourrait|envisagerait|"
    r"negocia|negociações|poderá|pondera|estuda)\b"
    r"|(مفاوضات|تدرس|تعتزم|قد\s|محتمل|تخطط)",
    re.IGNORECASE,
)
_CLAUSE_BOUNDARY = re.compile(
    r"(?<=[.!?;])\s+|(?:,\s*|\s+)(?P<connector>but|however|while|although|whereas|yet)(?:,\s*|\s+)",
    re.IGNORECASE,
)
_COORDINATED_EVENT_START = re.compile(
    r"^\s*(?:also\s+|then\s+)?"
    r"(?:appoint\w*|name\w*|confirm\w*|resign\w*|retir\w*|step\w*|"
    r"complet\w*|clos\w*|finali[sz]\w*|acquir\w*|merg\w*|"
    r"fin\w*|sanction\w*|downgrad\w*|default\w*|"
    r"conclu\w*|finalis\w*|nomm\w*|renonc\w*|mult\w*)\b",
    re.IGNORECASE,
)
# NGX submission types that are the event itself.
NGX_TYPE_EVENTS = {"directorsdealings": {SignalType.INSIDER_ACTIVITY}}


def classify(text: str, matchers: Optional[list[re.Pattern]] = None) -> set[SignalType]:
    """Signal types whose completed event the text reports (about the company, if matchers given)."""
    text = " ".join(html.unescape(text or "").replace("_", " ").split())
    if not text:
        return set()
    found = set()
    clauses: list[tuple[int, str, Optional[str]]] = []
    start = 0
    connector = None
    for boundary in _CLAUSE_BOUNDARY.finditer(text):
        clauses.append((start, text[start:boundary.start()], connector))
        start = boundary.end()
        connector = boundary.group("connector")
    clauses.append((start, text[start:], connector))
    previous_target_led = False
    for offset, clause, preceding_connector in clauses:
        if _SPECULATIVE.search(clause):
            local_starts = (
                [m.start() for pattern in matchers for m in [pattern.search(clause)] if m]
                if matchers else []
            )
            previous_target_led = False
            if local_starts:
                prefix = clause[:min(local_starts)].strip()
                previous_target_led = not prefix or bool(re.fullmatch(
                    r"(?i)(shares?|stocks?)\s+(of|in)", prefix
                ))
            continue
        mention = None
        target_led = False
        if matchers:
            starts = [m.start() for pattern in matchers for m in [pattern.search(clause)] if m]
            if starts:
                mention = min(starts)
                prefix = clause[:mention].strip()
                target_led = not prefix or bool(re.fullmatch(
                    r"(?i)(shares?|stocks?)\s+(of|in)", prefix
                ))
            elif (
                preceding_connector in {"but", "however", "yet"}
                and previous_target_led
                and _COORDINATED_EVENT_START.search(clause)
            ):
                mention = 0
            else:
                previous_target_led = False
                continue
        for sig_type, patterns in _COMPILED.items():
            if any(
                (match := pattern.search(clause))
                and (mention is None or mention <= match.start() + 5)
                for pattern in patterns
            ):
                found.add(sig_type)
        previous_target_led = target_led
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


NEWS_TOPICS = ["",
               "CEO OR chairman OR appoints OR resigns OR acquisition OR merger OR completes OR takeover",
               "downgrade OR default OR restructuring OR administration OR fined OR penalty OR sanctioned OR regulator"]
FRENCH_TOPICS = ["", "nomme OR démission OR acquisition OR fusion OR sanction"]
ARABIC_TOPICS = ["", "استحواذ OR استقالة OR تعيين OR غرامة OR هيكلة"]
PORTUGUESE_TOPICS = ["", "aquisição OR fusão OR renuncia OR nomeado OR multa"]


class NewsUnavailable(RuntimeError):
    """A news window could not be fetched completely (throttled or failing after retries)."""


# Google News throttles bursts. Every search goes through one shared pace (all threads), and a 429 or
# 5xx pauses every thread for a growing cool-down instead of hammering on.
_NEWS_LOCK = threading.Lock()
_NEWS_STATE = {"next": 0.0, "cooldown_until": 0.0, "strikes": 0}
NEWS_MIN_INTERVAL = float(os.environ.get("DEAL_INTEL_NEWS_INTERVAL", "0.3"))


def _news_pace() -> None:
    while True:
        with _NEWS_LOCK:
            now = time.monotonic()
            wait = max(_NEWS_STATE["cooldown_until"], _NEWS_STATE["next"]) - now
            if wait <= 0:
                _NEWS_STATE["next"] = now + NEWS_MIN_INTERVAL
                return
        time.sleep(min(wait, 5))


def _news_throttled() -> None:
    with _NEWS_LOCK:
        _NEWS_STATE["strikes"] = min(_NEWS_STATE["strikes"] + 1, 6)
        pause = 15 * 2 ** (_NEWS_STATE["strikes"] - 1)            # 15 s, 30 s, ... up to 8 minutes
        _NEWS_STATE["cooldown_until"] = max(_NEWS_STATE["cooldown_until"], time.monotonic() + pause)
    log.info("news throttled: pausing all searches for %ss", pause)


def _news_ok() -> None:
    with _NEWS_LOCK:
        _NEWS_STATE["strikes"] = max(_NEWS_STATE["strikes"] - 1, 0)


def _news_get(client: httpx.Client, url: str, attempts: int = 6) -> Optional[httpx.Response]:
    """One search with retries: throttling and server errors wait out a shared cool-down."""
    for _ in range(attempts):
        _news_pace()
        try:
            r = client.get(url)
        except httpx.HTTPError:
            # A dropped connection (a proxy or tunnel closing) is not throttling: retry at once on a
            # fresh connection rather than pausing every thread.
            time.sleep(1)
            continue
        if r.status_code == 200:
            _news_ok()
            return r
        if r.status_code in (429, 500, 502, 503, 504) or r.status_code == 404:
            _news_throttled()                  # Google answers some throttled searches with 404
            continue
        return None
    return None


def historical_news(
    client: httpx.Client, company: str, since: date, until: date, french: bool = False,
    arabic: bool = False, portuguese: bool = False, strict: bool = False,
    ticker: Optional[str] = None,
) -> Optional[list[dict]]:
    """
    Dated headlines about the company published in [since, until], from Google
    News date-restricted searches: [{title, publisher, date, url}]. A broad query
    returns at most 100 items, which one big story can fill, so each event family
    also gets its own query. None if every search failed.
    """
    window = f"after:{since.isoformat()} before:{until.isoformat()}"
    queries = [(f'"{company}" {t} {window}'.replace("  ", " "), ("en-US", "US", "en")) for t in NEWS_TOPICS]
    if french:
        queries += [(f'"{company}" {t} {window}'.replace("  ", " "), ("fr", "CI", "fr")) for t in FRENCH_TOPICS]
    if arabic:
        queries += [(f'"{company}" {t} {window}'.replace("  ", " "), ("ar", "EG", "ar")) for t in ARABIC_TOPICS]
    if portuguese:
        queries += [(f'"{company}" {t} {window}'.replace("  ", " "), ("pt-PT", "PT", "pt-150")) for t in PORTUGUESE_TOPICS]
    ticker_base = (ticker or "").upper().split(".", 1)[0]
    if len(ticker_base) >= 3:
        editions = [("en-US", "US", "en")]
        if french:
            editions.append(("fr", "CI", "fr"))
        if arabic:
            editions.append(("ar", "EG", "ar"))
        if portuguese:
            editions.append(("pt-PT", "PT", "pt-150"))
        queries.extend(
            (f'"{ticker_base}" {window}', edition)
            for edition in editions
        )
    out, seen, ok = [], set(), False
    for q, (hl, gl, lang) in queries:
        r = _news_get(client, GOOGLE_NEWS.format(q=quote(q), hl=hl, gl=gl, lang=lang))
        if r is None:
            log.warning("news search failed for %s after retries: %s", company, q[:80])
            if strict:                         # never return (and so never cache) a partial window
                raise NewsUnavailable(f"{company}: {q[:80]}")
            continue
        ok = True
        for it in re.findall(r"<item>(.*?)</item>", r.text, re.S):
            title = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(r"<title>(.*?)</title>", it, re.S) or [None, ""])[1]))
            if not title or title in seen:
                continue
            seen.add(title)
            publisher = html.unescape((re.search(r"<source[^>]*>(.*?)</source>", it, re.S) or [None, ""])[1])
            try:
                day = parsedate_to_datetime((re.search(r"<pubDate>(.*?)</pubDate>", it) or [None, ""])[1]).date()
            except (TypeError, ValueError):
                continue
            if not (since <= day <= until):
                continue
            if publisher and title.endswith(" - " + publisher):
                title = title[: -len(publisher) - 3]
            out.append({"title": title, "publisher": publisher, "date": day.isoformat(),
                        "url": (re.search(r"<link>(.*?)</link>", it) or [None, ""])[1]})
    return out if ok else None


def news_events(
    client: httpx.Client, company: str, since: date, until: date, french: bool = False,
    headlines: Optional[list[dict]] = None,
    ticker: Optional[str] = None,
) -> Optional[list[dict]]:
    """
    Completed events about the company in credible outlets (credibility >= 0.70)
    between since and until. None if the search returned nothing at all (no
    coverage: unknown, not 'no event').
    """
    from src.engines.deterministic_engine import _company_matchers, _source_credibility
    items = headlines if headlines is not None else historical_news(client, company, since, until, french, ticker=ticker)
    if not items:
        return None
    matchers = _company_matchers(company, ticker=ticker)
    out = []
    for it in items:
        if _source_credibility(it["publisher"]) < MIN_NEWS_CREDIBILITY:
            continue
        types = classify(it["title"], matchers)
        if types:
            out.append(_event(it["date"], f"{it['publisher']}: {it['title'][:90]}", types))
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
        items = historical_news(client, company, since, until, french=french,
                                arabic=t.endswith(".CA"), portuguese=t.endswith((".MZ", ".AO")), ticker=t)
        results.append(news_events(client, company, since, until, headlines=items, ticker=t) if items is not None else None)
        got = [r for r in results if r is not None]
        return [e for r in got for e in r] if got else None
    finally:
        if own:
            client.close()
