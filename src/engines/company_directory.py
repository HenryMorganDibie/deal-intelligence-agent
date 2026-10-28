"""
Every company the product knows: each listed share in the daily market snapshot and each private company the deals
database records as the target of a funding round, loan, acquisition, merger, exit or listing.

A private company is one row per normalised name, with its country and sector, how many transactions name it,
equity and debt raised, its latest round and valuation mark, and its investors. A company that also matches a
listing (by exact name or symbol in its country) is shown once, as listed, with its transaction history attached.
Search ranks listed and private companies together.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from src.engines import deals as deals_mod
from src.engines import markets
from src.engines.investors import parties

_TARGET_TYPES = {"equity_funding", "debt_financing", "acquisition", "merger", "exit", "ipo"}


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
    for key, rows in groups.items():
        rows.sort(key=lambda d: d.get("announced") or "", reverse=True)
        latest = rows[0]
        raised = [d for d in rows if d["deal_type"] in ("equity_funding", "debt_financing") and d.get("amount_usd")]
        marks = [d for d in rows if d.get("reported_valuation_usd") or d.get("implied_valuation_usd")]
        investors: list[str] = []
        for d in rows:
            for name, role in parties(d):
                if role in ("investor", "lender", "acquirer") and name not in investors:
                    investors.append(name)
        sector = next((d.get("sector") for d in rows if d.get("sector")), None)
        out.append({
            "kind": "private", "key": key, "name": latest["target"],
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


def directory(snapshot: dict, deals: Iterable[dict], today: Optional[date] = None) -> list[dict]:
    """Listed and private companies in one list. A private record that matches a listing in its country (exact
    name or symbol) is folded into the listing as its transaction history."""
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
    return out


_SORTS = {
    "recent": lambda r: (r.get("last_deal_date") or r.get("date") or ""),
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
