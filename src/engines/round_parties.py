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
_NAMES = r"(?P<names>[A-Z0-9][^.;:!?]{1,240}?)"
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
_NOT_A_NAME = {"the", "a", "an", "its", "their", "series", "seed", "round", "funding", "investors", "investor", "existing",
               "new", "other", "others", "several", "various", "local", "global", "international", "angel", "angels",
               "ceo", "founder", "founders", "co-founder", "management", "the company", "the startup", "both"}
MAX_NAMES_PER_SENTENCE = 10
_PERSON_OR_ROLE = re.compile(
    r"^.*?\b(?:angel\s+investors?|investors?|backers?|actors?|actress(?:es)?|musicians?|footballers?|founders?|"
    r"co-founders?|CEOs?|chief\s+executives?|executives?|entrepreneurs?|including|such\s+as|like)\s+(?=[A-Z0-9])",
    re.IGNORECASE)


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
        part = re.sub(r"^(?:existing\s+|new\s+|returning\s+)?(?:investors?\s+|backers?\s+)?", "", part.strip(), flags=re.I)
        # Descriptions before a name: "Angel investors X", "Hollywood actor X", "Silicon Valley investors including X",
        # "Mono CEOs X", "California-based X".
        part = _PERSON_OR_ROLE.sub("", part)
        part = re.sub(r"^[A-Z][\w.]*(?:\s+[A-Z][\w.]*)?-based\s+", "", part)
        part = re.sub(r"\s*\([^)]*\)$", "", part).strip(" '\"’”")
        if not part or not (part[0].isupper() or part[0].isdigit()) or len(part.split()) > 6 or part.lower() in _NOT_A_NAME:
            continue
        # A name has at most one lowercase connector word ("Bank of Industry"); more is a clause
        # ("Kasapreko's impressive financial performance").
        if sum(1 for w in part.split() if w[:1].islower() and w not in ("of", "and", "for", "de", "du", "la", "el", "&")) > 0:
            continue
        for name in inv.split_names(part):
            if name and inv.normalise_name(name) != target_key and name not in out:
                out.append(name)
    return out


def extract(text: str, target: str, deal_year: Optional[int] = None) -> dict:
    """{"lead": [...], "participants": [...], "round": str|None, "evidence": [{"name", "role", "sentence"}]}."""
    lead: list[str] = []
    participants: list[str] = []
    evidence: list[dict] = []
    stage = None
    target_key = inv.normalise_name(target or "")
    for sentence in _sentences(text):
        if not _ROUND_WORDS.search(sentence) or _OTHER_ROUND.search(sentence):
            continue
        years = {int(y) for y in re.findall(r"\b(20\d{2})\b", sentence)}
        if deal_year and years and deal_year not in years:
            continue                                    # a sentence about another year's round
        mentions_target = bool(target_key) and target_key.split()[0] in inv.normalise_name(sentence)
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


def _article_client() -> httpx.Client:
    """The research fetcher's safety checks apply; this client adds a browser identity and a longer wait,
    since many publishers refuse or time out on a bot agent with a 4-second limit."""
    global _ARTICLE_CLIENT
    if _ARTICLE_CLIENT is None:
        _ARTICLE_CLIENT = httpx.Client(timeout=12, follow_redirects=False, headers=_BROWSER)
    return _ARTICLE_CLIENT


def enrich(deal: dict, client: httpx.Client, fetch=None) -> tuple[dict, str]:
    """The deal with investors read from its articles (up to two sources tried), and a status."""
    from src.engines.research import _fetch_article_content
    if fetch is None:
        def fetch(item: dict) -> dict:                  # noqa: E306
            return _fetch_article_content(item, client=_article_client())
    year = int(deal["announced"][:4]) if deal.get("announced") else None
    status = "no_article"
    for source in (deal.get("sources") or [])[:2]:
        url = resolve_google_news(source.get("url") or "", client)
        if not url:
            continue
        page = fetch({"url": url, "title": source.get("title")})
        if page.get("content_status") != "article_text_retrieved":
            status = "article_unreadable"
            continue
        found = extract(page.get("content_text") or "", deal.get("target") or "", year)
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
        out["parties_checked"] = {"on": date.today().isoformat(), "status": "investors_found"}
        return out, "investors_found"
    return {**deal, "parties_checked": {"on": date.today().isoformat(), "status": status}}, status
