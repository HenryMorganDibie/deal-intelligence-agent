"""
Attribution evaluation sets built from real headlines only.

Source: the news headlines fetched for the 46 backtest companies (data/hist_cache), each with its
real publisher, date and link. Two sets:

  natural    a random sample of headlines that name a tracked company, half US and half African
             companies: rates as they occur in daily use. This is the set to quote.
  hard       real headlines selected by simple filters for known failure modes (denials, references
             back to the company, subsidiaries and parents, two tracked companies in one headline,
             rumours and hypotheticals, historical references, aliases and tickers): where it breaks.
             Enriched on purpose, so its overall rates are not representative.

    python -m evaluation.attribution.build_sets

Item files hold inputs only, so labels are made blind to the engine's output. Fixed seed.
"""
from __future__ import annotations

import glob
import json
import random
import re
from pathlib import Path

from src.engines.deterministic_engine import _company_matchers, _mentions_company
from src.engines.historical_backtest import UNIVERSE
from src.engines.outcome_labeller import market_for_ticker

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEED = 20261016
N_NATURAL_PER_MARKET = 200
N_HARD_PER_CATEGORY = 40

# Short forms an analyst or headline writer uses; the engine is given only the company name and ticker.
ALIASES = {
    "Procter & Gamble": ["P&G"], "Coca-Cola": ["Coke"], "PepsiCo": ["Pepsi"], "Kellanova": ["Kellogg"],
    "Guaranty Trust Holding": ["GTCO", "GTBank", "GTB"], "East African Breweries": ["EABL"], "MTN Nigeria": ["MTNN"],
    "United States Steel": ["U.S. Steel", "US Steel"], "Paramount Global": ["Paramount"], "Discover Financial": ["Discover"],
    "Anglo American": ["Anglo"], "Access Holdings": ["Access Bank", "Access Corp"], "First HoldCo": ["FBN Holdings", "FirstBank", "First Bank"],
    "Sibanye Stillwater": ["Sibanye"], "Transcorp": ["Transnational Corporation"], "Juniper Networks": ["Juniper"],
    "Walgreens": ["Walgreens Boots Alliance", "WBA"], "Spirit AeroSystems": ["Spirit Aero"], "Southwest Airlines": ["Southwest"],
    "Dangote Cement": ["Dangote"], "Nestle Nigeria": ["Nestlé Nigeria"], "Seplat Energy": ["Seplat"], "Standard Bank": ["Stanbic"],
}
FILTERS = {
    "negation": re.compile(r"\b(denies|denied|deny|rules?\s+out|ruled\s+out|no\s+plans?|will\s+not|won['’]t|not\s+in\s+talks|"
                           r"dismiss\w*|rejects?|rejected|refutes?|d[ée]ment\w*|exclut|no\s+longer)\b", re.IGNORECASE),
    "back_reference": re.compile(r"[;:,–-]\s.{0,80}\b(it|its|the\s+(company|group|firm|lender|bank|carrier|airline|retailer|"
                                 r"chipmaker|planemaker|miner|telco|operator|brewer|insurer|giant|maker))\b", re.IGNORECASE),
    "subsidiary_parent": re.compile(r"\b(unit|subsidiary|subsidiaries|arm|division|affiliate|Nigeria|Ghana|Uganda|Kenya|Zambia|"
                                    r"Rwanda|Cameroon|Côte d['’]Ivoire|Ivory Coast|South Africa|Tanzania|Mozambique|Botswana)\b"),
    "rumour_hypothetical": re.compile(r"\b(in\s+talks|talks\s+to|considering|considers|weighs|explores?|exploring|reportedly|"
                                      r"could|may|might|eyes|plans\s+to|if|rumou?r\w*|speculat\w*|possible)\b", re.IGNORECASE),
    "historical": re.compile(r"\b(formerly|former|years\s+after|since\s+its|once|in\s+(19|20)\d\d|anniversary|history|"
                             r"looking\s+back|decade)\b", re.IGNORECASE),
}


def pool() -> list[dict]:
    seen, rows = set(), []
    for f in sorted(glob.glob(str(ROOT / "data" / "hist_cache" / "*.json"))):
        try:
            data = json.loads(Path(f).read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(data, list):
            continue
        for x in data:
            if not (isinstance(x, dict) and x.get("title") and x.get("url")):
                continue
            title = x["title"]
            pub = x.get("publisher") or ""
            if pub and title.endswith(f" - {pub}"):
                title = title[: -len(pub) - 3]
            key = re.sub(r"\W+", " ", title.lower()).strip()
            if key in seen or len(title) < 20:
                continue
            seen.add(key)
            rows.append({"title": title, "publisher": pub, "date": x.get("date"), "url": x["url"]})
    return rows


def main() -> None:
    rng = random.Random(SEED)
    rows = pool()
    companies = [(e[0], e[1]) for e in UNIVERSE]
    matchers = {c: _company_matchers(c, ticker=t) for c, t in companies}
    named = []
    for r in rows:
        hit = [c for c, _ in companies if _mentions_company(r["title"], matchers[c])]
        if hit:
            named.append({**r, "named": hit})
    ticker = dict(companies)

    def item(r: dict, target: str, category: str, set_name: str) -> dict:
        return {"set": set_name, "category": category, "company": target, "ticker": ticker[target],
                "market": market_for_ticker(ticker[target]), "title": r["title"], "publisher": r["publisher"],
                "date": r["date"], "url": r["url"],
                "other_tracked_companies": [c for c in r.get("named", []) if c != target]}

    used: set[str] = set()
    natural = []
    for market in ("us", "africa"):
        cands = [r for r in named if any(market_for_ticker(ticker[c]) == market for c in r["named"])]
        for r in rng.sample(cands, N_NATURAL_PER_MARKET):
            target = rng.choice([c for c in r["named"] if market_for_ticker(ticker[c]) == market])
            natural.append(item(r, target, "natural", "natural"))
            used.add(r["title"])

    hard = []
    rest = [r for r in named if r["title"] not in used]
    for cat, rx in FILTERS.items():
        cands = [r for r in rest if rx.search(r["title"])]
        if cat == "subsidiary_parent":                 # a parent named, with a unit or a country subsidiary
            cands = [r for r in cands if any(c in ("MTN Group", "Standard Bank", "Access Holdings", "UBA", "Equity Group",
                                                    "KCB Group", "Vodacom", "Naspers", "Anglo American", "Shoprite", "Sasol",
                                                    "Walgreens", "Paramount Global", "Coca-Cola", "PepsiCo", "Nike",
                                                    "Boeing", "Intel", "Microsoft", "Apple") for c in r["named"])]
        for r in rng.sample(cands, min(N_HARD_PER_CATEGORY, len(cands))):
            hard.append(item(r, rng.choice(r["named"]), cat, "hard"))
            used.add(r["title"])
        rest = [r for r in rest if r["title"] not in used]
    two = [r for r in rest if len(r["named"]) >= 2]
    for r in rng.sample(two, min(N_HARD_PER_CATEGORY, len(two))):
        hard.append(item(r, rng.choice(r["named"]), "multi_party", "hard"))
        used.add(r["title"])
    # Aliases: headlines that use a short form the engine is not given, and do not name the company otherwise.
    alias_rows = []
    for r in rows:
        if r["title"] in used:
            continue
        for c, forms in ALIASES.items():
            if any(re.search(rf"(?<![\w&]){re.escape(f)}(?![\w&])", r["title"]) for f in forms) \
                    and not _mentions_company(r["title"], matchers[c]):
                alias_rows.append((r, c))
                break
    for r, c in rng.sample(alias_rows, min(N_HARD_PER_CATEGORY, len(alias_rows))):
        hard.append(item({**r, "named": [c]}, c, "alias", "hard"))

    rng.shuffle(natural)
    rng.shuffle(hard)
    for name, items in (("natural", natural), ("hard", hard)):
        for k, it in enumerate(items):
            it["item_id"] = f"{name[0]}{k:03d}"
        (HERE / f"{name}_items.jsonl").write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items))
        print(name, len(items))


if __name__ == "__main__":
    main()
