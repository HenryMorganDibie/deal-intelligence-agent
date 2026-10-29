"""Investments beyond single shares: exchange-traded funds, Treasury bills, listed property and policy rates.

Every figure comes from a named source and carries its date:
- JSE exchange-traded funds: Yahoo Finance delayed quotes (about 15 minutes), the same feed as JSE shares.
- Nigerian Treasury bills: the Central Bank of Nigeria's primary-auction results (stop rate per tenor).
- Kenyan Treasury bills: the Central Bank of Kenya's Treasury bill page (average rate at the last auction).
- Listed property (REITs and property funds): the daily equity snapshot.
- Policy rates: the country signals snapshot (Africa API, source kept per observation).

Funds that are not listed, fixed deposits and bond inventories are not covered: no free source publishes them
with dates and a consistent method.
"""
from __future__ import annotations

import html as html_mod
import logging
import re
from datetime import date, datetime, timezone
from typing import Optional

import httpx

from src.utils.paths import DATA_DIR
from src.utils.storage import load_json, save_json

log = logging.getLogger(__name__)

CBN_NTB = "https://www.cbn.gov.ng/api/GetAllSecuritiesNTB"
CBN_NTB_PAGE = "https://www.cbn.gov.ng/rates/GovtSecuritiesDrillDown.html?market=NTB"
CBK_TBILLS = "https://www.centralbank.go.ke/bills-bonds/treasury-bills/"
LOCAL_PATH = DATA_DIR / "market_instruments.json"   # the local copy; the hosted API keeps these in Supabase
ETF_DELAY = "about 15 minutes (Yahoo Finance)"

# JSE exchange-traded products by what they hold. Tickers were checked against the live feed; one that stops
# quoting simply drops out of the list.
JSE_ETFS: dict[str, str] = {
    **dict.fromkeys(["STX40", "ETFT40", "SYGT40", "CTOP50", "STXCAP", "ETFSWX", "STXRAF", "STXDIV", "STXQUA",
                     "STXMMT", "STXFIN", "STXIND", "STXRES"], "South African equity"),
    **dict.fromkeys(["STX500", "CSP500", "ETF500", "SYGUS", "STXNDQ", "STXWDM", "ETFWLD", "SYGWD", "STXESG",
                     "GLODIV", "SYG4IR", "SYGEU", "SYGUK", "SYGJP"], "Global equity"),
    **dict.fromkeys(["STXEMG", "SYGEMF", "STXCHN", "SYGCN"], "Emerging-market equity"),
    **dict.fromkeys(["STXGOV", "ETFBND", "STXILB", "STXINC"], "South African bonds and income"),
    **dict.fromkeys(["ETFGGB", "ETFUSD"], "Global bonds"),
    **dict.fromkeys(["STXPRO", "ETFSAP", "CSPROP"], "South African property"),
    **dict.fromkeys(["GLPROP", "SYGP", "ETFGRE"], "Global property"),
    **dict.fromkeys(["GLD", "ETFGLD", "NGPLT", "ETFPLT", "NGPLD", "ETFPLD", "ETFRHO"], "Precious metals"),
    **dict.fromkeys(["STXGLB"], "Multi-asset"),
}

# A year-to-date return beyond this is a unit change in the source (cents to rand), not a market move.
_YTD_LIMIT = 3.0


def build_etfs(client: httpx.Client, now: Optional[datetime] = None) -> dict:
    """Latest delayed quote for each JSE exchange-traded product: price, 1-day change, year-to-date return."""
    from src.engines import markets
    now = now or datetime.now(timezone.utc)
    quotes = markets._spark_all_range(client, [f"{t}.JO" for t in JSE_ETFS], "ytd")
    rows = []
    for ticker, exposure in JSE_ETFS.items():
        q = quotes.get(f"{ticker}.JO")
        if not q or not q.get("price"):
            continue
        ytd = q.get("ytd")
        rows.append({"symbol": ticker, "name": q.get("name") or ticker, "exposure": exposure, "currency": "ZAR",
                     "price": q["price"], "chg_1d": q.get("chg_1d"), "volume": q.get("volume"),
                     "ytd": ytd if ytd is not None and abs(ytd) <= _YTD_LIMIT else None,
                     "ytd_suspect": ytd is not None and abs(ytd) > _YTD_LIMIT,
                     "date": q.get("date"), "quote_time": q.get("time")})
    return {"captured_at": now.isoformat(), "exchange": "jse", "delay": ETF_DELAY, "rows": rows}


def _tenor_days(tenor: str) -> Optional[int]:
    m = re.match(r"\s*(\d+)\s*DAY", tenor or "", re.I)
    return int(m.group(1)) if m else None


def _cbn_date(s: str) -> Optional[date]:
    try:
        return datetime.strptime((s or "").strip(), "%B-%d-%Y").date()
    except ValueError:
        return None


def _num(s: object) -> Optional[float]:
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return None


def true_yield(discount_pct: float, days: int, basis: int = 365) -> Optional[float]:
    """Annual investment yield from a discount rate: d / (1 - d * t / basis). The CBN's published true yields match
    this on a 365-day basis."""
    d = discount_pct / 100
    denom = 1 - d * days / basis
    return round(d / denom * 100, 4) if denom > 0 else None


def parse_cbn_ntb(rows: object) -> dict:
    """The latest primary auction's stop rate for each Nigerian Treasury bill tenor, with its true yield."""
    latest: dict[int, dict] = {}
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or (r.get("rateDescription") or "").strip().lower() != "issue":
            continue
        days, when, rate = _tenor_days(r.get("tenor") or ""), _cbn_date(r.get("auctionDate") or ""), _num(r.get("rate"))
        if not days or not when or not rate or rate <= 0:
            continue
        key = 364 if days in (364, 365) else days            # the one-year bill is labelled either way
        if key in latest and latest[key]["auction_date"] >= when.isoformat():
            continue
        maturity = _cbn_date(r.get("maturityDate") or "")
        latest[key] = {
            "tenor_days": days, "auction_date": when.isoformat(),
            "maturity_date": maturity.isoformat() if maturity else None,
            "rate_type": "discount", "rate": rate, "true_yield": true_yield(rate, days, 365), "basis": 365,
            "offered_mn": _num(r.get("amtOffered")), "subscribed_mn": _num(r.get("totalSubscription")),
            "allotted_mn": _num(r.get("totalSuccessful")),
            "bid_range": (r.get("rangeBid") or "").strip() or None,
        }
    rows_out = [latest[k] for k in sorted(latest)]
    newest = max((r["auction_date"] for r in rows_out), default=None)
    # Only the most recent auction's tenors: an older auction's rate for a tenor not offered since is history.
    rows_out = [r for r in rows_out if newest and (date.fromisoformat(newest) - date.fromisoformat(r["auction_date"])).days <= 35]
    return {"country": "NG", "currency": "NGN", "issuer": "Federal Government of Nigeria",
            "source": "Central Bank of Nigeria, primary auction results", "source_url": CBN_NTB_PAGE, "rows": rows_out}


_CBK_BLOCK = re.compile(r"(91|182|364)-DAY.{0,600}?Auction Date:\s*([0-9]{1,2})(?:st|nd|rd|th)?\s+([A-Z][a-z]+)\s+(20\d\d)"
                        r".{0,600}?Previous Average Interest Rate:\s*([0-9]+(?:\.[0-9]+)?)", re.S)


def parse_cbk_tbills(page: str) -> dict:
    """Kenyan Treasury bills: the average interest rate at the last auction for each tenor. The page announces the
    next auction and quotes the previous result, so the rate is dated as 'before' that auction."""
    text = re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", page or "")))
    rows: dict[int, dict] = {}
    for tenor, day, month, year, rate in _CBK_BLOCK.findall(text):
        days = int(tenor)
        try:
            nxt = datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date()
        except ValueError:
            continue
        value = float(rate)
        if days in rows or not 0 < value < 100:
            continue
        rows[days] = {"tenor_days": days, "rate_type": "yield", "rate": value, "basis": 364,
                      "next_auction_date": nxt.isoformat(), "auction_date": None}
    return {"country": "KE", "currency": "KES", "issuer": "Government of Kenya",
            "source": "Central Bank of Kenya, Treasury bill auctions", "source_url": CBK_TBILLS,
            "rows": [rows[k] for k in sorted(rows)]}


def build_tbills(client: httpx.Client, now: Optional[datetime] = None) -> dict[str, dict]:
    """{country: block} for each central bank that answered with at least one tenor."""
    from src.engines import markets
    now = now or datetime.now(timezone.utc)
    out: dict[str, dict] = {}
    r = markets._get(client, CBN_NTB, headers={"User-Agent": "Mozilla/5.0"})
    try:
        ng = parse_cbn_ntb(r.json()) if r is not None else {"rows": []}
    except ValueError:
        ng = {"rows": []}
    if ng["rows"]:
        out["ng"] = {**ng, "captured_at": now.isoformat()}
    r = markets._get(client, CBK_TBILLS, headers={"User-Agent": "Mozilla/5.0"})
    ke = parse_cbk_tbills(r.text) if r is not None else {"rows": []}
    if ke["rows"]:
        out["ke"] = {**ke, "captured_at": now.isoformat()}
    return out


def instrument_rows(etfs: Optional[dict], tbills: dict[str, dict], captured_at: Optional[datetime] = None) -> list[dict]:
    """Rows for upsert_market_snapshots (kind 'instruments'): one per scope."""
    captured_at = captured_at or datetime.now(timezone.utc)
    day, at = captured_at.date().isoformat(), captured_at.isoformat()
    rows = [{"snapshot_date": day, "kind": "instruments", "scope": "etf_jse", "captured_at": at, "payload": etfs}] \
        if etfs and etfs.get("rows") else []
    rows += [{"snapshot_date": day, "kind": "instruments", "scope": f"tbill_{c}", "captured_at": at, "payload": b}
             for c, b in tbills.items()]
    return rows


def listed_property(snapshot: dict) -> list[dict]:
    """REITs and property funds from the daily equity snapshot, largest first."""
    pattern = re.compile(r"\bREIT\b|Real Estate Investment Trust|Property Fund|Properties|Property\b", re.I)
    out = []
    for ex, quotes in (snapshot.get("quotes") or {}).items():
        for q in quotes:
            if q.get("secondary_of") or not q.get("price"):
                continue
            if (q.get("sector") or "").lower().startswith("real estate") or pattern.search(q.get("name") or ""):
                out.append({k: q.get(k) for k in ("exchange", "symbol", "name", "price", "currency", "chg_1d",
                                                  "ytd", "mcap_usd", "dividend_yield", "date", "delayed", "quote_time")}
                           | {"exchange": ex})
    return sorted(out, key=lambda q: -(q.get("mcap_usd") or 0))


def policy_rates(signals: dict) -> list[dict]:
    """Each country's latest policy rate from the country signals snapshot, with its period and source."""
    out = []
    for code, block in ((signals or {}).get("countries") or {}).items():
        for o in (block or {}).get("observations") or []:
            if o.get("metric_key") == "policy_rate_pct" and isinstance(o.get("value"), (int, float)):
                out.append({"country": code, "country_name": block.get("country_name") or code,
                            "rate": o["value"], "as_of": o.get("as_of_period"), "freshness": o.get("freshness"),
                            "source": o.get("source")})
    return sorted(out, key=lambda r: r["country_name"])


def save_local(rows: list[dict]) -> None:
    """Keep the latest block per scope beside the local market snapshot (the hosted API stores them in Supabase)."""
    stored = load_json(LOCAL_PATH, dict) or {}
    stored.update({r["scope"]: r["payload"] for r in rows})
    save_json(LOCAL_PATH, stored)


def load_local() -> dict[str, dict]:
    return load_json(LOCAL_PATH, dict) or {}
