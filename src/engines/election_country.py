"""
Election coverage for the countries in src/data/election_profiles.py: one engine driven by each country's profile
(electoral body, parties, regions, dates), where Nigeria has its own deeper engine (election_news.py).

Coverage comes from Google News's public feed of the country's election reporting, so no publisher's site is
fetched and none is worked around; each story keeps the outlet that published it. Tagging is rules only, like
Nigeria's: parties and regions named in the headline or summary, topics, races, and incidents with a severity
(reusing Nigeria's incident rules, which describe events, not places).
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Iterable
from urllib.parse import quote_plus

from src.data.election_profiles import PROFILES
from src.engines import election_news as en
from src.engines.market_feed import COUNTRIES, parse_feed

NIGERIA = "ng-2027"


def feed_url(key: str, days: int = 3) -> str:
    p = PROFILES[key]
    gl = p["iso"]
    return (f"https://news.google.com/rss/search?q={quote_plus(p['query'] + f' when:{days}d')}"
            f"&hl=en-{gl}&gl={gl}&ceid={gl}:en")


def sources() -> list[tuple[str, str]]:
    """(election key, feed url) for every profiled election."""
    return [(k, feed_url(k)) for k in PROFILES]


# ── Per-profile patterns, built once ─────────────────────────────────────────

def _word(name: str) -> str:
    return r"(?<![\w-])" + re.escape(name).replace(r"\ ", r"\s+").replace("'", "['’]") + r"(?![\w-])"


def _compile(p: dict) -> dict:
    body_acr, body_name = p["body"]
    region_word = p["region_word"]
    regions = []
    for r in p["regions"]:
        pat = _word(r) + (rf"\s+{region_word}\b" if r in p.get("ambiguous_regions", ()) else "")
        regions.append((r, re.compile(pat, 0 if r in p.get("ambiguous_regions", ()) else re.I)))
    parties = []
    for acr, name in p["parties"].items():
        pats = [_word(name)]
        if acr not in p.get("ambiguous_parties", ()):
            pats.append(_word(acr))
        parties.append((acr, re.compile("|".join(pats))))
    # "campaign" and "rally" alone are left out: in sports and public-service headlines they mean something else.
    election = re.compile(
        r"(?i)\b(?:elections?|electoral|polls?|polling|voters?|voting|votes?|ballots?|campaign trail|campaigning|"
        r"political campaigns?|candidates?|candidacy|running mate|manifesto|presidential|parliamentary|gubernatorial|"
        r"governorship|aspirants?|primar(?:y|ies)|nominations?|tallying|referendum|re-?election|third term|"
        r"second term|political part(?:y|ies)|opposition)\b|" + _word(body_acr) + "|" + _word(body_name))
    year = re.compile(r"\b(?:" + "|".join(sorted({d[:4] for d, _ in p["dates"]})) + r")\b")
    own = re.compile(_word(p["country"].removeprefix("The ")) + r"(?:ese|ian|n)?\b|" + _word(body_name) + "|" +
                     _word(body_acr))
    others = [c.name for c in COUNTRIES if c.name not in (p["country"], p["country"].removeprefix("The "))]
    foreign = re.compile("|".join(r"(?<!South\s)" + _word(c) if c == "Sudan" else _word(c) for c in others))
    people = [(name, re.compile(rx)) for name, rx in p.get("people", {}).items()]
    admin = re.compile(r"(?i)\b(?:voter(?:s')? (?:card|registration|register|roll)|registration|polling (?:stations?|"
                       r"centres?|centers?)|ballot papers?|timetable|nominations?|tally\w*|electoral (?:roll|calendar)|"
                       r"accreditation|biometric|KIEMS)\b|" + _word(body_acr) + "|" + _word(body_name))
    return {"regions": regions, "parties": parties, "election": election, "year": year, "own": own,
            "foreign": foreign, "people": people, "admin": admin}


_PATTERNS = {k: _compile(p) for k, p in PROFILES.items()}

_RACES: tuple[tuple[str, re.Pattern], ...] = (
    ("presidential", re.compile(r"(?i)\bpresiden(?:tial|cy|t)\b|\bState House\b")),
    ("parliamentary", re.compile(r"(?i)\bparliament\w*|\bnational assembly\b|\bMPs?\b|\bsenat(?:e|or|orial)\b|"
                                 r"\bmembers? of parliament\b|\bnational legislature\b")),
    ("governorship", re.compile(r"(?i)\bgovernor(?:ship)?\b|\bgubernatorial\b")),
    ("local", re.compile(r"(?i)\b(?:MCA|ward rep\w*|councillors?|local government (?:election|polls?)|county assembly)\b")),
)
_GENERIC_TOPICS = tuple((t, p) for t, p in en._TOPICS if t not in ("inec_logistics", "economy", "party_crisis"))
# Pages that are not reporting: social posts, encyclopaedias, video channels.
_NOT_NEWS = re.compile(r"(?i)^(?:facebook|x|twitter|instagram|tiktok|youtube|linkedin|britannica|wikipedia|"
                       r"scribd|pinterest|reddit)\b")
_CONGRATULATE = re.compile(r"(?i)\bcongratulat\w*")


def tag(key: str, title: str, snippet: str = "") -> dict:
    """Parties, regions, topics and races a story names. Regions go under "states", the key every election shares."""
    pat = _PATTERNS[key]
    snippet = en._DATELINE.sub("", snippet or "", count=1)
    text = f"{title}. {snippet}"

    parties = sorted({acr for acr, p in pat["parties"] if p.search(text)})

    def topics(t: str) -> list[str]:
        found = [name for name, p in _GENERIC_TOPICS if p.search(t)]
        if parties and en._TOPICS_BY_NAME["party_crisis"].search(t):
            found.append("party_crisis")
        if pat["admin"].search(t):
            found.insert(1 if found[:1] == ["campaign"] else 0, "election_admin")
        return found
    return {
        "candidates": [],
        "people": [name for name, p in pat["people"] if p.search(text)],
        "parties": parties,
        "states": [r for r, p in pat["regions"] if p.search(text)],
        "lgas": [],
        "topics": topics(title) or topics(text),
        "races": [r for r, p in _RACES if p.search(text)],
    }


def relevant(key: str, title: str, snippet: str = "") -> bool:
    """The country's election coverage. The feed is already a search for the country's election reporting, so
    the headline must carry election wording, or name a party or leading figure with the election year. A headline
    about another country must also name this one (its people, body, parties or regions), so a neighbour's vote
    reported from here stays out, as do congratulations on someone's re-election elsewhere."""
    pat = _PATTERNS[key]
    ours = [p for _, p in pat["parties"]] + [p for _, p in pat["people"]]
    named = any(p.search(title) for p in ours)
    if not (pat["election"].search(title) or (named and pat["year"].search(title))):
        return False
    if _CONGRATULATE.search(title):
        return False
    if pat["foreign"].search(title) and not (named or pat["own"].search(title)
                                             or any(p.search(title) for _, p in pat["regions"])):
        return False
    return True


def collect(key: str, text: str, today: date, days: int = 3) -> list[dict]:
    """Relevant, recent items from one election's feed, each credited to its publisher."""
    oldest = (today - timedelta(days=days)).isoformat()
    out = []
    for item in parse_feed(text, ""):
        if not item.get("publisher") or _NOT_NEWS.search(item["publisher"]) or not item.get("date") \
                or not (oldest <= item["date"] <= today.isoformat()):
            continue
        if relevant(key, item["title"], item["snippet"]):
            out.append({**item, "outlet": item["publisher"]})
    return out


def tagger(key: str):
    return lambda title, snippet="": tag(key, title, snippet)


def headline_keys(key: str):
    def keys(story: dict) -> tuple[set, set]:
        t = tag(key, story.get("title", ""))
        # Parties are named less often than in Nigeria's coverage: the people involved, or the country, stand in.
        return set(t["states"]), set(t["parties"]) | set(t["people"]) or {key}
    return keys


def election_of(story: dict) -> str:
    return story.get("election") or NIGERIA


def split(stories: Iterable[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for s in stories:
        out.setdefault(election_of(s), []).append(s)
    return out
