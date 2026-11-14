"""
Company websites, read with web-harvester (github.com/HenryMorganDibie/web-harvester).

When someone looks a company up and its website is known (from the exchange profile, Yahoo Finance or the filed
statements), the site is queued. The hourly job builds a crawl config: from the home page, only the pages whose
address says what they hold (about, leadership, board, governance, subsidiaries, contact, investors), at most 12 per
site, robots.txt respected and one page every two seconds per site. The crawled pages are read by the cached language
model into fields and kept only where they can be found on the page they cite (src/engines/governance.verify), then
stored for the profile. A site is read again at most every 30 days.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Callable, Optional
from urllib.parse import urlparse

from src.engines import deals as deals_mod
from src.engines import governance

log = logging.getLogger(__name__)

PAGES_PER_SITE = 16
SEARCHES_PER_RUN = 1                    # Tavily's free tier is 1,000 credits a month; hourly runs, one each, stay inside
SITES_PER_RUN = 15
INCLUDE = [r"(?i)/(about|about-us|who-we-are|our-company|company|corporate|profile|overview|history|leadership|"
           r"management|team|executive|board|directors|governance|subsidiar|group|structure|businesses|our-businesses|"
           r"brands|portfolio|operations|investor|contact|annual-report|integrated-report|reports|results|financial)"
           r"(?:[/?#._-]|$)"]
EXCLUDE = [r"(?i)/(careers?|jobs|news|blog|press|media|events|login|signin|cart|shop|privacy|terms|cookie)",
           r"(?i)\.(pdf|jpe?g|png|zip)$", r"(?i)[?&](utm_|page=|lang=)"]
_RANK = re.compile(r"(?i)board|director|governance|leadership|management|executive|subsidiar|group|structure|about|"
                   r"who-we-are|contact|investor")
_PAGE_CHARS = 2500
_MAX_CHARS = 18000

SYSTEM = ("You read pages from a company's own website and return facts about the company as JSON. Copy every name, "
          "title and figure exactly as written on the page. Never infer or complete a value; leave out anything the "
          "pages do not state. Each item must give the page number it was read from (the [p N] tag).")
USER = """Pages from the website of {company}:

{pages}

Return one JSON object (omit a key, or use an empty list, when the pages do not state it):
"registered_office": head office or registered address as written, with "office_page";
"phone": main phone number as written, with "phone_page"; "email": general contact email, with "email_page";
"founded": year founded or incorporated as written, with "founded_page";
"board": [{{"name", "role", "page"}}] for members of the board of directors;
"management": [{{"name", "role", "page"}}] for executives and senior management;
"subsidiaries": [{{"name", "country" if stated, "percent" (ownership, as written) if stated, "page"}}] for companies
it owns or controls, as the site names them.
Return only the JSON object."""


def name_key(name: str) -> str:
    return (deals_mod.normalise_name(name) or re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip())[:120]


def normalise_site(url: Optional[str]) -> Optional[str]:
    """A company website as an https home page URL, or None when it is not a plain web address."""
    u = (url or "").strip()
    if not u:
        return None
    if not re.match(r"(?i)https?://", u):
        u = "https://" + u
    p = urlparse(u)
    host = (p.hostname or "").lower()
    if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", host) or host.endswith(("facebook.com", "linkedin.com", "twitter.com",
                                                                           "x.com", "instagram.com", "wikipedia.org")):
        return None
    return f"https://{host}/"


# ── A website for a company no listing names one for: Wikidata ─────────────

WIKIDATA = "https://www.wikidata.org/w/api.php"
_WD_AGENT = "deal-intelligence/1.0 (https://deal-intelligence.app)"
# Wikidata items that are kinds of company: business, enterprise, public company, company, bank, conglomerate,
# subsidiary, holding company, state-owned enterprise, startup.
_COMPANY_KINDS = {"Q4830453", "Q6881511", "Q891723", "Q783794", "Q22687", "Q778575", "Q658255", "Q219577", "Q270791",
                  "Q1058914", "Q18388277", "Q166280"}


def _wikidata(params: dict) -> dict:
    import urllib.parse
    import urllib.request
    req = urllib.request.Request(f"{WIKIDATA}?{urllib.parse.urlencode({**params, 'format': 'json'})}",
                                 headers={"User-Agent": _WD_AGENT})
    with urllib.request.urlopen(req, timeout=10) as r:            # nosec: fixed Wikidata API address
        return json.loads(r.read())


def wikidata_website(name: str, country: Optional[str] = None) -> Optional[str]:
    """The official website Wikidata records for the company: a company item whose name matches ours (and whose
    country does, when we know it). None when there is no confident match."""
    try:
        found = _wikidata({"action": "wbsearchentities", "search": name, "language": "en", "type": "item", "limit": 5})
        ids = [x["id"] for x in found.get("search", [])]
        if not ids:
            return None
        ents = _wikidata({"action": "wbgetentities", "ids": "|".join(ids), "props": "claims|labels|aliases",
                          "languages": "en"}).get("entities", {})
    except Exception as e:
        log.info("wikidata lookup failed for %s: %s", name, e)
        return None
    want = name_key(name)

    def values(e: dict, prop: str) -> list:
        return [c["mainsnak"].get("datavalue", {}).get("value") for c in e.get("claims", {}).get(prop, [])]
    for qid in ids:
        e = ents.get(qid) or {}
        names = [e.get("labels", {}).get("en", {}).get("value", "")] + [a.get("value", "") for a in e.get("aliases", {}).get("en", [])]
        if want not in {name_key(n) for n in names if n}:
            continue
        kinds = {v.get("id") for v in values(e, "P31") if isinstance(v, dict)}
        if not kinds & _COMPANY_KINDS:
            continue
        if country and not _country_matches(values(e, "P17"), country):
            continue
        sites = [v for v in values(e, "P856") if isinstance(v, str)]
        site = normalise_site(sites[0]) if sites else None
        if site:
            return site
    return None


def _country_matches(claims: list, country: str) -> bool:
    """The item's country (P17) is ours: its ISO code (P297) against our two-letter code."""
    ids = [v.get("id") for v in claims if isinstance(v, dict) and v.get("id")]
    if not ids:
        return True                     # no country recorded: the name and kind decide
    try:
        ents = _wikidata({"action": "wbgetentities", "ids": "|".join(ids[:3]), "props": "claims"}).get("entities", {})
    except Exception:
        return False
    for e in ents.values():
        for c in e.get("claims", {}).get("P297", []):
            if str(c["mainsnak"].get("datavalue", {}).get("value", "")).upper() == country.upper():
                return True
    return False


# ── A website by web search, in the scheduled job: Tavily ──────────────────

TAVILY = "https://api.tavily.com/search"
_NOT_COMPANY_SITES = re.compile(
    r"(?i)(linkedin|facebook|twitter|x\.com|instagram|youtube|wikipedia|wikidata|crunchbase|bloomberg|reuters|"
    r"zoominfo|dnb\.com|opencorporates|glassdoor|indeed|pitchbook|cbinsights|tracxn|ft\.com|forbes|techcabal|"
    r"techcrunch|businessday|nairametrics|punchng|guardian|vanguardngr|thisdaylive|premiumtimesng|allafrica|"
    r"african|ngxgroup|nse\.co\.ke|jse\.co\.za|marketscreener|investing\.com|yahoo|google|apple\.com|play\.google)")


def _name_in_domain(name: str, host: str) -> bool:
    """The site's domain carries the company's name: a distinctive word of it, or its initials."""
    label = host.lower().removeprefix("www.").split(".")[0].replace("-", "")
    words = [w for w in name_key(name).split() if len(w) >= 4]
    initials = "".join(w[0] for w in name_key(name).split() if w)
    # Initials count when they are three letters or more, or two on a short domain (gtco.com for Guaranty Trust).
    return any(w in label for w in words) or (len(initials) >= 3 and label.startswith(initials)) or \
        (len(initials) == 2 and len(label) <= 5 and label.startswith(initials))


def search_website(name: str, country_name: Optional[str] = None) -> Optional[str]:
    """The company's own website from a web search: the first result whose domain carries its name and is not a
    news site, social network, directory or exchange. None when no result qualifies."""
    import httpx
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key:
        return None
    query = f"{name} official website" + (f" {country_name}" if country_name else "")
    try:
        r = httpx.post(TAVILY, headers={"Authorization": f"Bearer {key}"}, timeout=20,
                       json={"query": query, "max_results": 6, "search_depth": "basic"})
        results = r.json().get("results", []) if r.status_code == 200 else []
    except (httpx.HTTPError, ValueError) as e:
        log.warning("company web: search failed for %s: %s", name, e)
        return None
    for res in results:
        host = urlparse(str(res.get("url") or "")).hostname or ""
        if host and not _NOT_COMPANY_SITES.search(host) and _name_in_domain(name, host):
            return normalise_site(f"https://{host}/")
    return None


# ── Queue and storage (the API's shared-secret database functions) ─────────

def request(name: str, website: Optional[str], country: Optional[str] = None,
            filing_url: Optional[str] = None) -> Optional[dict]:
    """Queue the company's site for the next crawl (if due) and return what is stored for it. With no website from
    a listing, the one Wikidata records is used (and remembered with the queued site)."""
    from src import hosted_market as hm
    key = name_key(name)
    if not hm._configured() or len(key) < 2:
        return None
    site = normalise_site(website)
    if not site and not filing_url:
        try:
            stored = hm._rpc_sync("company_web_get", {"p_name_key": key}, 10)
            if stored.status_code == 200 and stored.json():
                return stored.json()                     # already known (and queued or read)
        except Exception as e:
            log.warning("company web lookup failed for %s: %s", name, e)
            return None
        site = wikidata_website(name, country)
    if not site and filing_url:
        site = wikidata_website(name, country)
    try:
        if site or filing_url or os.environ.get("COMPANY_WEB_SEARCH", "1") != "0":
            # With no website at all the company is still queued: the scheduled job looks for its site.
            args = {"p_name_key": key, "p_name": name, "p_website": site}
            if filing_url:
                args["p_filing_url"] = filing_url
            hm._rpc_sync("company_web_request", args, 10)
        r = hm._rpc_sync("company_web_get", {"p_name_key": key}, 10)
        return r.json() if r.status_code == 200 else None
    except Exception as e:                      # the profile never fails because of the website queue
        log.warning("company web lookup failed for %s: %s", name, e)
        return None


def crawl_config(output_path: str, limit: int = SITES_PER_RUN) -> tuple[dict, list[dict]]:
    """A web-harvester crawl config for the queued sites, and the companies it covers."""
    from src import hosted_market as hm
    from src.engines.election_news import USER_AGENT
    r = hm._rpc_sync("company_web_take", {"p_limit": limit}, 15)
    companies = r.json() if r.status_code == 200 and isinstance(r.json(), list) else []
    searches = 0
    for c in companies:                 # no website known: look for the official one (licensed search API)
        if not c.get("website") and searches < SEARCHES_PER_RUN and os.environ.get("TAVILY_API_KEY"):
            searches += 1
            found = search_website(c["name"])
            if found:
                c["website"], c["website_source"] = found, "Tavily web search"
    cfg = {
        "user_agent": USER_AGENT, "robots_agent": "web-harvester",
        "concurrency": 3, "max_retries": 0, "request_timeout": "15s",
        "rate_per_host_rps": 0.5, "rate_burst": 1, "adaptive_rate": True,
        "sink_backend": "jsonl", "output_path": output_path, "report_interval": "30s",
        "targets": [target(dict(c, website=resolve(c["website"]))) for c in companies if c.get("website")],
    }
    return cfg, companies


def resolve(site: str) -> str:
    """Where the home page ends up after redirects (a company's www address often moves to another host), so the
    crawl follows links on the host that serves the pages. The original address if it cannot be reached."""
    import httpx
    from src.engines.election_news import USER_AGENT
    try:
        r = httpx.get(site, headers={"User-Agent": USER_AGENT}, timeout=15, follow_redirects=True)
        final = normalise_site(str(r.url)) if r.status_code < 400 else None
        return final or site
    except httpx.HTTPError:
        return site


def target(company: dict) -> dict:
    return {"name": company["name_key"], "start_urls": [company["website"]], "max_depth": 1,
            "max_pages": PAGES_PER_SITE, "include": INCLUDE, "exclude": EXCLUDE,
            "extract": {"text_limit": 20000},             # links kept: annual report PDFs are found among them
            # A page that is an empty JavaScript shell is rendered in headless Chromium (when the job installed it).
            **({"render": "auto"} if os.environ.get("HARVESTER_RENDER") == "auto" else {})}


# ── Reading the crawled pages ──────────────────────────────────────────────

def _choose(pages: list[dict]) -> list[dict]:
    """The pages most likely to hold the facts (board and leadership pages before the home page), readable ones only."""
    ok = [p for p in pages if p.get("status_code") == 200 and (p.get("text") or "").strip()]
    ok.sort(key=lambda p: (0 if _RANK.search((p.get("final_url") or p.get("url") or "") + " " + (p.get("title") or ""))
                           else 1, p.get("depth", 0)))
    return ok[:8]


def _page_text(p: dict) -> str:
    text = " ".join((p.get("text") or "").split())
    for block in p.get("json_ld") or []:            # schema.org Organization data often holds the address
        try:
            data = block if isinstance(block, dict) else json.loads(block)
        except (TypeError, ValueError):
            continue
        if isinstance(data, dict) and data.get("address"):
            addr = data["address"]
            if isinstance(addr, dict):
                addr = ", ".join(str(v) for k, v in addr.items() if not k.startswith("@") and v)
            text += f" Address: {addr}"
    return text


_SHINGLE = 12


def strip_shared(texts: list[str]) -> list[str]:
    """Each page's text without what most of the site's pages share (menus, footers): any run of 12 words found on
    more than half of the pages is dropped, so the page's own content is what gets read."""
    if len(texts) < 3:
        return texts
    tokens = [t.split() for t in texts]
    seen: dict[tuple, int] = {}
    for toks in tokens:
        for w in {tuple(toks[i:i + _SHINGLE]) for i in range(max(0, len(toks) - _SHINGLE + 1))}:
            seen[w] = seen.get(w, 0) + 1
    shared = {w for w, n in seen.items() if n > len(texts) / 2}
    out = []
    for toks in tokens:
        drop = [False] * len(toks)
        for i in range(max(0, len(toks) - _SHINGLE + 1)):
            if tuple(toks[i:i + _SHINGLE]) in shared:
                drop[i:i + _SHINGLE] = [True] * _SHINGLE
        out.append(" ".join(t for t, d in zip(toks, drop) if not d))
    return out


def read_site(company: dict, pages: list[dict], call: Optional[Callable[[str, str], str]] = None) -> Optional[dict]:
    """The facts confirmed on the company's crawled pages, each with the page it is on; None when nothing could be."""
    ok = [p for p in pages if p.get("status_code") == 200 and (p.get("text") or "").strip()]
    own = dict(zip((id(p) for p in ok), strip_shared([_page_text(p) for p in ok])))
    chosen = _choose(ok)
    if not chosen:
        return None
    texts = [own[id(p)] for p in chosen]
    blocks, used = [], []
    for i, t in enumerate(texts):
        block = f"[p {i + 1}] {chosen[i].get('final_url') or chosen[i].get('url')}\n{t[:_PAGE_CHARS]}\n"
        if sum(len(b) for b in blocks) + len(block) > _MAX_CHARS:
            continue
        blocks.append(block)
        used.append(i + 1)
    call = call or governance._default_call()
    if call is None:
        return None
    try:
        raw = governance._json(call(SYSTEM, USER.format(company=company["name"], pages="\n".join(blocks))))
    except Exception as e:
        log.warning("company web: reading %s failed: %s", company.get("website"), e)
        return None
    facts = governance.verify({k: raw.get(k) for k in ("registered_office", "office_page", "board", "subsidiaries")},
                              texts, used)
    management = governance.verify({"board": raw.get("management")}, texts, used).get("board")
    if management:
        facts["management"] = management
    for key, page_key, pattern in (("phone", "phone_page", None), ("email", "email_page", None),
                                   ("founded", "founded_page", r"(1[89]\d\d|20[0-2]\d)")):
        v, n = raw.get(key), raw.get(page_key)
        if not isinstance(v, str) or n not in used:
            continue
        page = texts[n - 1]
        if key == "phone":
            digits = re.sub(r"\D", "", v)
            if 7 <= len(digits) <= 15 and digits in re.sub(r"\D", "", page):
                facts["phone"], facts["phone_page"] = v.strip(), n
        elif key == "email":
            if re.fullmatch(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", v.strip()) and v.strip().lower() in page.lower():
                facts["email"], facts["email_page"] = v.strip(), n
        elif re.fullmatch(pattern, v.strip()) and re.search(rf"\b{v.strip()}\b", page):
            facts["founded"], facts["founded_page"] = v.strip(), n
    if not facts:
        return None
    facts["pages"] = [{"n": i + 1, "url": chosen[i].get("final_url") or chosen[i].get("url"),
                       "title": (chosen[i].get("title") or "")[:120]} for i in range(len(chosen)) if i + 1 in used]
    return facts


def apply_crawl(companies: list[dict], pages: list[dict], call: Optional[Callable[[str, str], str]] = None) -> dict:
    """Read each crawled site and store its facts (or the failure)."""
    from src import hosted_market as hm
    by_target: dict[str, list[dict]] = {}
    for p in pages:
        by_target.setdefault(p.get("target"), []).append(p)
    out = {"sites": len(companies), "with_facts": 0, "pages": len(pages)}
    for c in companies:
        site_pages = by_target.get(c["name_key"], [])
        facts = read_site(c, site_pages, call) if site_pages else None
        report = read_report(c, site_pages, call) if site_pages else None
        if report:
            facts = {**(facts or {}), "report": report}
        filing = read_filing(c, call) if c.get("filing_url") else None
        if filing:
            facts = {**(facts or {}), "filing": filing}
        if c.get("website_source") and c.get("website"):
            facts = {**(facts or {}), "website": c["website"], "website_source": c["website_source"]}
        ok = bool(site_pages) or bool(filing) or (not c.get("website") and bool(c.get("filing_url")))
        if not c.get("website") and not c.get("filing_url"):
            ok, site_pages = True, site_pages            # nothing to read yet: done until the next request
        status = "done" if ok else "failed"
        error = (None if ok else "no pages fetched (robots.txt, timeout or no matching pages)") if c.get("website") or \
            c.get("filing_url") else "no website found"
        hm._rpc_sync("company_web_save", {"p_name_key": c["name_key"], "p_status": status,
                                          "p_facts": facts or {}, "p_error": error}, 15)
        out["with_facts"] += bool(facts)
        out.setdefault("detail", []).append({
            "company": c["name_key"], "pages": len(site_pages), "report_url": find_report(site_pages) if site_pages else None,
            "facts": sorted(k for k in (facts or {}) if k not in ("pages", "report", "filing")),
            "report_facts": sorted(k for k in (report or {}) if isinstance((report or {}).get(k), (list, str)) and k not in
                                   ("source", "source_url", "method")),
            "filing_facts": sorted(k for k in (filing or {}) if isinstance((filing or {}).get(k), (list, str)))})
    return out


# ── The annual report the site publishes ───────────────────────────────────

_REPORT = re.compile(r"(?i)(annual|integrated)[\W_]*(report|financial[\W_]*statements?|results)")
MAX_REPORT_BYTES = 40 * 1024 * 1024


def find_report(pages: list[dict]) -> Optional[str]:
    """The newest annual or integrated report PDF linked from the crawled pages (the latest year in its address)."""
    links = {u for p in pages for u in (p.get("links") or []) if isinstance(u, str)}
    reports = [u for u in links if urlparse(u).path.lower().endswith(".pdf") and _REPORT.search(urlparse(u).path)
               and not re.search(r"(?i)summar|abridged|notice|proxy|agm|presentation", urlparse(u).path)]
    if not reports:
        return None

    def year(u: str) -> int:
        years = [int(y) for y in re.findall(r"(?<!\d)(20[0-3]\d)(?!\d)", u)]
        return max(years) if years else 0
    return max(reports, key=lambda u: (year(u), u))


def _robots_allow(url: str) -> bool:
    """The site's robots.txt allows web-harvester to fetch this address (as the crawler checks for pages)."""
    import httpx
    from urllib import robotparser
    from src.engines.election_news import USER_AGENT
    p = urlparse(url)
    rp = robotparser.RobotFileParser()
    try:
        r = httpx.get(f"{p.scheme}://{p.netloc}/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=15,
                      follow_redirects=True)
    except httpx.HTTPError:
        return False                    # unreachable robots.txt: assume not allowed, as the crawler does
    if r.status_code >= 500:
        return False
    if r.status_code >= 400:
        return True                     # no robots.txt: everything allowed
    rp.parse(r.text.splitlines())
    return rp.can_fetch("web-harvester", url)


def read_report(company: dict, pages: list[dict], call: Optional[Callable[[str, str], str]] = None) -> Optional[dict]:
    """Board, committees, shareholders, subsidiaries and corporate details from the annual report the company's own
    site links to, robots.txt permitting; each fact on the page it cites."""
    import httpx
    from src.engines.election_news import USER_AGENT
    url = find_report(pages)
    if not url or not _robots_allow(url):
        return None
    try:
        with httpx.stream("GET", url, headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True) as r:
            if r.status_code != 200:
                return None
            data = b""
            for chunk in r.iter_bytes():
                data += chunk
                if len(data) > MAX_REPORT_BYTES:
                    log.info("company web: report too large, skipped: %s", url)
                    return None
    except httpx.HTTPError as e:
        log.warning("company web: report %s could not be fetched: %s", url, e)
        return None
    name = urlparse(url).path.rsplit("/", 1)[-1]
    return governance.extract(data, company["name"], name, url, None, call,
                              source_label="Annual report published on the company's website", allow_ocr=True)


def read_filing(company: dict, call: Optional[Callable[[str, str], str]] = None) -> Optional[dict]:
    """The company's filed annual statements when they are a scan: read by OCR here, where Tesseract is installed."""
    from src.engines import financials as fin
    url = company["filing_url"]
    try:
        data = fin.pdf_bytes(url)
    except Exception as e:
        log.warning("company web: filing %s could not be fetched: %s", url, e)
        return None
    name = urlparse(url).path.rsplit("/", 1)[-1]
    return governance.extract(data, company["name"], name, url, None, call, allow_ocr=True)
