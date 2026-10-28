"""
Company profiles: identity, listing, market data, financial statements,
valuation multiples, transactions and filings for any African company.

Listed companies:
  * NGX: exchange profile (sector, board, auditor, registrar), trading summary,
    the filed statements list, and the latest audited annual statement parsed
    and arithmetic-checked (financials.ngx_financials).
  * Other exchanges Yahoo Finance carries (JSE, EGX, Casablanca, US, Euronext,
    London): profile, annual statements and multiples; SEC filers are
    cross-checked against their XBRL filings.
Private companies (and every company): transactions from the deals database
(funding history, acquisitions, investors, reported and implied valuations).

Each section names its source, so a reader can tell exchange filings from
data-vendor figures from news-derived deal records.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from src.data.africa_countries import Country, resolve
from src.engines import deals as deals_mod
from src.engines import financials as fin
from src.engines.investors import parties

log = logging.getLogger(__name__)


def _company_deals(name: str, deals: Iterable[dict]) -> list[dict]:
    key = deals_mod.normalise_name(name)
    if not key:
        return []
    out = []
    for d in deals:
        names = [d.get("target"), d.get("buyer"), d.get("seller"), *(d.get("investors") or [])]
        if any(n and (deals_mod.normalise_name(n) == key or key in deals_mod.normalise_name(n).split(" ") and len(key) > 3
                      or deals_mod.normalise_name(n).startswith(key + " ")) for n in names):
            out.append(d)
    return sorted(out, key=lambda d: d.get("announced") or "", reverse=True)


def private_market_summary(name: str, deals: Iterable[dict]) -> dict:
    """Funding and M&A history for a company from the deals database."""
    rows = _company_deals(name, deals)
    key = deals_mod.normalise_name(name)
    as_target = [d for d in rows if deals_mod.normalise_name(d.get("target")) == key]
    raised = [d for d in as_target if d["deal_type"] in ("equity_funding", "debt_financing") and d.get("amount_usd")]
    valuations = [{"announced": d.get("announced"), "usd": d.get("reported_valuation_usd") or d.get("implied_valuation_usd"),
                   "basis": "reported" if d.get("reported_valuation_usd") else "implied by stake and price",
                   "deal_id": d["id"]}
                  for d in as_target if d.get("reported_valuation_usd") or d.get("implied_valuation_usd")]
    investors = []
    for d in as_target:
        for n, role in parties(d):
            if role in ("investor", "lender", "acquirer") and n not in investors:
                investors.append(n)
    return {
        "deal_count": len(rows),
        "as_target": len(as_target),
        "total_raised_usd": round(sum(d["amount_usd"] for d in raised)) if raised else None,
        "equity_raised_usd": round(sum(d["amount_usd"] for d in raised if d["deal_type"] == "equity_funding")) or None,
        "debt_raised_usd": round(sum(d["amount_usd"] for d in raised if d["deal_type"] == "debt_financing")) or None,
        "last_round": next((d.get("round") for d in as_target if d.get("round")), None),
        "valuations": valuations,
        "investors_and_lenders": investors,
        "deals": [{k: d.get(k) for k in ("id", "deal_type", "stage", "round", "target", "buyer", "seller", "investors",
                                         "amount_usd", "stake_pct", "announced", "headline", "sources")}
                  for d in rows[:30]],
        "source": "Deals database (extracted from news and private-capital publications)",
    }


def _ngx_section(ticker: str, fetch=None) -> dict:
    data = fin.ngx_financials(ticker, fetch=fetch)
    prof = data.get("profile") or {}
    summ = data.get("summary") or {}
    annual = data.get("annual")
    out = {
        "identity": {
            "name": (prof.get("CompanyName") or "").title() or None,
            "sector": prof.get("Sector"), "sub_sector": prof.get("SubSector"),
            "business": prof.get("NatureofBusiness"), "board": [b.strip() for b in (prof.get("BoardOfDirectors") or "").split(",") if b.strip()],
            "auditor": prof.get("Auditor"), "company_secretary": prof.get("CompanySecretary"),
            "website": prof.get("Website"), "address": prof.get("CompanyAddress"),
            "listed": (prof.get("DateListed") or "")[:10] or None,
            "incorporated": (prof.get("DateOfIncorporation") or "")[:10] or None,
            "market_classification": prof.get("MarketClassification"),
            "source": "NGX company profile",
        },
        "market": {
            "price": summ.get("StockPriceCur"), "change_pct": summ.get("StockPricePercChange"),
            "volume": summ.get("Volume"), "high_52w": summ.get("HIGH52WK_PRICE"), "low_52w": summ.get("LOW52WK_PRICE"),
            "currency": "NGN", "as_at": _ngx_session_date(summ.get("as_at")), "served_at": summ.get("as_at"),
            "as_at_basis": "Latest NGX session on or before the time the summary was served; NGX does not state the "
                           "trade date, and exchange holidays are not accounted for",
            "source": "NGX trading summary",
        } if summ else None,
        "filings": data.get("statements", [])[:12],
    }
    if annual:
        mult = annual["multiplier"]
        currency = _statement_currency(annual.get("unit"))
        out["financials"] = {
            "source": f"Audited annual statement filed with NGX: {annual.get('document')}",
            "source_url": annual["source_url"], "filed": annual.get("filed"),
            "period": annual["period"], "currency": currency,
            "unit": _scaled_unit(currency, annual.get("unit")), "stated_unit": annual.get("unit"), "basis": annual["basis"],
            "items": {k: {"current": v["current"] * (1 if k == "eps" else mult),
                          "prior": v["prior"] * (1 if k == "eps" else mult), "line": v["line"]}
                      for k, v in annual["items"].items()},
            "checks": annual["checks"], "verified": annual.get("verified", False),
            "status": annual.get("status", {}),
        }
    return out


def _statement_currency(stated: Optional[str]) -> Optional[str]:
    """Currency of an NGX statement from its stated unit: naira by default, US dollars where the statement
    says so (e.g. Seplat's "US$ million"); None when the unit names neither."""
    text = (stated or "").strip()
    if re.search(r"US\s*\$|USD|\$", text, re.I):
        return "USD"
    if not text or text[:1] in ("N", "₦", "=") or re.search(r"naira|NGN", text, re.I):
        return "NGN"
    return None


def _ngx_session_date(stamp: Optional[str]) -> Optional[str]:
    """The NGX trading session a quote belongs to. The trading summary's "as_at" is the time it was served
    (e.g. "October 26, 2026, 11:50 pm", Lagos time), not when the price traded, so this takes the latest
    weekday session that had opened by then (sessions open at 10:00). Exchange holidays are not known."""
    m = re.match(r"\s*([A-Za-z]+ \d{1,2}, \d{4}),?\s*(\d{1,2}):(\d{2})\s*([ap]m)?", stamp or "", re.I)
    if not m:
        return None
    try:
        day = datetime.strptime(m.group(1), "%B %d, %Y").date()
    except ValueError:
        return None
    hour = int(m.group(2)) % 12 + (12 if (m.group(4) or "").lower() == "pm" else 0)
    if hour < 10:
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()


def _scaled_unit(currency: Optional[str], stated: Optional[str]) -> str:
    """Amounts are multiplied out to whole currency units, so the unit shown is the currency itself."""
    return f"{currency or 'currency'} (converted from {stated})" if stated else (currency or "currency units")


def _nse_section(name: str, fetch=None, ticker: Optional[str] = None) -> dict:
    data = fin.nse_financials(name, fetch=fetch)
    out: dict = {"filings": data["statements"]}
    prices = fin.nse_prices() if fetch is None else None      # tests inject documents only
    row = fin.nse_price_for(name, prices, ticker)
    if row:
        out["market"] = {"price": row["price"], "change_pct": row["change_pct"], "volume": row["volume"],
                         "currency": "KES", "as_at": prices["as_of"], "isin": row["isin"], "listing_name": row["name"],
                         "as_at_basis": "Last traded price on NSE Kenya's daily equity price list for this date",
                         "source": "NSE Kenya daily equity price list"}
    annual = data["annual"]
    if annual:
        mult = annual["multiplier"] if annual.get("unit") else 1e6       # Kenyan results are stated in KShs millions
        out["financials"] = {
            "source": f"Results filed with NSE Kenya: {annual.get('document')}", "source_url": annual["source_url"],
            "filed": annual.get("filed"), "period": annual["period"], "currency": "KES",
            "unit": _scaled_unit("KES", annual.get("unit") or "KShs million (assumed)"),
            "stated_unit": annual.get("unit") or "KShs million (assumed)",
            "basis": annual["basis"],
            "items": {k: {"current": v["current"] * (1 if k == "eps" else mult),
                          "prior": v["prior"] * (1 if k == "eps" else mult), "line": v["line"]}
                      for k, v in annual["items"].items()},
            "checks": annual["checks"], "verified": annual.get("verified", False), "status": annual.get("status", {}),
        }
    return out


_MINOR_UNITS = {"ZAc": ("ZAR", 100), "ZAC": ("ZAR", 100), "GBp": ("GBP", 100), "GBX": ("GBP", 100)}


def _yahoo_section(ticker: str) -> Optional[dict]:
    y = fin.yahoo_financials(ticker)
    if not y:
        return None
    info = y["info"]
    latest_period, latest = next(iter(y["annual"].items()), (None, {}))
    # Johannesburg and London quote prices in cents and pence (ZAc, GBp); statements are in rand and pounds,
    # so prices and the 52-week range are converted to the major unit to be comparable with them.
    currency, divisor = _MINOR_UNITS.get(info.get("currency"), (info.get("currency"), 1))
    major = lambda v: v / divisor if isinstance(v, (int, float)) else v       # noqa: E731
    traded = info.get("regularMarketTime")
    as_at = (datetime.fromtimestamp(traded, tz=timezone.utc).date().isoformat()
             if isinstance(traded, (int, float)) and traded > 0 else None)
    out = {
        "identity": {"name": info.get("longName"), "sector": info.get("sector"), "industry": info.get("industry"),
                     "business": info.get("longBusinessSummary"), "employees": info.get("fullTimeEmployees"),
                     "website": info.get("website"), "country": info.get("country"), "source": "Yahoo Finance"},
        "market": {"price": major(info.get("currentPrice") or info.get("regularMarketPrice")), "currency": currency,
                   "quoted_currency": info.get("currency"),
                   # Yahoo states market value and enterprise value in the major unit already.
                   "market_cap": info.get("marketCap"), "enterprise_value": info.get("enterpriseValue"),
                   "high_52w": major(info.get("fiftyTwoWeekHigh")), "low_52w": major(info.get("fiftyTwoWeekLow")),
                   "exchange": info.get("exchange"), "as_at": as_at,
                   "as_at_basis": "Date of the latest regular-session price Yahoo Finance reports (UTC)" if as_at else None,
                   "source": "Yahoo Finance"},
        "multiples": {k: info.get(k) for k in ("trailingPE", "forwardPE", "priceToBook", "enterpriseToRevenue",
                                               "enterpriseToEbitda", "dividendYield", "beta") if info.get(k) is not None},
        "financials": {"source": "Yahoo Finance annual statements", "currency": y.get("unit"),
                       "period": {"end": latest_period, "months": 12} if latest_period else None,
                       "annual": y["annual"],
                       "items": {k: {"current": v} for k, v in latest.items()},
                       "checks": y["checks"],
                       "verified": bool(y["checks"]) and all(c["passed"] for c in y["checks"])},
    }
    return out


# Exchanges whose listings the per-exchange sections above can read, by the suffix they use.
_SUFFIX = {"ngx": ".LG", "nse": ".NR", "jse": ".JO", "egx": ".CA"}
_EXCHANGE_OF_SUFFIX = {v: k for k, v in _SUFFIX.items()}
STALE_PRICE_DAYS = 7


def exchange_of(ticker: Optional[str]) -> Optional[str]:
    """The snapshot exchange key a Yahoo-style ticker belongs to ("DANGCEM.LG" -> "ngx")."""
    if not ticker or "." not in ticker:
        return None
    return _EXCHANGE_OF_SUFFIX.get("." + ticker.rsplit(".", 1)[1].upper())


def _apply_listing(profile: dict, listing: dict, today: Optional[datetime] = None) -> None:
    """Add the daily snapshot's quote: it replaces an older price (NGX's trading summary lags the price list by
    days), and supplies market cap, shares outstanding and year-to-date return where the exchange section has none."""
    profile["listing"] = {k: listing.get(k) for k in ("exchange", "exchange_name", "symbol", "name", "sector",
                                                      "secondary_of")}
    profile["exchange"] = profile.get("exchange") or listing.get("exchange_name")
    if not listing.get("price"):
        return                                          # listed, but the exchange publishes no daily price
    market = dict(profile.get("market") or {})
    newer = listing.get("date") and (not market.get("as_at") or listing["date"] > str(market["as_at"])[:10])
    if newer or not market.get("price"):
        market.update({"price": listing["price"], "currency": listing["currency"], "as_at": listing.get("date"),
                       "change_pct": None if listing.get("chg_1d") is None else round(listing["chg_1d"] * 100, 4),
                       "volume": listing.get("volume", market.get("volume")),
                       "as_at_basis": "Closing price on the exchange's daily price list for this date",
                       "source": f"{listing['exchange_name']} daily price list"})
    if not market.get("market_cap") and listing.get("mcap"):
        market["market_cap"] = listing["mcap"]
    market.update({"market_cap_usd": listing.get("mcap_usd"), "shares_outstanding": listing.get("shares"),
                   "ytd_pct": None if listing.get("ytd") is None else round(listing["ytd"] * 100, 2),
                   "ytd_usd_pct": None if listing.get("ytd_usd") is None else round(listing["ytd_usd"] * 100, 2)})
    if listing.get("ytd_suspect"):
        market["ytd_note"] = "Year-to-date figure is likely unadjusted for a split or bonus issue."
    profile["market"] = market


def _flag_stale_price(profile: dict, today: Optional[datetime] = None) -> None:
    """A price more than a week old cannot carry multiples or a valuation verdict; they are withheld, not shown."""
    market = profile.get("market") or {}
    as_at = str(market.get("as_at") or "")[:10]
    if not market.get("price") or not as_at:
        return
    try:
        age = ((today or datetime.now(timezone.utc)).date() - datetime.fromisoformat(as_at).date()).days
    except ValueError:
        return
    market["age_days"] = age
    market["stale"] = age > STALE_PRICE_DAYS
    if market["stale"] and profile.get("multiples"):
        profile["multiples_withheld"] = f"The latest price is {age} days old; multiples resume with a current price."
        profile["multiples"] = {}


def build(name: str, ticker: Optional[str] = None, country: Optional[str] = None,
          deals: Iterable[dict] = (), cik: Optional[int] = None, fetch=None, listing: Optional[dict] = None,
          today: Optional[datetime] = None) -> dict:
    """Full profile. Sections a source cannot fill are absent rather than guessed. `listing` is the company's
    quote in the daily market snapshot, when the name or ticker resolves to one."""
    deals = list(deals)
    if listing and not ticker and listing.get("exchange") in _SUFFIX:
        ticker = listing["symbol"] + _SUFFIX[listing["exchange"]]
    country = country or (listing or {}).get("country")
    c: Optional[Country] = resolve(country, ticker)
    # A bare exchange code with a Nigerian or Kenyan country ("SCOM", Kenya) is that exchange's listing.
    if ticker and "." not in ticker and c and c.iso2 in ("NG", "KE"):
        ticker = f"{ticker.upper()}{'.LG' if c.iso2 == 'NG' else '.NR'}"
    profile: dict = {"name": name, "ticker": ticker, "country": c.iso2 if c else None,
                     "country_name": c.name if c else None, "exchange": c.exchange if c and ticker else None,
                     "sources": []}
    listed = None
    if ticker and ticker.upper().endswith(".LG"):
        try:
            listed = _ngx_section(ticker, fetch)
            profile["sources"].append("NGX")
        except Exception:
            log.exception("NGX profile failed for %s", ticker)
    elif ticker and ticker.upper().endswith(".NR"):
        try:
            listed = _nse_section(name, fetch, ticker)
            profile["sources"].append("NSE Kenya")
        except Exception:
            log.exception("NSE profile failed for %s", name)
    elif ticker:
        listed = _yahoo_section(ticker)
        if listed:
            profile["sources"].append("Yahoo Finance")
            if cik:
                try:
                    y = fin.yahoo_financials(ticker)
                    profile["sec_cross_check"] = fin.cross_check(y, fin.sec_annual_facts(cik))
                    profile["sources"].append("SEC XBRL")
                except Exception:
                    log.exception("SEC cross-check failed for %s", ticker)
    if listed:
        profile.update(listed)
        if listed.get("identity", {}).get("name"):
            profile["name"] = listed["identity"]["name"]
    if listing:
        _apply_listing(profile, listing)
        profile["sources"].append("Daily exchange price list")
    _flag_stale_price(profile, today)
    profile["private_markets"] = private_market_summary(name, deals)
    if profile["private_markets"]["deal_count"]:
        profile["sources"].append("Deals database")
    if not profile.get("financials"):
        profile["financials_note"] = (
            ("No machine-readable statements were found for this listing. Most African exchanges outside NGX and NSE "
             "Kenya publish results without a data feed; filed documents are linked where available."
             if c else "No machine-readable statements were found for this listing.")
            if ticker or listing else
            "Private company: financial statements are not public; figures come from reported transactions.")
    return profile
