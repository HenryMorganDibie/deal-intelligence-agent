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

# (outlet, feed). Publishers' own feeds, checked against each site's robots.txt.
SOURCES: tuple[tuple[str, str], ...] = (
    ("Premium Times", "https://www.premiumtimesng.com/category/news/headlines/feed"),   # its politics feed is stale
    ("Premium Times", "https://www.premiumtimesng.com/category/news/top-news/feed"),
    ("Punch", "https://rss.punchng.com/v1/category/latest_news"),
    ("Vanguard", "https://www.vanguardngr.com/category/politics/feed/"),
    ("Daily Trust", "https://dailytrust.com/topics/politics/feed/"),
    ("BusinessDay", "https://businessday.ng/category/politics/feed/"),
    ("ThisDay", "https://www.thisdaylive.com/category/politics/feed/"),
    ("Leadership", "https://leadership.ng/category/politics/feed/"),
    ("INEC News", "https://inecnews.com/feed/"),
    ("Channels", "https://www.channelstv.com/feed/"),
)

# Outlets whose sites refuse automated readers (TheCable, Guardian) are read from Google News's public feed of
# their headlines instead: nothing is fetched from their servers, and their protection is never worked around.
# Channels' own feed carries ten items; Google News carries the rest of its coverage.
GOOGLE_NEWS_SITES: tuple[tuple[str, str], ...] = (
    ("TheCable", "thecable.ng"),
    ("Guardian", "guardian.ng"),
    ("Channels", "channelstv.com"),
)


def google_news_feed(site: str, days: int = 2) -> str:
    return f"https://news.google.com/rss/search?q=site:{site}+when:{days}d&hl=en-NG&gl=NG&ceid=NG:en"


def all_sources() -> list[tuple[str, str]]:
    return [*SOURCES, *((outlet, google_news_feed(site)) for outlet, site in GOOGLE_NEWS_SITES)]

# Where each outlet's article body is, for web-harvester's crawler (cmd/crawl) to read the full story. Outlets read
# through Google News have no entry: their sites refuse crawlers, so only their headlines are used.
ARTICLE_SELECTORS: dict[str, str] = {
    "Premium Times": ".entry-content p",
    "Leadership": ".entry-content p",
    "Punch": ".post-content p",
    "Channels": ".post-content p",
    "BusinessDay": ".post-content p",
    "Daily Trust": "article p",
    "ThisDay": ".article-content p",
    "Vanguard": ".section-content-single p",
    "INEC News": ".entry-content p",
}
# Sites whose robots.txt asks for a long pause between pages (Vanguard: 30 seconds) get fewer pages per hourly run,
# so they cannot crowd out the rest; the backlog is read over the following hours.
SLOW_OUTLETS: dict[str, int] = {"Vanguard": 10}
_BOILERPLATE = re.compile(r"(?i)subscribe to our|e-editions?|read also|click here|follow us on|"
                          r"^\s*\w+ \d{1,2}, 20\d\d\s*$|^\s*\d{1,2} \w+ 20\d\d\s*$")


def article_text(paragraphs: Iterable[str], limit: int = 20000) -> str:
    """An article's paragraphs as one text, without dates, subscription notices and similar furniture."""
    keep = [p.strip() for p in paragraphs if p and p.strip() and not _BOILERPLATE.search(p)]
    return " ".join(keep)[:limit]


def canonical_url(url: str) -> str:
    """A link without tracking parameters, so a crawled page can be matched to the feed item it came from."""
    base, _, query = (url or "").partition("?")
    kept = "&".join(q for q in query.split("&") if q and not q.startswith(("utm_", "fbclid", "amp")))
    return (base.rstrip("/") + ("?" + kept if kept else "")).lower()


def crawl_targets(stories: list[dict], limit: int = 150, per_outlet: int = 25) -> list[dict]:
    """web-harvester crawl targets for reports whose full article has not been read yet: one target per outlet,
    only the article pages themselves (depth 0), newest stories first, at most `per_outlet` pages per site."""
    urls: dict[str, list[str]] = {}
    n = 0
    for story in sorted(stories, key=lambda s: s.get("day") or "", reverse=True):
        for r in story.get("reports") or []:
            if n >= limit:
                break
            if r.get("words") is None and r.get("outlet") in ARTICLE_SELECTORS and "news.google.com" not in r["url"] \
                    and len(urls.get(r["outlet"], [])) < SLOW_OUTLETS.get(r["outlet"], per_outlet):
                urls.setdefault(r["outlet"], []).append(r["url"])
                n += 1
    return [{"name": outlet, "start_urls": links, "max_depth": 0, "max_pages": len(links),
             "extract": {"skip_links": True, "text_limit": -1,
                         "fields": {"body": {"selector": ARTICLE_SELECTORS[outlet], "all": True}}}}
            for outlet, links in urls.items()]


def body_tags(title: str, body: str) -> dict:
    """Tags from a full article that say what it is about, not everything it mentions: what the opening
    paragraphs name, plus what the article names at least twice."""
    lede = tag(title, body[:_LEDE_CHARS])
    rest = body[_LEDE_CHARS:]
    out = {k: list(v) for k, v in lede.items()}
    patterns = {"states": _STATE_PATTERNS, "topics": _TOPICS, "races": _RACES,
                "parties": [*_PARTY_NAMES, *_PARTY_ACRONYMS]}
    for key, pats in patterns.items():
        for name, p in pats:
            if name not in out[key] and len(p.findall(body)) >= 2 and p.search(rest):
                out[key].append(name)
    for person, p in _CANDIDATES:
        if person not in out["candidates"] and len(p.findall(body)) >= 2 and _candidates_in(rest).count(person):
            out["candidates"].append(person)
    tickets = {c: acr for acr, _, c, m in ng.TICKETS for c in (c, m)}
    out["parties"] = sorted(set(out["parties"]) | {tickets[c] for c in out["candidates"]})
    out["lgas"] = lgas_in(f"{title}. {body}", out["states"])
    return out


def apply_articles(stories: list[dict], pages: Iterable[dict]) -> set[str]:
    """Fold crawled article text into the stories' tags. A report is marked with its word count (0 when the page
    could not be read), so it is not crawled again; the article text itself is not stored."""
    index = {canonical_url(r["url"]): (s, r) for s in stories for r in s.get("reports") or []}
    changed: set[str] = set()
    for page in pages:
        hit = index.get(canonical_url(page.get("url", ""))) or index.get(canonical_url(page.get("final_url", "")))
        if not hit:
            continue
        story, report = hit
        body = article_text((page.get("fields") or {}).get("body") or []) if page.get("status_code") == 200 else ""
        report["words"] = len(body.split())
        changed.add(story["id"])
        if not body:
            continue
        extra = body_tags(report["title"], body)
        for key in _TAG_KEYS:
            story[key] = list(dict.fromkeys([*story.get(key, []), *extra[key]]))
        _merge_incident(story, incidents(report["title"], body))
        story["full_text_reports"] = sum(1 for r in story["reports"] if r.get("words"))
    return changed


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


# ── Places below state level ─────────────────────────────────────────────────

def _lga_patterns() -> dict[str, list[tuple[str, re.Pattern]]]:
    import json
    from pathlib import Path
    data = json.loads((Path(__file__).resolve().parents[1] / "data" / "ng_lgas.json").read_text())
    out: dict[str, list[tuple[str, re.Pattern]]] = {}
    for state, lgas in data.items():
        pats = []
        for raw in lgas:
            name = re.sub(r"\s*-\s*", "-", raw).strip()
            if name.upper() in _AMBIGUOUS_LGAS or name.upper() == state.upper():
                continue
            label = name.title().replace("'S", "'s")
            words = [re.escape(w) for w in re.split(r"[\s-]+", name.title())]
            pats.append((label, re.compile(r"\b" + r"[\s-]?".join(words) + r"\b", re.I if len(name) > 4 else 0)))
        out[state] = pats
    return out


# LGA names that are also everyday words, surnames or other places; never tagged from text.
_AMBIGUOUS_LGAS = frozenset({"OBI", "ISA", "ABI", "ASA", "AWE", "INI", "LAU", "IKA", "TAI", "MANI", "GAYA", "SONG",
                              "LOGO", "TORO", "BALI", "ADO", "EDU", "ITU", "OSE", "OJO", "IDO", "IBI", "ILA", "IVO",
                              "GURI", "MORO", "MARU", "KURA", "ZAKI", "BAYO", "TOTO", "GADA", "OFU", "OYI", "OYE",
                              "MUNICIPAL AREA COUNCIL", "BASSA", "IFELODUN", "IREPODUN"})
_LGAS: Optional[dict] = None


def lgas_in(text: str, states: Iterable[str]) -> list[str]:
    """LGAs named in the text, looked for only within states the story already names: an LGA name alone is often
    a common word, a surname or shared by two states."""
    global _LGAS
    if _LGAS is None:
        _LGAS = _lga_patterns()
    out = []
    for st in states:
        for label, p in _LGAS.get(st, []):
            if p.search(text):
                out.append(f"{label}, {st}")
    return out


# ── Incidents ────────────────────────────────────────────────────────────────

_INCIDENTS: tuple[tuple[str, re.Pattern], ...] = (
    ("violence", re.compile(r"(?i)\b(?:attack(?:s|ed|ers)?|clash(?:es|ed)?|gunmen|gunshots?|shot|shooting|kill(?:s|ed|ing)?(?! it\b)|"
                            r"injur(?:ed|ies)|machetes?|stabbed|violence|fracas|mayhem)\b")),
    ("thuggery", re.compile(r"(?i)\b(?:thugs?|thuggery|hoodlums|miscreants)\b")),
    ("abduction", re.compile(r"(?i)\b(?:kidnap\w*|abduct\w*)\b")),
    ("arson", re.compile(r"(?i)\b(?:set\s+(?:\w+\s+){0,3}(?:ablaze|on fire)|razed|razes|arson|burnt|burned|torch(?:es|ed)?|"
                         r"fire (?:guts|razes))\b")),
    ("ballot_snatching", re.compile(r"(?i)\b(?:snatch\w*\s+(?:of\s+)?(?:ballot|election|electoral)|ballot[- ]box\w* snatch\w*|"
                                    r"hijack\w* (?:of )?(?:election )?materials)\b")),
    ("vote_buying", re.compile(r"(?i)\b(?:vote[- ]buying|buying (?:of )?votes|cash for votes|inducement of voters|"
                               r"vote[- ]trading)\b")),
    ("intimidation", re.compile(r"(?i)\b(?:intimidat\w*|harass\w*|threat(?:s|en\w*)? (?:to )?voters|voter suppression|"
                                r"disenfranchis\w*)\b")),
    ("technology_failure", re.compile(r"(?i)\b(?:BVAS|IReV)\b.{0,40}\b(?:fail\w*|malfunction\w*|glitch\w*|"
                                      r"breakdown|not working|upload (?:failure|problems?))|\b(?:glitch\w*|malfunction\w*)\b.{0,40}\b(?:BVAS|IReV)\b")),
    ("logistics", re.compile(r"(?i)\b(?:late arrival|arrived late|delay(?:s|ed)? in (?:the )?(?:arrival|distribution|deployment)|"
                             r"shortage of (?:election )?materials|materials (?:did not|failed to) arrive)\b")),
    ("arrest", re.compile(r"(?i)\b(?:arrest(?:s|ed)?|detain(?:s|ed)?|in custody)\b")),
    ("hate_speech", re.compile(r"(?i)\b(?:hate speech|incitement|inciting|disinformation|misinformation|fake news)\b")),
)
_HIGH = re.compile(r"(?i)\b(?:kill(?:s|ed|ing)?|dead|death|deaths|gunmen|shot dead|murder\w*|gunfire|gunshots?|fired? (?:gun)?shots|"
                   r"shots fired|guns?|set\s+(?:\w+\s+){0,3}ablaze|torch(?:es|ed)?|razed|"
                   r"arson|burnt|abduct\w*|kidnap\w*|bomb\w*|explosion)\b")
_MEDIUM = re.compile(r"(?i)\b(?:attack\w*|injur\w*|clash\w*|snatch\w*|stabbed|machetes?|vandali[sz]\w*|hijack\w*)\b")
_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}


# "ADC, APM attack APC over manifesto": a war of words, not violence.
_VERBAL_ATTACK = re.compile(r"(?i)\battack(?:s|ed)?\s+(?:the\s+)?(?:" + "|".join(a for a, _, _, _ in ng.TICKETS) +
                            r"|INEC|government|FG|presidency|president|governor|tinubu|obi|atiku|makinde|shettima|"
                            r"amaechi|kwankwaso|party|opposition|critics)\b")
_PHYSICAL = re.compile(r"(?i)\b(?:thugs?|hoodlums|gunmen|guns?|shots?|machetes?|cutlass\w*|injur\w*|killed|"
                       r"venue|rally|rallies|supporters|members|journalist|office|vehicles?|convoy|secretariat|"
                       r"town hall|meeting|gathering)\b")


def incidents(title: str, text: str = "") -> dict:
    """Election incidents a story reports. Types come from the headline, which states what happened; the opening
    of the story only sets the severity (a summary mentions background, such as past killings, too freely)."""
    head = f"{title}. {(text or '')[:_LEDE_CHARS]}"
    types = [t for t, p in _INCIDENTS if p.search(title)]
    if "violence" in types and _VERBAL_ATTACK.search(title) and not _PHYSICAL.search(title):
        types.remove("violence")
    if not types or types == ["arrest"] and not _ELECTION_WORDS.search(head):
        return {}
    severity = "high" if _HIGH.search(head) else "medium" if _MEDIUM.search(head) else "low"
    return {"incident_types": types, "severity": severity}


def _merge_incident(story: dict, found: dict) -> None:
    if not found:
        return
    story["incident_types"] = list(dict.fromkeys([*story.get("incident_types", []), *found["incident_types"]]))
    if _SEVERITY_RANK[found["severity"]] > _SEVERITY_RANK.get(story.get("severity") or "", 0):
        story["severity"] = found["severity"]


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


_INCUMBENTS = frozenset({"Bola Tinubu", "Kashim Shettima"})
_LEDE_CHARS = 600
_DATELINE = re.compile(r"^\s*[A-Z][A-Za-z.\s]{1,30}?\s*(?:[—–-]|:)\s*")


def _named_parties(text: str) -> set[str]:
    """Parties the text names itself, not those implied by a candidate."""
    named = {acr for acr, p in _PARTY_NAMES if p.search(text)} | {acr for acr, p in _PARTY_ACRONYMS if p.search(text)}
    return named | ({"LP"} if _LABOUR.search(text) else set())


def tag(title: str, snippet: str = "") -> dict:
    """Candidates, parties, states, topics and races named in a story's headline and summary. States come from the
    headline and the summary without its dateline ("ABUJA —" says where the reporter sat, not what it is about)."""
    snippet = _DATELINE.sub("", snippet or "", count=1)
    text = f"{title}. {snippet}"
    candidates = _candidates_in(text)
    parties = _named_parties(text)
    tickets = {c: acr for acr, _, c, m in ng.TICKETS for c in (c, m)}
    parties |= {tickets[c] for c in candidates}             # naming a candidate names their party
    states = [s for s, p in _STATE_PATTERNS if p.search(text)]
    return {
        "candidates": candidates,
        "parties": sorted(parties),
        "states": states,
        "lgas": lgas_in(text, states),
        "topics": [t for t, p in _TOPICS if p.search(title)] or [t for t, p in _TOPICS if p.search(text)],
        "races": [r for r, p in _RACES if p.search(text)],
    }


def relevant(title: str, snippet: str = "") -> bool:
    """Coverage that concerns elections: election vocabulary, a candidate or a party in the headline, or a candidate
    or party with election vocabulary in the summary."""
    if _ELECTION_WORDS.search(title):
        return True
    head = tag(title)
    # The sitting president and vice president are in the news daily for governing; on their own they need
    # election wording, like anyone else's government business.
    if _named_parties(title) or set(head["candidates"]) - _INCUMBENTS:
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


_TAG_KEYS = ("candidates", "parties", "states", "lgas", "topics", "races")


def story_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def record(item: dict) -> dict:
    """A new story record from one feed item."""
    report = {"outlet": item["outlet"], "url": item["url"], "title": item["title"], "date": item["date"]}
    return {"id": story_id(item["url"]), "day": item["date"], "title": item["title"], "url": item["url"],
            "outlet": item["outlet"], "snippet": item.get("snippet", "")[:400], **tag(item["title"], item.get("snippet", "")),
            **incidents(item["title"], item.get("snippet", "")), "reports": [report], "outlets": [item["outlet"]]}


def merge(stories: list[dict], items: Iterable[dict]) -> tuple[list[dict], set[str]]:
    """Fold new feed items into existing stories. Returns all stories and the ids that changed."""
    by_url = {r["url"]: s for s in stories for r in s.get("reports", [])}
    changed: set[str] = set()
    for item in items:
        if not item.get("url") or not item.get("date") or item["url"] in by_url:
            continue
        match = next((s for s in stories if same_story(s, item)), None)
        if match and any(r["outlet"] == item["outlet"] and same_story(r, item) for r in match["reports"]):
            by_url[item["url"]] = match          # the same outlet's story again: another feed, or an edited headline
            continue
        if match:
            match["reports"].append({"outlet": item["outlet"], "url": item["url"], "title": item["title"],
                                     "date": item["date"]})
            match["outlets"] = sorted({r["outlet"] for r in match["reports"]})
            extra = tag(item["title"], item.get("snippet", ""))
            for key in _TAG_KEYS:
                match[key] = list(dict.fromkeys([*match.get(key, []), *extra[key]]))
            _merge_incident(match, incidents(item["title"], item.get("snippet", "")))
            changed.add(match["id"])
            by_url[item["url"]] = match
        else:
            s = record(item)
            stories.append(s)
            changed.add(s["id"])
            by_url[item["url"]] = s
    return stories, changed


def retag_missing(stories: list[dict]) -> set[str]:
    """Give stories stored before LGA and incident tagging existed those tags, from their headline and summary."""
    changed = set()
    for s in stories:
        if "lgas" in s:
            continue
        t = tag(s.get("title", ""), s.get("snippet", ""))
        for key in _TAG_KEYS:
            s[key] = list(dict.fromkeys([*s.get(key, []), *t[key]]))
        _merge_incident(s, incidents(s.get("title", ""), s.get("snippet", "")))
        changed.add(s["id"])
    return changed


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
    for key in (*_TAG_KEYS, "incident_types"):
        counts: dict[str, list[int]] = {}
        for s in rows:
            for v in s.get(key) or []:
                c = counts.setdefault(v, [0, 0])
                c[0] += 1
                c[1] += len(s.get("reports") or [1])
        out[key] = [{"name": k, "stories": a, "reports": b}
                    for k, (a, b) in sorted(counts.items(), key=lambda kv: (-kv[1][1], kv[0]))]
    return out
