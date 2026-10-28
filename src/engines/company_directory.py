"""
Every company the product knows: each listed share in the daily market snapshot and each private company the deals
database records as the target of a funding round, loan, acquisition, merger, exit or listing.

A private company is one row per normalised name, with its country and sector, how many transactions name it,
equity and debt raised, its latest round and valuation mark, and its investors. A company that also matches a
listing (by exact name or symbol in its country) is shown once, as listed, with its transaction history attached.
Search ranks listed and private companies together.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Iterable, Optional

from src.engines import deals as deals_mod
from src.engines import markets
from src.engines.investors import parties

_TARGET_TYPES = {"equity_funding", "debt_financing", "acquisition", "merger", "exit", "ipo"}
_EXTRA_DESCRIPTORS = {"billion", "million", "dollar", "valued", "leading", "largest", "fast", "growing", "popular",
                      "giant", "firm", "platform", "company", "based", "born", "backed", "owned"}
_NOT_A_PARTY = re.compile(r"(?i)^(?:and\s+)?others?$|^and\s+|^other\s+investors$|^existing\s+investors$")


def _descriptive(words: list[str]) -> bool:
    return all(deals_mod._is_description_word(w) or w in _EXTRA_DESCRIPTORS or w.isdigit() for w in words)


def _fold_described(groups: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """"Billion-Dollar Fintech Moniepoint" is Moniepoint: a key made of description words and another company's
    key joins that company."""
    for key in sorted(groups, key=len, reverse=True):
        words = key.split()
        for i in range(1, len(words)):
            rest = " ".join(words[i:])
            if rest in groups and rest != key and _descriptive(words[:i]):
                groups[rest].extend(groups.pop(key))
                break
    return groups


def private_companies(deals: Iterable[dict]) -> list[dict]:
    """One row per company the deals database names as a transaction's target, newest activity first."""
    groups: dict[str, list[dict]] = {}
    for d in deals:
        target = (d.get("target") or "").strip()
        if d.get("deal_type") not in _TARGET_TYPES or not target or target.lower().startswith("undisclosed"):
            continue
        key = deals_mod.normalise_name(target)
        if key:
            groups.setdefault(key, []).append(d)
    out = []
    for key, rows in _fold_described(groups).items():
        rows.sort(key=lambda d: d.get("announced") or "", reverse=True)
        latest = rows[0]
        # The plainest spelling names the company ("Moniepoint", not "Billion-Dollar Fintech Moniepoint").
        name = next((d["target"] for d in rows if deals_mod.normalise_name(d["target"]) == key), latest["target"])
        raised = [d for d in rows if d["deal_type"] in ("equity_funding", "debt_financing") and d.get("amount_usd")]
        marks = [d for d in rows if d.get("reported_valuation_usd") or d.get("implied_valuation_usd")]
        investors: list[str] = []
        for d in rows:
            for party, role in parties(d):
                if role in ("investor", "lender", "acquirer") and party not in investors and not _NOT_A_PARTY.search(party):
                    investors.append(party)
        sector = next((d.get("sector") for d in rows if d.get("sector")), None)
        out.append({
            "kind": "private", "key": key, "name": name,
            "country": next((d.get("country") for d in rows if d.get("country")), None),
            "sector": markets.DEAL_SECTOR_TO_LISTED.get(sector or "") or None, "deal_sector": sector,
            "deal_count": len(rows),
            "equity_raised_usd": round(sum(d["amount_usd"] for d in raised if d["deal_type"] == "equity_funding")) or None,
            "debt_raised_usd": round(sum(d["amount_usd"] for d in raised if d["deal_type"] == "debt_financing")) or None,
            "last_round": next((d.get("round") for d in rows if d.get("round")), None),
            "last_deal_type": latest["deal_type"], "last_deal_date": latest.get("announced"),
            "valuation_usd": (marks[0].get("reported_valuation_usd") or marks[0].get("implied_valuation_usd")) if marks else None,
            "valuation_date": marks[0].get("announced") if marks else None,
            "acquired": any(d["deal_type"] in ("acquisition", "merger") and (d.get("stake_pct") or 0) > 50 for d in rows),
            "investors": investors[:8], "investor_count": len(investors),
        })
    return sorted(out, key=lambda r: r["last_deal_date"] or "", reverse=True)


def _listed_row(q: dict) -> dict:
    return {"kind": "listed", "name": q["name"], "country": q["country"], "sector": markets._sector(q.get("sector")),
            "exchange": q["exchange"], "exchange_name": q["exchange_name"], "symbol": q["symbol"],
            "price": q.get("price"), "currency": q["currency"], "chg_1d": q.get("chg_1d"), "ytd_usd": q.get("ytd_usd"),
            "mcap_usd": q.get("mcap_usd"), "pe": q.get("pe"), "date": q.get("date"), "stale": q["stale"],
            "secondary_of": q.get("secondary_of")}


def event_companies(events: Iterable[dict]) -> list[dict]:
    """Companies corporate events name (a results warning, a regulator's fine, a board change), one row each,
    with how many events and the latest; for companies that appear in no recorded transaction."""
    from src.engines.event_filters import named_company
    groups: dict[str, dict] = {}
    for e in events:
        name = named_company(e.get("headline_en") or e.get("headline") or "")
        key = deals_mod.normalise_name(name)
        if not name or not key or not e.get("country"):
            continue
        g = groups.setdefault(key, {"kind": "private", "key": key, "name": name, "country": e.get("country"),
                                    "sector": markets.DEAL_SECTOR_TO_LISTED.get(e.get("sector") or ""),
                                    "deal_sector": e.get("sector"), "deal_count": 0, "event_count": 0,
                                    "last_event_date": None, "source": "corporate events"})
        g["event_count"] += 1
        g["last_event_date"] = max(g["last_event_date"] or "", e.get("day") or "") or None
    return list(groups.values())


def curated_companies() -> list[dict]:
    """The curated list of African companies the product recognises in headlines."""
    from src.data.african_companies import AFRICAN_COMPANIES
    return [{"kind": "private", "key": deals_mod.normalise_name(n), "name": n, "country": iso, "sector": None,
             "deal_count": 0, "source": "curated list"} for n, iso in AFRICAN_COMPANIES.items() if iso]


def directory(snapshot: dict, deals: Iterable[dict], today: Optional[date] = None,
              events: Iterable[dict] = ()) -> list[dict]:
    """Listed and private companies in one list. A private record that matches a listing in its country (exact
    name or symbol) is folded into the listing as its transaction history. Companies known only from corporate
    events or the curated list follow, when they match nothing already listed."""
    listed = [_listed_row(q) for q in markets.enrich(snapshot, today)]
    by_key: dict[tuple[str, str], dict] = {}
    for row in listed:
        for k in {markets._strict_key(row["name"]), deals_mod.normalise_name(row["name"])}:
            if k:
                by_key.setdefault((k, row["country"]), row)
        by_key.setdefault((row["symbol"].lower(), row["country"]), row)
    out = list(listed)
    for p in private_companies(deals):
        hit = by_key.get((p["key"], p["country"])) or by_key.get((markets._strict_key(p["name"]), p["country"]))
        if hit:
            hit.update(deal_count=p["deal_count"], equity_raised_usd=p["equity_raised_usd"],
                       debt_raised_usd=p["debt_raised_usd"], last_deal_date=p["last_deal_date"],
                       investors=p["investors"])
        else:
            out.append(p)
    known = {(deals_mod.normalise_name(r["name"]), r.get("country")) for r in out} | \
            {deals_mod.normalise_name(r["name"]) for r in out}
    for extra in [*event_companies(events), *curated_companies()]:
        k = extra["key"]
        if not k or k in known or (k, extra["country"]) in known or by_key.get((k, extra["country"])):
            continue
        known.add(k)
        out.append(extra)
    return out


_SORTS = {
    "recent": lambda r: (r.get("last_deal_date") or r.get("last_event_date") or r.get("date") or ""),
    "raised": lambda r: (r.get("equity_raised_usd") or 0) + (r.get("debt_raised_usd") or 0),
    "size": lambda r: r.get("mcap_usd") or r.get("valuation_usd") or 0,
    "deals": lambda r: r.get("deal_count") or 0,
}


def query(rows: list[dict], q: Optional[str] = None, kind: str = "all", country: Optional[str] = None,
          sector: Optional[str] = None, sort: str = "recent", limit: int = 50, offset: int = 0) -> dict:
    """Filter, search and page the directory. `counts` give listed and private matches before the kind filter."""
    if country:
        rows = [r for r in rows if (r.get("country") or "") == country.upper()]
    if sector:
        rows = [r for r in rows if (r.get("sector") or "").lower() == sector.lower()]
    if q:
        hits = markets.search_rows(rows, q)
        # Ties go to the company with more on record: a listing, then more transactions.
        rows = [r for _, r in sorted(hits, key=lambda h: (-round(h[0], 2), h[1]["kind"] != "listed",
                                                          -(h[1].get("deal_count") or 0)))]
    elif sort == "name":
        rows = sorted(rows, key=lambda r: (r.get("name") or "").lower())
    else:
        rows = sorted(rows, key=_SORTS.get(sort, _SORTS["recent"]), reverse=True)
    counts = {"listed": sum(1 for r in rows if r["kind"] == "listed"),
              "private": sum(1 for r in rows if r["kind"] == "private")}
    if kind in ("listed", "private"):
        rows = [r for r in rows if r["kind"] == kind]
    return {"total": len(rows), "offset": offset, "rows": rows[offset:offset + limit], "counts": counts}
