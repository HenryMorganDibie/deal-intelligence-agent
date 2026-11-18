"""Company facts read on the spot, while the user waits: no queue and no scheduled job.

A profile without stored governance asks for it once. The company's own site is read in-process (the home page and
its about, leadership, governance and investor pages, fetched together; robots.txt is not consulted), and its newest annual
report is found there or, failing that, by one licensed web search (Tavily) restricted to the company's own domain or
an exchange's document library. The report is read like an exchange filing (src/engines/governance: every fact on
the page it cites) and the result is stored, so later views are instant.

Budgets keep the whole read inside a request: pages 8 s each and 10 s in all, the search 10 s, the report 40 MB and
30 s, then the governance passes (10-30 s, run together).
"""

from __future__ import annotations

import html as _html
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

import httpx

from src import company_web
from src.engines import governance

log = logging.getLogger(__name__)

MAX_PAGES = 12
PAGE_TIMEOUT = 8
CRAWL_BUDGET = 10
REPORT_TIMEOUT = 30
MAX_REPORT_BYTES = company_web.MAX_REPORT_BYTES
# Exchanges' document libraries: a report found there is the company's filing even though the domain is not its own.
EXCHANGE_DOCS = ("doclib.ngxgroup.com", "ngxgroup.com", "nse.co.ke", "jse.co.za", "senjse.co.za", "brvm.org",
                 "gse.com.gh", "use.or.ug", "dse.co.tz", "rse.rw", "luse.co.zm", "zse.co.zw", "bse.co.bw", "nsx.com.na",
                 "sem.mu", "casablanca-bourse.com", "egx.com.eg")


# The reader identifies itself as this product, with its address, and checks robots.txt under the same name. Some
# sites' firewalls refuse generic crawler names; an honest product agent is not a browser disguise.
AGENT = "DealIntelligence"
USER_AGENT = "Mozilla/5.0 (compatible; DealIntelligence/1.0; +https://deal-intelligence.app)"


def _ua() -> str:
    return USER_AGENT


class _Page(HTMLParser):
    """Text, title and links of an HTML page, scripts, styles and navigation left out."""

    # Only non-text elements: some sites wrap the whole page in <header> or <nav>; menus are removed afterwards by
    # company_web.strip_shared, which drops what most pages repeat.
    SKIP = {"script", "style", "noscript", "svg", "template"}

    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base, self.links, self.parts, self.title = base, [], [], ""
        self._skip, self._in_title = 0, False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            href = dict(attrs).get("href")
            if href and not href.startswith(("mailto:", "tel:", "javascript:", "#")):
                self.links.append(urljoin(self.base, href.strip()))
        if tag in ("p", "div", "li", "br", "h1", "h2", "h3", "h4", "tr", "td", "section"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", _html.unescape("".join(self.parts)))).strip()


class _Robots:
    """Whether a page may be fetched. robots.txt is not consulted, by the owner's decision (as for news articles and
    round investors); this class stays the one place to change that."""

    def __init__(self, client: httpx.Client):
        self.client = client

    def allowed(self, url: str) -> bool:
        return True


def _fetch_page(client: httpx.Client, robots: _Robots, url: str, depth: int) -> Optional[dict]:
    if not robots.allowed(url):
        return None
    try:
        r = client.get(url, timeout=PAGE_TIMEOUT)
    except httpx.HTTPError:
        return None
    if r.status_code != 200 or "html" not in r.headers.get("content-type", "html"):
        return None
    page = _Page(str(r.url))
    try:
        page.feed(r.text[:2_000_000])
    except Exception:
        return None
    return {"url": url, "final_url": str(r.url), "status_code": 200, "title": page.title.strip()[:200],
            "text": page.text()[:20000], "links": page.links, "depth": depth}


def _same_site(a: str, b: str) -> bool:
    ha, hb = (urlparse(a).hostname or "").removeprefix("www."), (urlparse(b).hostname or "").removeprefix("www.")
    return bool(ha) and (ha == hb or ha.endswith("." + hb) or hb.endswith("." + ha))


def crawl(start: str, client: Optional[httpx.Client] = None) -> list[dict]:
    """The company's home page and the pages it links to that hold company facts (about, leadership, governance,
    investors, reports), fetched together within the crawl budget."""
    own = client is None
    client = client or httpx.Client(headers={"User-Agent": _ua()}, follow_redirects=True)
    try:
        robots = _Robots(client)
        home = _fetch_page(client, robots, start, 0)
        if not home:
            return []
        include = [re.compile(p) for p in company_web.INCLUDE]
        exclude = [re.compile(p) for p in company_web.EXCLUDE]
        seen, picks = {home["final_url"].rstrip("/")}, []
        for link in home["links"]:
            u = link.split("#")[0]
            path = urlparse(u).path.lower()
            if (not u.startswith("http") or u.rstrip("/") in seen or not _same_site(u, home["final_url"])
                    or path.endswith((".pdf", ".jpg", ".png", ".zip", ".docx", ".xlsx"))
                    or any(x.search(u) for x in exclude) or not any(i.search(u) for i in include)):
                continue
            seen.add(u.rstrip("/"))
            picks.append(u)
        picks.sort(key=lambda u: 0 if company_web._RANK.search(u) else 1)
        picks = picks[:MAX_PAGES - 1]
        deadline = time.monotonic() + CRAWL_BUDGET
        pages = [home]
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(_fetch_page, client, robots, u, 1) for u in picks]
            for f in futures:
                left = deadline - time.monotonic()
                try:
                    p = f.result(timeout=max(0.1, left))
                except Exception:
                    p = None
                if p:
                    pages.append(p)
        return pages
    finally:
        if own:
            client.close()


def _year(u: str) -> int:
    years = [int(y) for y in re.findall(r"(?<!\d)(20[0-3]\d)(?!\d)", u)]
    return max(years) if years else 0


def search_report(name: str, country_name: Optional[str] = None) -> Optional[str]:
    """The company's newest annual or integrated report PDF from one web search: on a domain carrying the company's
    name, or in an exchange's document library. None when no result qualifies or no key is set."""
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key:
        return None
    query = f"{name} annual report pdf" + (f" {country_name}" if country_name else "")
    try:
        r = httpx.post(company_web.TAVILY, headers={"Authorization": f"Bearer {key}"}, timeout=10,
                       json={"query": query, "max_results": 8, "search_depth": "basic"})
        rows = r.json().get("results", []) if r.status_code == 200 else []
    except (httpx.HTTPError, ValueError) as e:
        log.warning("company live: report search failed for %s: %s", name, e)
        return None
    found = []
    for row in rows:
        url = str(row.get("url") or "")
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        path = urlparse(url).path.lower()
        title = str(row.get("title") or "")
        if not url.startswith("https://") or ".pdf" not in path:
            continue
        if re.search(r"(?i)summar|abridged|notice|proxy|agm|presentation|interim|quarter|half[- ]year|unaudited",
                     path + " " + title):
            continue
        if not (company_web._REPORT.search(path) or company_web._REPORT.search(title)
                or re.search(r"(?i)financial[\W_]*statements?|rapport[\W_]*annuel", path + " " + title)):
            continue
        if not (company_web._name_in_domain(name, host) or any(host == d or host.endswith("." + d) for d in EXCHANGE_DOCS)):
            continue
        found.append(url)
    return max(found, key=lambda u: (_year(u), -found.index(u))) if found else None


def public_pages(name: str, country_name: Optional[str] = None) -> list[dict]:
    """Search results about the company (its profile, then its leadership), as pages the site reader can read: each
    result's text with its own address, so every fact keeps the source it was read from. Used when the company's own
    site refuses automated readers. Two searches (two credits); none without a key."""
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key:
        return []
    where = f" {country_name}" if country_name else ""
    queries = (f"{name}{where} company profile founded headquarters founders",
               f"{name}{where} chief executive leadership team board of directors")

    def one(q: str) -> list[dict]:
        try:
            r = httpx.post(company_web.TAVILY, headers={"Authorization": f"Bearer {key}"}, timeout=10,
                           json={"query": q, "max_results": 6, "search_depth": "basic"})
            return r.json().get("results", []) if r.status_code == 200 else []
        except (httpx.HTTPError, ValueError) as e:
            log.warning("company live: public search failed for %s: %s", name, e)
            return []
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = [row for batch in pool.map(one, queries) for row in batch]
    pages, seen = [], set()
    this_year = int(time.strftime("%Y"))
    for row in rows:
        url, text = str(row.get("url") or ""), " ".join(str(row.get("content") or "").split())
        if not url.startswith("https://") or len(text) < 80 or url in seen:
            continue
        # An old document (a year in its address more than a year back) can name people who have since left.
        years = [int(y) for y in re.findall(r"(?<!\d)(20[0-3]\d)(?!\d)", url)]
        if years and max(years) < this_year - 1:
            continue
        seen.add(url)
        pages.append({"url": url, "final_url": url, "status_code": 200, "title": str(row.get("title") or "")[:200],
                      "text": text[:6000], "links": [], "depth": 1})
    return pages[:10]


def _download(url: str, client: httpx.Client) -> Optional[bytes]:
    deadline = time.monotonic() + REPORT_TIMEOUT
    try:
        with client.stream("GET", url, timeout=PAGE_TIMEOUT * 2) as r:
            if r.status_code != 200:
                return None
            data = bytearray()
            for chunk in r.iter_bytes():
                data += chunk
                if len(data) > MAX_REPORT_BYTES or time.monotonic() > deadline:
                    log.info("company live: report too large or slow, stopped: %s", url)
                    return None
            return bytes(data) if data[:4] == b"%PDF" else None
    except httpx.HTTPError as e:
        log.warning("company live: report %s could not be fetched: %s", url, e)
        return None


def _archived(site: str) -> list[dict]:
    """The site's own pages from the Common Crawl archive (robots.txt not consulted, as for the live site)."""
    from src import company_archive
    return company_archive.archived_pages(site, None)


def read_now(name: str, website: Optional[str] = None, country_name: Optional[str] = None,
             call: Optional[Callable[[str, str], str]] = None) -> dict:
    """Read the company now: {"website", "facts" (site facts), "report" (governance from its annual report),
    "report_url", "timings"}. Any part that cannot be found is absent; nothing is queued."""
    t0 = time.monotonic()
    out: dict = {"timings": {}}
    site = (company_web.normalise_site(website) or company_web.wikidata_website(name)
            or company_web.search_website(name, country_name))
    with httpx.Client(headers={"User-Agent": _ua()}, follow_redirects=True) as client:
        pages = crawl(site, client) if site else []
        out["timings"]["site"] = round(time.monotonic() - t0, 1)
        if site:
            out["website"] = site
        report_url = company_web.find_report(pages) if pages else None
        if not report_url:
            report_url = search_report(name, country_name)
            out["timings"]["search"] = round(time.monotonic() - t0, 1)
        # No site known: the report's own domain, when it carries the company's name, is its site.
        if not pages and report_url:
            host = urlparse(report_url).hostname or ""
            if company_web._name_in_domain(name, host):
                site = company_web.normalise_site(f"https://{host}/")
                pages = crawl(site, client)
                out["website"] = site
                out["timings"]["site"] = round(time.monotonic() - t0, 1)
        robots = _Robots(client)

        def site_facts():
            facts = company_web.read_site({"name": name, "website": site}, pages, call) if pages else None
            if facts:
                return facts
            # The site refused us (a bot challenge) or holds nothing readable. Its own pages from the public web
            # archive come first, searched at the same time as public sources, so a slow or
            # unavailable archive costs no extra time.
            with ThreadPoolExecutor(max_workers=2) as both:
                f_archive = both.submit(_archived, site) if site else None
                f_public = both.submit(public_pages, name, country_name)
                archived = f_archive.result() if f_archive else []
                public = f_public.result()
            if archived:
                facts = company_web.read_site({"name": name, "website": site}, archived, call)
                if facts:
                    facts["origin"] = "web_archive"
                    facts["archived_at"] = max(p.get("archived_at") or "" for p in archived) or None
                    return facts
            facts = company_web.read_site({"name": name, "website": site}, public, call) if public else None
            if facts:
                facts["origin"] = "public_sources"
                for key in ("board", "management"):     # one entry per person across sources
                    if facts.get(key):
                        facts[key] = governance.dedupe_board(facts[key])
            return facts

        def report():
            if not (report_url and robots.allowed(report_url)):
                return None, None
            data = _download(report_url, client)
            out["timings"]["download"] = round(time.monotonic() - t0, 1)
            if not data:
                return None, None
            doc = urlparse(report_url).path.rsplit("/", 1)[-1]
            label = ("Annual statements filed with the exchange" if any(
                (urlparse(report_url).hostname or "").endswith(d) for d in EXCHANGE_DOCS)
                else "Annual report published on the company's website")
            gov = governance.extract(data, name, doc, report_url, None, call, source_label=label)
            if gov:
                return gov, None
            return None, report_url if governance.is_scanned(governance.page_texts(data, max_pages=12)) else None

        # The website and the report are read at the same time: the read takes as long as the slower of the two.
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_site, f_report = pool.submit(site_facts), pool.submit(report)
            facts = f_site.result()
            gov, scanned = f_report.result()
        if facts:
            out["facts"] = facts
        if gov:
            out["report"], out["report_url"] = gov, report_url
        if scanned:
            out["report_scanned"] = scanned
    out["timings"]["total"] = round(time.monotonic() - t0, 1)
    return out


def store(name: str, result: dict) -> bool:
    """Keep what was read with the company's stored facts (an earlier read of the same report is merged, so a
    weaker read loses nothing), so the next view shows it without reading again."""
    from src import hosted_market as hm
    key = company_web.name_key(name)
    if not hm._configured() or len(key) < 2:
        return False
    try:
        r = hm._rpc_sync("company_web_get", {"p_name_key": key}, 10)
        row = r.json() if r.status_code == 200 else None
        if not row:
            hm._rpc_sync("company_web_request", {"p_name_key": key, "p_name": name,
                                                 "p_website": result.get("website")}, 10)
            row = {"facts": {}}
        facts = dict(row.get("facts") or {})
        if result.get("facts"):
            facts.update(result["facts"])
        if result.get("report"):
            facts["report"] = governance.merge_reads(result["report"], facts.get("report"))
        if result.get("website"):
            facts["website"] = result["website"]
        facts["read_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        hm._rpc_sync("company_web_save", {"p_name_key": key, "p_status": "done", "p_facts": facts, "p_error": None}, 15)
        return True
    except Exception as e:                       # the result is still shown; it is read again next time
        log.warning("company live: %s not stored: %s", name, e)
        return False
