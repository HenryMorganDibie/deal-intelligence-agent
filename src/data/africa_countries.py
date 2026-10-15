"""
Registry of all 54 African Union member states recognised by the UN.

Each entry carries what the pipeline needs to work on a company from that
country: ISO codes, UN M49 sub-region, working languages for news search,
currency, stock exchange (and its Yahoo Finance suffix where Yahoo carries it),
central bank, securities regulator, and the Google News edition to search.

Countries without a national exchange are still covered: news search, deal
extraction, country risk and regulator detection work for every entry.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# Google News editions that exist for African countries ("GL:lang").
# Countries without one are searched through their language's edition with the
# country name added to the query.
_LANGUAGE_EDITION = {"en": "GB:en", "fr": "FR:fr", "pt": "PT:pt-150", "ar": "EG:ar", "es": "ES:es"}


@dataclass(frozen=True)
class Country:
    iso2: str
    iso3: str
    name: str
    region: str                       # UN M49: Northern, Western, Middle, Eastern, Southern Africa
    languages: tuple[str, ...]        # news search languages, primary first
    currency: str                     # ISO 4217
    central_bank: str
    exchange: Optional[str] = None
    yahoo_suffix: Optional[str] = None
    securities_regulator: Optional[str] = None
    regulator_acronyms: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()     # alternative names and demonyms
    news_edition: Optional[str] = None  # national Google News edition, e.g. "NG:en"

    def edition(self, language: Optional[str] = None) -> str:
        """Google News "GL:lang" edition for a language (default: the primary one)."""
        lang = language or self.languages[0]
        if self.news_edition and self.news_edition.split(":")[1].startswith(lang):
            return self.news_edition
        return _LANGUAGE_EDITION.get(lang, "GB:en")

    def news_url(self, query: str, language: Optional[str] = None) -> str:
        from urllib.parse import quote
        gl, ceid_lang = self.edition(language).split(":")
        hl = {"pt-150": "pt-PT"}.get(ceid_lang, ceid_lang if ceid_lang != "en" else f"en-{gl}")
        return f"https://news.google.com/rss/search?q={quote(query)}&hl={hl}&gl={gl}&ceid={gl}:{ceid_lang}"


_UMOA = dict(exchange="BRVM (Abidjan)", securities_regulator="AMF-UMOA", regulator_acronyms=("AMF-UMOA", "CREPMF", "BCEAO"),
             central_bank="BCEAO (Central Bank of West African States)", currency="XOF")
_CEMAC = dict(exchange="BVMAC (Douala)", securities_regulator="COSUMAF", regulator_acronyms=("COSUMAF", "BEAC"),
              central_bank="BEAC (Bank of Central African States)", currency="XAF")

COUNTRIES: tuple[Country, ...] = (
    # ── Northern Africa ──────────────────────────────────────────────────────
    Country("DZ", "DZA", "Algeria", "Northern Africa", ("ar", "fr"), "DZD", "Bank of Algeria",
            exchange="Algiers Stock Exchange", securities_regulator="COSOB", regulator_acronyms=("COSOB",),
            aliases=("Algerian", "Algérie", "Argélia")),
    Country("EG", "EGY", "Egypt", "Northern Africa", ("ar", "en"), "EGP", "Central Bank of Egypt",
            exchange="Egyptian Exchange (EGX)", yahoo_suffix=".CA",
            securities_regulator="Financial Regulatory Authority", regulator_acronyms=("FRA", "EGX", "CBE"),
            aliases=("Egyptian", "مصر", "Égypte", "Egito"), news_edition="EG:ar"),
    Country("LY", "LBY", "Libya", "Northern Africa", ("ar",), "LYD", "Central Bank of Libya",
            exchange="Libyan Stock Market", aliases=("Libyan", "Libye")),
    Country("MA", "MAR", "Morocco", "Northern Africa", ("fr", "ar"), "MAD", "Bank Al-Maghrib",
            exchange="Casablanca Stock Exchange", yahoo_suffix=".CS",
            securities_regulator="AMMC", regulator_acronyms=("AMMC",),
            aliases=("Moroccan", "Maroc", "المغرب", "Marrocos"), news_edition="MA:fr"),
    Country("SD", "SDN", "Sudan", "Northern Africa", ("ar", "en"), "SDG", "Central Bank of Sudan",
            exchange="Khartoum Stock Exchange", aliases=("Sudanese", "Soudan")),
    Country("TN", "TUN", "Tunisia", "Northern Africa", ("fr", "ar"), "TND", "Banque Centrale de Tunisie",
            exchange="Bourse de Tunis (BVMT)", yahoo_suffix=".TN",
            securities_regulator="Conseil du Marché Financier", regulator_acronyms=("CMF", "BCT"),
            aliases=("Tunisian", "Tunisie", "Tunísia")),

    # ── Western Africa ───────────────────────────────────────────────────────
    Country("BJ", "BEN", "Benin", "Western Africa", ("fr",), aliases=("Beninese", "Bénin"), **_UMOA),
    Country("BF", "BFA", "Burkina Faso", "Western Africa", ("fr",), aliases=("Burkinabe", "Burkinabè", "Burkina"), **_UMOA),
    Country("CV", "CPV", "Cabo Verde", "Western Africa", ("pt",), "CVE", "Banco de Cabo Verde",
            exchange="Bolsa de Valores de Cabo Verde", securities_regulator="AGMVM", regulator_acronyms=("AGMVM",),
            aliases=("Cape Verde", "Cape Verdean", "Cap-Vert")),
    Country("CI", "CIV", "Côte d'Ivoire", "Western Africa", ("fr",), yahoo_suffix=".BV",
            aliases=("Cote d'Ivoire", "Ivory Coast", "Ivorian", "Ivoirien", "Costa do Marfim"), news_edition="CI:fr", **_UMOA),
    Country("GM", "GMB", "Gambia", "Western Africa", ("en",), "GMD", "Central Bank of The Gambia",
            aliases=("The Gambia", "Gambian", "Gambie")),
    Country("GH", "GHA", "Ghana", "Western Africa", ("en",), "GHS", "Bank of Ghana",
            exchange="Ghana Stock Exchange", yahoo_suffix=".GH",
            securities_regulator="Securities and Exchange Commission Ghana", regulator_acronyms=("BoG",),
            aliases=("Ghanaian", "Gana"), news_edition="GH:en"),
    Country("GN", "GIN", "Guinea", "Western Africa", ("fr",), "GNF", "Banque Centrale de la République de Guinée",
            aliases=("Guinée", "Guinea-Conakry", "Guinean", "Guiné")),
    Country("GW", "GNB", "Guinea-Bissau", "Western Africa", ("pt", "fr"),
            aliases=("Guiné-Bissau", "Bissau-Guinean", "Guinée-Bissau", "Guinée Bissau", "Guinea Bissau"), **_UMOA),
    Country("LR", "LBR", "Liberia", "Western Africa", ("en",), "LRD", "Central Bank of Liberia",
            aliases=("Liberian", "Libéria")),
    Country("ML", "MLI", "Mali", "Western Africa", ("fr",), aliases=("Malian",), **_UMOA),
    Country("MR", "MRT", "Mauritania", "Western Africa", ("fr", "ar"), "MRU", "Banque Centrale de Mauritanie",
            aliases=("Mauritanian", "Mauritanie")),
    Country("NE", "NER", "Niger", "Western Africa", ("fr",), aliases=("Nigerien",), **_UMOA),
    Country("NG", "NGA", "Nigeria", "Western Africa", ("en",), "NGN", "Central Bank of Nigeria",
            exchange="Nigerian Exchange (NGX)", yahoo_suffix=".LG",
            securities_regulator="Securities and Exchange Commission Nigeria",
            regulator_acronyms=("CBN", "NGX", "FCCPC", "NAICOM", "PenCom", "NCC", "AMCON", "EFCC"),
            aliases=("Nigerian", "Nigéria"), news_edition="NG:en"),
    Country("SN", "SEN", "Senegal", "Western Africa", ("fr",), aliases=("Senegalese", "Sénégal", "Senegal"),
            news_edition="SN:fr", **_UMOA),
    Country("SL", "SLE", "Sierra Leone", "Western Africa", ("en",), "SLE", "Bank of Sierra Leone",
            exchange="Sierra Leone Stock Exchange", aliases=("Sierra Leonean", "Sierra Léone")),
    Country("TG", "TGO", "Togo", "Western Africa", ("fr",), aliases=("Togolese",), **_UMOA),

    # ── Middle Africa ────────────────────────────────────────────────────────
    Country("AO", "AGO", "Angola", "Middle Africa", ("pt",), "AOA", "Banco Nacional de Angola",
            exchange="BODIVA", yahoo_suffix=".AO", securities_regulator="Comissão do Mercado de Capitais",
            regulator_acronyms=("BODIVA", "BNA"), aliases=("Angolan", "Angolais")),
    Country("CM", "CMR", "Cameroon", "Middle Africa", ("fr", "en"), aliases=("Cameroonian", "Cameroun", "Camarões"),
            news_edition="CM:fr", **_CEMAC),
    Country("CF", "CAF", "Central African Republic", "Middle Africa", ("fr",),
            aliases=("Centrafrique", "Centrafricaine", "République centrafricaine"), **_CEMAC),
    Country("TD", "TCD", "Chad", "Middle Africa", ("fr", "ar"), aliases=("Chadian", "Tchad", "Chade"), **_CEMAC),
    Country("CG", "COG", "Republic of the Congo", "Middle Africa", ("fr",),
            aliases=("Congo-Brazzaville", "Congo Brazzaville", "Congolese"), **_CEMAC),
    Country("CD", "COD", "Democratic Republic of the Congo", "Middle Africa", ("fr",), "CDF",
            "Banque Centrale du Congo", aliases=("DR Congo", "DRC", "RDC", "Congo-Kinshasa", "RD Congo")),
    Country("GQ", "GNQ", "Equatorial Guinea", "Middle Africa", ("es", "fr"),
            aliases=("Equatoguinean", "Guinea Ecuatorial", "Guinée équatoriale", "Guiné Equatorial"), **_CEMAC),
    Country("GA", "GAB", "Gabon", "Middle Africa", ("fr",), aliases=("Gabonese",), **_CEMAC),
    Country("ST", "STP", "São Tomé and Príncipe", "Middle Africa", ("pt",), "STN",
            "Banco Central de São Tomé e Príncipe", aliases=("Sao Tome and Principe", "Santomean")),

    # ── Eastern Africa ───────────────────────────────────────────────────────
    Country("BI", "BDI", "Burundi", "Eastern Africa", ("fr", "en"), "BIF", "Banque de la République du Burundi",
            aliases=("Burundian",)),
    Country("KM", "COM", "Comoros", "Eastern Africa", ("fr", "ar"), "KMF", "Banque Centrale des Comores",
            aliases=("Comorian", "Comores")),
    Country("DJ", "DJI", "Djibouti", "Eastern Africa", ("fr", "ar"), "DJF", "Banque Centrale de Djibouti",
            aliases=("Djiboutian",)),
    Country("ER", "ERI", "Eritrea", "Eastern Africa", ("en", "ar"), "ERN", "Bank of Eritrea",
            aliases=("Eritrean", "Érythrée")),
    Country("ET", "ETH", "Ethiopia", "Eastern Africa", ("en",), "ETB", "National Bank of Ethiopia",
            exchange="Ethiopian Securities Exchange", securities_regulator="Ethiopian Capital Market Authority",
            regulator_acronyms=("ECMA", "NBE"), aliases=("Ethiopian", "Éthiopie", "Etiópia"), news_edition="ET:en"),
    Country("KE", "KEN", "Kenya", "Eastern Africa", ("en",), "KES", "Central Bank of Kenya",
            exchange="Nairobi Securities Exchange (NSE)", yahoo_suffix=".NR",
            securities_regulator="Capital Markets Authority", regulator_acronyms=("CMA", "CBK", "CAK"),
            aliases=("Kenyan", "Quénia", "Quênia", "IEBC", "Independent Electoral and Boundaries Commission"),
            news_edition="KE:en"),
    Country("MG", "MDG", "Madagascar", "Eastern Africa", ("fr",), "MGA", "Banque Centrale de Madagascar",
            aliases=("Malagasy",)),
    Country("MW", "MWI", "Malawi", "Eastern Africa", ("en",), "MWK", "Reserve Bank of Malawi",
            exchange="Malawi Stock Exchange", aliases=("Malawian", "Malawite")),
    Country("MU", "MUS", "Mauritius", "Eastern Africa", ("en", "fr"), "MUR", "Bank of Mauritius",
            exchange="Stock Exchange of Mauritius", securities_regulator="Financial Services Commission",
            regulator_acronyms=("FSC",), aliases=("Mauritian", "Maurice", "Maurícia")),
    Country("MZ", "MOZ", "Mozambique", "Eastern Africa", ("pt",), "MZN", "Banco de Moçambique",
            exchange="Bolsa de Valores de Moçambique", yahoo_suffix=".MZ", aliases=("Mozambican", "Moçambique", "Mozambicain")),
    Country("RW", "RWA", "Rwanda", "Eastern Africa", ("en", "fr"), "RWF", "National Bank of Rwanda",
            exchange="Rwanda Stock Exchange", securities_regulator="Capital Market Authority Rwanda",
            regulator_acronyms=("BNR",), aliases=("Rwandan", "Ruanda")),
    Country("SC", "SYC", "Seychelles", "Eastern Africa", ("en", "fr"), "SCR", "Central Bank of Seychelles",
            exchange="MERJ Exchange", securities_regulator="Financial Services Authority Seychelles",
            aliases=("Seychellois",)),
    Country("SO", "SOM", "Somalia", "Eastern Africa", ("en", "ar"), "SOS", "Central Bank of Somalia",
            aliases=("Somali", "Somalie")),
    Country("SS", "SSD", "South Sudan", "Eastern Africa", ("en",), "SSP", "Bank of South Sudan",
            aliases=("South Sudanese", "Soudan du Sud")),
    Country("TZ", "TZA", "Tanzania", "Eastern Africa", ("en",), "TZS", "Bank of Tanzania",
            exchange="Dar es Salaam Stock Exchange", securities_regulator="Capital Markets and Securities Authority",
            regulator_acronyms=("CMSA", "BoT"), aliases=("Tanzanian", "Tanzanie", "Tanzânia"), news_edition="TZ:en"),
    Country("UG", "UGA", "Uganda", "Eastern Africa", ("en",), "UGX", "Bank of Uganda",
            exchange="Uganda Securities Exchange", securities_regulator="Capital Markets Authority Uganda",
            regulator_acronyms=("BoU",), aliases=("Ugandan", "Ouganda"), news_edition="UG:en"),
    Country("ZM", "ZMB", "Zambia", "Eastern Africa", ("en",), "ZMW", "Bank of Zambia",
            exchange="Lusaka Securities Exchange", securities_regulator="Securities and Exchange Commission Zambia",
            aliases=("Zambian", "Zambie", "Zâmbia")),
    Country("ZW", "ZWE", "Zimbabwe", "Eastern Africa", ("en",), "ZWG", "Reserve Bank of Zimbabwe",
            exchange="Zimbabwe Stock Exchange", securities_regulator="Securities and Exchange Commission of Zimbabwe",
            regulator_acronyms=("RBZ", "SECZ"), aliases=("Zimbabwean", "Zimbabué"), news_edition="ZW:en"),

    # ── Southern Africa ──────────────────────────────────────────────────────
    Country("BW", "BWA", "Botswana", "Southern Africa", ("en",), "BWP", "Bank of Botswana",
            exchange="Botswana Stock Exchange", securities_regulator="NBFIRA", regulator_acronyms=("NBFIRA",),
            aliases=("Motswana", "Batswana", "Botsuana"), news_edition="BW:en"),
    Country("SZ", "SWZ", "Eswatini", "Southern Africa", ("en",), "SZL", "Central Bank of Eswatini",
            exchange="Eswatini Stock Exchange", securities_regulator="Financial Services Regulatory Authority",
            regulator_acronyms=("FSRA",), aliases=("Swaziland", "Swazi")),
    Country("LS", "LSO", "Lesotho", "Southern Africa", ("en",), "LSL", "Central Bank of Lesotho",
            exchange="Maseru Securities Market", aliases=("Basotho", "Mosotho")),
    Country("NA", "NAM", "Namibia", "Southern Africa", ("en",), "NAD", "Bank of Namibia",
            exchange="Namibian Stock Exchange", securities_regulator="NAMFISA", regulator_acronyms=("NAMFISA",),
            aliases=("Namibian", "Namibie", "Namíbia"), news_edition="NA:en"),
    Country("ZA", "ZAF", "South Africa", "Southern Africa", ("en",), "ZAR", "South African Reserve Bank",
            exchange="Johannesburg Stock Exchange (JSE)", yahoo_suffix=".JO",
            securities_regulator="Financial Sector Conduct Authority",
            regulator_acronyms=("FSCA", "SARB", "JSE", "Prudential Authority"),
            aliases=("South African", "RSA", "Mzansi", "Afrique du Sud", "África do Sul", "Sud-Africain"), news_edition="ZA:en"),
)

BY_ISO2: dict[str, Country] = {c.iso2: c for c in COUNTRIES}
BY_ISO3: dict[str, Country] = {c.iso3: c for c in COUNTRIES}
BY_SUFFIX: dict[str, Country] = {c.yahoo_suffix: c for c in COUNTRIES
                                 if c.yahoo_suffix and c.iso2 not in ("BJ", "BF", "GW", "ML", "NE", "SN", "TG")}

# Regional regulators and competition authorities that act across borders.
REGIONAL_REGULATORS = ("COMESA Competition Commission", "CCC", "ECOWAS", "WAEMU", "UEMOA", "CEMAC", "SADC",
                       "AfCFTA", "Afreximbank", "African Development Bank", "AfDB")


def get(code: Optional[str]) -> Optional[Country]:
    """Country by ISO2 or ISO3 code (any case)."""
    if not code:
        return None
    c = code.strip().upper()
    return BY_ISO2.get(c) or BY_ISO3.get(c)


def from_ticker(ticker: Optional[str]) -> Optional[Country]:
    """Country of listing from a Yahoo-style suffix ('DANGCEM.LG' -> Nigeria)."""
    if not ticker or "." not in ticker:
        return None
    return BY_SUFFIX.get("." + ticker.upper().rsplit(".", 1)[1])


def _names(c: Country) -> list[str]:
    return [c.name, *c.aliases]


# Longest names first so "South Sudan" wins over "Sudan", "Guinea-Bissau" over "Guinea",
# "Nigerian" over "Niger".
_NAME_INDEX: list[tuple[str, Country]] = sorted(
    ((n, c) for c in COUNTRIES for n in _names(c)), key=lambda p: -len(p[0]))
_NAME_RE = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(n) for n, _ in _NAME_INDEX) + r")(?![\w-])", re.IGNORECASE)
_NAME_LOOKUP = {n.lower(): c for n, c in _NAME_INDEX}


def countries_in_text(text: str) -> list[Country]:
    """African countries named in text, in order of first mention, without duplicates."""
    seen: dict[str, Country] = {}
    for m in _NAME_RE.finditer((text or "").replace("’", "'")):
        name = m.group(1)
        # "Niger" in title case only: avoids "niger" inside other contexts and "Chad" the first name.
        if name.lower() in ("niger", "chad", "togo", "mali") and not name[0].isupper():
            continue
        c = _NAME_LOOKUP.get(name.lower())
        if c and c.iso2 not in seen:
            seen[c.iso2] = c
    return list(seen.values())


def resolve(country: Optional[str] = None, ticker: Optional[str] = None,
            text: str = "") -> Optional[Country]:
    """Best country for a request: explicit code, then listing suffix, then the first country named."""
    return get(country) or from_ticker(ticker) or next(iter(countries_in_text(text)), None)


def regulator_acronyms() -> list[str]:
    """Every national regulator acronym in the registry, for rule matching."""
    return sorted({a for c in COUNTRIES for a in c.regulator_acronyms}, key=len, reverse=True)
