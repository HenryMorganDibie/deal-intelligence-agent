"""Major African companies that deal headlines often name without a country ("MTN agrees to buy IHS").

A name here places a headline in Africa, under that company's home market. Only names that are
unambiguous on their own are listed: no namesakes elsewhere (e.g. Woolworths, Fidelity) and no
groups headquartered outside Africa (e.g. Anglo American, Investec). Matching is case-sensitive.
"""
from __future__ import annotations

import re
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
    "Ecobank": "TG", "Afreximbank": "EG", "Ethio Telecom": "ET",
}


@lru_cache(maxsize=1)
def _pattern() -> re.Pattern:
    names = sorted(AFRICAN_COMPANIES, key=len, reverse=True)
    return re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in names) + r")(?:['’]s)?(?![\w-])")


def countries_of_companies(text: str) -> list[str]:
    """Home markets (ISO2) of the known African companies a text names, in order of mention."""
    out: list[str] = []
    for m in _pattern().finditer(text or ""):
        iso = AFRICAN_COMPANIES[m.group(1)]
        if iso not in out:
            out.append(iso)
    return out
