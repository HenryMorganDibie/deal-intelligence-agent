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
# International institutions belong to no one country: IFC sits in Washington and the EBRD in London, but neither
# is an American or British investor. National development banks (BII, Proparco, DFC) do count for their country.
_INTERNATIONAL = {"International Finance Corporation", "MIGA", "World Bank"}

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
    out: set[str] = set()
    for name, role in investors.parties(deal):
        if role not in _MONEY_ROLES:
            continue
        entry = investors.registry_entry(name)
        if entry and (entry.kind == "multilateral" or entry.name in _INTERNATIONAL):
            continue
        code = _hq_country(entry.hq) if entry else None
        if code:
            out.add(code)
        if headline:
            out |= _headline_countries(headline, name)
    return out


def from_country(deals: Iterable[dict], code: str) -> list[dict]:
    """The deals with at least one investor, lender or buyer from the given country."""
    return [d for d in deals if code in deal_investor_countries(d)]
