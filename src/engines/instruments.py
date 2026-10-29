"""Investments beyond single shares: exchange-traded funds, Treasury bills, listed property and policy rates.

Every figure comes from a named source and carries its date:
- JSE exchange-traded funds: Yahoo Finance delayed quotes (about 15 minutes), the same feed as JSE shares.
- Treasury bills: each central bank's (or regional market's) latest published auction results. Nigeria (CBN API),
  Kenya (CBK page), South Africa (SARB market-rates API, with two benchmark bond yields), Ghana (BoG table),
  Morocco (Bank Al-Maghrib results), Gambia (CBG results), Seychelles (CBS API), Tanzania (BoT API), Zambia (BoZ API)
  and the eight WAEMU states (UMOA-Titres auction pages). Every quoting convention was checked against the source's
  own figures: where a rate type or day-count basis cannot be confirmed it is shown as published and not converted.
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
SARB_RATES = "https://custom.resbank.co.za/SarbWebApi/WebIndicators/CurrentMarketRates"
SARB_PAGE = "https://www.resbank.co.za/en/home/what-we-do/statistics/key-statistics/current-market-rates"
BOG_TBILLS = "https://www.bog.gov.gh/treasury-and-the-markets/treasury-bill-rates/"
BAM_TBILLS = ("https://www.bkam.ma/Marches/Principaux-indicateurs/Marche-obligataire/Marche-des-bons-de-tresor/"
              "Marche-des-adjudications-des-bons-du-tresor/Resultats-des-emissions-de-bons-du-tresor")
CBG_TBILLS = "https://www.cbg.gm/auction-results/91-day-tbills"
CBS_TBILLS = "https://www.cbs.sc/Controller/MarketinfoController.jsp?type=tbill"
CBS_PAGE = "https://www.cbs.sc/marketinfo/TBILL.html"
BOT_TBILLS = "https://www.bot.go.tz/TBills?lang=en"
BOT_DETAIL = "https://www.bot.go.tz/Tbills/getTbillsDetails"
BOZ_TBILLS = "https://www.boz.zm/jsonapi/node/tbills_auction_results?include=field_tbills_auction_results&sort=-field_tbills_auction_date&page[limit]=1"
BOZ_PAGE = "https://www.boz.zm/markets-securities/treasury-bills"
UMOA_LIST = "https://www.umoatitres.org/fr/emissions/"
UMOA_COUNTRIES = {"Bénin": "BJ", "Burkina": "BF", "Burkina Faso": "BF", "Côte d’Ivoire": "CI", "Côte d'Ivoire": "CI",
                  "Guinée-Bissau": "GW", "Guinée Bissau": "GW", "Mali": "ML", "Niger": "NE", "Sénégal": "SN", "Togo": "TG"}
COUNTRY_NAMES = {"NG": "Nigeria", "KE": "Kenya", "ZA": "South Africa", "GH": "Ghana", "MA": "Morocco", "GM": "Gambia",
                 "SC": "Seychelles", "TZ": "Tanzania", "ZM": "Zambia", "BJ": "Benin", "BF": "Burkina Faso",
                 "CI": "Côte d'Ivoire", "GW": "Guinea-Bissau", "ML": "Mali", "NE": "Niger", "SN": "Senegal", "TG": "Togo"}
_UA = {"User-Agent": "Mozilla/5.0"}
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


def _cells(page: str) -> list[list[str]]:
    """Every table row of an HTML page as stripped cell texts (empty rows dropped)."""
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page or "", re.S):
        cells = [re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", "", c))).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if any(cells):
            out.append(cells)
    return out


def _fr_num(s: str) -> Optional[float]:
    """'2,26 %' or '1 830,00' (French formatting) as a float."""
    t = re.sub(r"[%\s ]", "", s or "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _block(country: str, currency: str, issuer: str, source: str, url: str, rows: list[dict], **extra) -> dict:
    return {"country": country, "country_name": COUNTRY_NAMES.get(country, country), "currency": currency,
            "issuer": issuer, "source": source, "source_url": url, "rows": rows, **extra}


def parse_sarb_rates(items: object) -> dict:
    """South Africa: Treasury bill tender rates (91 to 364 days) and two benchmark bond yields from the SARB. The
    feed does not say whether a tender rate is a discount rate or a yield, so it is shown as published."""
    rows, bonds = [], []
    for it in items if isinstance(items, list) else []:
        name, value, day = str(it.get("Name") or ""), it.get("Value"), str(it.get("Date") or "")[:10] or None
        if not isinstance(value, (int, float)):
            continue
        m = re.match(r"Treasury bills - (\d+) day", name)
        if m:
            rows.append({"tenor_days": int(m.group(1)), "rate_type": "tender", "rate": float(value), "basis": None,
                         "auction_date": day})
        elif "closing yields" in name:
            bonds.append({"name": name.replace(" (closing yields)", ""), "yield": float(value), "date": day})
    return _block("ZA", "ZAR", "Republic of South Africa", "South African Reserve Bank, current market rates",
                  SARB_PAGE, sorted(rows, key=lambda r: r["tenor_days"]), bonds=bonds)


def parse_bog_tbills(page: str) -> dict:
    """Ghana: the latest weekly tender's discount and interest rate per tenor. Both are published; they reconcile
    on a 364-day basis."""
    latest: dict[int, dict] = {}
    for c in _cells(page):
        if len(c) < 5:
            continue
        m = re.match(r"(\d+)\s*DAY", c[2], re.I)
        try:
            when = datetime.strptime(c[0], "%d %b %Y").date().isoformat()
        except ValueError:
            continue
        disc, rate = _num(c[3]), _num(c[4])
        if not m or not rate:
            continue
        days = int(m.group(1))
        if days not in latest or latest[days]["auction_date"] < when:
            latest[days] = {"tenor_days": days, "rate_type": "yield", "rate": rate, "discount_rate": disc,
                            "basis": 364, "auction_date": when, "tender": c[1]}
    return _block("GH", "GHS", "Government of Ghana", "Bank of Ghana, Treasury bill rates", BOG_TBILLS,
                  [latest[k] for k in sorted(latest)])


def parse_bam_tbills(page: str) -> dict:
    """Morocco: the latest Treasury auction's weighted average rate for bills (weeks); bonds quoted in price are
    skipped. The settlement date is the date shown."""
    m = re.search(r"name=['\"]date['\"][^>]*value=\"(\d\d)/(\d\d)/(\d{4})\"", page or "")
    settle = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None
    rows = []
    for c in _cells(page):
        w = re.match(r"(\d+)\s*semaines", c[0]) if c else None
        if not w or len(c) < 8:
            continue
        rate = _fr_num(c[7])
        if rate is None or "%" not in c[7]:
            continue
        rows.append({"tenor_days": int(w.group(1)) * 7, "tenor_label": f"{w.group(1)} weeks", "rate_type": "yield",
                     "rate": rate, "basis": 360, "auction_date": None, "settlement_date": settle,
                     "allotted_mn": _fr_num(c[5])})
    return _block("MA", "MAD", "Kingdom of Morocco", "Bank Al-Maghrib, Treasury auction results", BAM_TBILLS, rows)


def parse_cbg_tbills(page: str) -> dict:
    """Gambia: the latest auction's weighted average price and yield per tenor (Treasury bills; Sukuk-al-Salaam
    bills are left out). The yield reconciles with the price on a 365-day basis."""
    m = re.search(r"issued on \w+ (\w+ \d{1,2})(?:st|nd|rd|th)?, (\d{4})", page or "")
    when = None
    if m:
        try:
            when = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%B %d %Y").date().isoformat()
        except ValueError:
            pass
    rows = {}
    for c in _cells(page):
        d = re.match(r"(\d+)-Day T/Bills", c[0]) if c else None
        if not d or len(c) < 9:
            continue
        days = int(d.group(1))
        if days in rows:
            continue
        rows[days] = {"tenor_days": days, "rate_type": "yield", "rate": _num(c[6]), "price": _num(c[5]),
                      "basis": 365, "auction_date": when, "offered_mn": (_num(c[1]) or 0) / 1e6 or None,
                      "allotted_mn": (_num(c[3]) or 0) / 1e6 or None}
    return _block("GM", "GMD", "Government of The Gambia", "Central Bank of The Gambia, auction results",
                  CBG_TBILLS, [rows[k] for k in sorted(rows) if rows[k]["rate"]])


def parse_cbs_tbills(payload: object) -> dict:
    """Seychelles: the average interest rate per tenor as published (the basis is not stated)."""
    item = ((payload or {}).get("tbill") or [{}])[0] if isinstance(payload, dict) else {}
    try:
        when = datetime.strptime(str(item.get("date") or ""), "%d %B, %Y").date().isoformat()
    except ValueError:
        when = None
    rows = [{"tenor_days": days, "rate_type": "average", "rate": _num(item.get(key)), "basis": None, "auction_date": when}
            for days, key in ((91, "rate1"), (182, "rate2"), (365, "rate3")) if _num(item.get(key))]
    return _block("SC", "SCR", "Government of Seychelles", "Central Bank of Seychelles, Treasury bills", CBS_PAGE, rows)


def parse_bot_detail(payload: object, auction_date: Optional[str]) -> dict:
    """Tanzania: weighted average yield and price per tenor for one auction. Yields reconcile with prices on a
    365-day basis."""
    table = (payload or {}).get("TbillData") if isinstance(payload, dict) else None
    rows = []
    if table and len(table) > 1:
        head = table[0]
        by = {r[0]: r for r in table[1:] if r}
        yields, prices = by.get("Weighted Average Yield") or [], by.get("Weighted Average Price for Successful Bids") or []
        offered = by.get("Amount Offered TZS(000,000)") or []      # the allotted amount's unit label is ambiguous
        for i, label in enumerate(head[1:], start=1):
            m = re.match(r"(\d+)\s*Days", str(label))
            rate = _num(yields[i]) if i < len(yields) else None
            if m and rate:
                rows.append({"tenor_days": int(m.group(1)), "rate_type": "yield", "rate": rate,
                             "price": _num(prices[i]) if i < len(prices) else None, "basis": 365,
                             "auction_date": auction_date,
                             "offered_mn": _num(offered[i]) if i < len(offered) else None})
    return _block("TZ", "TZS", "United Republic of Tanzania", "Bank of Tanzania, Treasury bill auction results",
                  BOT_TBILLS, rows)


def parse_bot_list(page: str) -> Optional[tuple[str, str]]:
    """The newest auction number and date on the Bank of Tanzania's results page."""
    m = re.search(r"Treasury Bills Auction No\.\s*(\d+)\s+Held on (\d{2}-[A-Z]{3}-\d{4})", page or "")
    if not m:
        return None
    return m.group(1), datetime.strptime(m.group(2).title(), "%d-%b-%Y").date().isoformat()


def parse_boz_tbills(payload: object) -> dict:
    """Zambia: yield and discount rate per tenor at the latest auction. They reconcile on a 365-day basis."""
    data = (payload or {}).get("data") or [] if isinstance(payload, dict) else []
    when = ((data[0] or {}).get("attributes") or {}).get("field_tbills_auction_date") if data else None
    rows = []
    for inc in (payload or {}).get("included") or [] if isinstance(payload, dict) else []:
        a = inc.get("attributes") or {}
        days = next((int(m.group(1)) for k, v in a.items() if (m := re.match(r"(\d+)_days", str(v)))), None)
        yld = next((_num(v) for k, v in a.items() if "yield" in k), None)
        disc = next((_num(v) for k, v in a.items() if "discount" in k), None)
        if days and yld:
            rows.append({"tenor_days": days, "rate_type": "yield", "rate": yld, "discount_rate": disc, "basis": 365,
                         "auction_date": when})
    return _block("ZM", "ZMW", "Government of Zambia", "Bank of Zambia, Treasury bill auction results", BOZ_PAGE,
                  sorted(rows, key=lambda r: r["tenor_days"]))


_UMOA_ROW = re.compile(r"<tr class='emission-[^']*'>\s*<td[^>]*>.*?/>\s*([^<]+?)\s*<br>.*?</td>\s*<td>(BAT|OAT)</td>"
                       r".*?<td>(\d\d/\d\d/\d{4})</td>\s*<td>\d\d/\d\d/\d{4}</td>\s*<td>(\d\d/\d\d/\d{4})</td>\s*"
                       r"<td>(\d+)</td>.*?href='([^']+)'", re.S)


def parse_umoa_list(page: str) -> dict[str, list[dict]]:
    """{country code: recent bill auctions, newest first} from UMOA-Titres' list of completed issues: date, page,
    and the auction's instruments in order (bills and bonds, as their results are listed on the auction page)."""
    auctions: dict[str, dict] = {}
    for name, kind, op, maturity, months, link in _UMOA_ROW.findall(page or ""):
        code = UMOA_COUNTRIES.get(name.strip())
        if not code:
            continue
        when = datetime.strptime(op, "%d/%m/%Y").date().isoformat()
        a = auctions.setdefault(link, {"country": code, "date": when, "url": link, "instruments": []})
        a["instruments"].append({"kind": kind, "months": int(months),
                                 "maturity": datetime.strptime(maturity, "%d/%m/%Y").date().isoformat()})
    by_country: dict[str, list[dict]] = {}
    for a in auctions.values():
        if any(i["kind"] == "BAT" for i in a["instruments"]):
            by_country.setdefault(a["country"], []).append(a)
    return {c: sorted(v, key=lambda a: a["date"], reverse=True)[:6] for c, v in by_country.items()}


_UMOA_BLOCK = re.compile(r"\b(BAT|OAT) \| Montant sollicité:")


def _umoa_results(text: str) -> list[tuple[str, Optional[float], Optional[float]]]:
    """(kind, weighted average rate, weighted average yield) per instrument, in page order; '--' reads as None."""
    part = text[text.find("Résultats"):] if "Résultats" in text else text
    marks = list(_UMOA_BLOCK.finditer(part))
    out = []
    for n, m in enumerate(marks):
        block = part[m.start():marks[n + 1].start() if n + 1 < len(marks) else len(part)]
        rate = re.search(r"Taux moyen pondéré: \| ([\d,]+) %", block)
        yld = re.search(r"Rendement moyen pondéré \| ([\d,]+) %", block)
        out.append((m.group(1), _fr_num(rate.group(1)) if rate else None, _fr_num(yld.group(1)) if yld else None))
    return out


def parse_umoa_auction(page: str, auction: dict) -> dict:
    """One WAEMU auction page: the bill's weighted average discount rate and yield. The two reconcile on a
    360-day basis."""
    text = re.sub(r"(\| )+", "| ", re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " | ", page or ""))))
    results = _umoa_results(text)
    rows = []
    for inst, (kind, disc, yld) in zip(auction["instruments"], results):
        if inst["kind"] != "BAT" or kind != "BAT":
            continue
        rows.append({"tenor_days": round(inst["months"] * 30.4), "tenor_label": f"{inst['months']} months",
                     "rate_type": "discount", "rate": disc, "true_yield": yld, "basis": 360,
                     "auction_date": auction["date"], "maturity_date": inst["maturity"]})
    code = auction["country"]
    return _block(code, "XOF", f"Government of {COUNTRY_NAMES.get(code, code)}",
                  "UMOA-Titres, regional auction results", auction["url"], [r for r in rows if r["rate"]])


def _safe(label: str, fn):
    try:
        return fn()
    except Exception as exc:                                  # one source failing never stops the others
        log.warning("Treasury bill source %s failed: %s", label, exc)
        return None


def build_tbills(client: httpx.Client, now: Optional[datetime] = None) -> dict[str, dict]:
    """{country code (lower case): block} for every source that answered with at least one tenor."""
    from src.engines import markets
    now = now or datetime.now(timezone.utc)
    get = lambda url, **kw: markets._get(client, url, headers=_UA, **kw)          # noqa: E731
    blocks: list[Optional[dict]] = [
        _safe("cbn", lambda: parse_cbn_ntb(get(CBN_NTB).json())),
        _safe("cbk", lambda: parse_cbk_tbills(get(CBK_TBILLS).text)),
        _safe("sarb", lambda: parse_sarb_rates(get(SARB_RATES).json())),
        _safe("bog", lambda: parse_bog_tbills(get(BOG_TBILLS).text)),
        _safe("bam", lambda: parse_bam_tbills(get(BAM_TBILLS).text)),
        _safe("cbg", lambda: parse_cbg_tbills(get(CBG_TBILLS).text)),
        _safe("cbs", lambda: parse_cbs_tbills(get(CBS_TBILLS).json())),
        _safe("boz", lambda: parse_boz_tbills(get(BOZ_TBILLS).json())),
    ]

    def tanzania() -> Optional[dict]:
        newest = parse_bot_list(get(BOT_TBILLS).text)
        if not newest:
            return None
        r = client.post(BOT_DETAIL, data={"au_no": newest[0]}, headers=_UA)
        return parse_bot_detail(r.json(), newest[1]) if r.status_code == 200 else None
    blocks.append(_safe("bot", tanzania))

    listing = _safe("umoa", lambda: parse_umoa_list(get(UMOA_LIST).text)) or {}
    for code, recent in listing.items():
        for auction in recent:                       # an auction that allotted no bills has no rate: try the one before
            block = _safe(f"umoa-{code}", lambda a=auction: parse_umoa_auction(get(a["url"]).text, a))
            if block and block["rows"]:
                blocks.append(block)
                break

    out: dict[str, dict] = {}
    for b in blocks:
        if b and b.get("rows"):
            out[b["country"].lower()] = {"country_name": COUNTRY_NAMES.get(b["country"], b["country"]), **b,
                                         "captured_at": now.isoformat()}
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
