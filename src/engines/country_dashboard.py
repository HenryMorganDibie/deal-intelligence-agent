"""
What a country page shows beyond its own deal history, from data the platform already collects for other pages:

  - market: the country's exchange (dollar return this year, market value, breadth) and its largest listed companies;
  - rates: the policy rate, the latest Treasury bill auction, and the official dollar rate beside the stablecoin rate;
  - investor origin: where the investors in the country's deals of the last twelve months are based;
  - benchmarks: the country's rank among the 54 and its deal sizes and sectors against the continent's;
  - elections: the elections monitored there, with their dates and the page that follows them;
  - outlook: the IMF's current-year figures and forecasts (growth, inflation, government debt, current account);
  - compare: a few countries side by side on all of the above.

Pure functions over rows the caller supplies, so each block is testable without the network; only imf_outlook reads
the IMF's public DataMapper API (no key), cached for a day.
"""
from __future__ import annotations

import statistics
import time
from collections import Counter
from datetime import date, timedelta
from typing import Iterable, Optional

import httpx

from src.data import africa_countries

# ── Markets ──────────────────────────────────────────────────────────────────

def market_block(code: str, overview: dict, screener_rows: list[dict]) -> Optional[dict]:
    """The country's exchanges from the markets overview, and its largest listed companies by market value."""
    tiles = [t for t in (overview or {}).get("exchanges") or [] if t.get("country") == code]
    if not tiles:
        return None
    keep = ("exchange", "name", "currency", "index", "ytd_usd", "ytd_local", "ytd_median_usd", "mcap_usd", "listed",
            "priced_today", "advancers", "decliners", "market_chg_1d")
    companies = [{k: r.get(k) for k in ("exchange", "symbol", "name", "sector", "price", "currency", "chg_1d", "ytd_usd",
                                          "mcap_usd", "date")} for r in screener_rows[:10]]
    return {"exchanges": [{k: t.get(k) for k in keep} for t in tiles], "largest": companies,
            "mcap_usd": round(sum(t.get("mcap_usd") or 0 for t in tiles), 2) or None}


# ── Rates and currency ───────────────────────────────────────────────────────

def rates_block(code: str, policy_rates: list[dict], tbills: list[dict], stablecoins: list[dict]) -> dict:
    """Policy rate, latest Treasury bill auction and the official versus stablecoin dollar rate, each dated."""
    policy = next((r for r in policy_rates or [] if r.get("country") == code), None)
    bill = next((b for b in tbills or [] if b.get("country") == code), None)
    coin = next((r for r in stablecoins or [] if r.get("country") == code), None)
    return {
        "policy_rate": policy and {k: policy.get(k) for k in ("rate", "date", "date_kind", "source", "source_url",
                                                              "confirmed_by")},
        "tbills": bill and {"date": max((r.get("auction_date") or "" for r in bill.get("rows") or []), default=None) or None,
                            "source": bill.get("source"), "source_url": bill.get("source_url"),
                            "rows": [{k: r.get(k) for k in ("tenor_days", "rate_type", "rate", "auction_date")}
                                     for r in (bill.get("rows") or [])[:6]]},
        "stablecoin": coin and {k: coin.get(k) for k in ("pair", "rate", "official_per_usd", "premium", "source")},
    }


# ── Investor origin ──────────────────────────────────────────────────────────

def investor_origin(code: str, deals: Iterable[dict], today: date, days: int = 365) -> dict:
    """Where the investors in the country's deals of the last year are based: deals by investor home country, the
    country's own investors marked local. A deal with investors from two countries counts for both."""
    from src.engines import investor_origin as origin
    since = (today - timedelta(days=days)).isoformat()
    counts: Counter = Counter()
    placed = total = 0
    for d in deals:
        if (d.get("announced") or "") < since or code not in (d.get("countries") or [d.get("country")]):
            continue
        total += 1
        homes = origin.deal_investor_countries(d)
        if homes:
            placed += 1
            counts.update(homes)
    def name(c: str) -> str:
        place = africa_countries.get(c)
        return origin.country_name(c) or (place.name if place else c)
    rows = [{"country": c, "name": name(c), "deals": n,
             "share": round(n / placed, 4) if placed else 0, "local": c == code}
            for c, n in counts.most_common(12)]
    foreign = sum(n for c, n in counts.items() if c != code)
    return {"since": since, "deals": total, "deals_with_known_origin": placed, "origins": rows,
            "foreign_share": round(foreign / sum(counts.values()), 4) if counts else None,
            "note": "Counted for the deals whose investors' home countries are known; a floor, not a census."}


# ── Benchmarks against Africa ────────────────────────────────────────────────

def _in(d: dict, code: str) -> bool:
    return code in (d.get("countries") or [d.get("country")])


def benchmarks(code: str, deals: list[dict], today: date, days: int = 365) -> dict:
    """The country's rank among the 54 by deals in the last year, and its deal sizes, disclosure and sectors against
    the whole continent's."""
    since = (today - timedelta(days=days)).isoformat()
    recent = [d for d in deals if (d.get("announced") or "") >= since]
    per_country: Counter = Counter()
    for d in recent:
        for c in set(d.get("countries") or [d.get("country")]) - {None}:
            per_country[c] += 1
    ranked = [c for c, _ in per_country.most_common()]
    mine = [d for d in recent if _in(d, code)]

    def median(rows: list[dict]) -> Optional[float]:
        values = [d["amount_usd"] for d in rows if d.get("amount_usd")]
        return round(statistics.median(values), 2) if values else None

    def disclosed(rows: list[dict]) -> Optional[float]:
        return round(sum(1 for d in rows if d.get("amount_usd")) / len(rows), 4) if rows else None

    def sectors(rows: list[dict]) -> Counter:
        return Counter(d.get("sector") for d in rows if d.get("sector"))

    mine_s, all_s = sectors(mine), sectors(recent)
    sector_rows = [{"sector": s, "deals": n, "share": round(n / max(sum(mine_s.values()), 1), 4),
                    "africa_share": round(all_s.get(s, 0) / max(sum(all_s.values()), 1), 4)}
                   for s, n in mine_s.most_common(6)]
    return {"since": since, "deals": len(mine), "rank": ranked.index(code) + 1 if code in ranked else None,
            "countries_ranked": len(ranked), "africa_deals": len(recent),
            "median_size_usd": median(mine), "africa_median_size_usd": median(recent),
            "disclosed_share": disclosed(mine), "africa_disclosed_share": disclosed(recent),
            "sectors": sector_rows}


# ── Elections ────────────────────────────────────────────────────────────────

_ELECTION_PAGES = {"ng-2027": "/elections/nigeria", "gm-2026": "/elections/gambia"}


def elections(code: str, today: date) -> list[dict]:
    """The elections the platform monitors in this country, with their dates and the page that follows them."""
    from src.data.election_profiles import PROFILES
    out = []
    profiles = dict(PROFILES)
    profiles.setdefault("ng-2027", {"iso": "NG", "label": "Nigeria: 2027 general election",
                                    "dates": [("2027-01-16", "Presidential and National Assembly"),
                                              ("2027-02-06", "Governorship and state assembly")]})
    for key, p in profiles.items():
        if p.get("iso") != code:
            continue
        dates = [{"date": d, "label": label, "past": d < today.isoformat()} for d, label in p.get("dates") or []]
        out.append({"key": key, "label": p.get("label"), "dates": dates,
                    "page": _ELECTION_PAGES.get(key), "api": f"/v1/elections?election={key}"})
    return out


# ── IMF outlook ──────────────────────────────────────────────────────────────

IMF_INDICATORS = {
    "NGDP_RPCH": "Real GDP growth, %",
    "PCPIPCH": "Inflation, average consumer prices, %",
    "GGXWDG_NGDP": "Government gross debt, % of GDP",
    "BCA_NGDPD": "Current account balance, % of GDP",
}
IMF_URL = "https://www.imf.org/external/datamapper/api/v1/{indicator}"
_imf_cache: dict[str, tuple[float, dict]] = {}


def _imf_series(indicator: str, client: Optional[httpx.Client] = None) -> dict:
    """Every country's series for one indicator, cached a day (the IMF updates twice a year)."""
    hit = _imf_cache.get(indicator)
    if hit and time.monotonic() - hit[0] < 86_400:
        return hit[1]
    own = client is None
    client = client or httpx.Client(timeout=20, headers={"User-Agent": "deal-intelligence/1.0"})
    try:
        r = client.get(IMF_URL.format(indicator=indicator))
        data = (r.json().get("values") or {}).get(indicator) or {} if r.status_code == 200 else {}
    except (httpx.HTTPError, ValueError):
        data = {}
    finally:
        if own:
            client.close()
    if data:
        _imf_cache[indicator] = (time.monotonic(), data)
    return data


def imf_outlook(iso3: str, today: date, client: Optional[httpx.Client] = None) -> Optional[dict]:
    """Last year, this year and next year for each IMF indicator; the years from this one on are IMF projections."""
    years = [str(today.year - 1), str(today.year), str(today.year + 1)]
    rows = []
    for indicator, label in IMF_INDICATORS.items():
        series = _imf_series(indicator, client).get(iso3) or {}
        values = {y: series.get(y) for y in years}
        if any(v is not None for v in values.values()):
            rows.append({"indicator": indicator, "label": label, "values": values})
    if not rows:
        return None
    return {"years": years, "projected_from": str(today.year), "rows": rows, "source": "IMF World Economic Outlook",
            "source_url": f"https://www.imf.org/external/datamapper/profile/{iso3}"}


# ── Compare ──────────────────────────────────────────────────────────────────

def compare_row(country, risk: dict, bench: dict, origin: dict, market: Optional[dict], rates: dict,
                outlook: Optional[dict], currency: dict) -> dict:
    """One country's line in a side-by-side comparison."""
    top_origin = next((o for o in origin.get("origins") or [] if not o.get("local")), None)

    def outlook_value(indicator: str) -> Optional[float]:
        row = next((r for r in (outlook or {}).get("rows") or [] if r["indicator"] == indicator), None)
        return row and row["values"].get((outlook or {}).get("projected_from"))
    return {
        "iso2": country.iso2, "name": country.name, "currency": country.currency,
        "risk_score": risk.get("score"), "risk_tier": risk.get("tier"),
        "deals_12m": bench.get("deals"), "rank": bench.get("rank"), "median_size_usd": bench.get("median_size_usd"),
        "disclosed_share": bench.get("disclosed_share"),
        "top_sector": (bench.get("sectors") or [{}])[0].get("sector"),
        "foreign_investor_share": origin.get("foreign_share"),
        "top_foreign_origin": top_origin and top_origin["name"],
        "market_ytd_usd": (market or {}).get("exchanges", [{}])[0].get("ytd_usd") if market else None,
        "market_cap_usd": (market or {}).get("mcap_usd"),
        "policy_rate": (rates.get("policy_rate") or {}).get("rate"),
        "tbill": ((rates.get("tbills") or {}).get("rows") or [{}])[0].get("rate"),
        "stablecoin_premium": (rates.get("stablecoin") or {}).get("premium"),
        "currency_depreciation_last_year_pct": (currency or {}).get("last_year_depreciation_pct"),
        "gdp_growth": outlook_value("NGDP_RPCH"), "inflation": outlook_value("PCPIPCH"),
        "debt_to_gdp": outlook_value("GGXWDG_NGDP"),
    }
