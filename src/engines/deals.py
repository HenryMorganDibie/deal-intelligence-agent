"""
African deals database: private and public transactions extracted from news.

Each headline (with its snippet) that reports a transaction becomes a structured
deal: type, parties, amount (original currency and US dollars), stake, implied
valuation, round, stage, sector and country. Extraction is rule-based, so the
same headline always gives the same record and every field can be traced to the
words it came from. Reports of the same deal from several publishers merge into
one record that lists every source.

Coverage is what public reporting covers: undisclosed private deals that no one
reports cannot appear, and amounts are as reported.
"""
from __future__ import annotations

import hashlib
import re
import statistics
import unicodedata
from datetime import date
from typing import Callable, Iterable, Optional

from src.data.africa_countries import COUNTRIES, countries_in_text, get as get_country
from src.utils.paths import DATA_DIR
from src.utils.storage import load_json, save_json

DEALS_PATH = DATA_DIR / "deals.json"

DEAL_TYPES = ("acquisition", "merger", "equity_funding", "debt_financing", "fund_raise",
              "exit", "ipo", "joint_venture")

# ── Amounts ───────────────────────────────────────────────────────────────────

_CURRENCY_SYMBOLS = {
    "us$": "USD", "usd": "USD", "$": "USD", "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP",
    "₦": "NGN", "n": "NGN", "ngn": "NGN", "naira": "NGN",
    "ksh": "KES", "kshs": "KES", "kes": "KES", "sh": "KES",
    "r": "ZAR", "zar": "ZAR", "rand": "ZAR",
    "ghs": "GHS", "gh₵": "GHS", "ghc": "GHS", "ghȼ": "GHS", "cedis": "GHS",
    "egp": "EGP", "le": "EGP", "e£": "EGP", "egyptian pounds": "EGP",
    "mad": "MAD", "dh": "MAD", "dhs": "MAD", "dirhams": "MAD",
    "cfa": "XOF", "fcfa": "XOF", "xof": "XOF", "xaf": "XAF",
    "tzs": "TZS", "ugx": "UGX", "rwf": "RWF", "etb": "ETB", "birr": "ETB",
    "zmw": "ZMW", "kwacha": "ZMW", "bwp": "BWP", "pula": "BWP", "mur": "MUR",
    "aoa": "AOA", "kz": "AOA", "kwanza": "AOA", "mzn": "MZN", "mt": "MZN", "meticais": "MZN",
    "tnd": "TND", "dzd": "DZD", "nad": "NAD",
}
_MULTIPLIERS = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mn": 1e6, "mln": 1e6, "million": 1e6, "millions": 1e6, "milhões": 1e6, "milhoes": 1e6,
    "bn": 1e9, "b": 1e9, "billion": 1e9, "billions": 1e9, "milliard": 1e9, "milliards": 1e9,
    "mil milhões": 1e9, "trillion": 1e12, "tn": 1e12,
}
_PREFIX_CUR = r"(?P<pc>US\$|USD|\$|€|EUR|£|GBP|₦|N(?=\d)|NGN|KSh?s?|KES|R(?=\s?\d)|ZAR|GH₵|GHS|GHC|EGP|E£|LE|MAD|CFA|FCFA|XOF|XAF|TZS|UGX|RWF|ETB|ZMW|BWP|MUR|AOA|Kz|MZN|TND|DZD|NAD)"
_NUMBER = r"(?P<num>\d{1,3}(?:[,\s]\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)"
_MULT = r"(?P<mult>trillion|billions?|millions?|milliards?|mil\s+milhões|milhões|milhoes|thousand|bn|mln|mn|tn|[mbk])\b"
_SUFFIX_CUR = r"(?P<sc>naira|rand|cedis|dirhams|egyptian\s+pounds|birr|kwacha|pula|kwanza|meticais|FCFA|CFA|USD|EUR|dollars?|euros?|\$)"
_AMOUNT_PREFIXED = re.compile(rf"(?<![\w.]){_PREFIX_CUR}\s?{_NUMBER}\s?(?:{_MULT})?", re.IGNORECASE)
_AMOUNT_SUFFIXED = re.compile(rf"{_NUMBER}\s?{_MULT}\s*(?:de\s+|d['’]\s*)?{_SUFFIX_CUR}", re.IGNORECASE)


def _to_float(num: str) -> Optional[float]:
    n = num.replace(" ", "")
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", n):
        n = n.replace(",", "")
    elif "," in n and "." not in n:
        n = n.replace(",", ".")       # European decimal comma: "1,5 milliard"
    try:
        return float(n)
    except ValueError:
        return None


_FRENCH_CONTEXT = re.compile(r"(?i)\b(milliards?|millions?\s+de|milliards?\s+de)\b|FCFA|CFA|\bd['’]euros\b|\bde\s+dollars\b")


_INSTRUMENT_AFTER = re.compile(r"(?i)^\W{0,3}(?:\S+\s+){0,2}?(loan|facility|financing|funding|round|investment|equity|"
                               r"stake|deal|bond|notes|raise|seed|series|debt|credit|acquisition|buyout|fund|prêt|financement)\b")
_PLEDGE_BEFORE = re.compile(r"(?i)\b(promet|promises?|pledges?|vows?|plans?\s+to\s+invest|to\s+invest|commits?\s+to\s+invest)"
                            r"\s+(?:\S+\s+){0,2}$")
# "$7 billion fertiliser expansion": the cost of a project, not the deal.
_PROJECT_AFTER = re.compile(r"(?i)^\W{0,3}(?:\S+\s+){0,2}?(expansion|project|programme|plan|refinery|port|airport|plant|"
                            r"factory|complex|corridor|pipeline|railway)\b")


def deal_amount(text: str) -> Optional[tuple[float, str]]:
    """The transaction's amount when a headline has several: the one tied to an instrument word
    ("with $600m loan"), never a pledge or a project's total cost."""
    found = []
    for m in sorted([*_AMOUNT_PREFIXED.finditer(text), *_AMOUNT_SUFFIXED.finditer(text)], key=lambda m: m.start()):
        parsed = parse_amounts(text[m.start(): m.end() + 12])
        if not parsed:
            continue
        found.append((m, parsed[0]))
    if not found:
        return None
    usable = [(m, a) for m, a in found if not _PLEDGE_BEFORE.search(text[max(0, m.start() - 40): m.start()])
              and not (len(found) > 1 and _PROJECT_AFTER.match(text[m.end():]))]
    tied = [(m, a) for m, a in usable if _INSTRUMENT_AFTER.match(text[m.end():])]
    pick = (tied or usable or [None])[0]
    return pick[1] if pick else None


def parse_amounts(text: str) -> list[tuple[float, str]]:
    """Every money amount in the text as (value, ISO currency), in order."""
    out = []
    matches = sorted([*_AMOUNT_PREFIXED.finditer(text), *_AMOUNT_SUFFIXED.finditer(text)], key=lambda m: m.start())
    last_end = -1
    for m in matches:
        if m.start() < last_end:
            continue
        last_end = m.end()
        g = m.groupdict()
        raw_num = g["num"] or ""
        # "454,205 milliards de FCFA" is 454.205 billion: a comma before a French multiplier is a decimal mark.
        if "," in raw_num and "." not in raw_num and _FRENCH_CONTEXT.search(text[m.start(): m.end() + 12]):
            raw_num = raw_num.replace(" ", "").replace(",", ".")
        value = _to_float(raw_num)
        if value is None:
            continue
        mult = (g.get("mult") or "").lower()
        value *= _MULTIPLIERS.get(re.sub(r"\s+", " ", mult), 1)
        cur_raw = (g.get("pc") or g.get("sc") or "").lower()
        if cur_raw in ("dollar", "dollars"):
            cur = "USD"
        elif cur_raw in ("euro", "euros"):
            cur = "EUR"
        else:
            cur = _CURRENCY_SYMBOLS.get(re.sub(r"\s+", " ", cur_raw))
        if not cur:
            continue
        # A bare number with no multiplier is a price or a count, not a deal size.
        if not mult and value < 100_000:
            continue
        out.append((value, cur))
    return out


_CURRENCY_CODES = set(_CURRENCY_SYMBOLS.values()) | {"CFA", "FCFA"}

# Fallback USD rates (units per USD) when no live or annual rate is supplied.
_FALLBACK_PER_USD = {"USD": 1.0, "EUR": 0.92, "GBP": 0.78, "XOF": 600.0, "XAF": 600.0}


def to_usd(value: float, currency: str, year: Optional[int] = None,
           rates: Optional[Callable[[str, Optional[int]], Optional[float]]] = None) -> Optional[float]:
    """Convert at the deal year's average official rate (World Bank), else the given rate source."""
    if currency == "USD":
        return value
    per_usd = rates(currency, year) if rates else None
    if per_usd is None:
        per_usd = _annual_rate(currency, year)
    if per_usd is None:
        per_usd = _FALLBACK_PER_USD.get(currency)
    return round(value / per_usd, 0) if per_usd else None


def _annual_rate(currency: str, year: Optional[int]) -> Optional[float]:
    """LCU per USD for the year (or the latest year) from the committed World Bank snapshot."""
    from src.engines.country_risk import load_snapshot
    country = next((c for c in COUNTRIES if c.currency == currency), None)
    if country is None:
        return None
    series = (load_snapshot().get("series", {}).get("PA.NUS.FCRF") or {}).get(country.iso3) or {}
    if not series:
        return None
    key = str(year) if year and str(year) in series else max(series)
    return series[key]


# ── Parties ───────────────────────────────────────────────────────────────────

_TOKEN = (r"(?<![\w.$€£₦])(?!(?:R|N|Sh|KSh|Ksh|E|GH|US|K|CFA|FCFA|USD|EUR|NGN|KES|ZAR|EGP)[\d$£₵])(?!\d+(?:st|nd|rd|th)\b)"
          r"(?:[A-Z][\w&.'’+\-]*|\d+[A-Za-z][\w&.'’+\-]*)")
_CONNECTOR = r"(?:of|and|&|de|du|des|la|le|the|da|do|dos|pour|et)"
NAME = rf"{_TOKEN}(?:\s+(?:{_CONNECTOR}\s+)?{_TOKEN}|\s+(?:{_CONNECTOR}\s+)?[dl]['’]{_TOKEN}){{0,6}}"

_ROUND = re.compile(r"\b(pre[-\s]seed|seed|pre[-\s]series\s+[a-h]|series\s+[a-h]\d?|venture\s+debt|pre[-\s]ipo|"
                    r"(?:bridge|growth|extension)(?=\s+(?:round|funding|equity|capital|financing)))\b"
                    r"(?:\s+(?:round|funding|financing|extension))?", re.IGNORECASE)
_STAKE = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s?(?:%|per\s?cent|percent|pour\s?cent)\s+(?:equity\s+)?(?:stake|interest|shareholding|of|participation|da|du|de)",
                    re.IGNORECASE)
_MAJORITY = re.compile(r"\b(majority|controlling|minority)\s+(stake|interest|shareholding)\b", re.IGNORECASE)

# Leading words that describe rather than name a company.
_DESCRIPTOR_WORDS = {
    "the", "a", "an", "startup", "start-up", "fintech", "firm", "company", "group", "lender", "bank", "insurer",
    "telco", "operator", "giant", "conglomerate", "platform", "provider", "investor", "fund", "manager", "maker",
    "retailer", "miner", "producer", "developer", "app", "unicorn", "agritech", "healthtech", "edtech",
    "logistics", "e-commerce", "proptech", "insurtech", "cleantech", "energy", "solar", "mobility",
    "b2b", "b2c", "e-health", "health", "prop-tech", "ed-tech", "agri-tech", "software", "ai", "tech", "payments",
    "payment", "digital", "online", "electric", "ev", "lending", "credit", "telecoms", "infrastructure", "pharmaceutical",
    "healthcare", "mining", "oil", "gas", "food", "agribusiness", "retail", "real", "estate", "property",
    "insurance", "broker", "brokerage", "bottler", "brewer", "carrier", "airline", "distributor",
}
_STOP_TAIL = re.compile(r"\s+(?:Ltd|Limited|Plc|PLC|Inc|SA|S\.A\.|Holdings?|Group)\.?$")
_GENERIC = {"africa", "african", "african startups", "startups", "firm", "abu dhabi firm", "consortium",
            "government", "federal government", "fg", "house", "senate", "court", "parliament", "cabinet", "ministry",
            "police", "state", "shareholders", "residents", "students", "fans", "president", "governor", "accord",
            "world bank", "imf", "treasury", "central bank", "board", "union", "unions", "pdp", "apc", "anc",
            "fitch", "moody's", "moodys", "s&p global ratings", "gcr", "agusto", "now", "today", "trésor", "tresor",
            "groundbreaking", "landmark", "historic", "record", "major", "massive", "huge", "new", "exclusive",
            "trésor public", "ministry of finance", "debt management office", "dmo", "dgtcp", "dgtcp du mali", "etat",
            # African capitals: a city "raising" money is a sovereign issue
            "brazzaville", "kinshasa", "abuja", "nairobi", "dakar", "abidjan", "accra", "pretoria", "cairo", "rabat",
            "tunis", "algiers", "alger", "addis ababa", "kampala", "kigali", "dar es salaam", "dodoma", "lusaka", "harare",
            "maputo", "luanda", "yaoundé", "yaounde", "libreville", "niamey", "bamako", "ouagadougou", "lomé", "lome",
            "cotonou", "conakry", "freetown", "monrovia", "banjul", "bissau", "nouakchott", "windhoek", "gaborone",
            "maseru", "mbabane", "lilongwe", "antananarivo", "port louis", "moroni", "asmara", "mogadishu", "khartoum",
            "juba", "n'djamena", "ndjamena", "bangui", "malabo", "praia", "tripoli", "bujumbura",
            "central bank", "banque centrale", "reserve bank",
            "l'etat", "l’etat", "state government", "nigeria", "kenya", "egypt", "ghana", "startup", "startups", "report", "exclusive",
            "breaking", "update", "news", "deal", "deals", "how", "why", "what", "watch", "opinion", "analysis",
            "weekly", "the big deal", "funding", "investors", "series", "seed", "ceo", "it", "this"}


_CORPORATE_WORDS = {"industries", "group", "holdings", "holding", "bank", "capital", "partners", "ventures", "energy",
                    "power", "limited", "plc", "fund", "technologies", "motors", "resources", "investments",
                    "insurance", "telecom", "mining", "foods", "brands", "networks", "systems", "solutions"}
_BACKED = re.compile(r"^((?:[A-Z][\w&.]*[\s-]?){1,4})-backed\s+", re.IGNORECASE)


def _is_place(words: str) -> bool:
    found = countries_in_text(words)
    return bool(found) and normalise_name(words) in {normalise_name(n) for c in found for n in (c.name, *c.aliases)}


_GENERIC_TAIL = re.compile(r"\b(firms?|company|companies|startups?|producer|agency|lender|business(es)?|operator|"
                           r"manufacturer|platform|provider|investors?|billionaires|agreement|deal|projects?|"
                           r"licen[cs]e|subsidiary|unit|assets?|portfolio|stake|schools?|communities|programme|program|youth|"
                           r"farmers|smes|women|deadline|offer|forecast|target|bank|lender|insurer|telco|miner|bottler|brewer|"
                           r"retailer|distributor|carrier|airline|maker)$", re.IGNORECASE)
_ALWAYS_GENERIC_TAIL = re.compile(r"\b(schools?|communities|students|scholarships?|scheme|programmes?|programs?|youth|"
                                  r"farmers|women|summit|conference|forum|awards?|event|week|plant|factory|now|today|campus|hostel|game|"
                                  r"etfs?|etns?|aircraft|jets?|king|giant|leader|champion|rights?|licen[cs]es?|title|tour|datacent(?:er|re)s?|data\s+cent(?:er|re)s?|"
                                  r"facilities|infrastructure|hospitals|roads?|devices)$",
                                  re.IGNORECASE)
_GENERIC_RE = re.compile(r"^(?:(?:east|west|north|south|southern|central|sub-saharan)\s+)?africa(n)?$|"
                         r"^(?:north|south|latin|central)\s+americ(a|an)$|"
                         r"^(?:us|u\.s\.|uk|u\.k\.|usa|china|india|uae|france|europe|asia|gulf|global|local|"
                         r"foreign|international|chinese|indian|american|british|french|emirati|saudi)$", re.IGNORECASE)


def _is_lender(name: Optional[str]) -> bool:
    """A known lender: a registry DFI, multilateral or bank, or a name that says bank, fund or finance."""
    if not name:
        return False
    from src.engines.investors import registry_entry
    entry = registry_entry(name)
    return bool(entry and entry.kind in ("dfi", "multilateral", "bank", "pension", "sovereign")) or bool(
        re.search(r"(?i)\b(bank|banque|finance|financial|capital|fund|credit|exim|afc|eib|ebrd)\b", name))


def _is_descriptor(word: str) -> bool:
    w = word.lower()
    return w in _DESCRIPTOR_WORDS or bool(re.fullmatch(r"[\w]+-tech|e-\w+", w))


_FOREIGN_DEMONYMS = {"african", "pan-african", "chinese", "indian", "american", "british", "french", "emirati", "saudi",
                     "qatari", "turkish", "japanese", "german", "dutch", "swiss", "italian", "spanish", "portuguese",
                     "canadian", "australian", "russian", "korean", "brazilian", "israeli", "global", "international",
                     "us", "u.s.", "uk", "u.k.", "uae", "gulf", "european", "asian", "middle", "eastern"}
_OWNED_GENERIC = re.compile(r"(?i)\b(purchase|acquisition|expansion|project|operations?|unit|business|assets?|plant|"
                            r"factory|refinery|subsidiary|arm|division|fleet|network|programme|plan|growth|ipo|listing)$")
_FILLER = {"ratings", "rating", "three", "two", "four", "five", "six", "several", "local", "foreign", "its", "new",
           "major", "leading", "top", "big", "small", "global", "state", "private", "public", "owned", "listed",
           "investment", "consumer", "core", "banking", "insurance", "fashion", "travel", "technology", "telecom",
           "power", "energy", "brand", "brands", "school", "private", "regional", "unnamed", "undisclosed"}


def _is_filler(word: str) -> bool:
    w = word.lower().strip(",")
    return (_is_descriptor(word) or _is_place(word) or w in _FILLER or w.isdigit() or w.endswith("est")
            or (word.isupper() and len(word) <= 4))


def _clean_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    n = name.strip(" ,.;:'’\"-")
    n = _BACKED.sub("", n)
    n = re.sub(r"(?i)^(?:[A-Z][\w.]*[\s-]){0,2}?[A-Za-z]+-(?:based|founded|first|focused|headquartered|owned|listed)\s+", "", n)
    n = re.sub(r"^.*?-managed\s+", "", n)
    n = re.split(r"\s+(?:That|Which|Who|Behind|After|Before|As|With)\b", n)[0]
    n = n.strip("'\"‘’“” ")
    n = re.sub(r"^(?:Le|La|Les|L['’]|O|A|Os|As)\s+(?=[A-Z])", "", n)
    n = re.sub(r"^L['’][a-zéèêàç]+\s+", "", n)                       # "L'indien A2MP"
    n = re.sub(r"^(.+?)-led\s+(?:consortium|group|syndicate|investors)$", r"\1", n, flags=re.IGNORECASE)
    # "Nigeria's Moniepoint", "Tony Elumelu's United Capital" -> the company after the possessive.
    if re.search(r"(?:'s|’s)\s+\S", n):
        owner, owned = re.split(r"(?:'s|’s)\s+", n, maxsplit=1)
        # "Air Côte d'Ivoire's Airbus Purchase": the owner is the party; "Nigeria's Moniepoint": the owned is.
        n = owner if _OWNED_GENERIC.search(owned) and not _is_place(owner) else owned
    n = re.sub(r"(?:'s|’s)$", "", n)
    words = n.split()
    # Strip a leading run of place and descriptor words ("Egyptian E-Health Startup Reme-D") only when
    # it contains a descriptor and leaves a name: "Nigerian Breweries" and "Solar Industries" stay whole.
    run = 0
    while run < len(words) - 1 and (_is_descriptor(words[run]) or _is_place(words[run])
                                    or words[run].lower() in _FOREIGN_DEMONYMS):
        run += 1
    # A demonym can be incorrectly attached to a short company ticker/name
    # when the headline says e.g. "Australian gold miner TCMG".
    if run and words[0].lower() in _FOREIGN_DEMONYMS and words[-1].isupper() and len(words[-1]) >= 2:
        words = words[run:]
        run = 0
    if run and any(_is_descriptor(w) for w in words[:run]) and words[run].lower() not in _CORPORATE_WORDS \
            and not re.fullmatch(r"of|de|du|des|and|&|for|da|do", words[run].lower()):
        words = words[run:]
    n = " ".join(words).strip()
    if n.upper() in _CURRENCY_CODES or re.fullmatch(r"(?i)africa(?:n)?\s+\w+", n) and not re.search(r"\d", n):
        return None
    if (not n or _ALWAYS_GENERIC_TAIL.search(n) or n.lower() in _GENERIC or len(n) < 2 or n.isdigit() or _is_place(n) or _GENERIC_RE.match(n)
            or (_GENERIC_TAIL.search(n) and all(_is_filler(w) for w in n.split()[:-1]))):
        return None
    return n


def normalise_name(name: Optional[str]) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name.replace("’", "'")).encode("ascii", "ignore").decode().lower()
    s = _STOP_TAIL.sub("", s)
    s = re.sub(r"\b(ltd|limited|plc|inc|sa|holdings?|group|company|corp(oration)?)\b\.?", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# ── Deal patterns ─────────────────────────────────────────────────────────────
# Each: (deal_type, compiled pattern). Named groups: subj (the actor), obj (the counterparty).
_AUX = (r"(?:\s+(?:has|have|will|is|are|to|set\s+to|agrees?\s+to|agreed\s+to|moves?\s+to|plans?\s+to|in\s+talks\s+to|"
        r"aims?\s+to|looks?\s+to|hopes?\s+to|wants?\s+to|seeks?\s+to|targets?\s+to|is\s+considering|considers|mulls|"
        r"weighs|(?:wins?|gets?|receives?|secures?|obtains?)\s+(?:\S+\s+){0,2}?(?:approval|nod|clearance)\s+to))*")
_STAKE_IN = (r"(?:(?:an?\s+|the\s+)?(?:\S+\s+){0,3}?(?:stake|interest|shareholding|holding)\s+in\s+"
             r"|\d{1,3}(?:[.,]\d+)?\s?%\s+(?:of\s+|da\s+|do\s+|de\s+|du\s+|des\s+|in\s+))")

# Verbs, auxiliaries and prepositions are lowercased before matching, so Title Case
# headlines ("Zenith Bank Completes Acquisition Of Paramount Bank") parse like
# sentence case while company names keep their capitals.
_LOWER_WORDS = set("""
acquire acquires acquired acquiring buy buys bought buying snaps snap takes take took purchase purchases purchased
merge merges merged merging complete completes completed finalise finalises finalised finalize finalizes finalized
closes closed conclude concludes concluded announce announces announced sell sells sold selling divest divests
divested offload offloads offloaded dispose disposes exit exits exited raise raises raised raising secure secures
secured bag bags bagged lands landed nets netted get gets got snags attracts receive receives received lead leads
led co-lead co-leads co-led anchors anchored invest invests invested investing inject injects injected commit
commits committed backs backed lend lends lent extend extends extended provide provides provided approve approves
approved grant grants granted arrange arranges arranged sign signs signed disburse disburses disbursed obtain
obtains obtained issue issues issued lists listed debut debuts debuted files launch launches launched prices priced
reach reaches reached holds hits forms create creates increases ups enters agree agrees agreed moves plans set
has have will is are was were to of in into for from with by on at as after a an its their stake stakes interest
shareholding majority minority controlling significant strategic acquisition purchase takeover buyout round
funding financing loan facility close up over talks discloses proposed enters seeks seek exiting
calls call urges says wants targets eyes launched aims aim looks hopes achieves achieved attains wins win gets
across among
considering considers mulls weighs approval nod clearance
investit acquiert rachète cède lève obtient dans investe adquire compra vende capta obtém em
""".split())
_WORD = re.compile(r"\b[A-Za-z][\w'’-]*\b(?!\.)")


def _normalise_case(title: str) -> str:
    return _WORD.sub(lambda m: m.group(0).lower() if m.group(0).lower() in _LOWER_WORDS else m.group(0), title)


_PATTERNS: list[tuple[str, re.Pattern]] = [(t, re.compile(p)) for t, p in [
    ("fund_raise", rf"(?P<lp>{NAME}){_AUX}\s+(?:anchors?|anchored|backs?|backed|commits?\s+to|invests?\s+in)\s+(?:the\s+|a\s+)?(?:\S+\s+){{0,2}}?(?i:first|final|second|interim)?\s*close\s+(?:of|for)\s+(?P<subj>{NAME})"),
    ("fund_raise", rf"(?P<lp>{NAME}){_AUX}\s+(?:commits?|committed|invests?|invested|backs?|backed|anchors?|anchored)\s+(?:\S+\s+){{0,4}}?(?:in|into|to)\s+(?P<subj>{NAME}\s+(?i:fund)(?:\s+[IVX\d]+)?)"),
    ("merger", rf"(?P<subj>{NAME}){_AUX}\s+(?:completes?\s+|announces?\s+)?(?:merges?|merged|merging|to\s+merge)\s+with\s+(?P<obj>{NAME})"),
    ("merger", rf"(?i:merger\s+(?:of|between))\s+(?P<subj>{NAME})\s+and\s+(?P<obj>{NAME})"),
    ("acquisition", rf"(?P<subj>{NAME}){_AUX}\s+(?:completes?|completed|finali[sz]es?|closes?|concludes?|announces?)\s+(?:the\s+|its\s+)?(?:majority\s+|minority\s+)?(?:acquisition|purchase|takeover|buyout)\s+of\s+{_STAKE_IN}?(?P<obj>{NAME})"),
    ("acquisition", rf"(?P<subj>{NAME}){_AUX}\s+(?:completes?|completed|finali[sz]es?|closes?|concludes?|announces?)\s+(?:the\s+|its\s+)?(?P<obj>{NAME})\s+(?:acquisition|takeover|buyout|purchase)\b"),
    ("acquisition", rf"(?P<obj>{NAME})\s+(?:(?:is|was|has\s+been|gets|got|to\s+be)\s+)?(?:acquired|bought|taken\s+over|snapped\s+up)\s+by\s+(?:\S+\s+){{0,4}}?(?P<subj>{NAME})"),
    ("acquisition", rf"(?P<subj>{NAME}){_AUX}\s+(?:acquires?|acquired|acquiring|buys?|bought|buying|snaps?\s+up|takes?\s+over|took\s+over|purchases?|purchased|rachète|acquiert|adquire|compra|adquiriu)\s+{_STAKE_IN}?(?P<obj>{NAME})"),
    ("acquisition", rf"(?P<subj>{NAME}){_AUX}\s+(?:takes?|took|increases?|ups|raises?)\s+{_STAKE_IN}(?P<obj>{NAME})"),
    ("acquisition", rf"(?P<subj>{NAME})\s+(?i:prend\s+le\s+contr[ôo]le\s+de|prend\s+une\s+participation\s+dans)\s+(?P<obj>{NAME})"),
    ("exit", rf"(?P<subj>{NAME}){_AUX}\s+(?:sells?|sold|selling|divests?|divested|offloads?|offloaded|disposes?\s+of|cède|vende)\s+{_STAKE_IN}?(?P<obj>{NAME})(?:.{{0,40}}?\s+(?:to|à)\s+(?:the\s+|a\s+)?(?:[a-z]\S*\s+){{0,3}}(?P<to>{NAME}))?"),
    ("exit", rf"(?P<subj>{NAME}){_AUX}\s+(?:exits?|exited|exiting)\s+(?:its\s+|their\s+)?(?:\S+\s+){{0,2}}?(?:stake|investment|holding|position)s?\s+in\s+(?P<obj>{NAME})"),
    ("fund_raise", rf"(?P<subj>{NAME})(?:'s|’s)?(?:\s+(?i:fund|vehicle)(?:\s+[IVX\d]+)?)?{_AUX}\s+(?:announces?\s+|reaches?\s+|reached\s+|holds?\s+|hits?\s+|achieves?\s+|achieved\s+|attains?\s+)?(?:the\s+|its\s+|a\s+)?(?:\S+\s+){{0,2}}?(?i:first|final|second|third|interim|hard|\d(?:st|nd|rd|th))\s+close\b"),
    ("fund_raise", rf"(?P<subj>{NAME}){_AUX}\s+(?:closes?|closed|raises?|raised|launches?|launched|reaches?|hits?)\s+(?:its\s+|a\s+|an?\s+)?(?:\S+\s+){{0,3}}?(?<!to\s)(?i:fund|vehicle)\b(?!\s+(?:expansion|growth|its|the))"),
    ("debt_financing", rf"(?P<subj>{NAME}){_AUX}\s+(?:lends?|lent|extends?|extended|provides?|provided|approves?|approved|grants?|granted|arranges?|signs?|signed|disburses?)\s+(?:a\s+|an\s+)?(?:\S+\s+){{0,4}}?(?i:loan|facility|credit\s+line|debt|financing|guarantee|bond)s?\s+(?:to|for)\s+(?P<obj>{NAME})"),
    ("debt_financing", rf"(?P<subj>{NAME}){_AUX}\s+(?:secures?|secured|signs?|signed|obtains?|obtained|gets?|got|receives?|received|lands?|raises?|raised|closes?|closed|issues?|issued|obtient|obtém|lève)\s+(?:a\s+|an\s+|un\s+|une\s+|um\s+)?(?:\S+\s+){{0,4}}?(?i:loan|facility|credit\s+line|debt\s+financing|debt|bond|sukuk|notes|eurobond|prêt|financement|emprunt\s+obligataire|empréstimo|financiamento)s?\b(?:\s+from\s+(?P<obj>{NAME}))?(?:.{{0,30}}?\s+with\s+(?:the\s+)?(?P<with>{NAME}))?"),
    ("equity_funding", rf"(?P<subj>{NAME}){_AUX}\s+(?:leads?|led|co-leads?|co-led|anchors?)\s+(?:a\s+|an\s+|the\s+)?(?:\S+\s+){{0,5}}?(?i:round|investment|raise)\s+(?:in|into|for)\s+(?P<obj>{NAME})"),
    ("equity_funding", rf"(?P<subj>{NAME}){_AUX}\s+(?:discloses\s+|makes\s+|announces\s+|completes\s+)?(?:proposed\s+)?(?:(?:a|an|the|its|\S*\d\S*|million|billion|m|bn|equity|strategic|minority|majority|further|follow-on)\s+){{0,4}}(?i:investment|equity\s+investment)\s+in\s+(?P<obj>{NAME})"),
    ("equity_funding", rf"(?P<subj>{NAME}){_AUX}\s+(?:invests?|invested|investing|injects?|injected|commits?|committed|backs?|backed|investit|investe|injecte)\s+(?:(?:\S+\s+){{0,6}}?(?:in|into|dans|em|no|na)\s+)?(?P<obj>{NAME})"),
    ("equity_funding", rf"(?P<subj>{NAME}){_AUX}\s+(?:raises?|raised|raising|secures?|secured|bags?|bagged|lands?|landed|closes?|closed|nets?|netted|gets?|snags?|attracts?|receives?|received|lève|levée|capta|angaria)\b"),
    ("ipo", rf"(?P<subj>{NAME}){_AUX}\s+(?:lists?|listed|debuts?|debuted|files?\s+for|launches?|prices?|priced|plans?)\s+(?:its\s+|an?\s+)?(?:\S+\s+){{0,3}}?(?:on\s+the\s+|(?i:ipo|initial\s+public\s+offering|listing))"),
    ("joint_venture", rf"(?P<subj>{NAME})\s+and\s+(?P<obj>{NAME})\s+(?i:form|forms|launch|launches|sign|signs|create|creates|set\s+up|sets\s+up)\s+(?:a\s+)?(?i:joint\s+venture|JV)"),
]]

_NOT_A_DEAL = re.compile(r"\b(black\s+stars|super\s+eagles|super\s+falcons|bafana|national\s+teams?|sponsorship|sponsors?|"
                         r"smuggl\w+|fake|tap\s+sale|t-bills?|treasury\s+(?:bonds?|bills?)|bond\s+auction|"
                         r"infrastructure\s+bond|FC|forward|striker|midfielder|defender|goalkeeper|winger|coach|transfer\s+window|"
                         r"fighter\s+jets?|warplanes?|helicopters?|weapons?|missiles?|calls?\s+for|urges?|"
                         r"to\s+buy\s+now|stocks?\s+to\s+buy|shares\s+to\s+buy|altcoins?|price\s+prediction|"
                         r"raises?\s+(?:its\s+|the\s+)?(?:\S+\s+)?(?:outlook|forecast|rating|alarm|concerns?|awareness|"
                         r"questions?|prices?|tariffs?|rates?|fears?|hopes?|the\s+bar|bursary|igr|revenue\s+target))\b"
                         r"|\braise[sd]?\s+(?:\S+\s+){0,3}(cap|ceiling|limit|investment|capital|budget|allocation|target|commitment)\s+to\b",
                         re.IGNORECASE)
_VALUATION = re.compile(r"(?i)(?:at\s+(?:an?\s+)?(?P<a>[^,;]{2,25}?)\s+(?:(?:post|pre)-money\s+)?(?:valuation|valorisation)"
                        r"|(?P<d>\S*\d[\d.,]*\s?(?:billion|million|bn|m|b)?)\s+(?:price\s+tag|valuation)"
                        r"|valued\s+at\s+(?P<b>[^,;]{2,25}?)(?=$|[,;.]|\s+(?:in|after|as|following)\b)"
                        r"|valuation\s+of\s+(?P<c>[^,;]{2,25}?)(?=$|[,;.]|\s))")
_CAPEX_AFTER = re.compile(r"^\s*(?:'s\s+)?(?:\S+\s+)?(plant|factory|facility|facilities|project|expansion|hub|office|housing|"
                          r"warehouse|site|refinery|mine|campus|infrastructure|network|schools?|programme|scheme)\b",
                          re.IGNORECASE)
_EQUITY_EVIDENCE = re.compile(r"\b(invest\w*|funding|capital|stake|equity|round|seed|series|raise[sd]?|"
                              r"lève|levée|investit|investe|capta|financing|financement|investimento)\b", re.IGNORECASE)
_PUBLIC_SECTOR = re.compile(r"(?i)\b(government|ministry|treasury|trésor|state|federal|senate|house|parliament|court|"
                            r"police|army|military|council|municipality|county|dgtcp|gouvernement|minist[eè]re|tinubu|"
                            r"president|governor|minister|air\s+force|navy|defen[cs]e\s+force)\b")
_FUND_FOR = re.compile(r"(?i)\bfor\s+(?:its\s+|a\s+|an\s+|the\s+|new\s+)?(?:\S+\s+){0,4}?fund\b")
_FUND_PURPOSE = re.compile(r"\bto\s+(?:back|invest\s+in|support|finance)\s+(?:\S+\s+){0,5}?"
                           r"(businesses|startups|start-ups|companies|smes|entrepreneurs|founders|ventures)\b", re.IGNORECASE)
_DEBT_WORDS = re.compile(r"\b(loan|facility|debt|credit\s+line|bond|sukuk|notes|eurobond|financement\s+bancaire|prêt|"
                         r"financing\s+deals?|debt\s+financing|empréstimo)\b", re.IGNORECASE)
_FUND_WORDS = re.compile(r"\b(fund\s+(?:i{1,3}|iv|v|vi|\d)|first\s+close|final\s+close|fund\s+close|fundraise\s+for\s+its\s+fund|close\s+of\s+(?:its\s+)?fund)\b", re.IGNORECASE)
_LED_BY = re.compile(rf"(?:led|co-led|anchored)\s+by\s+(?P<lead>{NAME})", )
_FROM = re.compile(rf"\bfrom\s+(?P<list>{NAME}(?:\s*,\s*{NAME})*(?:,?\s+and\s+{NAME})?)")
_PARTICIPATION = re.compile(rf"(?:participation\s+from|backed\s+by|from\s+investors\s+(?:including|such\s+as)|investors\s+include|with\s+support\s+from|including)\s+(?P<list>{NAME}(?:\s*,\s*{NAME})*(?:,?\s+and\s+{NAME})?)")
_SPECULATIVE = re.compile(r"\b(talks?|considers?|considering|weighs?|weighing|explores?|exploring|eyes|eyeing|"
                          r"rumou?r\w*|reportedly|potential|could|may|might|seeks?|seeking|looking\s+to|in\s+the\s+running|"
                          r"envisage|pourrait|negocia\w*)\b", re.IGNORECASE)
_FORWARD = re.compile(r"\b(to|will|set\s+to|plans?\s+to|agrees?\s+to|seeks?\s+to|moves?\s+to|aims?\s+to)\s+"
                      r"(acquire|buy|merge|invest|sell|list|raise|close|exit|take|launch)\b|\b(raising|targeting|targets)\b",
                      re.IGNORECASE)
_ANNOUNCED = re.compile(r"\b(to\s+(acquire|buy|merge|invest|sell|list)|agrees?\s+to|agreed\s+to|signs?\s+(deal|agreement)|"
                        r"set\s+to|plans?\s+to|offer\s+for|bid\s+for|announces?\s+(intention|plan)|approves?|approval|"
                        r"launch(es)?\s+(fundraise|fundraising)|files?\s+for)\b", re.IGNORECASE)
_COMPLETED = re.compile(r"\b(completes?|completed|closes?|closed|finali[sz]e[sd]?|concludes?|concluded|raises?|raised|"
                        r"secures?|secured|acquired|bought|merged|sold|exited|lands?|landed|bagged|nets?|netted|"
                        r"invests?|invested|backs?|backed|injects?|injected|lends?|lent|disburses?|disbursed|listed|"
                        r"debuted|debuts?|receives?|received|obtient|obtém|lève|investit|investe|capta|reach(es|ed)\s+(\S+\s+)?(first|final|second)\s+close|"
                        r"gets?|got|bags?|wins?|won|pockets?|pocketed|grabs?|grabbed|snags?|snagged|scoops?|scooped|attracts?|attracted|"
                        r"lists?\s+on|divests?|divested|offloads?|offloaded|clinches|clinched|seals?|sealed|"
                        r"boucle|a\s+lev[ée]|cl[oô]ture|conclut|finalise)\b", re.IGNORECASE)

SECTORS: tuple[tuple[str, str], ...] = (
    ("fintech", r"fintech|payments?|mobile\s+money|wallet|neobank|digital\s+bank|lending\s+app|remittance|bnpl|insurtech|crypto"),
    ("banking", r"\bbank(ing)?\b|microfinance|lender|tier\s+1|deposit"),
    ("insurance", r"insur(ance|er)|reinsur|takaful|assurance"),
    ("energy", r"energy|power|solar|electricity|renewable|wind\s+farm|hydro|utility|grid|mini-grid|off-grid"),
    ("oil_gas", r"\boil\b|\bgas\b|petroleum|refinery|upstream|downstream|lng|crude|oilfield"),
    ("mining", r"mining|\bmine\b|gold|copper|lithium|cobalt|platinum|iron\s+ore|bauxite|manganese"),
    ("telecom", r"telecom|telco|mobile\s+operator|\bmtn\b|airtel|safaricom|vodacom|orange|fibre|fiber|data\s+cent(er|re)|tower"),
    ("agriculture", r"agri|agritech|farm|food\s+security|cocoa|coffee|tea\b|fertili[sz]er|poultry|crop|dairy"),
    ("healthcare", r"health|hospital|pharma|clinic|medical|healthtech|diagnostic|drug"),
    ("logistics", r"logistics|delivery|freight|shipping|supply\s+chain|port\b|trucking|courier|last-mile"),
    ("mobility", r"mobility|ride-hailing|electric\s+vehicle|\bevs?\b|motorbike|e-bike|transport"),
    ("ecommerce_retail", r"e-commerce|ecommerce|retail|marketplace|supermarket|grocery|b2b\s+commerce|fmcg|consumer\s+goods"),
    ("real_estate", r"real\s+estate|property|proptech|housing|reit\b|mortgage"),
    ("infrastructure", r"infrastructure|toll\s+road|airport|railway|rail\b|bridge\b|water\s+utility"),
    ("education", r"edtech|education|school|university|learning"),
    ("media_tech", r"media|software|saas|\bai\b|artificial\s+intelligence|cloud|cybersecurity|gaming|streaming"),
    ("manufacturing", r"manufactur|cement|steel|factory|industrial|plastics|packaging"),
    ("hospitality", r"hotel|hospitality|tourism|restaurant"),
)
_SECTOR_RE = [(name, re.compile(rf"(?:{pat})", re.IGNORECASE)) for name, pat in SECTORS]


def classify_sector(text: str) -> Optional[str]:
    best, hits = None, 0
    for name, rx in _SECTOR_RE:
        n = len(rx.findall(text))
        if n > hits:
            best, hits = name, n
    return best


def _split_names(s: str) -> list[str]:
    parts = re.split(r"\s*,\s*|\s+and\s+|\s*&\s+(?=[A-Z])", s)
    return [n for n in (_clean_name(p) for p in parts) if n]


def extract_deal(title: str, snippet: str = "", *, published: Optional[str] = None,
                 publisher: str = "", url: str = "", country_hint: Optional[str] = None,
                 africa_source: bool = False,
                 rates: Optional[Callable[[str, Optional[int]], Optional[float]]] = None) -> Optional[dict]:
    """A structured deal from one headline (and its snippet), or None if it reports no transaction."""
    title = re.sub(r"\s+", " ", unicodedata.normalize("NFC", title or "")).strip()
    if publisher and title.endswith(" - " + publisher):
        title = title[: -len(publisher) - 3]
    if len(title) < 12:
        return None
    text = f"{title}. {snippet or ''}"

    # A headline may say only that an investor "backs" a company while the source
    # description confirms a completed minority/majority equity investment. In
    # that case, normalize the wording for extraction but preserve the real title
    # and URL in the returned evidence. Do not promote generic endorsements.
    backing = re.match(r"(?is)^(?P<buyer>.+?)\s+backs\s+(?P<target>.+?)\s*$", title)
    explicit_equity_evidence = re.search(
        r"(?i)\b(?:(?:minority|majority|strategic)\s+)?(?:equity\s+)?investment\b|"
        r"\b(?:equity\s+)?stake\b|\bshareholding\b",
        snippet or "",
    )
    if backing and explicit_equity_evidence:
        buyer = backing.group("buyer").strip(" ,.;:'’\"-")
        target = backing.group("target").strip(" ,.;:'’\"-")
        countries = [country.iso2 for country in countries_in_text(text)]
        based = re.search(
            r"(?i)\b((?:[A-Z][A-Za-zÀ-ÿ'’.-]*\s+){0,3}[A-Z][A-Za-zÀ-ÿ'’.-]*)-based\b",
            snippet or "",
        )
        if based:
            for country in countries_in_text(based.group(1)):
                if country.iso2 not in countries:
                    countries.append(country.iso2)
        if buyer and target and countries:
            stage = "completed" if re.search(
                r"(?i)\b(has made|made|completed|has completed|invested|has invested)\b",
                snippet or "",
            ) else "announced"
            control_match = _MAJORITY.search(text)
            deal = {
                "deal_type": "equity_funding",
                "stage": stage,
                "round": None,
                "target": target,
                "buyer": buyer,
                "seller": None,
                "investors": [buyer],
                "amount": None,
                "currency": None,
                "amount_usd": None,
                "stake_pct": None,
                "control": control_match.group(1).lower() if control_match else None,
                "implied_valuation_usd": None,
                "reported_valuation_usd": None,
                "sector": classify_sector(text),
                "country": countries[0],
                "countries": countries,
                "announced": published,
                "headline": title,
                "sources": [{
                    "publisher": publisher, "url": url, "date": published,
                    "title": title, "stage": stage,
                }],
            }
            deal["id"] = deal_id(deal)
            return deal

    if sum(ch.isupper() for ch in title) > 0.6 * sum(ch.isalpha() for ch in title):
        return None                               # ALL-CAPS headlines carry no name boundaries
    # Public-sector calls for private investment are solicitations, not evidence
    # that a transaction has occurred. Keep this narrow so genuine company raises
    # (for example, "X seeks investment") remain eligible for extraction.
    if re.match(
        r"(?i)^\s*(?:FG|federal government|government|ministry(?:\s+of\s+[\w&-]+){0,4})"
        r"\s+seeks?\s+(?:private\s+)?investment\s+in\b",
        title,
    ):
        return None
    if _NOT_A_DEAL.search(title):
        return None
    if title.rstrip().endswith("?") or re.match(r"(?i)(why|how|what|should|could|can|will|is|are|does|do|opinion|analysis|explainer)\b", title):
        return None
    norm = _normalise_case(title)
    match = None
    for deal_type, rx in _PATTERNS:
        m = rx.search(norm)
        if m:
            match = (deal_type, m)
            break
    if match is None:
        return None
    deal_type, m = match
    subj = _clean_name(m.groupdict().get("subj"))
    obj = _clean_name(m.groupdict().get("obj"))
    if not subj and not obj:
        return None

    # "raises" etc. must be about money: an amount or funding word right after the verb.
    if deal_type == "equity_funding" and not m.groupdict().get("obj"):
        after = re.sub(r"(?i)^\s*(?:about|over|around|nearly|almost|some|another|an\s+additional|additional|fresh|new|a\s+further)\s+",
                       "", norm[m.end(): m.end() + 45])
        if not (_AMOUNT_PREFIXED.match(after.lstrip()) or _AMOUNT_SUFFIXED.match(after.lstrip())
                or re.search(r"(?i)^\W*(?:\S+\s+){0,3}?(funding|capital|round|seed|series|investment|"
                             r"financing|fonds|financement|investimento|pre-seed)", after)):
            return None
    # "X backs Y" is an endorsement unless money is attached ("backs Y with $5m").
    if deal_type == "equity_funding" and re.search(r"(?i)(?<!-)\b(backs|backed)\b", m.group(0)) \
            and not re.search(r"(?i)\bwith\s+(?:a\s+)?(?:US\$|\$|€|£|₦|N\d|R\d|KSh|USD|EUR)", text) \
            and not re.search(r"(?i)\b(?:(?:minority|majority|equity|strategic)\s+){0,2}investment\b|\b(?:equity\s+)?stake\b|\bshareholding\b", text):
        return None
    # Capital spending on a plant or project is not a transaction.
    if deal_type == "equity_funding" and m.groupdict().get("obj") and _CAPEX_AFTER.match(norm[m.end():]):
        return None
    vm = _VALUATION.search(title)
    valuation_amounts = parse_amounts(vm.group("a") or vm.group("b") or vm.group("c") or vm.group("d") or "") if vm else []
    deal_title = title[:vm.start()] + title[vm.end():] if vm else title
    # Amounts come from the headline only: a description's figures often refer to something else.
    best = deal_amount(deal_title)
    amounts = [best] if best else []
    amount, currency = amounts[0] if amounts else (None, None)
    if deal_type == "ipo" and amount and not re.search(
            r"(?i)\b(?:(?:rais\w*|offer\w*|ipo)\s+(?:of\s+|worth\s+|up\s+to\s+)?|(?:listing|float)\s+(?:to\s+raise\s+)?)"
            r"(?:US\$|\$|€|£|₦|N\d|R\d|KSh|USD)"
            r"|(?:billion|million|bn|m)\s+(?:ipo|offer\w*|listing|float)\b", deal_title):
        amount = currency = None                 # the figure is a company or asset value, not the offer size

    # Funding wording that is really debt or a fund close.
    backed = _BACKED.match(m.group("subj")) if m.groupdict().get("subj") else None
    if deal_type == "equity_funding" and _DEBT_WORDS.search(title) and not _ROUND.search(title):
        deal_type = "debt_financing"
    if deal_type in ("equity_funding", "debt_financing") and _FUND_WORDS.search(title):
        deal_type = "fund_raise"
    # "X raises $5m" with no amount and no round is too vague to be a deal.
    if deal_type == "equity_funding" and m.groupdict().get("obj") is None and amount is None and not _ROUND.search(text):
        return None

    target = buyer = seller = None
    investors: list[str] = []
    if deal_type in ("acquisition",):
        buyer, target = subj, obj
    elif deal_type == "merger":
        buyer, target = subj, obj
    elif deal_type == "exit":
        seller, target = subj, obj
        buyer = _clean_name(m.groupdict().get("to"))
        raw_obj = (m.groupdict().get("obj") or "").strip()
        place = countries_in_text(raw_obj.split()[0]) if raw_obj else []
        if place and re.search(r"(?i)\b(operations?|business|unit|subsidiary|assets?|arm)$", raw_obj) and subj:
            target = f"{subj} {place[0].name}"         # "Holcim to sell Nigerian operations" -> "Holcim Nigeria"
    if deal_type in ("equity_funding", "fund_raise") and obj and re.search(r"\b(fund|vehicle)(\s+[IVX\d]+)?$", obj, re.IGNORECASE):
        deal_type = "fund_raise"                 # an LP commitment to a fund
        target, investors = obj, [subj] if subj else []
    elif deal_type == "equity_funding":
        if m.groupdict().get("obj"):           # "Investor backs Company"
            buyer, target = subj, obj
            investors = [subj] if subj else []
        else:                                    # "Company raises $X"
            target = subj
    elif deal_type == "debt_financing":
        if re.search(r"\b(lends?|lent|extends?|extended|provides?|provided|approves?|approved|grants?|granted|arranges?|"
                     r"disburses?|backs?|backed|invests?|invested|commits?|committed|finances?|financed|funds?|funded)\b",
                     m.group(0), re.IGNORECASE):
            buyer, target = subj, obj            # lender, borrower
        else:
            target, buyer = subj, obj            # borrower, lender
        withp = _clean_name(m.groupdict().get("with"))
        raw = (m.groupdict().get("subj") or "")
        if withp and _is_lender(subj):
            buyer, target = subj, withp          # "Afreximbank signs a facility with X": Afreximbank lends
        elif " and " in raw:                     # "MIDROC and IFC sign a $80m loan"
            a, b = (_clean_name(x) for x in raw.split(" and ", 1))
            if a and b:
                buyer, target = (a, b) if _is_lender(a) and not _is_lender(b) else (b, a) if _is_lender(b) else (None, None)
                if not target:
                    return None
        if buyer:
            investors = [buyer]
    elif deal_type == "fund_raise" and not target:
        target = subj                            # the fund (or its manager)
        lp = _clean_name(m.groupdict().get("lp"))
        if lp:
            investors = [lp]                     # limited partner / anchor investor
    elif deal_type == "ipo":
        target = subj
    elif deal_type == "joint_venture":
        buyer, target = subj, obj
    # Reject headline-level statistics and product/asset purchases that match a
    # transaction verb but are not private-market transactions. These checks run
    # after party extraction so they can use the complete headline and parsed type.
    if re.search(r"(?i)\b(?:more than|less than|over|under|at least|nearly|almost)\s+\d+(?:[.,]\d+)?\s?%\s+(?:of\s+)?", title) and re.search(r"(?i)\b(?:exports?|imports?|revenue|sales|market share|production)\b", title):
        return None
    if re.search(r"(?i)\b(?:best places to buy|buys? .*? (?:first-ever|first ever) .*? in .+|acquires? the .{0,50}\b(?:car|vehicle|lamborghini|ferrari|jet|yacht)\b)", title):
        return None
    if re.search(r"(?i)\b(?:skills? push|skills? training|educational institutions|sanitary standards|local crafters|refugee empowerment|digital economy|green transition and support small businesses)\b", title) and re.search(r"(?i)\b(?:EU|European Union|South Korea|government|Ecobank)\b", title):
        return None
    if target and target.lower() in _FOREIGN_DEMONYMS:
        named_asset = re.search(
            r"(?i)\b(?:gold|copper|lithium|platinum|iron ore|rare earth|diamond)\s+"
            r"(?:miner|producer|company|developer)\s+(?P<name>[A-Z][A-Z0-9&.-]{1,15})\b",
            title,
        )
        if named_asset:
            target = named_asset.group("name")
    if target and re.fullmatch(r"(?i)(?:more than(?: half)?|less than|the|a|an|growth|economy|pickups?|tractors?|shs\d+[a-z]*|n\$\s?\d+|ai)", target.strip()):
        return None

    # Reject currency fragments and sentence debris captured as the target (e.g. GH¢, Q1, "We").
    # For fund closes, recover the complete named fund rather than keeping only "Fund II".
    if target and re.fullmatch(r"(?i)(?:gh|q\d|1m|pe|vc|we|be|ii|iii|iv|v|vi|vii|viii|ix|x)", target.strip()):
        if deal_type == "fund_raise" and re.fullmatch(r"(?i)(?:ii|iii|iv|v|vi|vii|viii|ix|x)", target.strip()):
            if subj and re.search(r"(?i)\bfund\b", subj):
                target = _clean_name(f"{subj} {target}")
            else:
                fund_name = re.search(r"(?i)(^.{1,100}?\bfund\s+(?:II|III|IV|V|VI|VII|VIII|IX|X|\d+))", title)
                if fund_name:
                    target = _clean_name(fund_name.group(1))
                else:
                    return None
        else:
            return None
    # Broad corporate/public capital expenditure is not a financing transaction unless equity,
    # a fund close, a loan, or an explicit external investment instrument is stated.
    if deal_type == "equity_funding" and re.search(r"(?i)\b(?:invests?|invested|spends?|spent)\b", title):
        capex = re.search(r"(?i)\b(?:infrastructure replacement|road sector|water treatment plants?|new feeders?|substations?|connectivity|service quality|outgrower|restoring|rehabilitat\w*|replacement across|capital expenditure|capex)\b", title)
        external_instrument = re.search(r"(?i)\b(?:equity|stake|shares?|venture capital|funding round|series [A-H]|seed round|loan|credit facility|debt financing|fund close|fund raises?)\b", title)
        if capex and not external_instrument:
            return None
    # Exclude non-dilutive grants, ordinary procurement contracts, and aggregate reports.
    if re.search(r"(?i)\bgrant\b", title) and not re.search(r"(?i)\b(?:loan|debt financing|credit facility)\b", title):
        return None
    if re.search(r"(?i)\b(?:lands?|wins?)\s+\$[\d.,]+[mbn]\b.{0,40}\b(?:rail|railway|locomotive|equipment|supply|procurement|contract)\s+deal\b", title):
        return None
    if re.search(r"(?i)\b(?:acquires?|buys?)\s+(?:six|five|four|three|\d+)\s+(?:new\s+)?(?:Boeing|Airbus|aircraft|airplanes?|planes?|vehicles?)\b", title):
        return None
    if re.search(r"(?i)\b(?:report|study|analysis)\b.*\b(?:startups?|companies)\s+(?:raise|raised|secure|secured|receive|received)\b.*\b(?:in|during)\s+20\d{2}\b", title) or re.search(r"(?i)\b(?:six|five|several|multiple)\s+(?:African|Nigerian|African tech)?\s*startups?\s+(?:secure|secured|raise|raised|receive|received)\b", title):
        return None
    if re.search(r"(?i)\b(?:ministry|government|department)\b", title) and re.search(r"(?i)\bbacks? private investment\b|\b(?:skills push|public policy|economic reforms)\b", title):
        return None
    if re.search(r"(?i)^cross river secures \$[\d.,]+m oil palm investment", title):
        return None
    # Weekly sector totals and public-sector programmes are not individual company deals.
    if re.search(r"(?i)\braises?\s+.{0,35}\bin week\s+\d+\b", title):
        return None
    if re.search(r"(?i)\b(?:skills? push|skills? training|educational institutions|sanitary standards|local crafters|refugee empowerment|digital economy|green transition and support small businesses|budget support loan|economic and green reforms|governance reforms|urban infrastructure|water security|economic reforms|TVET sector)\b", title) and re.search(r"(?i)\b(?:EU|European Union|South Korea|Canada|government|Ecobank|AfDB|African Development Bank|OPEC Fund|New Development Bank|Afreximbank)\b", title):
        return None
    if not target and not buyer:
        return None
    raw_subj = (m.groupdict().get("subj") or "").strip()
    if raw_subj and re.search(r"(?i)\b(air\s+force|navy|army|military|government|ministry|treasury|president|governor|"
                              r"minister|parliament|senate)\b", raw_subj):
        return None                              # state purchases and spending, not transactions
    # "Loan for Air Côte d'Ivoire's Airbus purchase": the possessor is the counterparty.
    raw_obj = (m.groupdict().get("obj") or "").strip()
    if raw_obj and re.search(r"(?:'s|’s)\s+\S", raw_obj) and re.match(
            r"(?i)\s+(purchase|acquisition|expansion|project|operations|unit|business|assets|plant|fleet)\b", norm[m.end():]):
        owner = _clean_name(re.split(r"(?:'s|’s)\s+", raw_obj, maxsplit=1)[0])
        if owner:
            if target == obj:
                target = owner
            obj = owner
    if raw_subj and not subj and (_is_place(raw_subj.split("'")[0].split("’")[0]) or _PUBLIC_SECTOR.search(raw_subj)):
        return None                              # governments and states: public spending, not deals
    if target and re.search(r"(?i)\b(central\s+bank|banque\s+centrale|reserve\s+bank|ministry|government|treasury)\b", target):
        return None                              # lending to a state is sovereign finance, not a company deal
    if deal_type in ("acquisition", "merger", "exit", "ipo", "fund_raise") and not target:
        return None                              # who or what changed hands must be named
    if deal_type == "fund_raise" and amount is None and not re.search(r"(?i)\b(first|final|second|third|interim|hard|\d(?:st|nd|rd|th))\s+close", title):
        return None
    # Bonds placed on a regional market are debt.
    if deal_type == "equity_funding" and re.search(r"(?i)\bsur\s+le\s+march[ée]\s+(?:de\s+l['’]\s*)?(?:uemoa|umoa|financier|obligataire|régional)"
                                                   r"|\b(?:à|a)\s+la\s+bourse\s+de\s+luxembourg|\beurobond|\bobligataire", title):
        deal_type = "debt_financing"
    # Financing needs evidence beyond a verb: an amount, or a named counterparty plus an investment word.
    if deal_type in ("equity_funding", "debt_financing"):
        if amount is None and not (_ROUND.search(text) or (obj and _EQUITY_EVIDENCE.search(text))):
            return None
        if deal_type == "equity_funding" and not target:
            return None                          # "X invests $Ym" with no investee: capital spending
        if deal_type == "equity_funding" and not m.groupdict().get("obj") and (_FUND_PURPOSE.search(title)
                                                                            or _FUND_FOR.search(title)):
            deal_type = "fund_raise"             # "raises $169m to back South African businesses"

    if backed:
        for n in _split_names(backed.group(1)):
            if n not in investors:
                investors.append(n)
    if deal_type in ("equity_funding", "debt_financing"):
        fm = _FROM.search(_normalise_case(title))
        if fm:
            for n in _split_names(fm.group("list")):
                if n not in investors and n != target:
                    investors.append(n)
            if not buyer and investors:
                buyer = investors[0]
    lead = _LED_BY.search(_normalise_case(text))
    if lead:
        lead_name = _clean_name(lead.group("lead"))
        if lead_name and lead_name not in investors:
            investors.insert(0, lead_name)
        if deal_type == "equity_funding" and not buyer and lead_name:
            buyer = lead_name
    for pm in _PARTICIPATION.finditer(_normalise_case(text)):
        for n in _split_names(pm.group("list")):
            if n not in investors and n != target:
                investors.append(n)
    investors = investors[:12]

    stake = None
    sm = _STAKE.search(text)
    if sm:
        stake = _to_float(sm.group(1))
        if stake is not None and not (0 < stake <= 100):
            stake = None
    control = _MAJORITY.search(text)

    year = int(published[:4]) if published and published[:4].isdigit() else None
    usd = to_usd(amount, currency, year, rates) if amount and currency else None
    if usd is not None and usd < 50_000:
        return None                              # donations and micro-grants, not transactions
    implied = round(usd / (stake / 100), 0) if usd and stake and deal_type in ("acquisition", "equity_funding", "exit") else None
    reported_valuation = (to_usd(valuation_amounts[0][0], valuation_amounts[0][1], year, rates)
                          if valuation_amounts else None)

    clause = norm[max(0, m.start() - 25): m.end()]
    if _SPECULATIVE.search(clause):
        stage = "rumoured"
    elif _FORWARD.search(clause):
        stage = "announced"
    elif _COMPLETED.search(clause):
        stage = "completed"
    elif _ANNOUNCED.search(clause):
        stage = "announced"
    elif _COMPLETED.search(title):
        stage = "completed"
    else:
        stage = "announced"

    rnd = _ROUND.search(text)
    countries = [c.iso2 for c in countries_in_text(text)]
    # Placement needs the text itself: a named African country, "Africa", or an Africa-only deal outlet.
    # A search's country is only a hint (Google returns foreign stories for country queries).
    if not countries and not (africa_source or re.search(r"\bafrica|\bafrique|\báfrica", text, re.IGNORECASE)):
        return None

    # A final series numeral is not a fund name; recover the named fund from the headline.
    if target and re.fullmatch(r"(?i)(?:ii|iii|iv|v|vi|vii|viii|ix|x)", target.strip()):
        fund_marker = re.search(r"(?i)fund", title)
        if fund_marker:
            target = _clean_name(f"{title[:fund_marker.end()]} {target}")
        elif deal_type == "fund_raise":
            return None

    deal = {
        "deal_type": deal_type,
        "stage": stage,
        "round": re.sub(r"\s+", " ", rnd.group(1).lower()) if rnd and deal_type in ("equity_funding",) else None,
        "target": target,
        "buyer": buyer,
        "seller": seller,
        "investors": investors,
        "amount": amount,
        "currency": currency,
        "amount_usd": usd,
        "stake_pct": stake,
        "control": control.group(1).lower() if control else None,
        "implied_valuation_usd": implied,
        "reported_valuation_usd": reported_valuation,
        "sector": classify_sector(text),
        "country": countries[0] if countries else None,
        "countries": countries,
        "announced": published,
        "headline": title,
        "sources": [{"publisher": publisher, "url": url, "date": published, "title": title, "stage": stage}],
    }
    deal["id"] = deal_id(deal)
    return deal


def deal_id(deal: dict) -> str:
    """Same transaction, same id: type, target (or buyer) and month."""
    # Some fund-raise patterns capture the trailing series numeral as the target.
    target = str(deal.get("target") or "")
    headline = str(deal.get("headline") or "")
    if deal.get("deal_type") == "fund_raise" and re.fullmatch(r"(?i)(?:ii|iii|iv|v|vi|vii|viii|ix|x)", target.strip()):
        fund_marker = re.search(r"(?i)fund", headline)
        if fund_marker:
            deal["target"] = _clean_name(f"{headline[:fund_marker.end()]} {target}")
    who = normalise_name(deal.get("target") or deal.get("buyer"))
    month = (deal.get("announced") or "")[:7]
    # Acquisition, merger, funding, financing and exit reports about one company in one month are
    # usually one transaction seen from different sides.
    kind = "txn" if deal["deal_type"] in ("acquisition", "merger", "equity_funding", "debt_financing", "exit") \
        else deal["deal_type"]
    return hashlib.sha1(f"{kind}|{who}|{month}".encode()).hexdigest()[:16]


_STAGE_RANK = {"rumoured": 0, "announced": 1, "completed": 2}


def _merged_type(a: dict, b: dict) -> str:
    """One type for two reports of a transaction: control beats a stake, debt beats generic funding."""
    types = {a["deal_type"], b["deal_type"]}
    if len(types) == 1:
        return a["deal_type"]
    stake = a.get("stake_pct") or b.get("stake_pct")
    control = a.get("control") or b.get("control")
    if "acquisition" in types or "merger" in types:
        if control in ("majority", "controlling") or (stake and stake >= 50) or "exit" in types and not stake:
            return "merger" if "merger" in types else "acquisition"
        if "equity_funding" in types or (stake and stake < 50):
            return "equity_funding"
        return "merger" if "merger" in types else "acquisition"
    if "debt_financing" in types:
        return "debt_financing"
    return a["deal_type"]


def merge(existing: dict, new: dict) -> dict:
    """Combine two reports of one deal: keep known fields, the most advanced stage, every source."""
    out = dict(existing)
    for k, v in new.items():
        if k in ("sources", "investors", "countries", "id"):
            continue
        if out.get(k) in (None, "", []) and v not in (None, "", []):
            out[k] = v
    out["deal_type"] = _merged_type(existing, new)
    if _STAGE_RANK.get(new.get("stage"), 0) > _STAGE_RANK.get(out.get("stage"), 0):
        out["stage"] = new["stage"]
    out["investors"] = list(dict.fromkeys((existing.get("investors") or []) + (new.get("investors") or [])))[:12]
    out["countries"] = list(dict.fromkeys((existing.get("countries") or []) + (new.get("countries") or [])))
    urls = {s.get("url") for s in existing.get("sources") or []}
    out["sources"] = list(existing.get("sources") or []) + [s for s in new.get("sources") or [] if s.get("url") not in urls]
    if new.get("announced") and (not out.get("announced") or new["announced"] < out["announced"]):
        out["announced"] = new["announced"]
    return out


def merge_all(deals: Iterable[dict], into: Optional[dict[str, dict]] = None) -> dict[str, dict]:
    store = dict(into or {})
    for d in deals:
        store[d["id"]] = merge(store[d["id"]], d) if d["id"] in store else d
    return store


# ── Local store ───────────────────────────────────────────────────────────────

def load_deals() -> dict[str, dict]:
    return load_json(DEALS_PATH, dict)


def save_deals(store: dict[str, dict]) -> None:
    save_json(DEALS_PATH, store)


# ── Queries ───────────────────────────────────────────────────────────────────

def search(deals: Iterable[dict], q: str = "", country: Optional[str] = None, deal_type: Optional[str] = None,
           sector: Optional[str] = None, since: Optional[str] = None, until: Optional[str] = None,
           investor: Optional[str] = None, min_usd: Optional[float] = None, limit: int = 100) -> list[dict]:
    """Deals matching every given filter, newest first."""
    qn = normalise_name(q)
    inv = normalise_name(investor) if investor else ""
    c = get_country(country) if country else None
    out = []
    for d in deals:
        if c and c.iso2 not in (d.get("countries") or [d.get("country")]):
            continue
        if deal_type and d.get("deal_type") != deal_type:
            continue
        if sector and d.get("sector") != sector:
            continue
        if since and (d.get("announced") or "") < since:
            continue
        if until and (d.get("announced") or "9999") > until:
            continue
        if min_usd and (d.get("amount_usd") or 0) < min_usd:
            continue
        if inv and not any(inv in normalise_name(n) for n in [d.get("buyer"), *(d.get("investors") or [])] if n):
            continue
        if qn:
            hay = normalise_name(" ".join(filter(None, [d.get("target"), d.get("buyer"), d.get("seller"),
                                                        d.get("headline"), *(d.get("investors") or [])])))
            if not all(t in hay for t in qn.split()):
                continue
        out.append(d)
    out.sort(key=lambda d: d.get("announced") or "", reverse=True)
    return out[:limit]


def _region(iso2: Optional[str]) -> Optional[str]:
    c = get_country(iso2) if iso2 else None
    return c.region if c else None


def comparables(deals: Iterable[dict], *, sector: Optional[str] = None, country: Optional[str] = None,
                deal_type: Optional[str] = None, amount_usd: Optional[float] = None,
                exclude_id: Optional[str] = None, limit: int = 15) -> dict:
    """
    Deals most like the reference (sector, country, type, size), with a transparent
    similarity score, plus size and implied-valuation statistics over the matches.
    """
    region = _region(country)
    scored = []
    for d in deals:
        if d.get("id") == exclude_id:
            continue
        score, why = 0.0, []
        if sector and d.get("sector") == sector:
            score += 3; why.append("same sector")
        if deal_type and (d.get("deal_type") == deal_type or
                          {deal_type, d.get("deal_type")} <= {"acquisition", "merger"}):
            score += 2; why.append("same deal type")
        if country and country in (d.get("countries") or []):
            score += 2; why.append("same country")
        elif region and _region(d.get("country")) == region:
            score += 1; why.append("same region")
        if amount_usd and d.get("amount_usd"):
            ratio = d["amount_usd"] / amount_usd
            if 1 / 3 <= ratio <= 3:
                score += 2; why.append("similar size")
            elif 0.1 <= ratio <= 10:
                score += 1; why.append("same order of magnitude")
        if score >= 3:
            scored.append({**d, "similarity": score, "why": why})
    scored.sort(key=lambda d: (d["similarity"], d.get("announced") or ""), reverse=True)
    top = scored[:limit]
    sizes = sorted(d["amount_usd"] for d in top if d.get("amount_usd"))
    vals = sorted(d["implied_valuation_usd"] for d in top if d.get("implied_valuation_usd"))

    def stats(xs: list[float]) -> Optional[dict]:
        if not xs:
            return None
        q = statistics.quantiles(xs, n=4) if len(xs) >= 2 else [xs[0]] * 3
        return {"n": len(xs), "min": xs[0], "p25": round(q[0]), "median": round(statistics.median(xs)),
                "p75": round(q[2]), "max": xs[-1]}

    return {"reference": {"sector": sector, "country": country, "deal_type": deal_type, "amount_usd": amount_usd},
            "deals": top, "size_usd": stats(sizes), "implied_valuation_usd": stats(vals),
            "method": "similarity = 3 same sector + 2 same type + 2 same country (1 same region) "
                      "+ 2 within 3x size (1 within 10x); deals scoring 3 or more"}
