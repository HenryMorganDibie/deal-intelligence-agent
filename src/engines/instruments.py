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
COUNTRY_NAMES = {"UG": "Uganda", "CM": "Cameroon", "CG": "Republic of the Congo", "GA": "Gabon", "TD": "Chad", "CF": "Central African Republic", "GQ": "Equatorial Guinea", "BW": "Botswana", "MW": "Malawi", "NA": "Namibia", "NG": "Nigeria", "KE": "Kenya", "ZA": "South Africa", "GH": "Ghana", "MA": "Morocco", "GM": "Gambia",
                 "SC": "Seychelles", "TZ": "Tanzania", "ZM": "Zambia", "BJ": "Benin", "BF": "Burkina Faso",
                 "CI": "Côte d'Ivoire", "GW": "Guinea-Bissau", "ML": "Mali", "NE": "Niger", "SN": "Senegal", "TG": "Togo"}
_UA = {"User-Agent": "Mozilla/5.0"}
CBK_CBR = "https://www.centralbank.go.ke/rates/central-bank-rate/"
CBN_MPR = "https://www.cbn.gov.ng/api/GetMPR_TOP"
BOG_HOME = "https://www.bog.gov.gh/"
BOB_HOME = "https://www.bankofbotswana.bw/"
RBM_HOME = "https://www.rbm.mw/"
BON_HOME = "https://www.bon.com.na/"
BOU_DOCS = ("https://bou.or.ug/api/financial-market-auction-information?populate=auctionInformation.items.file.file.file"
            "&populate=auctionInformation.items.file.fileWithMonth.file.file")
BOU_PAGE = "https://www.bou.or.ug/bouwebsite/financial-market-auction-information"
RBM_TBILLS = "https://www.rbm.mw/FinancialMarkets/TreasuryBills/"
BOB_AUCTIONS = "https://www.bankofbotswana.bw/government-securities-auctions"
BEAC_STATS = "https://www.beac.int/economie-stats/statistiques-titres-publics/"
_FR_MONTHS = {"janv": 1, "jan": 1, "fev": 2, "fév": 2, "fevr": 2, "févr": 2, "mars": 3, "avr": 4, "avril": 4, "mai": 5,
              "juin": 6, "juil": 7, "juillet": 7, "aout": 8, "août": 8, "sept": 9, "oct": 10, "nov": 11, "dec": 12, "déc": 12}
_BEAC_COUNTRIES = {"Camerounais": "CM", "Congolais": "CG", "Gabonais": "GA", "Tchadiens": "TD", "Centrafricains": "CF",
                   "Equato-guineens": "GQ", "Equato-guinéens": "GQ"}
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

NGX_ETFS_FEED = "https://doclib.ngxgroup.com/REST/api/statistics/etfs/?market=&sector=&orderby=&pageSize=300&pageNo=0"
NGX_ETFS_PAGE = "https://ngxgroup.com/exchange/data/etfs-price-list/"
# Lagos exchange-traded products: the feed carries symbols only, so names and holdings are kept here.
NGX_ETFS: dict[str, tuple[str, str]] = {
    "GREENWETF": ("Greenwich Alpha ETF", "Nigerian equity"),
    "LOTUSHAL15": ("Lotus Halal Equity ETF", "Nigerian equity"),
    "MERGROWTH": ("Meristem Growth ETF", "Nigerian equity"),
    "MERVALUE": ("Meristem Value ETF", "Nigerian equity"),
    "SIAMLETF40": ("SIAML Pension ETF 40", "Nigerian equity"),
    "STANBICETF30": ("Stanbic IBTC ETF 30", "Nigerian equity"),
    "VETBANK": ("Vetiva Banking ETF", "Nigerian equity"),
    "VETGOODS": ("Vetiva Consumer Goods ETF", "Nigerian equity"),
    "VETGRIF30": ("Vetiva Griffin 30 ETF", "Nigerian equity"),
    "VETINDETF": ("Vetiva Industrial ETF", "Nigerian equity"),
    "VSPBONDETF": ("Vetiva S&P Nigerian Sovereign Bond ETF", "Nigerian bonds"),
    "NEWGOLD": ("NewGold ETF", "Precious metals"),
}
# Nairobi exchange-traded products, found in the daily Nairobi price list by sector.
NSE_ETF_EXPOSURE = {"GLD": "Precious metals", "SMWF": "Global equity"}

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
    for row in rows:
        row["exchange"] = "jse"
    ngx = _safe("ngx-etfs", lambda: parse_ngx_etfs(markets._get(client, NGX_ETFS_FEED, headers=_UA).json(),
                                                     now.date().isoformat())) or []
    return {"captured_at": now.isoformat(), "exchange": "jse", "delay": ETF_DELAY, "rows": rows + ngx}


def parse_ngx_etfs(items: object, captured: str) -> list[dict]:
    """Lagos exchange-traded products from the NGX's ETF price list. The feed gives no trade date, so each price is
    dated by the day it was captured and marked as such."""
    out = []
    for it in items if isinstance(items, list) else []:
        sym = str(it.get("Symbol") or "").strip().upper()
        price, prev = _num(it.get("ClosePrice")), _num(it.get("PrevClosingPrice"))
        if not sym or not price:
            continue
        name, exposure = NGX_ETFS.get(sym, (sym, "Nigerian equity" if "BOND" not in sym else "Nigerian bonds"))
        out.append({"symbol": sym, "name": name, "exposure": exposure, "currency": "NGN", "exchange": "ngx",
                    "price": price, "chg_1d": round(price / prev - 1, 6) if prev else None,
                    "volume": _num(it.get("Volume")), "ytd": None, "ytd_suspect": False,
                    "date": captured, "date_kind": "captured", "quote_time": None})
    return out


def nse_etfs(snapshot: dict) -> list[dict]:
    """Nairobi exchange-traded products from the daily equity snapshot (the Nairobi list files them by sector)."""
    out = []
    for q in (snapshot.get("quotes") or {}).get("nse") or []:
        if (q.get("sector") or "") == "Exchange Traded Funds" and q.get("price"):
            out.append({"symbol": q["symbol"], "name": q.get("name") or q["symbol"], "currency": "KES",
                        "exposure": NSE_ETF_EXPOSURE.get(q["symbol"], "Other"), "exchange": "nse",
                        "price": q["price"], "chg_1d": q.get("chg_1d"), "volume": q.get("volume"),
                        "ytd": q.get("ytd"), "ytd_suspect": bool(q.get("ytd_suspect")),
                        "date": q.get("date"), "quote_time": q.get("quote_time")})
    return out


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
        # The CBK's day-count basis is not confirmed against its own figures, so the yield is not sent to the calculator.
        rows[days] = {"tenor_days": days, "rate_type": "yield", "rate": value, "basis": None,
                      "next_auction_date": nxt.isoformat(), "auction_date": None}
    return {"country": "KE", "currency": "KES", "issuer": "Government of Kenya",
            "source": "Central Bank of Kenya, Treasury bill auctions", "source_url": CBK_TBILLS,
            "rows": [rows[k] for k in sorted(rows)]}


def pdf_text(data: bytes) -> str:
    """The text of a PDF, page by page."""
    import io
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


_CBK_RESULT_LINK = re.compile(r'href="([^"]*treasury_bill_results/[^"]*RESULTS\s+(\d+)-091[^"]*?DATED\s+(\d\d)-(\d\d)-(\d{4})[^"]*\.pdf)"', re.I)


def parse_cbk_result_links(page: str) -> list[dict]:
    """The CBK's published Treasury bill result files, newest value date first: issue number, value date, URL."""
    seen, out = set(), []
    for href, issue, d, m, y in _CBK_RESULT_LINK.findall(page or ""):
        if issue in seen:
            continue
        seen.add(issue)
        url = href if href.startswith("http") else "https://www.centralbank.go.ke" + href
        out.append({"issue": issue, "value_date": f"{y}-{m}-{d}", "url": url.replace(" ", "%20")})
    return sorted(out, key=lambda r: (r["value_date"], r["issue"]), reverse=True)


def _row_values(text: str, label: str, pattern: str = r"([\d.,]+)%?") -> list[str]:
    m = re.search(label + r"\s*((?:" + pattern + r"\s*){3})", text, re.S)
    return re.findall(pattern, m.group(1)) if m else []


def parse_cbk_result_pdf(text: str, link: dict) -> dict:
    """One CBK results release: weighted average interest rate and price per KSh 100 for each tenor, the results
    announcement date (the auction day) and the value date. The rates reconcile with the published prices on a
    365-day basis (price = 100 / (1 + r * t / 365))."""
    t = re.sub(r"[ \t]+", " ", text or "")
    head = re.search(r"Tenor\s+(\d+)\s*DAYS\s+(\d+)\s*DAYS\s+(\d+)\s*DAYS", t)
    tenors = [int(x) for x in head.groups()] if head else []
    rates = _row_values(t, r"Weighted Average Interest Rate of\s*accepted bids")
    prices = _row_values(t, r"Price per Kshs 100 at average interest\s*rate")
    offered = _row_values(t, r"Amount Offered \(Kshs\. M\)")
    accepted = _row_values(t, r"Total Amount Accepted \(Kshs\. M\)")
    signed = re.search(r"\n([A-Z][a-z]+ \d{1,2}, \d{4})\s*\n", t)
    auction = None
    if signed:
        try:
            auction = datetime.strptime(signed.group(1), "%B %d, %Y").date().isoformat()
        except ValueError:
            pass
    rows = []
    for i, days in enumerate(tenors):
        rate = _num(rates[i]) if i < len(rates) else None
        price = _num(prices[i]) if i < len(prices) else None
        # A row whose rate and published price do not reconcile was misread: it is dropped, never shown.
        if not rate or not price or abs(100 / (1 + rate / 100 * days / 365) - price) > 0.01:
            continue
        rows.append({"tenor_days": days, "rate_type": "yield", "rate": rate, "basis": 365, "price": price,
                     "auction_date": auction, "value_date": link["value_date"], "issue": link["issue"],
                     "offered_mn": _num(offered[i]) if i < len(offered) else None,
                     "allotted_mn": _num(accepted[i]) if i < len(accepted) else None})
    return {"country": "KE", "currency": "KES", "issuer": "Government of Kenya",
            "source": "Central Bank of Kenya, Treasury bill auction results", "source_url": link["url"], "rows": rows}


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
            bonds.append({"name": name.replace(" (closing yields)", ""), "yield": float(value), "date": day, "kind": "closing"})
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


def parse_bou_docs(payload: object) -> list[dict]:
    """Bank of Uganda Treasury bill result press releases, newest first, from its document API."""
    found = []

    def walk(o):
        if isinstance(o, dict):
            name, url = str(o.get("name") or ""), str(o.get("url") or "")
            if url.endswith(".pdf") and re.search(r"t[\s_-]?bill", name, re.I) and re.search(r"press|result", name, re.I):
                m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?[\s_-]+([A-Za-z]{3,9})[\s_-]+(\d{4})", name)
                when = None
                if m:
                    for fmt in ("%d %b %Y", "%d %B %Y"):
                        try:
                            when = datetime.strptime(f"{m.group(1)} {m.group(2)[:3] if fmt == '%d %b %Y' else m.group(2)} {m.group(3)}", fmt).date()
                            break
                        except ValueError:
                            continue
                if when:
                    found.append({"date": when.isoformat(), "url": "https://bou.or.ug" + url if url.startswith("/") else url})
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(payload)
    return sorted({f["url"]: f for f in found}.values(), key=lambda f: f["date"], reverse=True)


def _line_numbers(text: str, label: str, n: int = 3) -> list[float]:
    m = re.search(label + r"\s+((?:[\d,]+\.?\d*\s+){%d})" % n, text + " ")
    return [_num(v) for v in m.group(1).split()] if m else []


def parse_bou_pdf(text: str, doc: dict) -> dict:
    """Uganda: cut-off price, annual discount rate and money-market yield per tenor. Each discount rate must
    reproduce its published price on a 365-day basis, or the row is dropped."""
    t = re.sub(r"[ \t]+", " ", text or "")
    m = re.search(r"AUCTION DATE:\s*\w*\s*(\d{1,2})-([A-Z]{3})-(\d{4})", t)
    auction = datetime.strptime(f"{m.group(1)} {m.group(2).title()} {m.group(3)}", "%d %b %Y").date().isoformat() if m else doc.get("date")
    tenors = [int(v) for v in _line_numbers(t, "MATURITIES")]
    prices, discs, mmy = _line_numbers(t, "CUT OFF PRICE"), _line_numbers(t, "ANN. DISC RATE"), _line_numbers(t, "MONEY MKT YIELD")
    rows = []
    for i, days in enumerate(tenors):
        if i >= min(len(prices), len(discs), len(mmy)) or not discs[i] or not prices[i]:
            continue
        if abs(100 * (1 - discs[i] / 100 * days / 365) - prices[i]) > 0.01:
            continue
        rows.append({"tenor_days": days, "rate_type": "discount", "rate": discs[i], "true_yield": mmy[i], "basis": 365,
                     "price": prices[i], "auction_date": auction})
    return _block("UG", "UGX", "Government of Uganda", "Bank of Uganda, Treasury bill auction results", doc["url"], rows)


def parse_rbm_results_links(page: str) -> list[dict]:
    """Reserve Bank of Malawi Treasury bill result files (newest first) from the results tab only."""
    start = (page or "").find('id="TreasuryBillsAuctionResults"')
    if start < 0:
        return []
    end = page.find('id="TreasuryBillsAuctionNotice"', start)
    seg = page[start:end if end > 0 else start + 20000]
    out = []
    for when, cid in re.findall(r"([A-Z][a-z]{2} \d{1,2}, \d{4}).*?GetContentFile/\?ContentID=(\d+)", seg, re.S):
        out.append({"date": datetime.strptime(when, "%b %d, %Y").date().isoformat(),
                    "url": f"https://www.rbm.mw/Home/GetContentFile/?ContentID={cid}"})
    return out


def parse_rbm_pdf(text: str, doc: dict) -> dict:
    """Malawi: the average yield per tenor at one auction. A tenor with nothing allotted (0.00) is skipped. No price is
    published to check a day-count basis, so the yield is shown as published."""
    t = re.sub(r"[ \t]+", " ", text or "")
    m = re.search(r"AUCTION HELD ON (\d{1,2}) ([A-Z]+) (\d{4})", t)
    auction = datetime.strptime(f"{m.group(1)} {m.group(2).title()} {m.group(3)}", "%d %B %Y").date().isoformat() if m else doc.get("date")
    rows = []
    for days, *vals in re.findall(r"\n(91|182|364) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)", t):
        allotted, current = _num(vals[2]), _num(vals[6])
        if allotted and current:
            rows.append({"tenor_days": int(days), "rate_type": "yield", "rate": current, "basis": None,
                         "auction_date": auction, "allotted_mn": allotted})
    return _block("MW", "MWK", "Government of Malawi", "Reserve Bank of Malawi, Treasury bill auction results", doc["url"], rows)


def parse_bob_links(page: str) -> list[str]:
    """Bank of Botswana government securities auction result files, in page order (newest first)."""
    seen, out = set(), []
    for href in re.findall(r'href="([^"]*auction-pdf-files/[^"]+\.pdf)"', page or ""):
        if re.search(r"announcement", href, re.I) or href in seen:
            continue
        seen.add(href)
        out.append(href if href.startswith("http") else "https://www.bankofbotswana.bw" + href)
    return out


def parse_bob_pdf(text: str, url: str) -> dict:
    """Botswana: one monthly auction. Bills give stop-out price and simple yield, which must reconcile over the days
    from settlement to maturity on 365 days; bonds give coupon, maturity and the weighted average winning yield."""
    t = re.sub(r"[ \t]+", " ", text or "")
    codes = re.findall(r"\bBOTS(?:TB|GB)\d{4}\b", t)

    def line(label: str) -> str:
        m = re.search(label + r"([^\n]+)", t)
        return m.group(1) if m else ""

    def parse_d(d: str) -> date:
        return datetime.strptime(d, "%d-%b-%y").date()

    day_pattern = r"(\d{1,2}-[A-Z][a-z]{2}-\d{2})"
    auction, settle = re.findall(day_pattern, line("AUCTION DATE")), re.findall(day_pattern, line("SETTLEMENT DATE"))
    maturity = re.findall(day_pattern, line("MATURITY DATE"))
    prices = re.findall(r"([\d.]+|-)", line("STOP OUT PRICE"))
    simple = re.findall(r"([\d.]+)%", line("SIMPLE YIELD"))
    way = re.findall(r"([\d.]+)%", line("WEIGHTED AVERAGE YIELD OF WINNING BIDS"))
    coupons = re.findall(r"(\d+(?:\.\d+)? percent|\b0\b)", line("COUPON"))
    rows, bonds = [], []
    for i, code in enumerate(codes):
        if i >= min(len(auction), len(settle), len(maturity)):
            break
        a, st, mt = parse_d(auction[i]), parse_d(settle[i]), parse_d(maturity[i])
        if code.startswith("BOTSTB"):
            price = _num(prices[i]) if i < len(prices) else None
            yld = _num(simple[i]) if i < len(simple) else None
            days = (mt - st).days
            if not price or not yld or abs((100 / price - 1) * 365 / days * 100 - yld) > 0.02:
                continue
            rows.append({"tenor_days": days, "tenor_label": f"{round(days / 30.4)} months", "rate_type": "yield",
                         "rate": yld, "basis": 365, "price": price, "auction_date": a.isoformat(),
                         "maturity_date": mt.isoformat(), "isin_code": code})
        else:
            yld = _num(way[i]) if i < len(way) else None
            cpn = coupons[i] if i < len(coupons) else None
            if yld:
                bonds.append({"name": code, "coupon": _num(cpn.replace(" percent", "")) if cpn else None,
                              "maturity": mt.isoformat(), "yield": yld, "date": a.isoformat(), "kind": "auction"})
    return _block("BW", "BWP", "Government of Botswana", "Bank of Botswana, government securities auctions", url, rows,
                  bonds=bonds)


def parse_beac_curve_links(page: str) -> dict[str, dict]:
    """{country code: newest monthly yield-curve PDF} from the BEAC's public securities statistics page."""
    best: dict[str, dict] = {}
    for href in re.findall(r'href="([^"]*Courbe-des-taux-de-rendement-des-titres-publics-([A-Za-zéè-]+?)-([a-zéû]+)\.?-(\d{2,4})(?:-\d)?\.pdf)"', page or "", re.I):
        url, people, month, year = href
        code = _BEAC_COUNTRIES.get(people)
        mon = _FR_MONTHS.get(month.lower().rstrip("."))
        if not code or not mon:
            continue
        yr = int(year) + (2000 if len(year) == 2 else 0)
        key = f"{yr:04d}-{mon:02d}"
        if code not in best or best[code]["month"] < key:
            best[code] = {"month": key, "url": url}
    return best


def parse_beac_curve(text: str, code: str, doc: dict) -> dict:
    """A CEMAC state's government yield curve for one month, as published by the BEAC: the 3, 6 and 12-month points
    as bill yields (curve figures, not auction results) and the longer points as bond yields."""
    t = re.sub(r"[ \t]+", " ", text or "")
    t = t[t.find("Maturités Rendements"):] if "Maturités Rendements" in t else t
    rows, bonds = [], []
    for label, value in re.findall(r"(\d+(?:,\d)? ?(?:mois|ans?|A)) (\d+,\d+)", t):
        y = _fr_num(value)
        num = _fr_num(re.match(r"[\d,]+", label).group(0))
        if y is None or num is None:
            continue
        if "mois" in label:
            rows.append({"tenor_days": round(num * 30.4), "tenor_label": f"{int(num)} months", "rate_type": "curve",
                         "rate": y, "basis": None, "auction_date": None, "curve_month": doc["month"]})
        elif num == 1 and "an" in label and "ans" not in label:
            rows.append({"tenor_days": 365, "tenor_label": "1 year", "rate_type": "curve", "rate": y, "basis": None,
                         "auction_date": None, "curve_month": doc["month"]})
        else:
            bonds.append({"name": f"{num:g}-year curve point", "yield": y,
                          "date": doc["month"], "kind": "curve"})
    seen = set()
    rows = [r for r in rows if not (r["tenor_days"] in seen or seen.add(r["tenor_days"]))]
    return _block(code, "XAF", f"Government of {COUNTRY_NAMES.get(code, code)}", "BEAC, monthly government yield curve",
                  doc["url"], rows, bonds=bonds)


_ERRORS: list[str] = []          # source failures in the current build, reported by the cron that ran it


def _safe(label: str, fn):
    try:
        return fn()
    except Exception as exc:                                  # one source failing never stops the others
        log.warning("Treasury bill source %s failed: %s", label, exc)
        _ERRORS.append(f"{label}: {type(exc).__name__}: {str(exc)[:120]}")
        return None


def take_errors() -> list[str]:
    """The source failures recorded since the last call, cleared."""
    out = list(_ERRORS)
    _ERRORS.clear()
    return out


def build_tbills(client: httpx.Client, now: Optional[datetime] = None) -> dict[str, dict]:
    """{country code (lower case): block} for every source that answered with at least one tenor."""
    from src.engines import markets
    now = now or datetime.now(timezone.utc)
    get = lambda url, **kw: markets._get(client, url, headers=_UA, **kw)          # noqa: E731
    def kenya() -> Optional[dict]:
        """The newest results release (dated, with prices); the bill page's undated summary if that fails."""
        page = get(CBK_TBILLS)
        if page is None:
            return None
        links = parse_cbk_result_links(page.text)
        for link in links[:2]:
            r = get(link["url"])
            block = _safe("cbk-pdf", lambda r=r, link=link: parse_cbk_result_pdf(pdf_text(r.content), link)) if r else None
            if block and block["rows"]:
                return block
        _ERRORS.append(f"cbk: results release unreadable ({len(links)} links found); used the undated bill page")
        return parse_cbk_tbills(page.text)

    blocks: list[Optional[dict]] = [
        _safe("cbn", lambda: parse_cbn_ntb(get(CBN_NTB).json())),
        _safe("cbk", lambda: kenya()),
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

    def uganda() -> Optional[dict]:
        for doc in parse_bou_docs(get(BOU_DOCS).json())[:2]:
            r = get(doc["url"])
            block = _safe("bou-pdf", lambda r=r, d=doc: parse_bou_pdf(pdf_text(r.content), d)) if r else None
            if block and block["rows"]:
                return block
        return None

    def malawi() -> Optional[dict]:
        for doc in parse_rbm_results_links(get(RBM_TBILLS).text)[:4]:   # an auction can allot nothing: try the next
            r = get(doc["url"])
            block = _safe("rbm-pdf", lambda r=r, d=doc: parse_rbm_pdf(pdf_text(r.content), d)) if r else None
            if block and block["rows"]:
                return block
        return None

    def botswana() -> Optional[dict]:
        bills, bonds = None, None
        for url in parse_bob_links(get(BOB_AUCTIONS).text)[:4]:          # bills from the newest file that has them
            r = get(url)
            block = _safe("bob-pdf", lambda r=r, u=url: parse_bob_pdf(pdf_text(r.content), u)) if r else None
            if not block:
                continue
            bonds = bonds if bonds is not None else (block.get("bonds") or None)
            if block["rows"]:
                bills = block
                break
        if bills and bonds:
            bills["bonds"] = bonds
        return bills

    blocks.append(_safe("bou", uganda))
    blocks.append(_safe("rbm", malawi))
    blocks.append(_safe("bob", botswana))
    for code, doc in (_safe("beac", lambda: parse_beac_curve_links(get(BEAC_STATS).text)) or {}).items():
        r = get(doc["url"])
        if r is not None:
            blocks.append(_safe(f"beac-{code}", lambda r=r, c=code, d=doc: parse_beac_curve(pdf_text(r.content), c, d)))

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


def _page_text(page: str) -> str:
    return re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", page or "", flags=re.S))))


def _rate(country: str, rate: Optional[float], when: Optional[str], kind: str, source: str, url: str) -> Optional[dict]:
    """A policy rate read from the central bank itself. kind says what the date is: 'decision' (the meeting that set
    it), 'published' (the bank's own data date), 'effective' (the month it took effect) or 'confirmed' (the day we
    read it, when the bank gives no date)."""
    if rate is None or not 0 <= rate < 100:
        return None
    return {"country": country, "country_name": COUNTRY_NAMES.get(country, country), "rate": rate, "date": when,
            "date_kind": kind, "source": source, "source_url": url, "confirmed_by": "central bank"}


def parse_sarb_policy(items: object) -> Optional[dict]:
    for it in items if isinstance(items, list) else []:
        if it.get("Name") == "SARB Policy Rate" and isinstance(it.get("Value"), (int, float)):
            return _rate("ZA", float(it["Value"]), str(it.get("Date") or "")[:10] or None, "published",
                         "South African Reserve Bank", SARB_PAGE)
    return None


def parse_cbk_cbr(page: str) -> Optional[dict]:
    """Kenya: the latest Monetary Policy Committee decision in the CBK's Central Bank Rate table."""
    best = None
    for c in _cells(page):
        try:
            when = datetime.strptime(c[0], "%d/%m/%Y").date()
        except (ValueError, IndexError):
            continue
        rate = _num(c[1]) if len(c) > 1 else None
        if rate is not None and (best is None or when > best[0]):
            best = (when, rate)
    return _rate("KE", best[1], best[0].isoformat(), "decision", "Central Bank of Kenya", CBK_CBR) if best else None


def parse_cbn_mpr(payload: object, today: str) -> Optional[dict]:
    item = payload[0] if isinstance(payload, list) and payload else {}
    return _rate("NG", _num(item.get("mpr")), today, "confirmed", "Central Bank of Nigeria", "https://www.cbn.gov.ng/")


def parse_bog_mpr(page: str, today: str) -> Optional[dict]:
    m = re.search(r"([\d.]+)\s*Current Monetary Policy Rate", _page_text(page))
    return _rate("GH", _num(m.group(1)), today, "confirmed", "Bank of Ghana", BOG_HOME) if m else None


def parse_bob_mopr(page: str) -> Optional[dict]:
    m = re.search(r"Date:\s*(\d{1,2} [A-Z][a-z]{2} \d{4})\s*BoBC Rate 7 Day:\s*[\d.]+\s*%?\s*Monetary Policy Rate:\s*([\d.]+)",
                  _page_text(page))
    if not m:
        return None
    when = datetime.strptime(m.group(1), "%d %b %Y").date().isoformat()
    return _rate("BW", _num(m.group(2)), when, "published", "Bank of Botswana", BOB_HOME)


def parse_rbm_policy(page: str) -> Optional[dict]:
    m = re.search(r"Policy Rate\s*([\d.]+)\s*([A-Z][a-z]{2}) - ?(\d{4})|Policy Rate\s*([\d.]+)\s*([A-Z][a-z]{2}) (\d{4})", _page_text(page))
    if not m:
        return None
    rate, mon, year = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(4), m.group(5), m.group(6))
    when = datetime.strptime(f"1 {mon} {year}", "%d %b %Y").date().isoformat()[:7]
    return _rate("MW", _num(rate), when, "effective", "Reserve Bank of Malawi", RBM_HOME)


def parse_bon_repo(page: str) -> Optional[dict]:
    """Namibia: the latest Monetary Policy Committee announcement on the Bank of Namibia's home page."""
    m = re.search(r"Repo Rate [A-Za-z0-9 ]*? (?:to|at) ([\d.]+) Percent.{0,40}?On (?:\d{1,2} and )?(\d{1,2}) ([A-Z][a-z]+) (\d{4})",
                  _page_text(page))
    if not m:
        return None
    when = datetime.strptime(f"{m.group(2)} {m.group(3)} {m.group(4)}", "%d %B %Y").date().isoformat()
    return _rate("NA", _num(m.group(1)), when, "decision", "Bank of Namibia", BON_HOME)


def build_policy_rates(client: httpx.Client, now: Optional[datetime] = None) -> dict:
    """Policy rates read from each central bank that publishes one in a readable form."""
    from src.engines import markets
    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()
    get = lambda url: markets._get(client, url, headers=_UA)                      # noqa: E731
    found = [
        _safe("sarb-policy", lambda: parse_sarb_policy(get(SARB_RATES).json())),
        _safe("cbk-cbr", lambda: parse_cbk_cbr(get(CBK_CBR).text)),
        _safe("cbn-mpr", lambda: parse_cbn_mpr(get(CBN_MPR).json(), today)),
        _safe("bog-mpr", lambda: parse_bog_mpr(get(BOG_HOME).text, today)),
        _safe("bob-mopr", lambda: parse_bob_mopr(get(BOB_HOME).text)),
        _safe("rbm-policy", lambda: parse_rbm_policy(get(RBM_HOME).text)),
        _safe("bon-repo", lambda: parse_bon_repo(get(BON_HOME).text)),
    ]
    return {"captured_at": now.isoformat(), "rows": [r for r in found if r]}


def policy_rates(signals: dict, confirmed: Optional[dict] = None) -> list[dict]:
    """Each country's policy rate: the central bank's own figure where we read one, otherwise the country signals
    snapshot (Africa API), whose observation period is not a decision date and whose value is not confirmed. A
    feed value that disagrees with the central bank is reported beside it."""
    banks = {r["country"]: r for r in (confirmed or {}).get("rows") or []}
    feed = {}
    for code, block in ((signals or {}).get("countries") or {}).items():
        for o in (block or {}).get("observations") or []:
            if o.get("metric_key") == "policy_rate_pct" and isinstance(o.get("value"), (int, float)):
                feed[code] = {"country": code, "country_name": block.get("country_name") or code, "rate": o["value"],
                              "date": o.get("as_of_period"), "date_kind": "observation", "source": "Africa API",
                              "source_url": "https://africa-api.com/docs/signals", "confirmed_by": None}
    out = []
    for code in sorted(set(banks) | set(feed)):
        row = dict(banks.get(code) or feed[code])
        if code in banks and code in feed:
            row["country_name"] = feed[code]["country_name"]
            if abs(feed[code]["rate"] - row["rate"]) > 1e-9:
                row["feed_disagreed"] = {"rate": feed[code]["rate"], "date": feed[code]["date"]}
        out.append(row)
    return sorted(out, key=lambda r: r["country_name"])


def save_local(rows: list[dict]) -> None:
    """Keep the latest block per scope beside the local market snapshot (the hosted API stores them in Supabase)."""
    stored = load_json(LOCAL_PATH, dict) or {}
    stored.update({r["scope"]: r["payload"] for r in rows})
    save_json(LOCAL_PATH, stored)


def load_local() -> dict[str, dict]:
    return load_json(LOCAL_PATH, dict) or {}
