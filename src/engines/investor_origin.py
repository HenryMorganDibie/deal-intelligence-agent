"""
Where a deal's money comes from: the home countries of its investors, lenders and buyers.

Two kinds of evidence, both from what is already stored with the deal:
- the investor registry's head office ("Washington, DC, United States" for IFC, "London, United Kingdom" for BII);
- the headline's own description of a party ("US-based Visa", "UAE's AD Ports", "French investor Meridiam",
  "Japanese trading house Sumitomo").

Only the money side counts: the company receiving the investment is African by construction, and a target's
nationality says nothing about who invested. A party with neither kind of evidence is left unplaced rather than
guessed, so a brief on "US investors" lists deals that verifiably involve one.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from src.data import africa_countries as ac

# Investor home countries offered outside Africa: ISO code -> (name, words a headline uses for it).
FOREIGN: dict[str, tuple[str, tuple[str, ...]]] = {
    "US": ("United States", ("US", "U.S.", "USA", "American", "United States")),
    "GB": ("United Kingdom", ("UK", "U.K.", "British", "United Kingdom", "Britain")),
    "FR": ("France", ("French", "France")),
    "DE": ("Germany", ("German", "Germany")),
    "NL": ("Netherlands", ("Dutch", "Netherlands")),
    "CH": ("Switzerland", ("Swiss", "Switzerland")),
    "SE": ("Sweden", ("Swedish", "Sweden")),
    "NO": ("Norway", ("Norwegian", "Norway")),
    "DK": ("Denmark", ("Danish", "Denmark")),
    "BE": ("Belgium", ("Belgian", "Belgium")),
    "LU": ("Luxembourg", ("Luxembourg",)),
    "ES": ("Spain", ("Spanish", "Spain")),
    "IT": ("Italy", ("Italian", "Italy")),
    "CA": ("Canada", ("Canadian", "Canada")),
    "AE": ("United Arab Emirates", ("UAE", "Emirati", "United Arab Emirates", "Abu Dhabi", "Dubai")),
    "SA": ("Saudi Arabia", ("Saudi", "Saudi Arabia")),
    "QA": ("Qatar", ("Qatari", "Qatar")),
    "CN": ("China", ("Chinese", "China")),
    "JP": ("Japan", ("Japanese", "Japan")),
    "IN": ("India", ("Indian", "India")),
    "SG": ("Singapore", ("Singaporean", "Singapore")),
    "KR": ("South Korea", ("Korean", "South Korea")),
    "TR": ("Turkey", ("Turkish", "Turkey", "Türkiye")),
}
_BY_NAME = {name.lower(): code for code, (name, _) in FOREIGN.items()}
# Head offices of companies and groups that invest but are companies first (MTN, Old Mutual, Naspers). They stay out of
# the investor registry, which other features read as "this name is an investor, not a company".
COMPANY_HOMES: dict[str, str] = {
    "Goldman Sachs": "New York, United States",
    "Harith General Partners": "Johannesburg, South Africa",
    "Harith": "Johannesburg, South Africa",
    "Stanlib": "Johannesburg, South Africa",
    "Old Mutual": "Johannesburg, South Africa",
    "Old Mutual Limited": "Johannesburg, South Africa",
    "Sanlam": "Cape Town, South Africa",
    "Sanlam Group": "Cape Town, South Africa",
    "Google": "Mountain View, United States",
    "Alphabet": "Mountain View, United States",
    "Microsoft": "Redmond, United States",
    "Visa": "San Francisco, United States",
    "Visa Inc": "San Francisco, United States",
    "Mastercard": "Purchase, New York, United States",
    "Uber": "San Francisco, United States",
    "Robinhood Ventures": "Menlo Park, United States",
    "Naspers": "Cape Town, South Africa",
    "Prosus": "Amsterdam, Netherlands",
    "Danone": "Paris, France",
    "Orange": "Paris, France",
    "Orange Group": "Paris, France",
    "Orange SA": "Paris, France",
    "QatarEnergy": "Doha, Qatar",
    "Sumitomo Corporation": "Tokyo, Japan",
    "Sumitomo": "Tokyo, Japan",
    "Mitsui & Co": "Tokyo, Japan",
    "Mitsui": "Tokyo, Japan",
    "Toyota Tsusho": "Nagoya, Japan",
    "Asahi Group": "Tokyo, Japan",
    "Asahi": "Tokyo, Japan",
    "Epiroc": "Stockholm, Sweden",
    "FLSmidth": "Copenhagen, Denmark",
    "MTN Group": "Johannesburg, South Africa",
    "Vodacom": "Johannesburg, South Africa",
    "Vodacom Group": "Johannesburg, South Africa",
    "Dangote Group": "Lagos, Nigeria",
    "Dangote": "Lagos, Nigeria",
    "Dangote Industries": "Lagos, Nigeria",
    "Amsons Group": "Dar es Salaam, Tanzania",
    "Amsons": "Dar es Salaam, Tanzania",
    "Wafa Assurance": "Casablanca, Morocco",
    "Al Mada": "Casablanca, Morocco",
    "Al Mada Ventures": "Casablanca, Morocco",
}

# International institutions belong to no one country: IFC sits in Washington and the EBRD in London, but neither
# is an American or British investor. National development banks (BII, Proparco, DFC) do count for their country.
_INTERNATIONAL = {"International Finance Corporation", "MIGA", "World Bank"}

# Countries set in the investor_homes table (the owner's review list and the article reader), by normalised name.
# A None country means the owner marked the investor as belonging to no single country. Loaded by the API.
_homes: dict[str, Optional[str]] = {}


def use_homes(rows: Iterable[dict]) -> None:
    """Install the investor_homes rows: [{name_key, country}, ...]."""
    global _homes
    _homes = {str(r["name_key"]): r.get("country") for r in rows if r.get("name_key")}


def name_key(name: str) -> str:
    from src.engines.deals import normalise_name
    return normalise_name(name)


# The parties that put money in; the target is excluded on purpose.
_MONEY_ROLES = {"investor", "lender", "acquirer", "buyer", "lp"}


def country_code(value: Optional[str]) -> Optional[str]:
    """An investor home country from an ISO code or a name: any of FOREIGN, or an African country."""
    v = (value or "").strip()
    if not v:
        return None
    if v.upper() in FOREIGN:
        return v.upper()
    if v.lower() in _BY_NAME:
        return _BY_NAME[v.lower()]
    african = ac.get(v)
    if african:
        return african.iso2
    named = ac.countries_in_text(v)
    return named[0].iso2 if len(named) == 1 and len(v) <= 40 else None


def country_name(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    if code in FOREIGN:
        return FOREIGN[code][0]
    african = ac.get(code)
    return african.name if african else None


def _hq_country(hq: Optional[str]) -> Optional[str]:
    """The country of a registry head office written "City, Country"."""
    if not hq:
        return None
    return country_code(hq.split(",")[-1].strip())


def _company_home(name: str) -> Optional[str]:
    from src.engines.deals import normalise_name
    key = normalise_name(name)
    return next((hq for n, hq in COMPANY_HOMES.items() if normalise_name(n) == key), None)


# Cities that stand for a country in "London-based X" or "based in San Francisco".
_CITIES: dict[str, str] = {
    "London": "GB", "Edinburgh": "GB", "New York": "US", "San Francisco": "US", "Silicon Valley": "US", "Boston": "US",
    "Washington": "US", "Palo Alto": "US", "Menlo Park": "US", "Austin": "US", "Chicago": "US", "Los Angeles": "US",
    "Paris": "FR", "Berlin": "DE", "Munich": "DE", "Hamburg": "DE", "Frankfurt": "DE", "Amsterdam": "NL",
    "The Hague": "NL", "Zurich": "CH", "Geneva": "CH", "Stockholm": "SE", "Oslo": "NO", "Copenhagen": "DK",
    "Brussels": "BE", "Madrid": "ES", "Barcelona": "ES", "Milan": "IT", "Rome": "IT", "Toronto": "CA", "Montreal": "CA",
    "Dubai": "AE", "Abu Dhabi": "AE", "Riyadh": "SA", "Jeddah": "SA", "Doha": "QA", "Beijing": "CN", "Shanghai": "CN",
    "Shenzhen": "CN", "Tokyo": "JP", "Mumbai": "IN", "Bengaluru": "IN", "Bangalore": "IN", "New Delhi": "IN",
    "Singapore": "SG", "Seoul": "KR", "Istanbul": "TR",
}
_PLACE = r"(?P<place>[A-Z][\w'’.-]*(?:\s+[A-Z][\w'’.-]*){0,2})"


def place_country(place: str) -> Optional[str]:
    """The country a place phrase names: a country, a nationality, a known city, or an African country or city."""
    p = place.strip(" ,.")
    if p in _CITIES:
        return _CITIES[p]
    for code, (_, words) in FOREIGN.items():
        if p in words:
            return code
    found = ac.countries_in_text(p)
    return found[0].iso2 if len(found) == 1 else None


def _described_countries(text: str, party: str) -> set[str]:
    """Countries a sentence gives a party by description: "Lagos-based X", "X, a London-based fund",
    "X, based in Paris", "X, a French investor"."""
    p = re.escape(party)
    out: set[str] = set()
    patterns = (
        rf"{_PLACE}-(?:based|headquartered)\s+(?:(?:[a-z][\w-]*|VC|PE)\s+){{0,4}}{p}\b",
        rf"\b{p},?\s+(?:an?|the)\s+(?:[\w-]+\s+){{0,5}}?{_PLACE}-(?:based|headquartered)\b",
        rf"\b{p},?\s+(?:(?:an?|the)\s+(?:[\w-]+\s+){{0,5}}?)?(?:based|headquartered)\s+in\s+{_PLACE}",
    )
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            code = place_country(m.group("place"))
            if code:
                out.add(code)
    for m in re.finditer(rf"\b{p},\s+(?:an?|the)\s+(?P<place>[A-Z][\w'’-]+)\s+(?:[a-z][\w-]*\s+){{0,3}}"
                         r"(?:investor|fund|firm|bank|lender|group|company|manager|investment)", text):
        code = place_country(m.group("place"))
        if code:
            out.add(code)
    return out


def _headline_countries(headline: str, party: str) -> set[str]:
    """Countries a headline attaches to one party: "US-based X", "UAE's X", "French investor X"."""
    out: set[str] = set()
    p = re.escape(party)
    for code, (_, words) in FOREIGN.items():
        for w in words:
            word = re.escape(w)
            # The descriptor right before the name, allowing up to three role words between
            # ("Japanese trading house Sumitomo", "US investment firm Helios").
            pattern = (rf"(?<![\w.]){word}(?:['’]s|-based|-headquartered|-listed)?\s+(?:[a-z][\w-]*\s+){{0,3}}{p}\b")
            if re.search(pattern, headline):
                out.add(code)
                break
    return out


def deal_investor_countries(deal: dict) -> set[str]:
    """ISO codes of the home countries of a deal's investors, lenders and buyers, where known."""
    from src.engines import investors
    headline = " ".join(filter(None, [deal.get("headline"),
                                      *[(s or {}).get("title") for s in (deal.get("sources") or [])][:5]]))
    # The sentence each investor was read from in the article (round_parties), where one was stored.
    sentences: dict[str, str] = {}
    for e in deal.get("investor_evidence") or []:
        if isinstance(e, dict) and e.get("name") and e.get("sentence"):
            k = name_key(str(e["name"]))
            sentences[k] = (sentences.get(k, "") + " " + str(e["sentence"]))[:2000]
    out: set[str] = set()
    for name, role in investors.parties(deal):
        if role not in _MONEY_ROLES:
            continue
        key = name_key(name)
        if key in _homes:                              # the owner's or the article reader's answer decides
            if _homes[key]:
                out.add(_homes[key])
            continue
        entry = investors.registry_entry(name)
        if entry and (entry.kind == "multilateral" or entry.name in _INTERNATIONAL):
            continue
        code = _hq_country(entry.hq) if entry else _hq_country(_company_home(name))
        if code:
            out.add(code)
        if headline:
            out |= _headline_countries(headline, name) | _described_countries(headline, name)
        if key in sentences:
            out |= _headline_countries(sentences[key], name) | _described_countries(sentences[key], name)
    return out


def from_country(deals: Iterable[dict], code: str) -> list[dict]:
    """The deals with at least one investor, lender or buyer from the given country."""
    return [d for d in deals if code in deal_investor_countries(d)]


def money_parties(deal: dict) -> list[str]:
    from src.engines import investors
    return [name for name, role in investors.parties(deal) if role in _MONEY_ROLES]


def unplaced_investors(deals: Iterable[dict], limit: int = 100) -> list[dict]:
    """Investors with no known home country, most frequent first, with a sample headline: the owner's review list."""
    from src.engines import investors
    counts: dict[str, dict] = {}
    for d in deals:
        for name in money_parties(d):
            key = name_key(name)
            if not key or key in _homes:
                continue
            entry = investors.registry_entry(name)
            if entry and (entry.kind == "multilateral" or entry.name in _INTERNATIONAL or _hq_country(entry.hq)):
                continue
            if _hq_country(_company_home(name)):
                continue
            if deal_investor_countries({**d, "buyer": name, "investors": [], "deal_type": "equity_funding"}):
                continue                                # the headline already places this party
            row = counts.setdefault(key, {"name_key": key, "name": name, "deals": 0, "example": d.get("headline")})
            row["deals"] += 1
    return sorted(counts.values(), key=lambda r: (-r["deals"], r["name"].lower()))[:limit]


# ── Reading source articles (weekly job) ─────────────────────────────────────

USER_AGENT = "DealIntelligence/1.0 (+https://deal-intelligence.app)"


def article_sentences(html: str, party: str) -> list[str]:
    """The sentences of an article page that mention the party."""
    from src.company_live import _Page
    page = _Page("https://example.invalid/")
    try:
        page.feed(html[:2_000_000])
    except Exception:                               # noqa: BLE001 - a malformed page yields nothing
        return []
    text = re.sub(r"\s+", " ", page.text())
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if party in s][:12]


def home_from_article(html: str, party: str) -> Optional[tuple[str, str]]:
    """(country, sentence) when the article describes the party's home unambiguously, else None."""
    found: dict[str, str] = {}
    for sentence in article_sentences(html, party):
        for code in _described_countries(sentence, party) | _headline_countries(sentence, party):
            found.setdefault(code, sentence)
    if len(found) != 1:                             # nothing, or conflicting descriptions: leave it to the owner
        return None
    code, sentence = next(iter(found.items()))
    return code, sentence[:400]


def read_articles(deals: Iterable[dict], fetch, record, max_fetches: int = 200) -> dict:
    """For investors with no known home, read their deals' source articles (fetch(url) -> html or None; the caller
    resolves news links and applies the publisher's robots rules) and record unambiguous descriptions with record(...)."""
    fetched = recorded = 0
    done: set[str] = set()
    for d in deals:
        parties = [n for n in money_parties(d) if name_key(n) not in _homes and name_key(n) not in done]
        parties = [n for n in parties if not deal_investor_countries({**d, "buyer": n, "investors": [],
                                                                      "deal_type": "equity_funding"})]
        if not parties:
            continue
        for src in (d.get("sources") or [])[:3]:
            url = (src or {}).get("url") or ""
            if not url.startswith("http"):
                continue
            if fetched >= max_fetches:
                return {"fetched": fetched, "recorded": recorded, "stopped": "fetch limit"}
            html = fetch(url)
            fetched += 1
            if not html:
                continue
            for party in list(parties):
                hit = home_from_article(html, party)
                if hit:
                    record(name_key(party), party, hit[0], hit[1], url)
                    recorded += 1
                    done.add(name_key(party))
                    parties.remove(party)
            if not parties:
                break
    return {"fetched": fetched, "recorded": recorded}
