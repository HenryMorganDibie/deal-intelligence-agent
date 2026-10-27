"""Major African companies that deal headlines often name without a country ("MTN agrees to buy IHS").

A name here places a headline in Africa, under that company's home market. Only names that are
unambiguous on their own are listed: no namesakes elsewhere (e.g. Woolworths, Fidelity) and no
groups headquartered outside Africa (e.g. Anglo American, Investec). Matching is case-sensitive.
"""
from __future__ import annotations

import re
from typing import Optional
from functools import lru_cache

AFRICAN_COMPANIES: dict[str, str] = {
    # South Africa
    "MTN Group": "ZA", "MTN": "ZA", "Vodacom": "ZA", "Naspers": "ZA", "Sasol": "ZA", "Shoprite": "ZA",
    "Standard Bank": "ZA", "FirstRand": "ZA", "Absa": "ZA", "Nedbank": "ZA", "Capitec": "ZA", "Sanlam": "ZA",
    "Old Mutual": "ZA", "Bidvest": "ZA", "MultiChoice": "ZA", "Sibanye-Stillwater": "ZA",
    "Sibanye Stillwater": "ZA", "Impala Platinum": "ZA", "Gold Fields": "ZA", "Harmony Gold": "ZA", "Pick n Pay": "ZA",
    "Remgro": "ZA", "Mr Price": "ZA", "Tiger Brands": "ZA", "Aspen Pharmacare": "ZA", "Growthpoint": "ZA",
    "Exxaro": "ZA", "Kumba Iron Ore": "ZA",
    # Nigeria
    "Dangote": "NG", "Access Bank": "NG", "Access Holdings": "NG", "Zenith Bank": "NG", "GTCO": "NG",
    "Guaranty Trust": "NG", "UBA": "NG", "FirstHoldCo": "NG", "First HoldCo": "NG", "Seplat": "NG", "Oando": "NG",
    "BUA Group": "NG", "Transcorp": "NG", "Flutterwave": "NG", "Paystack": "NG", "Moniepoint": "NG",
    "Interswitch": "NG", "Stanbic IBTC": "NG", "Kuda": "NG",
    # Kenya
    "Safaricom": "KE", "KCB Group": "KE", "KCB": "KE", "Equity Group": "KE", "Equity Bank": "KE",
    "East African Breweries": "KE", "NCBA": "KE", "M-Kopa": "KE", "Twiga Foods": "KE", "Britam": "KE",
    # North Africa
    "Fawry": "EG", "Talaat Moustafa": "EG", "Elsewedy Electric": "EG", "Orascom Construction": "EG",
    "Attijariwafa": "MA", "Maroc Telecom": "MA", "OCP Group": "MA",
    # Pan-African and other markets
    "Airtel Africa": "NG", "Ecobank": "TG", "Afreximbank": "EG", "Ethio Telecom": "ET",
}


@lru_cache(maxsize=1)
def _pattern() -> re.Pattern:
    names = sorted(AFRICAN_COMPANIES, key=len, reverse=True)
    return re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in names) + r")(?:['’]s)?(?![\w-])")


# Listed in Johannesburg but headquartered or primarily listed elsewhere: their deals are not placed in Africa
# by their name alone.
_FOREIGN_PRIMARY = re.compile(
    r"^(?:AB InBev|Anglo American$|BHP|British American Tobacco|Bytes Technology|Capital & (?:Counties|Regional)|"
    r"Compagnie Financiere Richemont|Deutsche Konsum|Echo Polska|Glencore|Globe Trade Centre|Hammerson|Intu Properties|"
    r"Investec|Irongate|Mondi|NEPI Rockcastle|Ninety One|Prosus|Quilter|Reinet|Schroder|Sirius Real Estate|South32|"
    r"Stenprop|Textainer|Mediclinic|MAS Real Estate|Steinhoff International Holdings NV|Montauk|Net 1 UEPS|"
    r"Great Basin Gold|Eastern Platinum|Atlantic Leaf|Grindrod Shipping|Lonmin|Lighthouse Capital|"
    r"London Finance|Europa Metals|Alphamin|Kore Potash|Orion Minerals|Tawana Resources|Gemfields)")
# Cross-listed African companies whose home market is not the exchange the list records.
_HOME_OVERRIDE = {"Oando": "NG", "Choppies Enterprises": "BW", "Hwange Colliery": "ZW", "Wilderness Holdings": "BW",
                  "Grit Real Estate Income Group": "MU", "Trustco Group Holdings": "NA", "Kibo Mining": "TZ"}


@lru_cache(maxsize=1)
def _listed() -> tuple[dict, Optional[re.Pattern]]:
    """Listed African companies and their home markets (src/data/african_listed_companies.json). A one-word
    name counts only when it is distinctive enough not to be an ordinary word ("Equity", "Total")."""
    import json
    from pathlib import Path
    try:
        names = json.loads((Path(__file__).with_name("african_listed_companies.json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, None
    if isinstance(names, list):
        return {}, None
    # Multi-word names only: one-word listed names are often ordinary words in a title-case headline
    # ("Discovery", "Spur"). Groups headquartered outside Africa never place a deal.
    usable = {n: _HOME_OVERRIDE.get(n, iso) for n, iso in names.items()
              if iso and " " in n.strip() and not _FOREIGN_PRIMARY.match(n)}
    if not usable:
        return {}, None
    ordered = sorted(usable, key=len, reverse=True)
    return usable, re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in ordered) + r")(?:['’]s)?(?![\w-])")


def countries_of_companies(text: str) -> list[str]:
    """Home markets (ISO2) of the known African companies a text names (the curated list, then listed
    companies), in order of mention."""
    out: list[str] = []
    for m in _pattern().finditer(text or ""):
        iso = AFRICAN_COMPANIES[m.group(1)]
        if iso not in out:
            out.append(iso)
    names, pattern = _listed()
    if pattern:
        for m in pattern.finditer(text or ""):
            iso = names[m.group(1)]
            if iso not in out:
                out.append(iso)
    return out
