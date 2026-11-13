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


def sources() -> list[tuple[str, str, str]]:
    """(election key, outlet, feed url) for every profiled election: its Google News search (outlet "") and the
    publishers' own feeds."""
    out = []
    for k, p in PROFILES.items():
        out.append((k, "", feed_url(k)))
        out += [(k, outlet, url) for outlet, url in p.get("sources", ())]
    return out


# ── Per-profile patterns, built once ─────────────────────────────────────────

def _word(name: str) -> str:
    return r"(?<![\w-])" + re.escape(name).replace(r"\ ", r"\s+").replace("'", "['’]") + r"(?![\w-])"


# Neighbours' leading politicians and parties: a headline naming them, and nothing of this country, is about
# their politics ("Blow to Muhoozi as Museveni's party rejects presidential bid" is Uganda's).
FOREIGN_FIGURES = {
    "Uganda": r"\bMuseveni\b|\bMuhoozi\b|\bBobi\s+Wine\b|\bKyagulanyi\b|\bNRM\b|\bNUP\b",
    "Tanzania": r"\bSamia\b|\bSuluhu\b|\bCCM\b|\bChadema\b|\bTundu\s+Lissu\b",
    "Rwanda": r"\bKagame\b", "Ethiopia": r"\bAbiy\b", "Somalia": r"\bHassan\s+Sheikh\b",
    "Democratic Republic of the Congo": r"\bTshisekedi\b|\bKabila\b",
    "Sudan": r"\bBurhan\b|\bHemedti\b|\bRSF\b", "Senegal": r"\bSonko\b|\bDiomaye\s+Faye\b",
    "Nigeria": r"\bTinubu\b|\bAtiku\b|\bINEC\b", "Ghana": r"\bMahama\b",
    "Kenya": r"\bRuto\b|\bGachagua\b|\bIEBC\b", "Gambia": r"\bAdama\s+Barrow\b", "South Sudan": r"\bSalva\s+Kiir\b",
}


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
        r"governorship|aspirants?|" + en.PRIMARIES + r"|nominations?|tallying|referendum|re-?election|third term|"
        r"second term|political part(?:y|ies)|opposition)\b|" + _word(body_acr) + "|" + _word(body_name))
    year = re.compile(r"\b(?:" + "|".join(sorted({d[:4] for d, _ in p["dates"]})) + r")\b")
    own = re.compile(_word(p["country"].removeprefix("The ")) + r"(?:ese|ian|n)?\b|" + _word(body_name) + "|" +
                     _word(body_acr))
    others = [c.name for c in COUNTRIES if c.name not in (p["country"], p["country"].removeprefix("The "))]
    figures = [rx for country, rx in FOREIGN_FIGURES.items() if country not in (p["country"], p["country"].removeprefix("The "))]
    foreign = re.compile("|".join([r"(?<!South\s)" + _word(c) if c == "Sudan" else _word(c) for c in others] + figures))
    people = [(name, re.compile(rx)) for name, rx in p.get("people", {}).items()]
    candidates = [(c["name"], re.compile(c["pattern"]), c.get("party")) for c in p.get("candidates", ())
                  if c.get("status") != "rejected"]
    admin = re.compile(r"(?i)\b(?:voter(?:s')? (?:card|registration|register|roll)|registration|polling (?:stations?|"
                       r"centres?|centers?)|ballot papers?|timetable|nominations?|tally\w*|electoral (?:roll|calendar)|"
                       r"accreditation|biometric|KIEMS)\b|" + _word(body_acr) + "|" + _word(body_name))
    return {"regions": regions, "parties": parties, "election": election, "year": year, "own": own,
            "foreign": foreign, "people": people, "candidates": candidates, "admin": admin}


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

    candidates = [name for name, p, _ in pat["candidates"] if p.search(text)]
    # naming a candidate names their party
    parties = sorted({acr for acr, p in pat["parties"] if p.search(text)} |
                     {party for name, _, party in pat["candidates"] if party and name in candidates})

    def topics(t: str) -> list[str]:
        found = [name for name, p in _GENERIC_TOPICS if p.search(t)]
        if parties and en._TOPICS_BY_NAME["party_crisis"].search(t):
            found.append("party_crisis")
        if pat["admin"].search(t):
            found.insert(1 if found[:1] == ["campaign"] else 0, "election_admin")
        return found
    return {
        "candidates": candidates,
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
    ours = [p for _, p in pat["parties"]] + [p for _, p in pat["people"]] + [p for _, p, _ in pat["candidates"]]
    named = any(p.search(title) for p in ours)
    if not (pat["election"].search(title) or (named and pat["year"].search(title))):
        return False
    if _CONGRATULATE.search(title):
        return False
    if pat["foreign"].search(title) and not (named or pat["own"].search(title)
                                             or any(p.search(title) for _, p in pat["regions"])):
        return False
    return True


def _about_elsewhere(key: str, title: str, snippet: str) -> bool:
    """A publisher's own feed covers the region too ("NRM primaries" is Uganda's): a story whose headline or
    summary names another country, and does not name this one, its people, parties or regions, is elsewhere."""
    pat = _PATTERNS[key]
    text = f"{title}. {snippet or ''}"
    if not pat["foreign"].search(text):
        return False
    ours = [p for _, p in pat["parties"]] + [p for _, p in pat["people"]] + [p for _, p, _ in pat["candidates"]] + \
        [p for _, p in pat["regions"]] + [pat["own"]]
    return not any(p.search(text) for p in ours)


def collect(key: str, text: str, today: date, days: int = 3, outlet: str = "") -> list[dict]:
    """Relevant, recent items from one of an election's feeds: its Google News search (each item credited to its
    publisher) or a publisher's own feed (`outlet`)."""
    oldest = (today - timedelta(days=days)).isoformat()
    out = []
    for item in parse_feed(text, outlet):
        name = outlet or item.get("publisher") or ""
        if not name or _NOT_NEWS.search(name) or not item.get("date") or not (oldest <= item["date"] <= today.isoformat()):
            continue
        if relevant(key, item["title"], item["snippet"]) and not (outlet and _about_elsewhere(key, item["title"], item["snippet"])):
            out.append({**item, "outlet": name})
    return out


def body_tags(key: str):
    """Tags from a full article that say what it is about: what the opening names, plus what the article names at
    least twice (the same rule as Nigeria's)."""
    pat = _PATTERNS[key]

    def tags(title: str, body: str) -> dict:
        out = tag(key, title, body[:en._LEDE_CHARS])
        rest = body[en._LEDE_CHARS:]
        groups = {"states": pat["regions"], "parties": pat["parties"], "people": pat["people"],
                  "candidates": [(n, p) for n, p, _ in pat["candidates"]]}
        for field, pats in groups.items():
            for name, p in pats:
                if name not in out[field] and len(p.findall(body)) >= 2 and p.search(rest):
                    out[field].append(name)
        out["parties"] = sorted(set(out["parties"]) | {party for n, _, party in pat["candidates"]
                                                       if party and n in out["candidates"]})
        return out
    return tags


# Capitalised two- and three-word names in headlines that no list covers, for keeping the lists current.
_NAME = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z]\.)?(?:\s+[A-Z][a-z’']+){1,2})\b")
_NOT_NAMES = re.compile(r"(?i)\b(?:Commission|Council|Party|Movement|Alliance|Congress|Court|Assembly|Parliament|"
                        r"Ministry|Minister|President|Union|Nations|Republic|State|County|Region|Agency|Police|Army|"
                        r"Africa|Kenya|Gambia|Sudan|Nairobi|Banjul|Juba|January|February|March|April|May|June|July|"
                        r"August|September|October|November|December|Monday|Tuesday|Wednesday|Thursday|Friday|"
                        r"Saturday|Sunday|News|Times|Post|Radio|Daily|Election|Elections|National|General|Supreme)\b")


def untracked_names(key: str, stories: Iterable[dict], min_stories: int = 3) -> list[dict]:
    """Names in at least `min_stories` of an election's headlines that are not a listed candidate, figure, party or
    region: who the coverage is about that the profile does not yet track."""
    pat = _PATTERNS[key]
    known = [p for _, p in pat["people"]] + [p for _, p, _ in pat["candidates"]] + [p for _, p in pat["parties"]] + \
        [p for _, p in pat["regions"]]
    counts: dict[str, int] = {}
    for s in stories:
        seen = set()
        for m in _NAME.finditer(s.get("title", "")):
            name = m.group(1)
            if _NOT_NAMES.search(name) or any(p.search(name) for p in known) or name in seen:
                continue
            seen.add(name)
            counts[name] = counts.get(name, 0) + 1
    return [{"name": n, "stories": c} for n, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if c >= min_stories]


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
