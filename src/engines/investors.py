"""
Investors, funds, LPs and GP activity, built from the deals database.

Every party in a deal gets a role:
  investor   equity investor in a funding round (lead or participant)
  lender     provider of a loan, facility or bond
  acquirer   buyer in an acquisition or merger
  seller     seller in an exit or divestment
  lp         limited partner / anchor commitment to a fund
  gp         fund manager raising or closing a fund

A profile aggregates one party's deals: counts by role, disclosed US dollars,
sectors, countries, stages, co-investors and the most recent transactions.
A curated registry of Africa-focused investors supplies type, headquarters and
name variants ("BII" and "CDC Group" are British International Investment), so
reports under different names land on one profile.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional

from src.engines.deals import normalise_name


@dataclass(frozen=True)
class Investor:
    name: str
    kind: str                  # dfi, multilateral, private_equity, private_credit, venture_capital, growth, impact,
                               # sovereign, pension, bank, foundation, corporate_venture, accelerator
    hq: str
    aliases: tuple[str, ...] = ()


REGISTRY: tuple[Investor, ...] = (
    # Development finance institutions and multilaterals
    Investor("International Finance Corporation", "dfi", "Washington, DC, United States", ("IFC", "International Financing Corporation")),
    Investor("British International Investment", "dfi", "London, United Kingdom", ("BII", "CDC Group", "CDC")),
    Investor("Proparco", "dfi", "Paris, France"),
    Investor("FMO", "dfi", "The Hague, Netherlands", ("Dutch entrepreneurial development bank",)),
    Investor("Norfund", "dfi", "Oslo, Norway"),
    Investor("Swedfund", "dfi", "Stockholm, Sweden"),
    Investor("Finnfund", "dfi", "Helsinki, Finland"),
    Investor("DEG", "dfi", "Cologne, Germany", ("DEG - Deutsche Investitions- und Entwicklungsgesellschaft",)),
    Investor("U.S. International Development Finance Corporation", "dfi", "Washington, DC, United States",
             ("DFC", "OPIC", "Overseas Private Investment Corporation")),
    Investor("European Investment Bank", "multilateral", "Luxembourg", ("EIB",)),
    Investor("African Development Bank", "multilateral", "Abidjan, Côte d'Ivoire", ("AfDB", "BAD", "Banque africaine de développement")),
    Investor("Afreximbank", "multilateral", "Cairo, Egypt", ("African Export-Import Bank",)),
    Investor("Africa Finance Corporation", "multilateral", "Lagos, Nigeria", ("AFC",)),
    Investor("Africa50", "multilateral", "Casablanca, Morocco", ("Africa50 Infrastructure Acceleration Fund",)),
    Investor("Shelter Afrique", "multilateral", "Nairobi, Kenya"),
    Investor("Trade and Development Bank", "multilateral", "Nairobi, Kenya", ("TDB Group", "TDB")),
    Investor("Islamic Development Bank", "multilateral", "Jeddah, Saudi Arabia", ("IsDB",)),
    Investor("AgDevCo", "dfi", "London, United Kingdom"),
    Investor("European Bank for Reconstruction and Development", "multilateral", "London, United Kingdom", ("EBRD",)),
    Investor("KfW", "dfi", "Frankfurt, Germany", ("KfW Development Bank", "KfW Entwicklungsbank")),
    Investor("Agence Française de Développement", "dfi", "Paris, France", ("AFD",)),
    Investor("BIO", "dfi", "Brussels, Belgium", ("Belgian Investment Company for Developing Countries",)),
    Investor("IFU", "dfi", "Copenhagen, Denmark", ("Investment Fund for Developing Countries",)),
    Investor("SIFEM", "dfi", "Bern, Switzerland", ("Swiss Investment Fund for Emerging Markets",)),
    Investor("Cofides", "dfi", "Madrid, Spain"),
    Investor("OeEB", "dfi", "Vienna, Austria", ("Development Bank of Austria",)),
    Investor("JICA", "dfi", "Tokyo, Japan", ("Japan International Cooperation Agency",)),
    Investor("JBIC", "dfi", "Tokyo, Japan", ("Japan Bank for International Cooperation",)),
    Investor("China Development Bank", "dfi", "Beijing, China"),
    Investor("Private Infrastructure Development Group", "dfi", "London, United Kingdom", ("PIDG",)),
    Investor("InfraCo Africa", "dfi", "London, United Kingdom"),
    Investor("GuarantCo", "dfi", "London, United Kingdom"),
    Investor("Emerging Africa Infrastructure Fund", "dfi", "London, United Kingdom", ("EAIF",)),
    Investor("Development Bank of Southern Africa", "dfi", "Midrand, South Africa", ("DBSA",)),
    Investor("Industrial Development Corporation", "dfi", "Johannesburg, South Africa", ("IDC",)),
    Investor("Bank of Industry", "dfi", "Lagos, Nigeria", ("BOI",)),
    Investor("Development Bank of Nigeria", "dfi", "Abuja, Nigeria", ("DBN",)),
    Investor("Fund for Export Development in Africa", "dfi", "Kigali, Rwanda", ("FEDA",)),
    Investor("AgriFI", "dfi", "Brussels, Belgium", ("EU AgriFI",)),
    Investor("African Development Fund", "multilateral", "Abidjan, Côte d'Ivoire"),
    Investor("West African Development Bank", "multilateral", "Lomé, Togo", ("BOAD",)),
    Investor("ECOWAS Bank for Investment and Development", "multilateral", "Lomé, Togo", ("EBID",)),
    Investor("New Development Bank", "multilateral", "Shanghai, China", ("NDB",)),
    Investor("OPEC Fund for International Development", "multilateral", "Vienna, Austria", ("OPEC Fund",)),
    Investor("Arab Bank for Economic Development in Africa", "multilateral", "Khartoum, Sudan", ("BADEA",)),
    Investor("Islamic Corporation for the Development of the Private Sector", "multilateral", "Jeddah, Saudi Arabia", ("ICD",)),
    Investor("International Islamic Trade Finance Corporation", "multilateral", "Jeddah, Saudi Arabia", ("ITFC",)),
    # Private equity and growth
    Investor("Helios Investment Partners", "private_equity", "London, United Kingdom", ("Helios",)),
    Investor("Development Partners International", "private_equity", "London, United Kingdom", ("DPI",)),
    Investor("Actis", "private_equity", "London, United Kingdom"),
    Investor("AfricInvest", "private_equity", "Tunis, Tunisia"),
    Investor("Adenia Partners", "private_equity", "Port Louis, Mauritius", ("Adenia",)),
    Investor("Amethis", "private_equity", "Paris, France"),
    Investor("Lightrock", "growth", "London, United Kingdom"),
    Investor("Ninety One", "private_equity", "London, United Kingdom"),
    Investor("Old Mutual Alternative Investments", "private_equity", "Cape Town, South Africa", ("OMAI",)),
    Investor("African Infrastructure Investment Managers", "private_equity", "Cape Town, South Africa", ("AIIM",)),
    Investor("Metier", "private_equity", "Johannesburg, South Africa", ("Metier Capital Growth Fund III",)),
    Investor("Mediterrania Capital Partners", "private_equity", "Barcelona, Spain", ("Mediterrania Capital",)),
    Investor("SPE Capital", "private_equity", "Tunis, Tunisia"),
    Investor("Inspired Evolution", "private_equity", "Cape Town, South Africa"),
    Investor("Adiwale Partners", "private_equity", "Abidjan, Côte d'Ivoire"),
    Investor("Sahel Capital", "private_equity", "Lagos, Nigeria"),
    Investor("Verod Capital", "private_equity", "Lagos, Nigeria", ("Verod Capital Management",)),
    Investor("Aruwa Capital Management", "private_equity", "Lagos, Nigeria", ("Aruwa Capital",)),
    Investor("CardinalStone", "private_equity", "Lagos, Nigeria", ("CardinalStone Capital Advisers",)),
    Investor("Denham Capital", "private_equity", "Boston, United States"),
    Investor("Emerging Capital Partners", "private_equity", "Washington, DC, United States", ("ECP",)),
    Investor("Apis Partners", "private_equity", "London, United Kingdom"),
    Investor("Abraaj", "private_equity", "Dubai, United Arab Emirates", ("Abraaj Group",)),
    Investor("Climate Fund Managers", "private_equity", "Rotterdam, Netherlands"),
    Investor("Phatisa", "private_equity", "Port Louis, Mauritius"),
    Investor("Alterra Capital Partners", "private_equity", "Washington, DC, United States"),
    Investor("Convergence Partners", "private_equity", "Johannesburg, South Africa"),
    Investor("Ethos Private Equity", "private_equity", "Johannesburg, South Africa", ("Ethos",)),
    Investor("Capitalworks", "private_equity", "Johannesburg, South Africa"),
    Investor("Sanari Capital", "private_equity", "Johannesburg, South Africa"),
    Investor("Kibo Capital Partners", "private_equity", "Port Louis, Mauritius"),
    Investor("Cauris Management", "private_equity", "Lomé, Togo"),
    Investor("Investisseurs & Partenaires", "private_equity", "Paris, France", ("I&P",)),
    Investor("Ascent Capital Africa", "private_equity", "Nairobi, Kenya"),
    Investor("Catalyst Principal Partners", "private_equity", "Nairobi, Kenya"),
    Investor("Fanisi Capital", "private_equity", "Nairobi, Kenya"),
    Investor("XSML Capital", "private_equity", "Amsterdam, Netherlands", ("XSML",)),
    Investor("DOB Equity", "private_equity", "Nijmegen, Netherlands"),
    Investor("Growth Investment Partners Ghana", "private_equity", "Accra, Ghana", ("GIP Ghana",)),
    Investor("Sango Capital", "private_equity", "Johannesburg, South Africa"),
    Investor("Enko Capital", "private_equity", "Johannesburg, South Africa"),
    Investor("Kasada Capital Management", "private_equity", "Paris, France", ("Kasada Capital", "Kasada")),
    Investor("Alcazar Energy Partners", "private_equity", "Dubai, United Arab Emirates"),
    Investor("LeapFrog Investments", "private_equity", "London, United Kingdom", ("LeapFrog",)),
    Investor("Carlyle", "private_equity", "Washington, DC, United States", ("Carlyle Group", "The Carlyle Group")),
    Investor("KKR", "private_equity", "New York, United States"),
    Investor("Blackstone", "private_equity", "New York, United States"),
    Investor("TPG", "private_equity", "Fort Worth, United States", ("TPG Rise", "The Rise Fund")),
    Investor("Warburg Pincus", "private_equity", "New York, United States"),
    Investor("General Atlantic", "growth", "New York, United States"),
    Investor("Tiger Global", "growth", "New York, United States", ("Tiger Global Management",)),
    Investor("SoftBank", "growth", "Tokyo, Japan", ("SoftBank Vision Fund", "SoftBank Group")),
    # Private credit
    Investor("Vantage Capital", "private_credit", "Johannesburg, South Africa"),
    Investor("Verdant Capital", "private_credit", "Johannesburg, South Africa"),
    Investor("TLG Capital", "private_credit", "London, United Kingdom", ("TLG",)),
    Investor("BluePeak Private Capital", "private_credit", "Luxembourg", ("BluePeak",)),
    Investor("African Local Currency Bond Fund", "private_credit", "Luxembourg", ("ALCB Fund",)),
    Investor("Africa Go Green Fund", "private_credit", "Luxembourg"),
    Investor("Symbiotics", "private_credit", "Geneva, Switzerland"),
    # Impact investors and foundations
    Investor("Acumen", "impact", "New York, United States", ("Acumen Fund",)),
    Investor("Mirova", "impact", "Paris, France"),
    Investor("Incofin", "impact", "Antwerp, Belgium", ("Incofin Investment Management",)),
    Investor("Bill & Melinda Gates Foundation", "foundation", "Seattle, United States", ("Gates Foundation",)),
    Investor("Mastercard Foundation", "foundation", "Toronto, Canada"),
    Investor("Rockefeller Foundation", "foundation", "New York, United States"),
    # Venture capital and accelerators
    Investor("Partech Africa", "venture_capital", "Paris, France", ("Partech",)),
    Investor("TLcom Capital", "venture_capital", "London, United Kingdom", ("TLcom",)),
    Investor("Novastar Ventures", "venture_capital", "Nairobi, Kenya", ("Novastar",)),
    Investor("Factor[e] Ventures", "venture_capital", "Washington, DC, United States", ("Factore Ventures", "Factor E Ventures")),
    Investor("4DX Ventures", "venture_capital", "Washington, DC, United States"),
    Investor("Ventures Platform", "venture_capital", "Abuja, Nigeria"),
    Investor("Future Africa", "venture_capital", "Lagos, Nigeria"),
    Investor("Norrsken22", "venture_capital", "Stockholm, Sweden"),
    Investor("Algebra Ventures", "venture_capital", "Cairo, Egypt"),
    Investor("Sawari Ventures", "venture_capital", "Cairo, Egypt"),
    Investor("Janngo Capital", "venture_capital", "Abidjan, Côte d'Ivoire", ("Janngo",)),
    Investor("Y Combinator", "accelerator", "San Francisco, United States", ("YC",)),
    Investor("Goodwell Investments", "venture_capital", "Amsterdam, Netherlands", ("Goodwell",)),
    Investor("AHL Venture Partners", "venture_capital", "Nairobi, Kenya"),
    Investor("Teranga Capital", "venture_capital", "Dakar, Senegal"),
    Investor("Saviu Ventures", "venture_capital", "Paris, France"),
    Investor("Breega", "venture_capital", "Paris, France"),
    Investor("P1 Ventures", "venture_capital", "Lagos, Nigeria"),
    Investor("Knife Capital", "venture_capital", "Cape Town, South Africa"),
    Investor("Greenhouse Capital", "venture_capital", "Lagos, Nigeria"),
    Investor("HAVAÍC", "venture_capital", "Cape Town, South Africa", ("Havaic",)),
    Investor("Renew Capital", "venture_capital", "Addis Ababa, Ethiopia"),
    Investor("Aqua-Spark", "venture_capital", "Utrecht, Netherlands"),
    Investor("MaC Venture Capital", "venture_capital", "Los Angeles, United States", ("Mac VC", "MaC VC")),
    Investor("Verod-Kepple Africa Ventures", "venture_capital", "Lagos, Nigeria"),
    Investor("Kepple Africa Ventures", "venture_capital", "Nairobi, Kenya"),
    Investor("LoftyInc Capital", "venture_capital", "Lagos, Nigeria", ("LoftyInc",)),
    Investor("Microtraction", "venture_capital", "Lagos, Nigeria"),
    Investor("Launch Africa Ventures", "venture_capital", "Port Louis, Mauritius", ("Launch Africa",)),
    Investor("Savannah Fund", "venture_capital", "Nairobi, Kenya"),
    Investor("Golden Palm Investments", "venture_capital", "Nairobi, Kenya", ("GPI",)),
    Investor("Raba Partnership", "venture_capital", "Port Louis, Mauritius", ("Raba",)),
    Investor("Quona Capital", "venture_capital", "Washington, DC, United States", ("Quona",)),
    Investor("QED Investors", "venture_capital", "Alexandria, United States", ("QED",)),
    Investor("Flourish Ventures", "venture_capital", "San Francisco, United States", ("Flourish",)),
    Investor("Global Ventures", "venture_capital", "Dubai, United Arab Emirates"),
    Investor("Endeavor Catalyst", "venture_capital", "New York, United States"),
    Investor("Timon Capital", "venture_capital", "Lagos, Nigeria"),
    Investor("Lightspeed Venture Partners", "venture_capital", "Menlo Park, United States", ("Lightspeed",)),
    Investor("Sequoia Capital", "venture_capital", "Menlo Park, United States", ("Sequoia",)),
    Investor("Andreessen Horowitz", "venture_capital", "Menlo Park, United States", ("a16z",)),
    Investor("Google for Startups Africa Investment Fund", "corporate_venture", "Mountain View, United States",
             ("Google's Africa Investment Fund", "Google’s Africa Investment Fund", "Google Africa Investment Fund")),
    Investor("J&J Impact Ventures", "corporate_venture", "New Brunswick, United States"),
    Investor("Catalyst Fund", "accelerator", "Boston, United States"),
    # Sovereign and pension
    Investor("Public Investment Corporation", "pension", "Pretoria, South Africa", ("PIC",)),
    Investor("Nigeria Sovereign Investment Authority", "sovereign", "Abuja, Nigeria", ("NSIA",)),
    Investor("Fonds Mohammed VI pour l'Investissement", "sovereign", "Rabat, Morocco", ("Fonds Mohammed VI",)),
    Investor("Mubadala", "sovereign", "Abu Dhabi, United Arab Emirates", ("Mubadala Investment Company",)),
    Investor("Qatar Investment Authority", "sovereign", "Doha, Qatar", ("QIA",)),
    Investor("Public Investment Fund", "sovereign", "Riyadh, Saudi Arabia", ("PIF",)),
    Investor("ADQ", "sovereign", "Abu Dhabi, United Arab Emirates"),
    Investor("Temasek", "sovereign", "Singapore"),
    Investor("GIC", "sovereign", "Singapore"),
    Investor("Ghana Infrastructure Investment Fund", "sovereign", "Accra, Ghana", ("GIIF",)),
    Investor("Minerals Income Investment Fund", "sovereign", "Accra, Ghana", ("MIIF",)),
    Investor("FONSIS", "sovereign", "Dakar, Senegal", ("Fonds Souverain d'Investissements Stratégiques",)),
    Investor("The Sovereign Fund of Egypt", "sovereign", "Cairo, Egypt", ("TSFE", "Sovereign Fund of Egypt")),
    Investor("Ithmar Capital", "sovereign", "Rabat, Morocco"),
    Investor("Caisse de Dépôt et de Gestion", "sovereign", "Rabat, Morocco", ("CDG",)),
    Investor("Government Employees Pension Fund", "pension", "Pretoria, South Africa", ("GEPF",)),
    Investor("SSNIT", "pension", "Accra, Ghana", ("Social Security and National Insurance Trust",)),
    # Banks active as lenders and investors
    Investor("Standard Bank", "bank", "Johannesburg, South Africa", ("Standard Bank Group",)),
    Investor("Absa", "bank", "Johannesburg, South Africa", ("Absa Group", "Absa Bank")),
    Investor("FirstRand", "bank", "Johannesburg, South Africa"),
    Investor("Rand Merchant Bank", "bank", "Johannesburg, South Africa", ("RMB",)),
    Investor("Nedbank", "bank", "Johannesburg, South Africa", ("Nedbank Group",)),
    Investor("Ecobank", "bank", "Lomé, Togo", ("Ecobank Transnational", "ETI")),
    Investor("Equity Bank", "bank", "Nairobi, Kenya", ("Equity Group", "Equity Group Holdings")),
    Investor("KCB Group", "bank", "Nairobi, Kenya", ("KCB", "KCB Bank")),
    Investor("Access Bank", "bank", "Lagos, Nigeria", ("Access Holdings", "Access Bank Plc")),
    Investor("Zenith Bank", "bank", "Lagos, Nigeria"),
    Investor("Stanbic IBTC", "bank", "Lagos, Nigeria"),
    Investor("Attijariwafa Bank", "bank", "Casablanca, Morocco", ("Attijariwafa",)),
)

_ALIAS: dict[str, Investor] = {}
for _inv in REGISTRY:
    for _n in (_inv.name, *_inv.aliases):
        _ALIAS[normalise_name(_n)] = _inv


_ACRONYMS: dict[str, Investor] = {a: inv for inv in REGISTRY for a in inv.aliases
                                   if a.isupper() and len(a) >= 3 and a not in ("BID", "CDC")}


def canonical(name: Optional[str]) -> Optional[str]:
    """Registry name for a known investor, or the name as given."""
    if not name:
        return None
    key = normalise_name(name)
    if key in _ALIAS:
        return _ALIAS[key].name
    # "World Bank's IFC": an upper-case registry acronym as a whole word (case-sensitive, so "bid" is not IsDB).
    for word in re.findall(r"[A-Za-z0-9]+", name):
        if word in _ACRONYMS:
            return _ACRONYMS[word].name
    # Multi-word registry names inside a longer name ("Helios Investment Partners Fund IV" -> Helios).
    for alias, inv in _ALIAS.items():
        if " " in alias and f" {alias} " in f" {key} ":
            return inv.name
    # A descriptor before a registry name: "French DFI Proparco", "Dutch lender FMO".
    words = name.strip().split()
    for k in (1, 2):
        tail = normalise_name(" ".join(words[-k:])) if len(words) > k else ""
        # A common word at the end of a name is not a registry name ("Grazia Equity" is not Equity Bank).
        if tail in _ALIAS and len(tail) >= 4 and tail not in _COMMON_WORDS:
            return _ALIAS[tail].name
    # A description before a name: "Billionaire Joe Lonsdale", "South African PE Firm Harith".
    described = _DESCRIPTOR.match(name.strip())
    if described and described.group("rest")[:1].isupper() and len(described.group("rest")) >= 3:
        return canonical(described.group("rest"))
    corporate = _CORPORATE_ALIASES.get(key)
    if corporate:
        return corporate
    # Unknown parties: one display form per company ("Standard Bank Group" and "Standard Bank" are one,
    # "NATCO Pharma" and "Natco Pharma" are one). A lone remaining word is kept only if distinctive.
    stripped = re.sub(r"(?:\s+(?:Group|Holdings?|Plc|PLC|Limited|Ltd\.?|Inc\.?|S\.?A\.?))+$", "", name.strip())
    if len(stripped.split()) < 2 and (not stripped or stripped.lower() in _COMMON_WORDS or len(stripped) < 4):
        stripped = name.strip()
    return _DISPLAY.setdefault(normalise_name(stripped), stripped)


_DISPLAY: dict[str, str] = {}
_DESCRIPTOR = re.compile(
    r"^(?:(?:South\s+African|Nigerian|Kenyan|Ghanaian|Egyptian|Moroccan|Ethiopian|Ugandan|Tanzanian|Rwandan|"
    r"Zambian|Zimbabwean|Senegalese|Ivorian|Tunisian|African|Pan-African|American|US|U\.S\.|UK|British|French|German|"
    r"Dutch|Chinese|Indian|Emirati|Saudi|Japanese|Swiss|Norwegian|Swedish|Danish|Canadian|Israeli|Mauritian)\s+)?"
    r"(?:(?:richest\s+man|richest\s+woman|pharma\s+tycoon|oil\s+tycoon)|billionaire|tycoon|businessman|businesswoman|investor|entrepreneur|PE\s+firm|private\s+equity\s+firm|VC|"
    r"VC\s+firm|venture\s+capital\s+firm|venture\s+firm|fund\s+manager|asset\s+manager|lender|DFI|"
    r"development\s+finance\s+institution|insurer|bank|miner|telco|operator)\s+(?P<rest>.+)$", re.IGNORECASE)
# One company reported under two names (a rename, or a holding company and its bank).
# Keys are normalised names ("Access Holdings" and "Equity Group" normalise to "access" and "equity").
_CORPORATE_ALIASES = {"total": "TotalEnergies", "totalenergies": "TotalEnergies",
                      "access": "Access Bank", "equity": "Equity Bank"}
_COMMON_WORDS = {"access", "equity", "standard", "first", "union", "national", "united", "sterling", "fidelity",
                 "heritage", "premier", "prime", "summit", "diamond", "royal", "liberty", "imperial", "capital",
                 "africa", "african", "global", "international"}

# Extraction fragments: a headline clause rather than a name ("Tolaram Welcomes IFC", "Why Uganda").
_FRAGMENT = re.compile(
    r"\b(welcomes?|makes?|confirms?|says?|plans?|eyes|backs?|announces?|secures?|raises?|signs?|seeks?|targets?|"
    r"invests?|wins?|gets?|bags?|joins?|launches?|unveils?|agreement|deal|move)\b|^(why|how|what|when|govt|others?|"
    r"other\s+investors|investors?|saudi\s+investor)\b|\.\s+\S",
    re.IGNORECASE,
)
_GENERIC_PARTY = re.compile(r"^(capital\s+market|investors?|others?|other\s+investors|govt|government|state|the\s+state)$",
                            re.IGNORECASE)
_GENERIC_PARTY_KEYS = {"public", "first", "million", "millions", "billion", "billions",
                       "company", "unknown", "president", "presidente", "une", "fund", "n a", "na"}


# Amounts, unnamed descriptions and markets are not parties: "USD 180m", "New York investment firm",
# "African Venture Capital Firm", "Foreign FIs", "Kenya-based", "LP".
_NOT_AN_ENTITY = re.compile(
    r"(?i)^(?:(?:US\$|USD|NGN|KES|ZAR|GHS|EUR|N|R|\$|€|£)\s*[\d.,]+\s*(?:m|bn|b|k|million|billion)?|[\d.,]+\s*(?:m|bn|million|billion))$"
    r"|^(?:(?:new\s+york|london|dubai|us|uk|african|foreign|local|global|international|unnamed|undisclosed)\s+)?"
    r"(?:investment\s+firm|venture\s+capital\s+firm|vc|vc\s+firm|pe\s+firm|investors?|fis?|lenders?|banks?|"
    r"funds?|consortium|firm|lp|lps|gp)$"
    r"|-based$|^(?:debt-strained|cash-strapped|struggling|operating)\s|^boost\s|^(?:largest|biggest|record|first)(?:-ever)?\b|-(?:ever|focused|backed|based)$|\s+and\s+(?:ethiopia|kenya|nigeria)$")


_PLACES = {
    "us", "u s", "usa", "uk", "u k", "eu", "uae", "lagos", "nairobi", "johannesburg", "cairo", "accra", "abuja", "kigali",
    "dakar", "casablanca", "addis ababa", "dar es salaam", "kampala", "london", "dubai", "washington", "paris", "beijing",
    "china", "chinese", "india", "indian", "japan", "japanese", "germany", "german", "france", "french", "netherlands",
    "dutch", "sweden", "swedish", "norway", "norwegian", "denmark", "danish", "finland", "finnish", "spain", "spanish",
    "italy", "italian", "russia", "russian", "turkey", "turkish", "qatar", "qatari", "saudi", "saudi arabia", "kuwait",
    "south korea", "korea", "korean", "brazil", "canada", "canadian", "switzerland", "swiss", "belgium", "belgian",
    "israel", "israeli", "united states", "united kingdom", "america", "american", "british", "emirati", "singapore",
    "australia", "australian", "gov t", "govt", "government", "dfi", "dfis", "capital", "private equity firm", "reps",
    "chinese firm", "foreign investors", "richest man", "richest woman", "state", "the state"}


def _is_place(name: str) -> bool:
    """A country or city on its own ("Kenya", "Lagos", "US") is not an investor."""
    from src.data.africa_countries import countries_in_text
    key = normalise_name(name)
    if key in _PLACES:
        return True
    found = countries_in_text(name)
    return bool(found) and normalise_name(" ".join(c.name for c in found)) == key


def split_names(name: Optional[str]) -> list[str]:
    """Canonical parties in an extracted party string: combined names are split ("IFC and Proparco" ->
    IFC, Proparco); headline fragments and generic phrases yield nothing, so no deal is credited to them."""
    if not name or not name.strip():
        return []
    raw = name.strip()
    parts = re.split(r"\s+(?:and|&|et|e)\s+|\s*,\s*", raw)
    if len(parts) > 1 and all(p.strip() for p in parts):
        # Split only when a part is a known investor: "Procter & Gamble" and "Johnson & Johnson" stay whole.
        if any(registry_entry(p) for p in parts):
            return [c for p in parts for c in split_names(p)]
    if _GENERIC_PARTY.match(raw) or not normalise_name(raw) or normalise_name(raw) in _GENERIC_PARTY_KEYS or _FRAGMENT.search(raw):
        return []
    # A name starts with a capital or digit ("eBay"-style brands aside); a lowercase start is a clause.
    if _NOT_AN_ENTITY.search(raw) or _is_place(raw) or not (raw[0].isupper() or raw[0].isdigit() or raw[1:2].isupper()):
        return []
    c = canonical(raw)
    return [c] if c else []


def registry_entry(name: str) -> Optional[Investor]:
    c = canonical(name)
    return _ALIAS.get(normalise_name(c)) if c else None


def parties(deal: dict) -> list[tuple[str, str]]:
    """(canonical name, role) for every party of a deal."""
    t = deal.get("deal_type")
    out: list[tuple[str, str]] = []

    def add(name: Optional[str], role: str) -> None:
        for c in split_names(name):
            if (c, role) not in out:
                out.append((c, role))

    if t == "equity_funding":
        add(deal.get("buyer"), "investor")
        for n in deal.get("investors") or []:
            add(n, "investor")
    elif t == "debt_financing":
        add(deal.get("buyer"), "lender")
        for n in deal.get("investors") or []:
            add(n, "lender")
    elif t in ("acquisition", "merger"):
        add(deal.get("buyer"), "acquirer")
        add(deal.get("seller"), "seller")
    elif t == "exit":
        add(deal.get("seller"), "seller")
        add(deal.get("buyer"), "acquirer")
    elif t == "fund_raise":
        add(deal.get("target"), "gp")
        for n in deal.get("investors") or []:
            add(n, "lp")
    return out


def profiles(deals: Iterable[dict]) -> dict[str, dict]:
    """Every party's profile, keyed by canonical name."""
    deals = list(deals)
    by_party: dict[str, list[tuple[dict, str]]] = defaultdict(list)
    for d in deals:
        for name, role in parties(d):
            by_party[name].append((d, role))
    out = {}
    for name, rows in by_party.items():
        out[name] = _profile(name, rows)
    return out


_INVESTMENT_FIRM = re.compile(r"(?i)\b(capital|ventures?|partners|fund|private\s+equity|equity\s+partners|"
                              r"investments?|asset\s+management|angels?|accelerator|vc)\b")
_BANK = re.compile(r"(?i)\b(bank|banque|banco)\b")


def _inferred_kind(name: str, roles: Counter) -> str:
    """Unregistered parties: an investment firm when the name says so, else a corporate (strategic buyer,
    seller or borrower). Marked as inferred, never presented as registry data."""
    if _BANK.search(name) and not _INVESTMENT_FIRM.search(name):
        return "bank"
    return "investment_firm" if _INVESTMENT_FIRM.search(name) else "corporate"


def _median(values: list[float]) -> Optional[float]:
    if not values:
        return None
    v = sorted(values)
    mid = len(v) // 2
    return round(v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2)


def _stage(deal: dict) -> Optional[str]:
    """A round's stage, normalised ("Series A", "seed", "pre-seed")."""
    r = (deal.get("round") or "").strip().lower()
    if not r:
        return None
    m = re.match(r"(pre-seed|seed|pre-series\s+[a-f]|series\s+[a-f]|bridge|growth|extension)", r)
    return m.group(1).replace("  ", " ") if m else None


INVESTMENT_PERIOD_YEARS = 5      # a closed-end fund typically invests for about five years, then harvests


def portfolio(deals: list[dict], name: str) -> list[dict]:
    """Companies this party backed or bought, with what happened to each afterwards: a later round, an exit
    (sale, acquisition by someone else, IPO), or nothing recorded yet."""
    rows = [(d, role) for d in deals for n, role in parties(d) if n == name and role in ("investor", "acquirer", "lender")]
    by_target: dict[str, dict] = {}
    for d, role in sorted(rows, key=lambda r: r[0].get("announced") or ""):
        target = d.get("target")
        # A target that is not a recognisable name ("Africa-focused", a headline clause) is left out.
        if not target or not split_names(target) or len(target.split()) > 6:
            continue
        key = normalise_name(target)
        by_target.setdefault(key, {"company": target, "first_deal": d.get("announced"), "role": role,
                                   "deal_id": d["id"], "since": []})
    for d in deals:
        key = normalise_name(d.get("target"))
        entry = by_target.get(key)
        if not entry or not d.get("announced") or d["announced"] <= (entry["first_deal"] or ""):
            continue
        t = d.get("deal_type")
        event = ("raised again" if t == "equity_funding" else "listed" if t == "ipo"
                 else "exited" if t in ("exit", "acquisition", "merger") and name not in {n for n, _ in parties(d)} else None)
        if event:
            entry["since"].append({"event": event, "date": d["announced"], "deal_id": d["id"]})
    out = []
    for e in by_target.values():
        latest = max(e["since"], key=lambda x: x["date"]) if e["since"] else None
        out.append({**{k: v for k, v in e.items() if k != "since"},
                    "status": latest["event"] if latest else "no later deal recorded",
                    "status_date": latest["date"] if latest else None})
    return sorted(out, key=lambda e: e["first_deal"] or "", reverse=True)


def fund_lifecycle(deals: list[dict], name: str, today: Optional[str] = None) -> Optional[dict]:
    """The latest fund this party raised as manager, and where it likely is in its life: investing (within
    about five years of the close) or harvesting (beyond it, when exits are due)."""
    from datetime import date
    raised = [d for d in deals if d.get("deal_type") == "fund_raise" and d.get("announced")
              and name in {n for n, role in parties(d) if role == "gp"}]
    if not raised:
        return None
    latest = max(raised, key=lambda d: d["announced"])
    years = round((date.fromisoformat(today or date.today().isoformat()) - date.fromisoformat(latest["announced"][:10])).days / 365.25, 1)
    return {"fund": latest.get("target"), "announced": latest["announced"], "amount_usd": latest.get("amount_usd"),
            "stage": latest.get("stage"), "years_since": years,
            "phase": "investing" if years < INVESTMENT_PERIOD_YEARS else "harvesting",
            "note": f"Closed-end funds typically invest for about {INVESTMENT_PERIOD_YEARS} years, then sell; "
                    "this is an estimate from the fund's announcement date, not a reported fund term."}


def filter_deals(deals: Iterable[dict], sector: Optional[str] = None, country: Optional[str] = None,
                 stage: Optional[str] = None, deal_type: Optional[str] = None, since: Optional[str] = None,
                 until: Optional[str] = None, min_usd: Optional[float] = None, max_usd: Optional[float] = None) -> list[dict]:
    """The deals a screen covers; investors are then ranked on these deals only."""
    out = []
    for d in deals:
        if sector and d.get("sector") != sector:
            continue
        if country and country not in (d.get("countries") or [d.get("country")]):
            continue
        if stage and _stage(d) != stage.lower():
            continue
        if deal_type and d.get("deal_type") != deal_type:
            continue
        day = (d.get("announced") or "")[:10]
        if (since and (not day or day < since)) or (until and (not day or day > until)):
            continue
        amount = d.get("amount_usd")
        if (min_usd is not None and (amount is None or amount < min_usd)) or (max_usd is not None and (amount is None or amount > max_usd)):
            continue
        out.append(d)
    return out


def _profile(name: str, rows: list[tuple[dict, str]]) -> dict:
    entry = registry_entry(name)
    roles = Counter(role for _, role in rows)
    disclosed = [d["amount_usd"] for d, _ in rows if d.get("amount_usd")]
    co = Counter()
    for d, _ in rows:
        for other, _role in parties(d):
            if other != name:
                co[other] += 1
    recent = sorted(rows, key=lambda r: r[0].get("announced") or "", reverse=True)
    return {
        "name": name,
        "type": entry.kind if entry else _inferred_kind(name, roles),
        "type_inferred": entry is None,
        "hq": entry.hq if entry else None,
        "in_registry": entry is not None,
        "deal_count": len({d["id"] for d, _ in rows}),
        "roles": dict(roles),
        "disclosed_usd": round(sum(disclosed)),
        "disclosed_count": len(disclosed),
        "sectors": dict(Counter(d.get("sector") for d, _ in rows if d.get("sector")).most_common(8)),
        "countries": dict(Counter(c for d, _ in rows for c in (d.get("countries") or [])).most_common(10)),
        "deal_types": dict(Counter(d.get("deal_type") for d, _ in rows)),
        "co_investors": [{"name": n, "deals": k} for n, k in co.most_common(10)],
        "first_seen": min((d.get("announced") for d, _ in rows if d.get("announced")), default=None),
        "last_seen": max((d.get("announced") for d, _ in rows if d.get("announced")), default=None),
        "lead_count": sum(1 for d, _ in rows if name in {canonical(n) for n in d.get("lead_investors") or []}),
        "activity_by_year": dict(sorted(Counter((d.get("announced") or "")[:4] for d, _ in rows
                                                if d.get("announced")).items())),
        "typical_round_usd": _median([d["amount_usd"] for d, role in rows
                                      if role == "investor" and d.get("deal_type") == "equity_funding" and d.get("amount_usd")]),
        "rounds_by_stage": dict(Counter(_stage(d) for d, role in rows if role == "investor" and _stage(d))),
        "recent": [{"id": d["id"], "role": role, "deal_type": d.get("deal_type"), "target": d.get("target"),
                    "amount_usd": d.get("amount_usd"), "announced": d.get("announced"), "country": d.get("country"),
                    "headline": d.get("headline")} for d, role in recent[:15]],
    }


def profile(deals: Iterable[dict], name: str) -> Optional[dict]:
    """One party's profile (any alias works), or None if it appears in no deal."""
    target = canonical(name)
    rows = [(d, role) for d in deals for n, role in parties(d) if n == target]
    if not rows:
        key = normalise_name(name)
        rows = [(d, role) for d in deals for n, role in parties(d) if key and key in normalise_name(n)]
        if not rows:
            return None
        target = parties(rows[0][0])[0][0] if parties(rows[0][0]) else name
    return _profile(target, rows)


def leaderboard(deals: Iterable[dict], role: Optional[str] = None, kind: Optional[str] = None,
                limit: int = 50, lead_only: bool = False) -> list[dict]:
    """Most active parties, optionally by role (investor, lender, acquirer, seller, lp, gp), registry type,
    or only those that led a round."""
    rows = []
    for p in profiles(deals).values():
        if role and not p["roles"].get(role):
            continue
        if lead_only and not p["lead_count"]:
            continue
        if kind and p["type"] != kind:
            continue
        rows.append(p)
    rows.sort(key=lambda p: (p["roles"].get(role, 0) if role else p["deal_count"], p["disclosed_usd"]), reverse=True)
    return [{k: p[k] for k in ("name", "type", "type_inferred", "hq", "deal_count", "lead_count", "roles", "disclosed_usd",
                               "countries", "typical_round_usd", "last_seen")}
            for p in rows[:limit]]


def funds(deals: Iterable[dict]) -> list[dict]:
    """Fund raises and closes (GP activity) with their LPs, newest first."""
    out = []
    for d in deals:
        if d.get("deal_type") != "fund_raise":
            continue
        out.append({"id": d["id"], "fund_or_manager": d.get("target"), "stage": d.get("stage"),
                    "amount_usd": d.get("amount_usd"), "lps": [canonical(n) for n in d.get("investors") or []],
                    "announced": d.get("announced"), "country": d.get("country"), "headline": d.get("headline"),
                    "sources": d.get("sources")})
    return sorted(out, key=lambda f: f.get("announced") or "", reverse=True)
