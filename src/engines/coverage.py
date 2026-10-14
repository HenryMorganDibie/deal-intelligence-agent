"""
Data coverage and verification, country by country.

For each of the 54 countries this states what the product can read and how
far each kind of data can be verified, so no one has to infer coverage from
marketing copy:

  listing data     machine-readable prices and statements (NGX, NSE Kenya,
                   Yahoo-carried exchanges) versus none
  filings          official disclosure sources the pipeline reads
  news             national Google News edition or a language edition, in
                   which languages
  regulators       national regulators and central bank matched by the rules
  country risk     share of the risk components with World Bank data
  deals / events   records in the live database (when supplied)

Verification tier:
  A  official filings and prices are machine-readable, so signals can be
     confirmed by exchange disclosures and judged on price
  B  prices or statements from a data vendor, filings not machine-readable;
     confirmation relies on credible news
  C  no listing data; coverage is news, deals and country risk, confirmation
     relies on credible news only
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable, Optional

from src.data.africa_countries import COUNTRIES, Country
from src.engines import country_risk as cr

# What the pipeline actually reads per listing suffix.
LISTING_SOURCES: dict[str, dict] = {
    "NG": {"prices": "NGX price list and 20-day history; daily snapshot", "statements": "NGX audited statements (parsed and checked)",
           "filings": "NGX disclosures library (full history)", "tier": "A"},
    "KE": {"prices": "NSE Kenya price list (myStocks); daily snapshot", "statements": "NSE Kenya results (parsed and checked)",
           "filings": "NSE Kenya document library (full history)", "tier": "A"},
    "ZA": {"prices": "Yahoo Finance (.JO)", "statements": "Yahoo Finance annual statements",
           "filings": "JSE SENS (current day only, via Sharenet)", "tier": "B"},
    "EG": {"prices": "Yahoo Finance (.CA)", "statements": "Yahoo Finance annual statements", "filings": None, "tier": "B"},
    "MA": {"prices": "Yahoo Finance (.CS)", "statements": "Yahoo Finance where carried", "filings": None, "tier": "B"},
}
_DEFAULT_LISTED = {"prices": None, "statements": None, "filings": None, "tier": "C"}


def country_row(c: Country, deals: Iterable[dict] = (), events: Iterable[dict] = ()) -> dict:
    listing = LISTING_SOURCES.get(c.iso2, _DEFAULT_LISTED)
    risk = cr.assess(c, fx=lambda _: None)
    deal_rows = [d for d in deals if c.iso2 in (d.get("countries") or [d.get("country")])]
    event_rows = [e for e in events if c.iso2 in (e.get("countries") or [e.get("country")])]
    return {
        "iso2": c.iso2, "country": c.name, "region": c.region,
        "exchange": c.exchange, "currency": c.currency,
        "prices": listing["prices"] or ("Yahoo Finance (" + c.yahoo_suffix + ") suffix known; availability not verified"
                                        if c.yahoo_suffix else None),
        "statements": listing["statements"],
        "filings": listing["filings"],
        "news": {"edition": c.edition(), "national_edition": bool(c.news_edition), "languages": list(c.languages)},
        "regulators": [r for r in (c.central_bank, c.securities_regulator) if r],
        "regulator_acronyms": list(c.regulator_acronyms),
        "country_risk": {"score": risk["score"], "tier": risk["tier"], "coverage": risk["coverage"]},
        "deals": len(deal_rows),
        "deal_value_usd": round(sum(d.get("amount_usd") or 0 for d in deal_rows)),
        "events": len(event_rows),
        "tier": listing["tier"],
    }


def matrix(deals: Iterable[dict] = (), events: Iterable[dict] = ()) -> dict:
    deals, events = list(deals), list(events)
    rows = [country_row(c, deals, events) for c in COUNTRIES]
    return {
        "countries": rows,
        "summary": {
            "countries": len(rows),
            "by_tier": dict(Counter(r["tier"] for r in rows)),
            "national_news_editions": sum(r["news"]["national_edition"] for r in rows),
            "full_country_risk_coverage": sum(r["country_risk"]["coverage"] == 1.0 for r in rows),
            "with_deals": sum(r["deals"] > 0 for r in rows),
            "with_events": sum(r["events"] > 0 for r in rows),
        },
        "tiers": {
            "A": "Official filings and prices machine-readable: signals confirmed by exchange disclosures and judged on price.",
            "B": "Prices or statements from a data vendor; filings not machine-readable; confirmation by credible news.",
            "C": "No listing data; news, deals and country risk; confirmation by credible news only.",
        },
    }


def country(code: str, deals: Iterable[dict] = (), events: Iterable[dict] = ()) -> Optional[dict]:
    from src.data.africa_countries import get
    c = get(code)
    return country_row(c, deals, events) if c else None
