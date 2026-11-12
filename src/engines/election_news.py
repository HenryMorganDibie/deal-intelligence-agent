"""
Election news: Nigerian political coverage collected from publishers' own feeds, kept to what concerns the 2027
elections, tagged by candidate, party, state, topic and race, and merged so one story reported by several outlets
is one record with every report attached.

Rules only, no language model: every tag can be traced to the words that produced it. Sources are fetched as their
owners publish them (RSS), robots.txt permitting; outlets that refuse automated readers are left out, never worked
around.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from typing import Iterable, Optional

from src.data import elections_ng_2027 as ng
from src.engines.market_feed import parse_feed

USER_AGENT = "Mozilla/5.0 (compatible; web-harvester/0.1; +https://github.com/HenryMorganDibie/web-harvester)"

# (outlet, feed). Checked against each site's robots.txt; outlets answering 403 to an honest crawler are omitted.
SOURCES: tuple[tuple[str, str], ...] = (
    ("Premium Times", "https://www.premiumtimesng.com/category/news/politics/feed"),
    ("Punch", "https://rss.punchng.com/v1/category/latest_news"),
    ("Vanguard", "https://www.vanguardngr.com/category/politics/feed/"),
    ("Daily Trust", "https://dailytrust.com/topics/politics/feed/"),
    ("BusinessDay", "https://businessday.ng/category/politics/feed/"),
    ("ThisDay", "https://www.thisdaylive.com/category/politics/feed/"),
    ("Leadership", "https://leadership.ng/category/politics/feed/"),
    ("INEC News", "https://inecnews.com/feed/"),
)

# ── Relevance ────────────────────────────────────────────────────────────────

_ELECTION_WORDS = re.compile(
    r"(?i)\b(?:20(?:26|27)\b(?=\s*[:,]|\s+(?:election|poll|race|ticket|presidency|governorship|general))|"
    r"elections?|electoral|INEC|IReV|BVAS|PVCs?|voters?|voting|vote[sd]?|ballot|polling|primar(?:y|ies)|"
    r"governorship|presidential|presidency|campaigns?|candidates?|running mate|manifesto|rally|rallies|"
    r"town hall|defect(?:s|ed|ion|ors)?|aspirants?|tickets?|re-?election|second term|"
    r"#\w+Decides20\d\d|certificate of return|tribunal|collation|accreditation|political part(?:y|ies)|"
    r"pre-?regist\w*|registration)\b|\b2027\b(?!.*\bbudget\b)")

# ── Tagging ──────────────────────────────────────────────────────────────────

def _name_pattern(name: str) -> str:
    return r"\b" + re.escape(name).replace(r"\ ", r"\s+").replace(r"\-", r"[-\s]?") + r"\b"


def _candidate_patterns() -> list[tuple[str, re.Pattern]]:
    out = []
    for _, _, candidate, mate in ng.TICKETS:
        for person in (candidate, mate):
            names = (person, *ng.ALIASES.get(person, ()))
            out.append((person, re.compile("|".join(_name_pattern(n) for n in names), re.I)))
    return out


_CANDIDATES = _candidate_patterns()
_PARTY_NAMES = [(acr, re.compile(_name_pattern(name), re.I)) for acr, name, _, _ in ng.TICKETS]
_PARTY_ACRONYMS = [(acr, re.compile(rf"(?<![\w-]){acr}(?![\w-])")) for acr, _, _, _ in ng.TICKETS
                   if acr not in ng.AMBIGUOUS_ACRONYMS]
_LABOUR = re.compile(r"\bLabour Party\b|\bLP\b(?=\s+(?:candidate|chieftain|chairman|members?|leaders?|ticket|crisis))")

_STATE_PATTERNS: list[tuple[str, re.Pattern]] = []
for _s in ng.STATES:
    if _s == "Niger":
        _p = r"\bNiger\s+State\b|\bMinna\b"
    elif _s == "Delta":
        _p = r"(?<!Niger\s)\bDelta\b(?!\s+(?:Air|variant))"
    elif _s == "FCT":
        _p = r"\bFCT\b|\bAbuja\b|\bFederal Capital Territory\b"
    elif _s == "Rivers":
        _p = r"\bRivers(?:\s+State)?\b(?=\W|$)"
    elif _s == "Plateau":
        _p = r"\bPlateau\b(?!\s+in\b)"
    else:
        _p = _name_pattern(_s)
    _STATE_PATTERNS.append((_s, re.compile(_p)))

_TOPICS: tuple[tuple[str, re.Pattern], ...] = (
    ("campaign", re.compile(r"(?i)\b(?:campaigns?|rall(?:y|ies)|town hall|manifesto|canvass\w*|stump)\b")),
    ("inec_logistics", re.compile(r"(?i)\b(?:INEC|PVCs?|voter(?:s')? (?:card|registration|register)|BVAS|IReV|"
                                  r"mock accreditation|polling units?|accreditation|timetable|ballot papers?|pre-?regist\w*|"
                                  r"registration|election materials)\b")),
    ("security", re.compile(r"(?i)\b(?:violence|violent|thugs?|thuggery|attack(?:s|ed)?|kill(?:s|ed|ing)?|"
                            r"kidnap\w*|clash(?:es)?|gunmen|security|insecurity|riot\w*)\b")),
    ("courts", re.compile(r"(?i)\b(?:courts?|tribunal|suit|judg(?:e)?ment|appeal|Supreme Court|injunction|petition)\b")),
    ("defection", re.compile(r"(?i)\b(?:defect(?:s|ed|ion|ors)?|dumps?|dumped|cross(?:es|ed)? (?:over|carpet)|"
                             r"joins?|switch(?:es|ed)?)\b")),
    ("endorsement", re.compile(r"(?i)\b(?:endorse(?:s|d|ment)?|backs?|throws? weight|adopts?|declares? support)\b")),
    ("results", re.compile(r"(?i)\b(?:election results?|results? of|declared (?:the )?winner|collation|"
                           r"certificate of return|returning officer|wins? (?:\w+ ){0,3}(?:primary|election|poll|"
                           r"re-?run|seat)|won (?:\w+ ){0,3}(?:primary|election|poll|re-?run|seat))\b")),
    ("polls", re.compile(r"(?i)\b(?:opinion polls?|poll(?:s|ster)?\s+(?:shows?|finds?|predicts?)|survey)\b")),
    ("debate", re.compile(r"(?i)\bdebates?\b")),
    ("party_crisis", re.compile(r"(?i)\b(?:crisis|faction\w*|leadership tussle|suspend(?:s|ed)?|expel(?:s|led)?|"
                                r"caretaker)\b")),
    ("economy", re.compile(r"(?i)\b(?:economy|inflation|naira|fuel|subsidy|tax(?:es)?|budget|unemployment)\b")),
)

_RACES: tuple[tuple[str, re.Pattern], ...] = (
    ("presidential", re.compile(r"(?i)\bpresiden(?:tial|cy|t)\b|\bAso Rock\b|\bVilla\b")),
    ("governorship", re.compile(r"(?i)\bgovernorship\b|\bgubernatorial\b|\bgov(?:ernor)? candidate\b")),
    ("national_assembly", re.compile(r"(?i)\bsenat(?:e|orial|or)\b|\bHouse of Reps\b|\bRepresentatives\b|"
                                     r"\bNational Assembly\b")),
    ("state_assembly", re.compile(r"(?i)\bState (?:House of )?Assembly\b")),
    ("off_cycle", re.compile(r"(?i)#\w+Decides20(?:24|25|26)\b|\barea councils?\b|\bLG(?:A)? polls?\b|"
                             r"\blocal government (?:election|polls?)\b")),
)


def _candidates_in(text: str) -> list[str]:
    found = []
    for person, pattern in _CANDIDATES:
        for m in pattern.finditer(text):
            word = m.group(0).split()[-1].title()
            before = text[:m.start()].split()[-1:] if len(m.group(0).split()) == 1 else []
            after = text[m.end():].split()[:1]
            if before and before[0].strip("'’\",").title() in ng.RELATIVES.get(word, ()):
                continue
            if after and after[0].strip("'’\",.").title() in ng.NOT_CANDIDATE_AFTER.get(word, ()):
                continue
            found.append(person)
            break
    return found


_DATELINE = re.compile(r"^\s*[A-Z][A-Za-z.\s]{1,30}?\s*(?:[—–-]|:)\s*")


def tag(title: str, snippet: str = "") -> dict:
    """Candidates, parties, states, topics and races named in a story's headline and summary. States come from the
    headline and the summary without its dateline ("ABUJA —" says where the reporter sat, not what it is about)."""
    snippet = _DATELINE.sub("", snippet or "", count=1)
    text = f"{title}. {snippet}"
    candidates = _candidates_in(text)
    parties = {acr for acr, p in _PARTY_NAMES if p.search(text)} | {acr for acr, p in _PARTY_ACRONYMS if p.search(text)}
    if _LABOUR.search(text):
        parties.add("LP")
    tickets = {c: acr for acr, _, c, m in ng.TICKETS for c in (c, m)}
    parties |= {tickets[c] for c in candidates}             # naming a candidate names their party
    return {
        "candidates": candidates,
        "parties": sorted(parties),
        "states": [s for s, p in _STATE_PATTERNS if p.search(text)],
        "topics": [t for t, p in _TOPICS if p.search(title)] or [t for t, p in _TOPICS if p.search(text)],
        "races": [r for r, p in _RACES if p.search(text)],
    }


def relevant(title: str, snippet: str = "") -> bool:
    """Coverage that concerns elections: election vocabulary, a candidate or a party in the headline, or a candidate
    or party with election vocabulary in the summary."""
    if _ELECTION_WORDS.search(title):
        return True
    head = tag(title)
    if head["candidates"] or head["parties"]:
        return True
    t = tag(title, snippet)
    return bool(t["candidates"] or t["parties"]) and bool(_ELECTION_WORDS.search(snippet or ""))


# ── One record per story ─────────────────────────────────────────────────────

_STOP = frozenset("a an the of in on at to for and or as by with from is are was were be has have had it its into "
                  "over after before says said say ahead amid against why how what who will would not no new "
                  "2026 2027 s".split())


def _words(title: str) -> frozenset[str]:
    return frozenset(w for w in re.findall(r"[a-z0-9]+", title.lower().replace("’", "'")) if w not in _STOP and len(w) > 1)


def same_story(a: dict, b: dict, days: int = 2) -> bool:
    """Two reports of one story: near-identical headlines within a couple of days. Either side may be a feed item
    ("date") or a stored story ("day"); a story matches if any of its reports does."""
    if a.get("reports"):
        return any(same_story(r, b, days) for r in a["reports"])
    try:
        da, db = date.fromisoformat(a.get("date") or a.get("day")), date.fromisoformat(b.get("date") or b.get("day"))
    except (TypeError, ValueError):
        return False
    if abs((da - db).days) > days:
        return False
    wa, wb = _words(a["title"]), _words(b["title"])
    if len(wa) < 3 or len(wb) < 3:
        return a["title"].strip().lower() == b["title"].strip().lower()
    shared = len(wa & wb)
    return shared / len(wa | wb) >= 0.6 or (shared >= 4 and shared / min(len(wa), len(wb)) >= 0.8)


def story_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def record(item: dict) -> dict:
    """A new story record from one feed item."""
    report = {"outlet": item["outlet"], "url": item["url"], "title": item["title"], "date": item["date"]}
    return {"id": story_id(item["url"]), "day": item["date"], "title": item["title"], "url": item["url"],
            "outlet": item["outlet"], "snippet": item.get("snippet", "")[:400], **tag(item["title"], item.get("snippet", "")),
            "reports": [report], "outlets": [item["outlet"]]}


def merge(stories: list[dict], items: Iterable[dict]) -> tuple[list[dict], set[str]]:
    """Fold new feed items into existing stories. Returns all stories and the ids that changed."""
    by_url = {r["url"]: s for s in stories for r in s.get("reports", [])}
    changed: set[str] = set()
    for item in items:
        if not item.get("url") or not item.get("date") or item["url"] in by_url:
            continue
        match = next((s for s in stories if same_story(s, item)), None)
        if match:
            match["reports"].append({"outlet": item["outlet"], "url": item["url"], "title": item["title"],
                                     "date": item["date"]})
            match["outlets"] = sorted({r["outlet"] for r in match["reports"]})
            extra = tag(item["title"], item.get("snippet", ""))
            for key in ("candidates", "parties", "states", "topics", "races"):
                match[key] = list(dict.fromkeys([*match.get(key, []), *extra[key]]))
            changed.add(match["id"])
            by_url[item["url"]] = match
        else:
            s = record(item)
            stories.append(s)
            changed.add(s["id"])
            by_url[item["url"]] = s
    return stories, changed


def collect(texts: Iterable[tuple[str, str]], today: date, days: int = 3) -> list[dict]:
    """Relevant, recent items from (outlet, feed text) pairs."""
    oldest = (today - timedelta(days=days)).isoformat()
    out = []
    for outlet, text in texts:
        for item in parse_feed(text, outlet):
            if item.get("date") and oldest <= item["date"] <= today.isoformat() and relevant(item["title"], item["snippet"]):
                out.append({**item, "outlet": outlet})
    return out


def summary(stories: list[dict], since: Optional[str] = None) -> dict:
    """How much coverage each candidate, party, state and topic got: stories and reports."""
    rows = [s for s in stories if not since or (s.get("day") or "") >= since]
    out: dict = {"stories": len(rows), "reports": sum(len(s.get("reports") or [1]) for s in rows)}
    for key in ("candidates", "parties", "states", "topics", "races"):
        counts: dict[str, list[int]] = {}
        for s in rows:
            for v in s.get(key) or []:
                c = counts.setdefault(v, [0, 0])
                c[0] += 1
                c[1] += len(s.get("reports") or [1])
        out[key] = [{"name": k, "stories": a, "reports": b}
                    for k, (a, b) in sorted(counts.items(), key=lambda kv: (-kv[1][1], kv[0]))]
    return out
