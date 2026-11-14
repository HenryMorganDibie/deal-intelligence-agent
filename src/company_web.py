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
import re
from typing import Callable, Optional
from urllib.parse import urlparse

from src.engines import deals as deals_mod
from src.engines import governance

log = logging.getLogger(__name__)

PAGES_PER_SITE = 12
SITES_PER_RUN = 15
INCLUDE = [r"(?i)/(about|about-us|who-we-are|our-company|company|corporate|profile|overview|history|leadership|"
           r"management|team|executive|board|directors|governance|subsidiar|group|structure|businesses|our-businesses|"
           r"brands|portfolio|operations|investor|contact)(?:[/?#._-]|$)"]
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


# ── Queue and storage (the API's shared-secret database functions) ─────────

def request(name: str, website: Optional[str]) -> Optional[dict]:
    """Queue the company's site for the next crawl (if due) and return what is stored for it."""
    from src import hosted_market as hm
    site = normalise_site(website)
    key = name_key(name)
    if not hm._configured() or len(key) < 2:
        return None
    try:
        if site:
            hm._rpc_sync("company_web_request", {"p_name_key": key, "p_name": name, "p_website": site}, 10)
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
    cfg = {
        "user_agent": USER_AGENT, "robots_agent": "web-harvester",
        "concurrency": 3, "max_retries": 0, "request_timeout": "15s",
        "rate_per_host_rps": 0.5, "rate_burst": 1, "adaptive_rate": True,
        "sink_backend": "jsonl", "output_path": output_path, "report_interval": "30s",
        "targets": [target(dict(c, website=resolve(c["website"]))) for c in companies],
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
            "extract": {"skip_links": True, "text_limit": 20000}}


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
        status = "done" if site_pages else "failed"
        error = None if site_pages else "no pages fetched (robots.txt, timeout or no matching pages)"
        hm._rpc_sync("company_web_save", {"p_name_key": c["name_key"], "p_status": status,
                                          "p_facts": facts or {}, "p_error": error}, 15)
        out["with_facts"] += bool(facts)
    return out
