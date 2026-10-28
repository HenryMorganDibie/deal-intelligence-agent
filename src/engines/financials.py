"""
Financial statements from published filings, with arithmetic verification.

Sources by listing:
  * NGX: the audited annual statements the company files with the exchange
    (PDF, from the NGX document library). Text is parsed deterministically:
    each line item's first two figures are the Group's current and prior year,
    the layout Nigerian statements use (Group current, Group prior, Company
    current, Company prior). Units come from the column header (N'million,
    N'000).
  * Yahoo Finance: annual statements for JSE, EGX, Casablanca, US and other
    listings Yahoo carries.
  * SEC XBRL (companyfacts): revenue and net income for SEC filers, used to
    cross-check the Yahoo figures.

Every figure is checked where accounting allows it (gross profit = revenue -
cost of sales; profit after tax = profit before tax - tax; assets = liabilities
+ equity) and the result reports each check, so a reader can see which figures
are internally consistent.
"""
from __future__ import annotations

import io
import logging
import re
from typing import Callable, Optional

import httpx

log = logging.getLogger(__name__)
logging.getLogger("pypdf").setLevel(logging.ERROR)     # font-encoding warnings on every page

_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) deal-intelligence-agent/1.0"}

# field -> label patterns (line starts). First match wins, so specific labels come first.
LINE_ITEMS: tuple[tuple[str, str], ...] = (
    ("revenue", r"(?:total\s+)?revenue(?:\s+from\s+contracts\s+with\s+customers)?|gross\s+earnings|turnover"),
    ("cost_of_sales", r"(?:production\s+)?cost\s+of\s+(?:sales|revenue|goods\s+sold)"),
    ("gross_profit", r"gross\s+profit"),
    ("net_interest_income", r"net\s+interest\s+income"),
    ("operating_profit", r"(?:profit|income)\s+from\s+operati(?:ng\s+activities|ons)|operating\s+(?:profit|income)|results\s+from\s+operating\s+activities"),
    ("finance_costs", r"finance\s+costs?|interest\s+expense"),
    ("profit_before_tax", r"(?:profit|\(loss\)/profit|profit/\(loss\))\s+before\s+(?:income\s+)?tax(?:ation)?"),
    ("income_tax", r"income\s+tax\s+(?:expense|credit)|taxation|tax\s+expense"),
    ("profit_after_tax", r"profit\s+for\s+the\s+(?:year|period)(?:/year)?|profit\s+after\s+tax(?:ation)?|profit/\(loss\)\s+for\s+the\s+(?:year|period)"),
    ("eps", r"(?:basic\s+)?earnings\s+per\s+share(?:,?\s+basic(?:\s+and\s+diluted)?)?"),
    ("total_assets", r"total\s+assets"),
    ("total_liabilities", r"total\s+liabilities"),
    ("total_equity", r"total\s+equity(?:\s+attributable)?"),
    ("loans_to_customers", r"loans\s+and\s+advances\s+to\s+customers"),
    ("customer_deposits", r"deposits\s+from\s+customers"),
    ("cash", r"cash\s+and\s+cash\s+equivalents\s+at\s+(?:the\s+)?end|cash\s+and\s+(?:cash\s+)?equivalents\s*$|cash\s+and\s+(?:cash\s+)?equivalents(?=\s+[\d(])"),
    ("total_debt", r"(?:total\s+)?(?:interest[- ]bearing\s+)?(?:loans\s+and\s+)?borrowings|bank\s+loans|debt\s+securities\s+in\s+issue"),
    ("operating_cash_flow", r"net\s+cash\s+(?:generated\s+from|from|provided\s+by|\(used\s+in\)/generated\s+from|generated\s+from/\(used\s+in\))\s+operating\s+activities"),
    ("investing_cash_flow", r"net\s+cash\s+(?:used\s+in|from|generated\s+from/\(used\s+in\)|\(used\s+in\)/generated\s+from)\s+investing\s+activities"),
    ("financing_cash_flow", r"net\s+cash\s+(?:used\s+in|from|generated\s+from/\(used\s+in\)|\(used\s+in\)/generated\s+from)\s+financing\s+activities"),
)
_ITEM_RES = [(f, re.compile(rf"^\s*(?:{p})\b", re.IGNORECASE)) for f, p in LINE_ITEMS]
_NUM = re.compile(r"\(?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?|\(?-?\d+(?:\.\d+)?\)?")
_UNIT = re.compile(r"(?<![A-Za-z])(?:₦|N|=N=|NGN|KShs?|KES|R|ZAR|GH¢|GHS|\$|US\$)\s*['’]?\s*(million|000|billion|m|bn)\b|"
                   r"\bin\s+(millions?|thousands?|billions?)\s+of\b", re.IGNORECASE)
_PERIOD = re.compile(r"(?:for\s+the\s+)?(year|six\s+months|nine\s+months|three\s+months|period)\s+ended\s+"
                     r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})", re.IGNORECASE)
_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                        "september", "october", "november", "december"], 1)}
_SEPARATOR_ONLY = re.compile(r"^[\s\-–—]*$")


def _value(token: str) -> Optional[float]:
    neg = token.startswith("(") and token.endswith(")") or token.startswith("-")
    t = token.strip("()-").replace(",", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _line_numbers(line: str) -> list[float]:
    """Figures on a statement line, without the note reference ("Revenue 5 4,306,704 ...")."""
    body = re.sub(r"^[^\d(\-]*(?:\([A-Za-z][^)]*\)\s*)?", "", line)       # label text and "(Naira)"
    body = re.sub(r"^\s*\d{1,2}(?:\.\d+){2,}\s+", "", body)                 # "30.6.1"
    tokens = _NUM.findall(body)
    # Statements have an even number of columns (current/prior, Group/Company): an extra leading
    # integer is a note reference ("5", "13"), a two-part one like "18.3" too.
    if len(tokens) >= 3 and len(tokens) % 2 == 1 and re.fullmatch(r"\d{1,2}(?:\.\d)?", tokens[0]):
        tokens = tokens[1:]
    values = [_value(t) for t in tokens]
    return [v for v in values if v is not None]


def parse_statement_text(text: str) -> dict:
    """
    Group current- and prior-period figures from statement text.
    Returns {"period": {...}, "unit": ..., "multiplier": ..., "items": {field: {"current", "prior", "line"}}}.
    """
    unit_m = _UNIT.search(text)
    unit = unit_m.group(0) if unit_m else None
    word = (unit_m.group(1) or unit_m.group(2) or "").lower().rstrip("s") if unit_m else ""
    mult = {"million": 1e6, "m": 1e6, "000": 1e3, "thousand": 1e3, "billion": 1e9, "bn": 1e9}.get(word, 1)
    period = None
    pm = _PERIOD.search(text)
    if pm:
        months = {"year": 12, "six months": 6, "nine months": 9, "three months": 3, "period": None}[
            re.sub(r"\s+", " ", pm.group(1).lower())]
        mon = _MONTHS.get(pm.group(3).lower())
        if mon:
            period = {"months": months, "end": f"{pm.group(4)}-{mon:02d}-{int(pm.group(2)):02d}",
                      "label": re.sub(r"\s+", " ", pm.group(0)).strip()}
    items: dict[str, dict] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or _SEPARATOR_ONLY.match(line):
            continue
        for field, rx in _ITEM_RES:
            if field in items or not rx.match(line):
                continue
            nums = _line_numbers(line[rx.match(line).end():])
            figures = _NUM.findall(line[rx.match(line).end():])
            # Statement figures carry thousands separators or are large; small bare numbers are note references.
            if field != "eps" and not any("," in f or abs(_value(f) or 0) >= 1000 for f in figures[-max(len(nums), 1):]):
                continue
            if len(nums) >= 2:
                items[field] = {"current": nums[0], "prior": nums[1], "line": line[:160]}
            break
    return {"period": period, "unit": unit, "multiplier": mult, "items": items}


def verify(items: dict, tolerance: float = 0.01) -> list[dict]:
    """Accounting identities over the parsed figures (current period)."""
    def get(f: str) -> Optional[float]:
        return items[f]["current"] if f in items else None

    checks = []

    def check(name: str, lhs: Optional[float], rhs: Optional[float], fields: tuple[str, ...] = ()) -> None:
        if lhs is None or rhs is None:
            return
        ok = abs(lhs - rhs) <= tolerance * max(abs(lhs), abs(rhs), 1)
        checks.append({"check": name, "passed": ok, "lhs": lhs, "rhs": round(rhs, 3), "fields": list(fields)})

    rev, cos, gp = get("revenue"), get("cost_of_sales"), get("gross_profit")
    if rev is not None and cos is not None:
        check("gross profit = revenue - cost of sales", gp, rev - abs(cos), ("gross_profit", "revenue", "cost_of_sales"))
    pbt, tax, pat = get("profit_before_tax"), get("income_tax"), get("profit_after_tax")
    if pbt is not None and tax is not None:
        check("profit after tax = profit before tax - income tax", pat, pbt + tax if tax < 0 else pbt - tax,
              ("profit_after_tax", "profit_before_tax", "income_tax"))
    ta, tl, te = get("total_assets"), get("total_liabilities"), get("total_equity")
    if tl is not None and te is not None:
        check("total assets = total liabilities + total equity", ta, tl + te,
              ("total_assets", "total_liabilities", "total_equity"))
    if pbt is not None and rev:
        checks.append({"check": "profit before tax does not exceed revenue", "passed": pbt <= abs(rev),
                       "lhs": pbt, "rhs": rev, "fields": ["profit_before_tax", "revenue"]})
    flows = [get(k) for k in ("operating_cash_flow", "investing_cash_flow", "financing_cash_flow")]
    cash_prior = items["cash"].get("prior") if "cash" in items else None
    if all(v is not None for v in flows) and get("cash") is not None and cash_prior is not None:
        # Net flows explain the change in cash up to exchange-rate effects; a dropped bracket (a sign error) on
        # any of the three lines breaks this by twice that line's size.
        net, change = sum(flows), get("cash") - cash_prior
        checks.append({"check": "operating + investing + financing cash flow = change in cash (within 15% of gross flows)",
                       "passed": abs(net - change) <= 0.15 * sum(abs(v) for v in flows), "lhs": net,
                       "rhs": round(change, 3),
                       "fields": ["operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "cash"]})
    if pbt is not None and pat is not None:
        checks.append({"check": "profit after tax does not exceed profit before tax by more than 50%",
                       "passed": pat <= pbt * 1.5 if pbt > 0 else True, "lhs": pat, "rhs": pbt,
                       "fields": ["profit_after_tax", "profit_before_tax"]})
    return checks


def item_status(items: dict, checks: list[dict]) -> dict[str, str]:
    """Per figure: 'verified' (in a passed identity), 'inconsistent' (in a failed one), or 'unchecked'."""
    status = {f: "unchecked" for f in items}
    identities = [c for c in checks if "=" in c["check"]]
    for c in identities:
        for f in c.get("fields", []):
            if f in status and status[f] != "inconsistent":
                status[f] = "verified" if c["passed"] else "inconsistent"
    for c in checks:                                # bound checks can only demote
        if not c["passed"]:
            for f in c.get("fields", []):
                if f in status:
                    status[f] = "inconsistent"
    return status


def _pdf_text(data: bytes, max_pages: int = 45) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for p in reader.pages[:max_pages]:
        try:
            pages.append(p.extract_text() or "")
        except Exception:                       # malformed page: skip it, keep the rest
            continue
    return "\n".join(pages)


def statement_from_pdf(url: str, fetch: Optional[Callable[[str], bytes]] = None) -> Optional[dict]:
    """Parse one statement PDF; None when it cannot be read or holds no statement lines."""
    try:
        data = fetch(url) if fetch else httpx.get(url, headers=_HEADERS, timeout=60, follow_redirects=True).content
        text = _pdf_text(data)
    except Exception as e:
        log.warning("statement %s unreadable: %s", url, e)
        return None
    parsed = parse_statement_text(text)
    if len(parsed["items"]) < 2:
        return None
    parsed["checks"] = verify(parsed["items"])
    parsed["verified"] = bool(parsed["checks"]) and all(c["passed"] for c in parsed["checks"])
    parsed["status"] = item_status(parsed["items"], parsed["checks"])
    parsed["source_url"] = url
    parsed["basis"] = "Group (consolidated), first two figure columns: current and prior period"
    return parsed


# ── NGX ───────────────────────────────────────────────────────────────────────

NGX_WIDGETS = "https://ngxgroup.com/wp-json/ngx-data-widgets/v1/company/"


def ngx_company(symbol: str, client: Optional[httpx.Client] = None) -> dict:
    """NGX profile, latest trading summary and the list of filed financial statements."""
    c = client or httpx.Client(timeout=30, headers=_HEADERS, follow_redirects=True)
    code = symbol.upper().rsplit(".", 1)[0]
    out: dict = {"symbol": code}
    for section in ("profile", "summary", "financial-statements"):
        try:
            r = c.get(NGX_WIDGETS + section, params={"symbol": code})
            out[section] = r.json() if r.status_code == 200 else None
        except Exception as e:
            log.warning("NGX %s for %s unavailable: %s", section, code, e)
            out[section] = None
    docs = []
    for row in out.pop("financial-statements") or []:
        if not isinstance(row, dict):
            continue
        url = (row.get("URL") or {}).get("Url")
        desc = (row.get("URL") or {}).get("Description") or ""
        if url:
            docs.append({"title": desc.strip(), "url": url, "filed": (row.get("Modified") or "")[:10],
                         "audited": bool(re.search(r"audited|annual|full\s+year|year\s+ended", desc, re.I))
                         and not re.search(r"unaudited|quarter|half|interim", desc, re.I)})
    out["statements"] = docs
    return out


def ngx_financials(symbol: str, client: Optional[httpx.Client] = None,
                   fetch: Optional[Callable[[str], bytes]] = None) -> dict:
    """Profile plus the latest audited annual statement, parsed and verified."""
    data = ngx_company(symbol, client)
    annual = next((d for d in data["statements"] if d["audited"]), None)
    data["annual"] = statement_from_pdf(annual["url"], fetch) if annual else None
    if data["annual"]:
        data["annual"]["document"] = annual["title"]
        data["annual"]["filed"] = annual["filed"]
    return data


# ── NSE Kenya ─────────────────────────────────────────────────────────────────

NSE_MEDIA = "https://www.nse.co.ke/wp-json/wp/v2/media"
_ANNUAL_TITLE = re.compile(r"(?i)(audited|full\s+year|annual)\s+(financial\s+)?(results|statements|report)|results\s+for\s+the\s+year")


def nse_documents(company: str, client: Optional[httpx.Client] = None) -> list[dict]:
    """The company's documents in NSE Kenya's library, newest first."""
    import html as _html
    c = client or httpx.Client(timeout=30, headers=_HEADERS, follow_redirects=True)
    try:
        rows = c.get(NSE_MEDIA, params={"search": company, "per_page": 50, "orderby": "date", "order": "desc",
                                        "_fields": "date,title,source_url,mime_type"}).json()
    except Exception as e:
        log.warning("NSE documents unavailable for %s: %s", company, e)
        return []
    docs = []
    for r in rows if isinstance(rows, list) else []:
        if r.get("mime_type") and r["mime_type"] != "application/pdf":
            continue
        title = _html.unescape((r.get("title") or {}).get("rendered", ""))
        docs.append({"title": title, "url": r.get("source_url"), "filed": (r.get("date") or "")[:10],
                     "audited": bool(_ANNUAL_TITLE.search(title)) and not re.search(r"(?i)unaudited|six\s+months|half", title)})
    return docs


NSE_PRICES_PAGE = "https://www.nse.co.ke/dataservices/market-statistics/"
NSE_PRICES_AJAX = "https://www.nse.co.ke/dataservices/wp-admin/admin-ajax.php"
_NSE_EQUITY_SECTORS = ("agric", "auto", "bank", "comm", "const", "energy", "insr", "invest", "investse", "manu",
                       "tele", "real", "exchange")
_NSE_PRICE_ROW = re.compile(r"<tr><td>(?P<name>[^<]+)</td>\s*<td>(?P<isin>[A-Z0-9]{12})</td>\s*<td>(?P<volume>[\d,.]*)</td>"
                            r"\s*<td>(?P<price>[\d,.]+)</td>\s*<td[^>]*>(?:<span>)?\s*(?P<change>[-+]?[\d.]+)?")
_nse_prices_cache: dict = {"at": 0.0, "value": None}


def nse_prices(client: Optional[httpx.Client] = None, max_age: float = 3600) -> Optional[dict]:
    """NSE Kenya's daily equity price list: {"as_of": ISO date, "rows": [{name, isin, volume, price, change_pct}]}.
    Read sector by sector from the exchange's market-statistics page, as its own site does; cached for an hour."""
    import time as _time
    from datetime import datetime as _dt
    if _nse_prices_cache["value"] and _time.monotonic() - _nse_prices_cache["at"] < max_age:
        return _nse_prices_cache["value"]
    c = client or httpx.Client(timeout=30, headers={**_HEADERS, "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                               "AppleWebKit/537.36 Chrome/120 Safari/537.36"}, follow_redirects=True)
    try:
        page = c.get(NSE_PRICES_PAGE).text
        nonce = re.search(r'price-cc-js-js-extra">\s*var wp_ajax = \{[^}]*"ajaxnonce":"(\w+)"', page)
        stamp = re.search(r"Statistics as of (\d{1,2}-[A-Za-z]{3}-\d{4})", page)
        if not nonce or not stamp:
            return None
        rows = []
        for sector in _NSE_EQUITY_SECTORS:
            body = c.post(NSE_PRICES_AJAX, data={"action": "display_prices", "security": nonce.group(1),
                                                 "sector": sector}).text
            for m in _NSE_PRICE_ROW.finditer(body):
                rows.append({"name": m["name"].strip(), "isin": m["isin"],
                             "volume": float(m["volume"].replace(",", "")) if m["volume"] else None,
                             "price": float(m["price"].replace(",", "")),
                             "change_pct": float(m["change"]) if m["change"] else None})
    except Exception as e:
        log.warning("NSE price list unavailable: %s", e)
        return None
    if not rows:
        return None
    value = {"as_of": _dt.strptime(stamp.group(1), "%d-%b-%Y").date().isoformat(), "rows": rows}
    _nse_prices_cache.update(at=_time.monotonic(), value=value)
    return value


_NAME_NOISE = re.compile(r"(?i)\b(ltd|limited|plc|ord|ords|holdings?|group|company|co|the|kenya|kes)\b|[\d.]+")


def nse_price_for(company: str, prices: Optional[dict], ticker: Optional[str] = None) -> Optional[dict]:
    """The price-list row for a company, matched on the distinctive words of its name (the list says
    "Safaricom Ltd Ord 0.05"), or on initials for names the market abbreviates ("KCB" is listed as Kenya
    Commercial Bank); None when nothing matches."""
    def words(text: str) -> list[str]:
        return [w for w in re.findall(r"[a-z]+", _NAME_NOISE.sub(" ", text.lower())) if len(w) > 1]

    def initials(text: str) -> str:
        return "".join(w[0] for w in re.findall(r"[a-z]+", re.sub(r"(?i)\b(ltd|limited|plc|ord|the|of|and)\b|[\d.]+",
                                                                    " ", text.lower())))
    want = words(company)
    codes = {w.lower() for w in re.findall(r"\b[A-Z]{2,5}\b", company)}
    if ticker:
        codes.add(ticker.split(".")[0].lower())
    if not prices or not (want or codes):
        return None
    best, score = None, 0
    for row in prices["rows"]:
        have = words(row["name"])
        if want and have and have[0] == want[0]:
            overlap = 1 + len(set(want) & set(have))
        elif initials(row["name"]) in codes:
            overlap = 1
        else:
            continue
        if overlap > score:
            best, score = row, overlap
    return best


def nse_financials(company: str, client: Optional[httpx.Client] = None,
                   fetch: Optional[Callable[[str], bytes]] = None) -> dict:
    docs = nse_documents(company, client)
    annual = next((d for d in docs if d["audited"]), None)
    parsed = statement_from_pdf(annual["url"], fetch) if annual else None
    if parsed:
        parsed["document"], parsed["filed"] = annual["title"], annual["filed"]
        parsed["basis"] = "First two figure columns: current and prior year (Group where presented)"
    return {"statements": docs[:12], "annual": parsed}


# ── Yahoo Finance ─────────────────────────────────────────────────────────────

_YAHOO_ROWS = {
    "revenue": ("Total Revenue", "Operating Revenue"),
    "gross_profit": ("Gross Profit",),
    "operating_profit": ("Operating Income", "EBIT"),
    "ebitda": ("EBITDA", "Normalized EBITDA"),
    "profit_before_tax": ("Pretax Income",),
    "income_tax": ("Tax Provision",),
    "profit_after_tax": ("Net Income", "Net Income Common Stockholders"),
    "eps": ("Basic EPS",),
    "total_assets": ("Total Assets",),
    "total_liabilities": ("Total Liabilities Net Minority Interest",),
    "total_equity": ("Stockholders Equity", "Total Equity Gross Minority Interest"),
    "total_debt": ("Total Debt",),
    "cash": ("Cash And Cash Equivalents",),
    "operating_cash_flow": ("Operating Cash Flow",),
    "capex": ("Capital Expenditure",),
    "free_cash_flow": ("Free Cash Flow",),
}
_YAHOO_INFO = ("longName", "sector", "industry", "country", "website", "fullTimeEmployees", "longBusinessSummary",
               "currency", "financialCurrency", "marketCap", "enterpriseValue", "trailingPE", "forwardPE",
               "priceToBook", "enterpriseToRevenue", "enterpriseToEbitda", "dividendYield", "beta",
               "currentPrice", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "exchange", "regularMarketPrice",
               "regularMarketTime")


def yahoo_financials(ticker: str, years: int = 4) -> Optional[dict]:
    """Annual statements and valuation multiples from Yahoo Finance, or None if Yahoo has no data."""
    try:
        from src.engines.market_data import yahoo
        yf = yahoo()
        t = yf.Ticker(ticker)
        info = t.info or {}
        frames = [t.income_stmt, t.balance_sheet, t.cashflow]
    except Exception as e:
        log.warning("Yahoo financials unavailable for %s: %s", ticker, e)
        return None
    if all(f is None or f.empty for f in frames):
        return None
    periods: dict[str, dict] = {}
    for frame in frames:
        if frame is None or frame.empty:
            continue
        for col in list(frame.columns)[:years]:
            key = str(col)[:10]
            row = periods.setdefault(key, {})
            for field, names in _YAHOO_ROWS.items():
                if field in row:
                    continue
                for n in names:
                    if n in frame.index:
                        v = frame.at[n, col]
                        try:
                            if v == v:                      # not NaN
                                row[field] = float(v)
                                break
                        except (TypeError, ValueError):
                            continue
    ordered = dict(sorted(periods.items(), reverse=True))
    latest = next(iter(ordered.values()), {})
    items = {f: {"current": v} for f, v in latest.items()}
    return {"source": "Yahoo Finance", "ticker": ticker, "info": {k: info.get(k) for k in _YAHOO_INFO if info.get(k) is not None},
            "annual": ordered, "checks": verify(items), "unit": info.get("financialCurrency") or info.get("currency")}


# ── SEC XBRL cross-check ──────────────────────────────────────────────────────

SEC_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
_SEC_HEADERS = {"User-Agent": "deal-intelligence-agent research contact@example.com"}
_SEC_CONCEPTS = {
    "revenue": (("us-gaap", "Revenues"), ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
                ("ifrs-full", "Revenue")),
    "profit_after_tax": (("us-gaap", "NetIncomeLoss"), ("ifrs-full", "ProfitLoss")),
    "total_assets": (("us-gaap", "Assets"), ("ifrs-full", "Assets")),
}


def sec_annual_facts(cik: int, client: Optional[httpx.Client] = None) -> dict[str, dict[str, float]]:
    """{field: {fiscal year end: value}} from annual (10-K / 20-F) XBRL facts."""
    import os
    headers = dict(_SEC_HEADERS)
    if os.environ.get("SEC_USER_AGENT"):
        headers["User-Agent"] = os.environ["SEC_USER_AGENT"]
    c = client or httpx.Client(timeout=30, headers=headers)
    try:
        facts = c.get(SEC_FACTS.format(cik=int(cik))).json().get("facts", {})
    except Exception as e:
        log.warning("SEC facts unavailable for CIK %s: %s", cik, e)
        return {}
    out: dict[str, dict[str, float]] = {}
    for field, concepts in _SEC_CONCEPTS.items():
        for taxonomy, name in concepts:
            units = facts.get(taxonomy, {}).get(name, {}).get("units", {})
            for unit, rows in units.items():
                for r in rows:
                    if r.get("form") in ("10-K", "20-F", "40-F") and r.get("fp") == "FY" and r.get("end"):
                        start = r.get("start")
                        if start and (int(r["end"][:4]) - int(start[:4])) * 12 + int(r["end"][5:7]) - int(start[5:7]) < 11:
                            continue                       # a quarter reported inside the annual filing
                        out.setdefault(field, {})[r["end"]] = r["val"]
            if field in out:
                break
    return out


def cross_check(yahoo: dict, sec: dict[str, dict[str, float]], tolerance: float = 0.02) -> list[dict]:
    """Yahoo annual figures compared with the SEC filing for the same fiscal year end."""
    out = []
    for period, row in (yahoo or {}).get("annual", {}).items():
        for field in ("revenue", "profit_after_tax", "total_assets"):
            filed = (sec.get(field) or {}).get(period)
            if filed is None or field not in row:
                continue
            ok = abs(row[field] - filed) <= tolerance * max(abs(filed), 1)
            out.append({"period": period, "field": field, "yahoo": row[field], "sec_filing": filed, "match": ok})
    return out
