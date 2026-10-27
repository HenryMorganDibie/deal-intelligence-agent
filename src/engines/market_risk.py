"""
Currency risk, sector risk and the valuation view.

Currency risk (the 42 distinct currencies of the 54 countries):
  exchange-rate regime, live spot rate, last annual depreciation against the US
  dollar, five-year annualised depreciation and the volatility of annual
  changes, from World Bank official rates (period averages). The score is a
  fixed formula of those numbers, reduced for hard pegs.

Sector risk (any sector, optionally one country):
  the balance of adverse corporate events (credit, distress, restructuring,
  regulatory action) against deal flow and other events in the monitored
  feed, with additive smoothing so a thin sample stays near neutral.

Valuation view:
  reported and stake-implied valuations from the company's own transactions,
  size and valuation statistics of comparable deals, and listed multiples
  where the company trades.
"""
from __future__ import annotations

import statistics
from collections import Counter
from datetime import date, timedelta
from typing import Callable, Iterable, Optional

from src.data.africa_countries import COUNTRIES, get as get_country
from src.engines import country_risk as cr
from src.engines import deals as deals_mod

# Exchange-rate regimes (IMF AREAER categories, simplified).
PEGS: dict[str, tuple[str, str]] = {
    "XOF": ("hard peg", "Fixed to the euro (655.957 per EUR) under the WAEMU monetary union, guaranteed by the French Treasury"),
    "XAF": ("hard peg", "Fixed to the euro (655.957 per EUR) under the CEMAC monetary union"),
    "KMF": ("hard peg", "Fixed to the euro (491.968 per EUR)"),
    "CVE": ("hard peg", "Fixed to the euro (110.265 per EUR)"),
    "STN": ("hard peg", "Fixed to the euro (24.5 per EUR)"),
    "NAD": ("hard peg", "At par with the South African rand (Common Monetary Area)"),
    "LSL": ("hard peg", "At par with the South African rand (Common Monetary Area)"),
    "SZL": ("hard peg", "At par with the South African rand (Common Monetary Area)"),
    "DJF": ("hard peg", "Currency board, fixed to the US dollar (177.721 per USD)"),
    "ERN": ("conventional peg", "Pegged to the US dollar"),
    "MAD": ("basket peg", "Pegged to a euro-dollar basket within a band"),
    "BWP": ("crawling peg", "Crawling peg to a rand-SDR basket"),
    "TND": ("managed float", "Managed against a basket"),
    "LYD": ("conventional peg", "Pegged to the SDR"),
}
_REGIME_FACTOR = {"hard peg": 0.4, "conventional peg": 0.6, "basket peg": 0.6, "crawling peg": 0.7, "managed float": 0.9}


def _clamp(x: float) -> float:
    return round(max(0.0, min(100.0, x)), 1)


def currency_history(currency: str, snapshot: Optional[dict] = None) -> dict[str, float]:
    """{year: LCU per USD}, from the country using the currency with the longest series."""
    snap = snapshot if snapshot is not None else cr.load_snapshot()
    series = snap.get("series", {}).get("PA.NUS.FCRF") or {}
    best = max((series.get(c.iso3) or {} for c in COUNTRIES if c.currency == currency), key=len, default={})
    current, _ = cr.fx_series_after_break(best)          # earlier years are in the pre-redenomination unit
    return dict(sorted(current.items()))


def currency_risk(currency: str, snapshot: Optional[dict] = None,
                  fx: Optional[Callable[[str], Optional[float]]] = None) -> dict:
    hist = currency_history(currency, snapshot)
    years = sorted(hist)
    changes = [(hist[b] / hist[a] - 1) * 100 for a, b in zip(years, years[1:]) if hist[a] > 0]
    last = changes[-1] if changes else None
    five = None
    if len(years) >= 2:
        span = years[-6:] if len(years) >= 6 else years
        n = int(span[-1]) - int(span[0])
        if n > 0 and hist[span[0]] > 0:
            five = ((hist[span[-1]] / hist[span[0]]) ** (1 / n) - 1) * 100
    vol = statistics.pstdev(changes[-5:]) if len(changes) >= 2 else None
    regime, regime_note = PEGS.get(currency, ("floating or managed float", "Market-determined with central bank intervention"))
    parts = []
    if last is not None:
        parts.append(("last_year_depreciation", 0.4, _clamp(last / 50 * 100)))
    if five is not None:
        parts.append(("five_year_annualised_depreciation", 0.35, _clamp(five / 30 * 100)))
    if vol is not None:
        parts.append(("volatility_of_annual_changes", 0.25, _clamp(vol / 25 * 100)))
    weight = sum(w for _, w, _ in parts)
    raw = sum(w * r for _, w, r in parts) / weight if weight else None
    factor = _REGIME_FACTOR.get(regime, 1.0)
    score = round(raw * factor, 1) if raw is not None else None
    spot = (fx or cr.spot_fx)(currency)
    latest_official = hist[years[-1]] if years else None
    return {
        "currency": currency,
        "countries": [c.iso2 for c in COUNTRIES if c.currency == currency],
        "regime": regime, "regime_note": regime_note,
        "spot_per_usd": spot,
        "official_per_usd": {"value": round(latest_official, 4), "year": int(years[-1])} if latest_official else None,
        "spot_vs_official_pct": round((spot / latest_official - 1) * 100, 1) if spot and latest_official else None,
        "last_year_depreciation_pct": round(last, 2) if last is not None else None,
        "five_year_annualised_depreciation_pct": round(five, 2) if five is not None else None,
        "volatility_pct": round(vol, 2) if vol is not None else None,
        "history": {y: round(v, 4) for y, v in hist.items()},
        "score": score, "tier": cr.tier(score) if score is not None else None,
        "components": [{"name": n, "weight": w, "risk": r} for n, w, r in parts],
        "method": "Weighted: last-year depreciation / 50% (0.4), five-year annualised / 30% (0.35), volatility of "
                  "annual changes / 25 points (0.25); times a regime factor (hard peg 0.4, peg 0.6, crawling 0.7, "
                  "managed 0.9, float 1.0). Spot vs official gap shown separately: a large gap signals a parallel "
                  "market or a pending devaluation.",
    }


def all_currencies(snapshot: Optional[dict] = None) -> list[dict]:
    seen, rows = set(), []
    for c in COUNTRIES:
        if c.currency in seen:
            continue
        seen.add(c.currency)
        rows.append(currency_risk(c.currency, snapshot, fx=lambda _: None))
    return sorted(rows, key=lambda r: (r["score"] is None, -(r["score"] or 0)))


ADVERSE = {"credit_risk", "distressed_asset", "debt_restructuring", "regulatory_action"}


def sector_risk(sector: str, events: Iterable[dict], deals: Iterable[dict], country: Optional[str] = None,
                days: int = 90, today: Optional[date] = None, prior: float = 5.0) -> dict:
    """Adverse-event share for a sector over the window, smoothed toward 50 with `prior` pseudo-observations."""
    today = today or date.today()
    since = (today - timedelta(days=days)).isoformat()
    c = get_country(country) if country else None

    def in_scope(row: dict, day_key: str) -> bool:
        if row.get("sector") != sector or (row.get(day_key) or "") < since:
            return False
        return not c or c.iso2 in (row.get("countries") or [row.get("country")])

    ev = [e for e in events if in_scope(e, "day")]
    dl = [d for d in deals if in_scope(d, "announced")]
    adverse = [e for e in ev if e.get("signal_type") in ADVERSE]
    other = len(ev) - len(adverse) + len(dl)
    share = (len(adverse) + prior * 0.5) / (len(adverse) + other + prior)
    score = _clamp(share * 100)
    return {
        "sector": sector, "country": c.iso2 if c else None, "window_days": days,
        "adverse_events": len(adverse), "other_events": len(ev) - len(adverse), "deals": len(dl),
        "deal_value_usd": round(sum(d.get("amount_usd") or 0 for d in dl)),
        "adverse_by_type": dict(Counter(e["signal_type"] for e in adverse)),
        "score": score, "tier": cr.tier(score),
        "sample": len(ev) + len(dl),
        "low_sample": len(ev) + len(dl) < 10,
        "examples": [{"headline": e["headline"], "day": e.get("day"), "signal_type": e["signal_type"], "url": e.get("url")}
                     for e in sorted(adverse, key=lambda e: e.get("day") or "", reverse=True)[:8]],
        "method": f"(adverse events + {prior / 2:g}) / (all events and deals + {prior:g}) over {days} days; "
                  "adverse = credit risk, distress, debt restructuring, regulatory action.",
    }


def valuation_view(company: str, deals: Iterable[dict], profile: Optional[dict] = None) -> dict:
    """Own transaction valuations, comparable deals and listed multiples for one company."""
    deals = list(deals)
    key = deals_mod.normalise_name(company)
    own = [d for d in deals if deals_mod.normalise_name(d.get("target")) == key]
    ref = max(own, key=lambda d: d.get("announced") or "", default=None)
    marks = [{"announced": d.get("announced"), "deal_type": d["deal_type"], "amount_usd": d.get("amount_usd"),
              "stake_pct": d.get("stake_pct"),
              "valuation_usd": d.get("reported_valuation_usd") or d.get("implied_valuation_usd"),
              "basis": "reported" if d.get("reported_valuation_usd") else ("implied by stake" if d.get("implied_valuation_usd") else None),
              "headline": d.get("headline")} for d in sorted(own, key=lambda d: d.get("announced") or "")]
    comps = deals_mod.comparables(
        deals, sector=(ref or {}).get("sector") or (profile or {}).get("identity", {}).get("sector"),
        country=(ref or {}).get("country") or (profile or {}).get("country"),
        deal_type=(ref or {}).get("deal_type") or "equity_funding",
        amount_usd=(ref or {}).get("amount_usd"), exclude_id=(ref or {}).get("id"))
    listed = (profile or {}).get("multiples") or {}
    market = (profile or {}).get("market") or {}
    return {"company": company, "transaction_marks": [m for m in marks if m["valuation_usd"] or m["amount_usd"]],
            "latest_mark": next((m for m in reversed(marks) if m["valuation_usd"]), None),
            "comparables": comps, "listed_multiples": listed,
            "market_cap": market.get("market_cap"), "market_currency": market.get("currency"),
            "note": "Valuations are as reported in the press or implied by a disclosed stake and price; "
                    "comparable deals are matched on sector, type, country and size."}
