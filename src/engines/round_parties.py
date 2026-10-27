"""Investors in a funding round, read from the article rather than the headline.

A headline names one investor at best ("X raises $5m"); the article usually names the lead and the
participants ("led by A, with participation from B and C"). This module resolves a deal's news link to
the publisher's article, reads its text, and extracts the round's investors sentence by sentence. Every
investor it credits keeps the sentence that names it, so each attribution can be checked.

Sentences about other rounds ("previously raised", "in 2022 it raised") are skipped, so earlier backers
are not credited to this round. Names pass through the investor registry's cleaning, which drops places,
amounts and descriptions.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
from datetime import date
from typing import Optional

import httpx

from src.engines import investors as inv

log = logging.getLogger(__name__)

_BROWSER = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}

# Where a list of names ends: punctuation, or a word that starts another clause.
_LIST_END = (r"(?=[.;:!?()\[\]]|,?\s+(?:to|in|at|for|which|who|that|as|bringing|taking|valuing|according|"
             r"after|while|following|this|its|their|with|alongside|joined|backed|plus)\b|$)")
_NAMES = r"(?:the\s+)?(?P<names>[A-Z0-9][^.;:!?]{1,240}?)"
# "a manufacturer led by its founder" names management, not a round's lead investor.
_LEAD = [re.compile(r"(?<!manufacturer )(?<!company )(?<!firm )(?<!startup )(?<!business )(?<!platform )(?<!group )"
                    r"(?<!operator )(?<!developer )(?<!maker )(?<!producer )(?<!provider )(?<!team )(?<!bank )"
                    r"\b(?:co-)?led\s+by\s+" + _NAMES + _LIST_END),
         re.compile(_NAMES + r"\s+(?:led|co-led|spearheaded|anchored)\s+the\s+(?:round|raise|investment|funding|deal)\b")]
_PARTICIPANT = [
    re.compile(r"\b(?:with\s+)?(?:participation|participating)\s+(?:from|of|by)\s+" + _NAMES + _LIST_END),
    re.compile(r"\balongside\s+(?:existing\s+|new\s+)?(?:investors?\s+)?" + _NAMES + _LIST_END),
    re.compile(r"\b(?:also\s+)?(?:joined|backed)\s+by\s+(?:existing\s+|new\s+)?(?:investors?\s+)?" + _NAMES + _LIST_END),
    re.compile(r"\binvestors?\s+(?:including|include|included|such\s+as|like)\s+" + _NAMES + _LIST_END),
    re.compile(_NAMES + r"\s+(?:also\s+)?(?:participated|joined\s+the\s+round|took\s+part)\b"),
    re.compile(r"\b(?:raised|raises|raising|secured|secures|closed|closes|bagged|lands|landed)\s+(?:a\s+|an\s+)?"
               r"(?:\S+\s+){0,6}?(?:US\$|\$|€|£|₦|N|R|KSh|USD)\s?[\d.,]+\s*(?:million|billion|m|bn|k)?\s+"
               r"(?:\S+\s+){0,4}?from\s+(?:investors?\s+(?:including|such\s+as)\s+)?" + _NAMES + _LIST_END),
]
_ROUND_WORDS = re.compile(r"(?i)\b(round|raise[ds]?|raising|funding|investment|financing|seed|series|backers?|"
                          r"investors?|capital|secured|closes?|closed)\b")
_OTHER_ROUND = re.compile(r"(?i)\b(previously|previous|earlier|prior|past|last\s+year|last\s+round|had\s+raised|"
                          r"has\s+raised\s+a\s+total|to\s+date|in\s+total|since\s+(?:its\s+)?(?:launch|founding|inception)|"
                          r"portfolio\s+includes?|follows?\s+an?\b|following\s+an?\b|comes?\s+(?:\S+\s+){0,4}after|"
                          r"after\s+(?:raising|securing|closing)|in\s+which|its\s+seed\s+round|first\s+round)\b")
_STAGE = re.compile(r"(?i)\b(pre-seed|seed|pre-series\s+[a-f]|series\s+[a-f]|bridge|growth|extension)(?:\s+(?:round|funding|extension))?\b")
_NOT_A_NAME = {"however", "also", "meanwhile", "additionally", "moreover", "this", "these", "it", "they", "we",
               "the", "a", "an", "its", "their", "series", "seed", "round", "funding", "investors", "investor", "existing",
               "new", "other", "others", "several", "various", "local", "global", "international", "angel", "angels",
               "ceo", "founder", "founders", "co-founder", "management", "the company", "the startup", "both"}
MAX_NAMES_PER_SENTENCE = 10
# Lowercase role words, or a capitalised title after another word ("Mono CEOs X"); a capitalised first word is
# part of a name ("Founders Factory Africa").
_PERSON_OR_ROLE = re.compile(
    r"^(?:.*?\b(?:angel\s+investors?|investors?|backers?|actors?|actress(?:es)?|musicians?|footballers?|founders?|"
    r"co-founders?|chief\s+executives?|executives?|entrepreneurs?|including|such\s+as|like)|\S+.*?\b(?:CEOs?|CTOs?|"
    r"COOs?|CFOs?|Founders?|Co-founders?))\s+(?=[A-Z0-9])")
_ORG_WORD = re.compile(r"(?i)\b(?:bank|fund|capital|ventures?|partners|group|holdings?|investments?|corporation|"
                       r"company|foundation|trust|authority|agency|council|ministry|institute|association)\b")
_ROLE_ONLY = re.compile(r"(?i)\b(?:CEO|CTO|COO|CFO|founder|co-founder|chairman|chairperson|director|partner)s?$")


def resolve_google_news(url: str, client: httpx.Client) -> Optional[str]:
    """The publisher URL behind a news.google.com article link, or None."""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host != "news.google.com":
        return url
    gid = urllib.parse.urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    try:
        page = client.get(f"https://news.google.com/rss/articles/{gid}", headers=_BROWSER)
        sig = re.search(r'data-n-a-sg="([^"]+)"', page.text)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page.text)
        if not (sig and ts):
            return None
        inner = ["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None,
                                 0, 1], "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
                 gid, int(ts.group(1)), sig.group(1)]
        r = client.post("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                        data={"f.req": json.dumps([[["Fbv4je", json.dumps(inner), None, "generic"]]])},
                        headers={**_BROWSER, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
        data = json.loads(r.text.split("\n\n", 1)[-1])
        resolved = json.loads(data[0][2])[1]
        return resolved if isinstance(resolved, str) and resolved.startswith("https://") else None
    except Exception as e:                                  # layout changed, throttled: no article this time
        log.info("could not resolve %s: %s", url[:80], e)
        return None


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"“])|\n+", text or "") if 20 <= len(s.strip()) <= 600]


def _names(fragment: str, target: str) -> list[str]:
    target_key = inv.normalise_name(target or "")
    out = []
    for part in re.split(r",\s*(?:and\s+)?|\s+and\s+|\s+as\s+well\s+as\s+", fragment):
        part = re.sub(r"^(?:the\s+)?(?:existing\s+|new\s+|returning\s+)?(?:investors?\s+|backers?\s+)?", "", part.strip(), flags=re.I)
        # Descriptions before a name: "Angel investors X", "Hollywood actor X", "Silicon Valley investors including X",
        # "Mono CEOs X", "California-based X".
        part = _PERSON_OR_ROLE.sub("", part)
        part = re.sub(r"^[A-Z][\w.]*(?:\s+[A-Z][\w.]*)?-based\s+", "", part)
        part = re.sub(r"\s*\([^)]*\)$", "", part).strip(" '\"’”")
        # "Jeff Bezos' Bezos Expeditions" is the fund; "Ken Njoroge of PANI" is the person, not the company he runs.
        owned = re.match(r"^([A-Z][\w.-]*(?:\s+[A-Z][\w.-]*){0,2})(?:'s|’s|'|’)\s+(?=[A-Z])(.*)$", part)
        if owned:
            owner, held = owned.groups()
            # A firm's own fund is credited to the firm ("Development Partners International's ADP III fund").
            if re.search(r"\s(?:fund|vehicle|arm)$", held) or _ORG_WORD.search(owner) or inv.registry_entry(owner):
                part = owner
            elif held.split()[0] in ("Africa", "African", "Global", "Impact", "Venture", "Ventures", "Investment"):
                part = f"{owner}'s {held}"              # "Google's Africa Investment Fund" names Google's fund
            else:
                part = held                             # "Jeff Bezos' Bezos Expeditions"
        person_of = re.match(r"^([A-Z][a-z]+\s+[A-Z][a-z]+)\s+of\s+[A-Z]", part)
        if person_of and not _ORG_WORD.search(person_of.group(1)):
            part = person_of.group(1)
        if not part or not (part[0].isupper() or part[0].isdigit()) or len(part.split()) > 6 or part.lower() in _NOT_A_NAME:
            continue
        if _ROLE_ONLY.search(part):                     # "Cowrywise CTO" is a job, not an investor's name
            continue
        # A name has at most one lowercase connector word ("Bank of Industry"); more is a clause
        # ("Kasapreko's impressive financial performance").
        if sum(1 for w in part.split() if w[:1].islower() and w not in ("of", "and", "for", "de", "du", "la", "el", "&")) > 0:
            continue
        for name in inv.split_names(part):
            if name and inv.normalise_name(name) != target_key and name not in out:
                out.append(name)
    return out


def extract(text: str, target: str, deal_year: Optional[int] = None, strict: bool = False) -> dict:
    """{"lead": [...], "participants": [...], "round": str|None, "evidence": [{"name", "role", "sentence"}]}.

    Strict reading (for reports found by search, which may cover several companies) takes a sentence about
    "the round" only when it or one of the two sentences before it names the company."""
    lead: list[str] = []
    participants: list[str] = []
    evidence: list[dict] = []
    stage = None
    target_key = inv.normalise_name(target or "")
    text = re.sub(r"(\w)\[(\w)\]", r"\1\2", text or "")    # "Factor[e] Ventures": a bracket would end the list
    recent: list[bool] = []
    for sentence in _sentences(text):
        named_here = bool(target_key) and target_key.split()[0] in inv.normalise_name(sentence)
        named_before = any(recent[-2:])
        recent.append(named_here)
        if not _ROUND_WORDS.search(sentence) or _OTHER_ROUND.search(sentence):
            continue
        years = {int(y) for y in re.findall(r"\b(20\d{2})\b", sentence)}
        if deal_year and years and deal_year not in years:
            continue                                    # a sentence about another year's round
        mentions_target = named_here
        if strict and not (named_here or named_before):
            continue
        if not mentions_target and not re.search(
                r"(?i)\b(?:the|this|its)\s+(?:\S*\d\S*\s+(?:million\s+|billion\s+)?)?(?:round|raise|funding|investment|deal|"
                r"company|startup|series\s+[a-f]|seed|pre-seed|financing)\b", sentence):
            continue
        found: list[tuple[str, str]] = []
        for role, patterns in (("lead", _LEAD), ("participant", _PARTICIPANT)):
            for pattern in patterns:
                for m in pattern.finditer(sentence):
                    found += [(n, role) for n in _names(m.group("names"), target)]
        if not found or len({n for n, _ in found}) > MAX_NAMES_PER_SENTENCE:
            continue
        stage = stage or (m.group(1).lower() if (m := _STAGE.search(sentence)) else None)
        for name, role in found:
            if role == "lead" and name not in lead:
                lead.append(name)
            elif role == "participant" and name not in participants and name not in lead:
                participants.append(name)
            if not any(e["name"] == name for e in evidence):
                evidence.append({"name": name, "role": role, "sentence": sentence[:400]})
    participants = [p for p in participants if p not in lead]
    return {"lead": lead, "participants": participants, "round": stage, "evidence": evidence}


_ARTICLE_CLIENT: Optional[httpx.Client] = None


# Publishers whose round reports are usually readable and name the investors; tried first.
_READABLE_PUBLISHERS = ("techcabal.com", "techcrunch.com", "disrupt-africa.com", "weetracker.com", "techpoint.africa",
                        "techmoran.com", "condia.com", "launchbaseafrica.com", "wamda.com", "businessday.ng",
                        "techeconomy.ng", "itnewsafrica.com", "ventureburn.com", "africabusinesscommunities.com",
                        "thebigdeal.substack.com", "techafricanews.com", "benjamindada.com", "innovation-village.com")
# A digest headline covers several companies ("Kuda's Series B, Catalyst Fund's programme, MTN's new execs").
_ROUNDUP = re.compile(r"(?i)\b(?:round-?up|weekly|this\s+week|week\s+in|newsletter|digest|funding\s+tracker|"
                      r"startups?\s+that\s+raised)\b|,[^,]+,[^,]+")
COVERAGE_WINDOW_DAYS = 45
MAX_COVERAGE = 4


def other_coverage(deal: dict, client: httpx.Client, tried: set[str]) -> list[dict]:
    """Other reports of the same round: a news search for the company's name with funding words, kept only when
    the headline names the company and a round, and it was published within six weeks of the deal."""
    from datetime import timedelta
    from email.utils import parsedate_to_datetime
    from xml.etree import ElementTree
    target = (deal.get("target") or "").strip()
    if len(target) < 3 or not deal.get("announced") or re.match(r"(?i)(?:undisclosed|unnamed)\b", target):
        return []                                   # an unnamed company cannot be searched for
    day = date.fromisoformat(deal["announced"][:10])
    window = timedelta(days=COVERAGE_WINDOW_DAYS)
    query = (f'"{target}" (raises OR raised OR funding OR round OR investment OR secures) '
             f"after:{(day - window).isoformat()} before:{(day + window).isoformat()}")
    try:
        resp = client.get("https://news.google.com/rss/search?q=" + urllib.parse.quote(query) +
                          "&hl=en-US&gl=US&ceid=US:en", headers=_BROWSER, timeout=10)
        resp.raise_for_status()
        root = ElementTree.fromstring(resp.content)
    except Exception as e:                              # noqa: BLE001 - the search is a best effort
        log.info("coverage search failed for %s: %s", target, e)
        return []
    name = re.compile(r"(?i)(?<![\w])" + re.escape(target) + r"(?![\w])")
    found = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source = item.find("source")
        publisher = (source.get("url") if source is not None else "") or ""
        if not link or link in tried or not name.search(title) or not _ROUND_WORDS.search(title) or _ROUNDUP.search(title):
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "").date()
        except (TypeError, ValueError):
            continue
        if abs((published - day).days) > COVERAGE_WINDOW_DAYS:
            continue
        host = urllib.parse.urlparse(publisher).hostname or ""
        rank = 0 if any(host.endswith(p) for p in _READABLE_PUBLISHERS) else 1
        found.append((rank, abs((published - day).days), {"url": link, "title": title, "publisher": host}))
    found.sort(key=lambda r: (r[0], r[1]))
    hosts, out = set(), []
    for _, _, item in found:                            # one report per publisher
        if item["publisher"] not in hosts:
            hosts.add(item["publisher"])
            out.append(item)
    return out[:MAX_COVERAGE]


def _article_client() -> httpx.Client:
    """The research fetcher's safety checks apply; this client adds a browser identity and a longer wait,
    since many publishers refuse or time out on a bot agent with a 4-second limit."""
    global _ARTICLE_CLIENT
    if _ARTICLE_CLIENT is None:
        _ARTICLE_CLIENT = httpx.Client(timeout=12, follow_redirects=False, headers=_BROWSER)
    return _ARTICLE_CLIENT


def enrich(deal: dict, client: httpx.Client, fetch=None, search=None) -> tuple[dict, str]:
    """The deal with investors read from its articles, and a status. The deal's own sources (up to two) are read
    first; when none is readable or names an investor, other reports of the same round are read."""
    from src.engines.research import _fetch_article_content
    if fetch is None:
        def fetch(item: dict) -> dict:                  # noqa: E306
            return _fetch_article_content(item, client=_article_client())
    if search is None:
        search = other_coverage
    year = int(deal["announced"][:4]) if deal.get("announced") else None
    status = "no_article"
    own = [{"url": s.get("url") or "", "title": s.get("title")} for s in (deal.get("sources") or [])[:2]]
    tried = {s["url"] for s in own}
    queue, searched = list(own), False
    while queue or not searched:
        if not queue:
            searched = True
            queue = search(deal, client, tried)
            tried |= {s["url"] for s in queue}
            continue
        source = queue.pop(0)
        url = resolve_google_news(source["url"], client)
        if not url:
            continue
        page = fetch({"url": url, "title": source.get("title")})
        if page.get("content_status") != "article_text_retrieved":
            status = "article_unreadable" if status != "no_investors_named" else status
            continue
        found = extract(page.get("content_text") or "", deal.get("target") or "", year, strict=searched)
        if not (found["lead"] or found["participants"]):
            status = "no_investors_named"
            continue
        out = dict(deal)
        names = found["lead"] + found["participants"]
        out["investors"] = list(dict.fromkeys((deal.get("investors") or []) + names))[:12]
        out["lead_investors"] = found["lead"]
        out["investor_evidence"] = [{**e, "url": page.get("content_url") or url} for e in found["evidence"]]
        if found["round"] and not deal.get("round"):
            out["round"] = found["round"]
        checked = {"on": date.today().isoformat(), "status": "investors_found"}
        if searched:
            checked["via"] = "other_coverage"
        out["parties_checked"] = checked
        return out, "investors_found"
    return {**deal, "parties_checked": {"on": date.today().isoformat(), "status": status, "searched": True}}, status
