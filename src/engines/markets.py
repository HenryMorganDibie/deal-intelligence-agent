"""
African equity markets: one daily snapshot of every listed share on 16 exchanges, their benchmark indices and
the dollar exchange rates, and the views built from it (exchange tiles, movers, sectors, screener, search).

Sources, all free and public:

  * african-markets.com listing tables: price, 1-day and year-to-date change, market capitalisation and the
    trade date of every share on NGX, EGX, Casablanca, BRVM, GSE, BSE, DSE, LuSE, MSE, NSX, RSE, SEM, ZSE and
    BVMT; and the 17 benchmark indices (level, 1-day change).
  * NGX's own daily price list (volume, value, trades), which supersedes the listing table for NGX prices.
  * myStocks for Nairobi (price, 1-day change, volume, sector; the NSE site sits behind a captcha).
  * Yahoo Finance's batch chart endpoint for Johannesburg (price, change, volume, year-to-date from the first
    close of the year). Yahoo quotes JSE shares in cents.
  * open.er-api.com for spot dollar rates and the currency-api archive on jsDelivr for 1 January's rates,
    which turn local year-to-date returns into dollar returns.

Each source fails on its own: a missing exchange is reported, never filled in. A quote whose trade date is more
than STALE_DAYS old is marked stale, and stale quotes are left out of movers, sector moves and exchange returns.
"""
from __future__ import annotations

import html as html_mod
import logging
import re
import statistics
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

import httpx

from src.utils.paths import DATA_DIR
from src.utils.storage import load_json, save_json

log = logging.getLogger(__name__)

AM_BASE = "https://www.african-markets.com/en/stock-markets/{slug}/listed-companies"
NGX_PRICE_LIST = "https://doclib.ngxgroup.com/REST/api/statistics/equities/?market=&sector=&orderby=&pageSize=500&pageNo=0"
NSE_PRICE_LIST = "https://live.mystocks.co.ke/m/pricelist"
YAHOO_SPARK = "https://query1.finance.yahoo.com/v7/finance/spark"
USE_PRICES = "https://www.use.or.ug/api/delayed-data"
USE_EQUITIES = "https://www.use.or.ug/securities/equities"
ESX_LISTED = "https://esx.et/equity-market/listed-companies/"
FX_LATEST = "https://open.er-api.com/v6/latest/USD"
FX_ON_DATE = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{day}/v1/currencies/usd.json"

STALE_DAYS = 7
SNAPSHOT_PATH = DATA_DIR / "market_snapshot.json"   # the local copy; the hosted API keeps snapshots in Supabase
_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            "Accept": "text/html,application/json"}
# Yahoo throttles (429) a full browser user agent from datacentre addresses and serves a bare one.
_YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0"}


@dataclass(frozen=True)
class Exchange:
    key: str
    name: str
    country: str            # ISO2; BRVM's home is Côte d'Ivoire (regional exchange of eight WAEMU states)
    currency: str
    slug: str               # african-markets.com path
    index: str              # the benchmark as the index table names it
    mcap: str = "local_bn"  # the listing table's M.Cap column: billions of local currency, or billions of shares
    source: str = "listing"


EXCHANGES: dict[str, Exchange] = {e.key: e for e in (
    Exchange("jse", "Johannesburg Stock Exchange", "ZA", "ZAR", "jse", "JSE ASI", source="yahoo"),
    Exchange("ngx", "Nigerian Exchange", "NG", "NGN", "ngse", "NGX ASI"),
    Exchange("egx", "Egyptian Exchange", "EG", "EGP", "egx", "EGX 30", mcap="shares_bn"),
    Exchange("nse", "Nairobi Securities Exchange", "KE", "KES", "nse", "NSE ASI", source="mystocks"),
    Exchange("bvc", "Casablanca Stock Exchange", "MA", "MAD", "bvc", "MASI"),
    Exchange("brvm", "BRVM (West African regional exchange)", "CI", "XOF", "brvm", "BRVM-CI"),
    Exchange("gse", "Ghana Stock Exchange", "GH", "GHS", "gse", "GSE-CI"),
    Exchange("sem", "Stock Exchange of Mauritius", "MU", "MUR", "sem", "SEM ASI"),
    Exchange("bvmt", "Bourse de Tunis", "TN", "TND", "bvmt", "TUNINDEX"),
    Exchange("bse", "Botswana Stock Exchange", "BW", "BWP", "bse", "BSE DCI"),
    Exchange("dse", "Dar es Salaam Stock Exchange", "TZ", "TZS", "dse", "DSE ASI"),
    Exchange("luse", "Lusaka Securities Exchange", "ZM", "ZMW", "luse", "LuSE ASI"),
    Exchange("mse", "Malawi Stock Exchange", "MW", "MWK", "mse", "MSE ASI"),
    Exchange("nsx", "Namibian Stock Exchange", "NA", "NAD", "nsx", "NSX OI"),
    Exchange("rse", "Rwanda Stock Exchange", "RW", "RWF", "rse", "RSE ASI"),
    Exchange("zse", "Zimbabwe Stock Exchange", "ZW", "ZWG", "zse", "ZSE ASI"),
    Exchange("use", "Uganda Securities Exchange", "UG", "UGX", "use", "USE ASI", source="use"),
    Exchange("esx", "Ethiopian Securities Exchange", "ET", "ETB", "esx", "", source="esx"),
)}
_BY_SLUG = {e.slug: e for e in EXCHANGES.values()}


def _client() -> httpx.Client:
    return httpx.Client(timeout=30, follow_redirects=True, headers=_HEADERS)


# ── Parsing helpers ───────────────────────────────────────────────────────────

_TAG = re.compile(r"<[^>]+>")
_ROW = re.compile(r'<tr class="tabrow[^"]*">(.*?)</tr>', re.S)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)


def _text(cell: str) -> str:
    return html_mod.unescape(_TAG.sub("", cell)).replace("\xa0", " ").strip()


def _num(s: Optional[str]) -> Optional[float]:
    """'1,341.90' -> 1341.9; '-' or '' -> None."""
    s = (s or "").replace(",", "").strip()
    if not s or s in {"-", "—"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _pct(s: Optional[str]) -> Optional[float]:
    """'+9.80%' -> 0.098."""
    v = _num((s or "").replace("%", "").replace("+", ""))
    return None if v is None else round(v / 100, 6)


def _volume(s: Optional[str]) -> Optional[float]:
    """'2.75M' -> 2750000; '21,308' -> 21308."""
    s = (s or "").replace(",", "").strip()
    mult = {"K": 1e3, "M": 1e6, "B": 1e9}.get(s[-1:].upper(), 1)
    v = _num(s[:-1] if mult != 1 else s)
    return None if v is None else v * mult


def _day_month(s: str, today: date) -> Optional[str]:
    """'27/10' -> the most recent such date on or before today (the table gives no year)."""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", (s or "").strip())
    if not m:
        return None
    d, mo = int(m.group(1)), int(m.group(2))
    for year in (today.year, today.year - 1):
        try:
            day = date(year, mo, d)
        except ValueError:
            return None
        if day <= today + timedelta(days=1):         # a day ahead allows for exchanges east of UTC
            return day.isoformat()
    return None


def _table(page: str, ruleset: str) -> Optional[str]:
    m = re.search(r'<table id="tab_\w+" class="tabtable-' + ruleset + r'.*?</table>', page, re.S)
    return m.group(0) if m else None


# ── african-markets.com ───────────────────────────────────────────────────────

def parse_listing(page: str, exchange: Exchange, today: Optional[date] = None) -> list[dict]:
    """Every share in an exchange's listing table: symbol (the page's company code), name, sector, price, 1-day
    and year-to-date change, market capitalisation (local currency) or shares outstanding, and trade date."""
    today = today or date.today()
    table = _table(page, "rs_01k0jris")
    if not table:
        return []
    head = re.search(r"<thead>(.*?)</thead>", table, re.S)
    # Most tables read Company, Sector, Price, 1D, YTD, M.Cap, Date. Tunis adds a Symbol column, has no cap, and
    # labels its price column "1D" and its 1-day column "Change".
    with_symbol = bool(head) and [_text(c) for c in _CELL.findall(head.group(1))][1:2] == ["Symbol"]
    out = []
    for row in _ROW.findall(table):
        cells = [_text(c) for c in _CELL.findall(row)]
        code = re.search(r"code=([^'\"&]+)", row)
        if len(cells) < 7 or not code:
            continue                                    # header, or a table without prices (JSE, NSE)
        if with_symbol:
            name, _, sector, price, d1, ytd, day = cells[:7]
            mcap = ""
        else:
            name, sector, price, d1, ytd, mcap, day = cells[:7]
        p = _num(price)
        if not p or p <= 0:
            continue
        quote = {"symbol": html_mod.unescape(code.group(1)).strip().upper(), "name": name, "sector": sector or None,
                 "price": p, "chg_1d": _pct(d1), "ytd": _pct(ytd), "date": _day_month(day, today)}
        m = _num(mcap)
        if m and m > 0 and m != p:                      # a cap equal to the price is a known table glitch
            if exchange.mcap == "shares_bn":
                quote["shares"] = m * 1e9
                quote["mcap"] = round(m * 1e9 * p, 2)
            else:
                quote["mcap"] = round(m * 1e9, 2)
                quote["shares"] = round(m * 1e9 / p)
        out.append(quote)
    return out


def parse_listing_names(page: str) -> list[dict]:
    """(name, symbol, sector) from a listing table without prices: JSE's carries a Symbol column; NSE's none."""
    table = _table(page, "rs_01k0jris")
    out = []
    for row in _ROW.findall(table or ""):
        cells = [_text(c) for c in _CELL.findall(row)]
        if len(cells) >= 3 and cells[0] != "Company" and re.fullmatch(r"[A-Z0-9]{2,6}", cells[1] or ""):
            out.append({"name": cells[0], "symbol": cells[1], "sector": cells[2] or None})
    return out


def parse_indices(page: str, today: Optional[date] = None) -> list[dict]:
    """The benchmark-index table every listing page carries: exchange, index name, level, 1-day change, date."""
    today = today or date.today()
    out = []
    for row in _ROW.findall(_table(page, "rs_m316x72x") or ""):
        slug = re.search(r"/stock-markets/(\w+)'", row)
        cells = [_text(c) for c in _CELL.findall(row)]
        if not slug or len(cells) < 5:
            continue
        ex = _BY_SLUG.get(slug.group(1))
        level = _num(cells[2])
        if ex and level:
            out.append({"exchange": ex.key, "name": cells[1], "level": level, "chg_1d": _pct(cells[3]),
                        "date": _day_month(cells[4], today)})
    return out


# ── Exchanges' own lists ──────────────────────────────────────────────────────

def parse_ngx_doclib(rows: object) -> dict[str, dict]:
    """{symbol: {price, prev, volume, value, trades, date, sector}} from NGX's daily equities list."""
    out: dict[str, dict] = {}
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        sym, close = (r.get("Symbol") or "").strip().upper(), r.get("ClosePrice")
        if not sym or not isinstance(close, (int, float)) or close <= 0:
            continue
        out[sym] = {"price": float(close), "prev": r.get("PrevClosingPrice"), "volume": r.get("Volume"),
                    "value": r.get("Value"), "trades": r.get("Trades"), "date": (r.get("TradeDate") or "")[:10] or None,
                    "sector": (r.get("Sector") or "").strip().title() or None}
    return out


_MS_DATE = re.compile(r"Market Pricelist\s*(?:&amp;#8212;|&#8212;|—|-)\s*(\d{1,2} [A-Z][a-z]{2} \d{4})")
_MS_OPTION = re.compile(r"<option value=([^>\s]+)>([^<]+)</option>")
_MS_PART = re.compile(r"<th class=head colspan=\d+><h2>([^<]+)</h2>|"
                      r'<td class=nm><a href="/m/stock=[^"]*">([A-Z][A-Z0-9&.\-]{0,11})</a>(?:<br>)?\s*'
                      r'<td class=n>([\d,]+(?:\.\d+)?)<td class="n x(-?\d)">(?:&#9650;|&#9660;|&nbsp;)?\s*([\d.]+%|-)'
                      r"<td class=n>([\d.,]+[KMB]?|-)")


def parse_mystocks(page: str) -> list[dict]:
    """Every Nairobi share on the myStocks price list: symbol, name, sector, price, 1-day change, volume, date."""
    m = _MS_DATE.search(page)
    day = datetime.strptime(m.group(1), "%d %b %Y").date().isoformat() if m else None
    names = {html_mod.unescape(s): html_mod.unescape(n).strip() for s, n in _MS_OPTION.findall(page)}
    out, sector = [], None
    for head, sym, price, sign, chg, vol in _MS_PART.findall(page):
        if head:
            sector = html_mod.unescape(head).strip()
            continue
        p = _num(price)
        if not p or sym.startswith("^"):
            continue
        c = _pct(chg) if chg != "-" else 0.0
        out.append({"symbol": sym, "name": names.get(sym, sym), "sector": sector, "price": p,
                    "chg_1d": (-c if sign == "-1" and c else c), "volume": _volume(vol) if vol != "-" else 0.0,
                    "date": day})
    return out


def parse_spark(payload: object) -> dict[str, dict]:
    """{symbol: {price, chg_1d, volume, ytd, date, currency}} from Yahoo's batch chart (range=ytd)."""
    out: dict[str, dict] = {}
    results = ((payload or {}).get("spark") or {}).get("result") or [] if isinstance(payload, dict) else []
    for item in results:
        resp = (item.get("response") or [None])[0] or {}
        meta = resp.get("meta") or {}
        price = meta.get("regularMarketPrice")
        if not isinstance(price, (int, float)) or price <= 0:
            continue
        closes = [c for c in ((resp.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [] if c]
        scale = 0.01 if meta.get("currency") == "ZAc" else 1.0          # JSE quotes are in cents
        t = meta.get("regularMarketTime")
        chg = meta.get("regularMarketChangePercent")
        out[item.get("symbol") or meta.get("symbol")] = {
            "price": round(price * scale, 4), "chg_1d": None if chg is None else round(chg / 100, 6),
            "volume": meta.get("regularMarketVolume"),
            "ytd": round(price / closes[0] - 1, 6) if closes else None,
            "date": datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat() if t else None,
            "name": meta.get("longName") or meta.get("shortName")}
    return out


# ── Fetching ──────────────────────────────────────────────────────────────────

def _get(client: httpx.Client, url: str, **kw) -> Optional[httpx.Response]:
    try:
        r = client.get(url, **kw)
        return r if r.status_code == 200 else None
    except httpx.HTTPError as e:
        log.warning("market source unavailable %s: %s", url, e)
        return None


def fetch_exchange(ex: Exchange, client: httpx.Client, today: Optional[date] = None,
                   previous: Optional[list[dict]] = None) -> tuple[list[dict], list[dict]]:
    """(quotes, indices) for one exchange; the index table rides along on every african-markets page."""
    if ex.source == "index_only":
        return [], []
    if ex.source == "use":
        return _use_quotes(client, today or date.today()), []
    if ex.source == "esx":
        r = _get(client, ESX_LISTED)
        return (parse_esx(r.text) if r is not None else []), []
    page = ""
    for wait in (0, 3, 8):                              # the listing site throttles a run of requests
        if wait:
            time.sleep(wait)
        r = _get(client, AM_BASE.format(slug=ex.slug))
        page = r.text if r is not None else ""
        if "tabtable-rs_01k0jris" in page:
            break
    indices = parse_indices(page, today)
    if ex.source == "listing":
        quotes = parse_listing(page, ex, today)
        if ex.key == "ngx":
            quotes = _overlay_ngx(quotes, client)
        if ex.key == "egx":
            quotes = _overlay_yahoo_multiples(quotes, "CAI", ".CA")
        return quotes, indices
    if ex.source == "mystocks":
        r = _get(client, NSE_PRICE_LIST)
        return (parse_mystocks(r.text) if r is not None else []), indices
    return _jse_quotes(page, client, previous), indices


def _spark_all(client: httpx.Client, symbols: list[str]) -> dict[str, dict]:
    """Yahoo batch quotes with the year's closes, 20 symbols a call (its limit), four calls at a time."""
    def batch(chunk: list[str]) -> dict[str, dict]:
        r = _get(client, YAHOO_SPARK, headers=_YAHOO_HEADERS,
                 params={"symbols": ",".join(chunk), "range": "ytd", "interval": "1d"})
        try:
            return parse_spark(r.json()) if r is not None else {}
        except ValueError:
            return {}
    from concurrent.futures import ThreadPoolExecutor
    priced: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for part in pool.map(batch, [symbols[i:i + 20] for i in range(0, len(symbols), 20)]):
            priced.update(part)
    return priced


def yahoo_screen(exchange: str, attempts: int = 3) -> dict[str, dict]:
    """Every equity Yahoo lists on an exchange ("JNB", "CAI"), with shares outstanding, earnings, book value and
    dividends. Yahoo's screener needs a session cookie and crumb, which yfinance manages; it is rate limited, so
    an empty result is expected now and then and callers fall back."""
    try:
        import yfinance as yf
        from yfinance import EquityQuery
    except ImportError:
        return {}
    for attempt in range(attempts):
        out: dict[str, dict] = {}
        try:
            offset = 0
            while True:
                r = yf.screen(EquityQuery("eq", ["exchange", exchange]), offset=offset, size=250,
                              sortField="intradaymarketcap", sortAsc=False)
                rows = r.get("quotes") or []
                out.update({q["symbol"]: q for q in rows if q.get("symbol")})
                offset += len(rows)
                if len(rows) < 250 or offset >= (r.get("total") or 0):
                    return out
        except Exception as e:
            log.info("Yahoo screener %s attempt %s failed: %r", exchange, attempt + 1, e)
            time.sleep(4 * (attempt + 1))
    return {}


def parse_screen_row(row: dict) -> dict:
    """Price, shares, cap and multiples from a Yahoo screener row. JSE prices are in cents while earnings and book
    value are in rand, so multiples are recomputed in one unit and kept only within sane bounds."""
    scale = 0.01 if row.get("currency") in ("ZAc", "ZAC") else 1.0
    major = "ZAR" if scale != 1.0 else row.get("currency")
    price = row.get("regularMarketPrice")
    price = round(price * scale, 4) if isinstance(price, (int, float)) and price > 0 else None
    shares = row.get("sharesOutstanding") if isinstance(row.get("sharesOutstanding"), (int, float)) else None
    same_unit = (row.get("financialCurrency") or major) == major
    eps, book = row.get("epsTrailingTwelveMonths"), row.get("bookValue")
    pe = round(price / eps, 2) if price and same_unit and isinstance(eps, (int, float)) and eps > 0 else None
    pb = round(price / book, 2) if price and same_unit and isinstance(book, (int, float)) and book > 0 else None
    dy = row.get("dividendYield")
    t = row.get("regularMarketTime")
    chg = row.get("regularMarketChangePercent")
    return {
        "name": row.get("longName") or row.get("shortName"), "price": price,
        "chg_1d": round(chg / 100, 6) if isinstance(chg, (int, float)) else None,
        "volume": row.get("regularMarketVolume"),
        "date": datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat() if isinstance(t, (int, float)) and t > 0 else None,
        "shares": shares, "mcap": round(price * shares, 2) if price and shares else None,
        "pe": pe if pe and pe < 200 else None, "pb": pb if pb and pb < 50 else None,
        "dividend_yield": round(dy / 100, 4) if isinstance(dy, (int, float)) and 0 < dy < 30 else None,
    }


def _jse_quotes(page: str, client: httpx.Client, previous: Optional[list[dict]] = None) -> list[dict]:
    """Every JSE equity: Yahoo's screener for the full list with shares and multiples, its batch chart for
    year-to-date. When the screener is rate limited, the previous snapshot's list (with its shares and
    multiples), else the listing page's names."""
    names = {x["symbol"]: x for x in parse_listing_names(page)}
    screened = {k[:-3]: v for k, v in yahoo_screen("JNB").items() if k.endswith(".JO")}
    before = {q["symbol"]: q for q in previous or []}
    symbols = list(screened or before or names)
    priced = _spark_all(client, [f"{s}.JO" for s in symbols])
    quotes = []
    for sym in symbols:
        row = parse_screen_row(screened[sym]) if sym in screened else {}
        spark = priced.get(f"{sym}.JO") or {}
        price = spark.get("price") or row.get("price")
        if not price:
            continue
        q = {"symbol": sym, "name": (names.get(sym) or {}).get("name") or row.get("name") or spark.get("name") or sym,
             "sector": (names.get(sym) or {}).get("sector"), "price": price,
             "chg_1d": spark.get("chg_1d") if spark.get("chg_1d") is not None else row.get("chg_1d"),
             "ytd": spark.get("ytd"), "volume": spark.get("volume") or row.get("volume"),
             "date": spark.get("date") or row.get("date")}
        if not row and sym in before:                   # carried from the last screen, repriced
            old = before[sym]
            q["name"] = (names.get(sym) or {}).get("name") or old.get("name") or q["name"]
            q["sector"] = q["sector"] or old.get("sector")
            row = {"shares": old.get("shares")}
            if old.get("price"):
                ratio = price / old["price"]
                row.update({k: round(old[k] * ratio, 2) for k in ("pe", "pb") if old.get(k)})
                if old.get("dividend_yield"):
                    row["dividend_yield"] = round(old["dividend_yield"] / ratio, 4)
        if row.get("shares"):
            q.update(shares=row["shares"], mcap=round(row["shares"] * price, 2))
        q.update({k: row[k] for k in ("pe", "pb", "dividend_yield") if row.get(k) is not None})
        quotes.append(q)
    return quotes


def _overlay_yahoo_multiples(quotes: list[dict], exchange: str, suffix: str) -> list[dict]:
    """Shares outstanding and multiples from Yahoo's screener for an exchange priced from another source."""
    screened = {k[:-len(suffix)]: parse_screen_row(v) for k, v in yahoo_screen(exchange).items() if k.endswith(suffix)}
    for q in quotes:
        row = screened.get(q["symbol"])
        if not row:
            continue
        if not q.get("shares") and row.get("shares"):
            q.update(shares=row["shares"], mcap=round(row["shares"] * q["price"], 2))
        q.update({k: row[k] for k in ("pe", "pb", "dividend_yield") if row.get(k) is not None})
    return quotes


def parse_use(prices: object, equities_page: str, today: date) -> list[dict]:
    """Uganda: the exchange's delayed-data feed (price, cap, volume) with names from its equities list.
    Government bonds in the feed are left out. The feed carries no trade date: a weekday capture is dated today."""
    names = {}
    for row in re.findall(r"<tr.*?</tr>", equities_page or "", re.S):
        cells = [_text(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)]
        if len(cells) >= 3 and cells[0] and cells[0] != "Counter":
            names[cells[0].upper()] = cells[2]
    day = today if today.weekday() < 5 else today - timedelta(days=today.weekday() - 4)
    out = []
    for r in prices if isinstance(prices, list) else []:
        sym = str(r.get("stock") or "").strip()
        price = r.get("price")
        if r.get("type") != "EQUITY" or not sym or sym.upper().startswith("FXD") or not isinstance(price, (int, float)) or price <= 0:
            continue
        q = {"symbol": sym.upper(), "name": names.get(sym.upper()) or sym.title(), "sector": None, "price": float(price),
             "chg_1d": None, "volume": r.get("volume"), "date": day.isoformat()}
        cap = r.get("market_cap")
        if isinstance(cap, (int, float)) and cap > 0:
            q.update(mcap=float(cap), shares=round(cap / price))
        out.append(q)
    return out


def _use_quotes(client: httpx.Client, today: date) -> list[dict]:
    r = _get(client, USE_PRICES)
    e = _get(client, USE_EQUITIES)
    try:
        return parse_use(r.json() if r is not None else [], e.text if e is not None else "", today)
    except ValueError:
        return []


def parse_esx(page: str) -> list[dict]:
    """Ethiopia: the listed companies (the exchange publishes no daily price list). Listed without a price."""
    out = []
    for row in re.findall(r"<tr.*?</tr>", page or "", re.S):
        cells = [_text(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)]
        if len(cells) >= 3 and cells[0] != "Name" and re.fullmatch(r"[A-Z]{2,8}", cells[1] or ""):
            out.append({"symbol": cells[1], "name": cells[0], "sector": cells[2].replace("Servicess", "Services"),
                        "price": None, "chg_1d": None, "date": None, "listed": cells[3] if len(cells) > 3 else None})
    return out


def _overlay_ngx(quotes: list[dict], client: httpx.Client) -> list[dict]:
    """NGX's own list is the official close and carries volume and value."""
    r = _get(client, NGX_PRICE_LIST)
    try:
        official = parse_ngx_doclib(r.json()) if r is not None else {}
    except ValueError:
        official = {}
    for q in quotes:
        o = official.get(q["symbol"])
        if not o:
            continue
        if o["date"] and (not q.get("date") or o["date"] >= q["date"]):
            if q.get("shares"):
                q["mcap"] = round(q["shares"] * o["price"], 2)
            q["price"], q["date"] = o["price"], o["date"]
            prev = o.get("prev")
            if isinstance(prev, (int, float)) and prev > 0:
                q["chg_1d"] = round(o["price"] / prev - 1, 6)
        q.update({k: o[k] for k in ("volume", "value", "trades") if o.get(k) is not None})
    return quotes


def fetch_fx(client: httpx.Client, today: Optional[date] = None) -> dict:
    """Dollar rates now and on 1 January: {as_of, rates: {NGN: 1353.4}, jan1: {...}, jan1_date}."""
    today = today or date.today()
    out: dict = {"rates": {}, "jan1": {}, "as_of": None, "jan1_date": f"{today.year}-01-01"}
    r = _get(client, FX_LATEST)
    if r is not None:
        try:
            d = r.json()
            out["rates"] = {k: v for k, v in (d.get("rates") or {}).items() if k in _CURRENCIES}
            out["as_of"] = d.get("time_last_update_utc")
        except ValueError:
            pass
    r = _get(client, FX_ON_DATE.format(day=out["jan1_date"]))
    if r is not None:
        try:
            out["jan1"] = {k.upper(): v for k, v in (r.json().get("usd") or {}).items() if k.upper() in _CURRENCIES}
        except ValueError:
            pass
    return out


_CURRENCIES = {e.currency for e in EXCHANGES.values()} | {"USD", "EUR", "GBP", "CNY"}


def build_snapshot(client: Optional[httpx.Client] = None, today: Optional[date] = None,
                   exchanges: Optional[Iterable[str]] = None, previous: Optional[dict] = None) -> dict:
    """Fetch every exchange, the index table and FX. {"quotes": {exchange: [...]}, "indices": [...], "fx": {...},
    "errors": [exchange...]}."""
    today = today or date.today()
    own = client is None
    c = client or _client()
    try:
        quotes: dict[str, list[dict]] = {}
        indices: dict[str, dict] = {}
        errors = []
        def one(key: str) -> tuple[str, list[dict], list[dict]]:
            try:
                return (key, *fetch_exchange(EXCHANGES[key], c, today, ((previous or {}).get("quotes") or {}).get(key)))
            except Exception as e:                      # one exchange's failure never sinks the snapshot
                log.warning("market snapshot failed for %s: %r", key, e)
                return key, [], []
        # Three at a time: Johannesburg's batched quotes take longest, and the listing site throttles bursts.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(one, list(exchanges or EXCHANGES)))
        for key, qs, idx in results:
            for i in idx:
                indices.setdefault(i["exchange"], i)
            if qs:
                quotes[key] = qs
            elif EXCHANGES[key].source != "index_only":
                errors.append(key)
        fx = fetch_fx(c, today)
    finally:
        if own:
            c.close()
    return {"quotes": quotes, "indices": sorted(indices.values(), key=lambda i: i["exchange"]), "fx": fx,
            "errors": errors}


def snapshot_rows(snapshot: dict, captured_at: Optional[datetime] = None) -> list[dict]:
    """Rows for the upsert_market_snapshots RPC: one per exchange's quotes, one for indices, one for FX."""
    captured_at = captured_at or datetime.now(timezone.utc)
    day = captured_at.date().isoformat()
    rows = [{"snapshot_date": day, "kind": "quotes", "scope": ex, "captured_at": captured_at.isoformat(),
             "payload": {"as_of": _latest_date(qs), "rows": qs}} for ex, qs in snapshot["quotes"].items()]
    if snapshot["indices"]:
        rows.append({"snapshot_date": day, "kind": "indices", "scope": "all", "captured_at": captured_at.isoformat(),
                     "payload": {"rows": snapshot["indices"]}})
    if snapshot["fx"].get("rates"):
        rows.append({"snapshot_date": day, "kind": "fx", "scope": "usd", "captured_at": captured_at.isoformat(),
                     "payload": snapshot["fx"]})
    return rows


def from_rows(quote_rows: list[dict], index_rows: list[dict], fx_rows: list[dict]) -> dict:
    """A snapshot from the list_market_snapshots RPC's output (latest row per scope)."""
    quotes = {r["scope"]: (r.get("payload") or {}).get("rows") or [] for r in quote_rows if r.get("scope") in EXCHANGES}
    indices = ((index_rows[0].get("payload") or {}).get("rows") or []) if index_rows else []
    fx = (fx_rows[0].get("payload") or {}) if fx_rows else {}
    captured = max((r.get("captured_at") or "" for r in quote_rows), default=None)
    return {"quotes": quotes, "indices": indices, "fx": fx, "captured_at": captured}


def save_local(snapshot: dict) -> None:
    save_json(SNAPSHOT_PATH, {**snapshot, "captured_at": datetime.now(timezone.utc).isoformat()})


def load_local() -> dict:
    return load_json(SNAPSHOT_PATH, dict) or {"quotes": {}, "indices": [], "fx": {}}


def _latest_date(quotes: list[dict]) -> Optional[str]:
    return max((q["date"] for q in quotes if q.get("date")), default=None)


# ── Derived views ─────────────────────────────────────────────────────────────

def _usd(amount: Optional[float], currency: str, rates: dict) -> Optional[float]:
    rate = rates.get(currency)
    return round(amount / rate, 2) if amount and rate else None


def enrich(snapshot: dict, today: Optional[date] = None) -> list[dict]:
    """Every quote with exchange, country, currency, staleness, dollar market cap and dollar year-to-date."""
    today = today or date.today()
    fx = snapshot.get("fx") or {}
    rates, jan1 = fx.get("rates") or {}, fx.get("jan1") or {}
    out = []
    for key, quotes in (snapshot.get("quotes") or {}).items():
        ex = EXCHANGES.get(key)
        if not ex:
            continue
        for q in quotes:
            age = None
            if q.get("date"):
                try:
                    age = (today - date.fromisoformat(q["date"])).days
                except ValueError:
                    pass
            ytd_usd = None
            if q.get("ytd") is not None and rates.get(ex.currency) and jan1.get(ex.currency):
                ytd_usd = round((1 + q["ytd"]) * jan1[ex.currency] / rates[ex.currency] - 1, 6)
            row = {**q, "exchange": ex.key, "exchange_name": ex.name, "country": ex.country,
                   "currency": ex.currency, "age_days": age, "stale": age is None or age > STALE_DAYS,
                   "mcap_usd": _usd(q.get("mcap"), ex.currency, rates), "ytd_usd": ytd_usd,
                   "value_traded": q.get("value") or (q["volume"] * q["price"] if q.get("volume") and q.get("price") else None)}
            row["value_traded_usd"] = _usd(row["value_traded"], ex.currency, rates)
            if (row["mcap_usd"] or 0) > MAX_CAP_USD:
                # Larger than any share whose home is one of these exchanges: a table error (EGX's shares column
                # sometimes holds the cap) or a foreign group's worldwide cap on a secondary listing.
                row.update(mcap=None, shares=None, mcap_usd=None, cap_note="implausible market cap withheld")
            if q.get("ytd") is not None and q["ytd"] <= SUSPECT_YTD:
                row["ytd_suspect"] = True
            out.append(row)
    _mark_cross_listings(out)
    return out


# A loss this large in under a year is more often a split or bonus issue the table has not adjusted for (NMB
# Tanzania, Sonatel); such a figure is shown with a flag and left out of exchange and sector returns.
SUSPECT_YTD = -0.6
MAX_CAP_USD = 40e9
# Where a company listed on several of these exchanges has its primary listing.
_HOME_ORDER = ("jse", "nse", "ngx", "egx", "bvc", "gse", "brvm", "sem", "bvmt", "zse", "bse", "luse", "dse", "mse",
               "nsx", "rse", "use")
_STRICT_NOISE = re.compile(r"(?i)\b(plc|ltd|limited|holdings?|group|share\s+company|company|co|corporation|corp|inc|the)\b\.?")


def _strict_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _STRICT_NOISE.sub(" ", (name or "").lower().replace("&", " and "))).strip()


def _mark_cross_listings(rows: list[dict]) -> None:
    """Mark the secondary listings of a company listed on several exchanges (Equity Group in Nairobi, Kigali and
    Dar es Salaam); their caps are the group's, so exchange and sector totals count the primary listing only."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        k = _strict_key(r.get("name") or "")
        if k:
            groups.setdefault(k, []).append(r)
    for listings in groups.values():
        if len({r["exchange"] for r in listings}) < 2:
            continue
        # The primary listing is where the shares trade most (Oando in Lagos, not Johannesburg); without
        # turnover on both sides, the larger exchange.
        traded = [r for r in listings if r.get("value_traded_usd")]
        home = (max(traded, key=lambda r: r["value_traded_usd"]) if len(traded) >= 2 else
                min(listings, key=lambda r: _HOME_ORDER.index(r["exchange"]) if r["exchange"] in _HOME_ORDER else 99))
        for r in listings:
            if r["exchange"] != home["exchange"]:
                r["secondary_of"] = home["exchange"]


def _cap_weighted(rows: list[dict], field: str) -> Optional[float]:
    """Cap-weighted return: today's total cap against the total cap each return started from."""
    now = start = 0.0
    for r in rows:
        ret, cap = r.get(field), r.get("mcap_usd") if field.endswith("_usd") else r.get("mcap")
        if ret is None or not cap or ret <= -1 or r.get("secondary_of") or (field.startswith("ytd") and r.get("ytd_suspect")):
            continue
        now += cap
        start += cap / (1 + ret)
    return round(now / start - 1, 6) if start else None


def _median(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return round(statistics.median(vals), 6) if vals else None


def overview(snapshot: dict, today: Optional[date] = None, movers: int = 8) -> dict:
    """Exchange tiles, currency moves, top movers, most traded and sector moves for the markets home page."""
    today = today or date.today()
    rows = enrich(snapshot, today)
    fresh = [r for r in rows if not r["stale"]]
    fx = snapshot.get("fx") or {}
    rates, jan1 = fx.get("rates") or {}, fx.get("jan1") or {}
    indices = {i["exchange"]: i for i in snapshot.get("indices") or []}

    tiles = []
    for ex in EXCHANGES.values():
        own = [r for r in rows if r["exchange"] == ex.key]
        live = [r for r in own if not r["stale"]]
        idx = indices.get(ex.key)
        if not own and not idx:
            continue
        caps = [r["mcap_usd"] for r in own if r.get("mcap_usd") and not r.get("secondary_of")]
        fx_ytd = (jan1[ex.currency] / rates[ex.currency] - 1) if rates.get(ex.currency) and jan1.get(ex.currency) else None
        tiles.append({
            "exchange": ex.key, "name": ex.name, "country": ex.country, "currency": ex.currency,
            "index": idx and {"name": idx["name"], "level": idx["level"], "chg_1d": idx["chg_1d"], "date": idx["date"]},
            "listed": len(own), "priced_today": len(live),
            "advancers": sum(1 for r in live if (r.get("chg_1d") or 0) > 0),
            "decliners": sum(1 for r in live if (r.get("chg_1d") or 0) < 0),
            "mcap_usd": round(sum(caps), 2) if caps else None, "mcap_coverage": len(caps),
            "ytd_local": _cap_weighted(live, "ytd"), "ytd_usd": _cap_weighted(live, "ytd_usd"),
            # Johannesburg and Nairobi carry no cap column; their typical share's move stands in.
            "ytd_median_local": _median(r.get("ytd") for r in live if not r.get("ytd_suspect")),
            "ytd_median_usd": _median(r.get("ytd_usd") for r in live if not r.get("ytd_suspect")),
            "currency_ytd_vs_usd": None if fx_ytd is None else round(fx_ytd, 6),
            "as_of": _latest_date(own) or (idx and idx["date"]),
            "stale": not live,
        })
    tiles.sort(key=lambda t: -(t["mcap_usd"] or 0))

    # Movers among shares worth tracking: a known cap of at least $10m, or any NSE/JSE share (no cap column).
    # Primary listings only: a secondary line (Old Mutual in Blantyre) moves on thin trade.
    tradable = [r for r in fresh if r.get("chg_1d") is not None and not r.get("secondary_of")
                and ((r.get("mcap_usd") or 0) >= 1e7 or r.get("mcap_usd") is None)]

    def slim(r: dict) -> dict:
        return {k: r.get(k) for k in ("exchange", "symbol", "name", "sector", "price", "currency", "chg_1d", "ytd",
                                      "ytd_usd", "mcap_usd", "volume", "value_traded", "date")}
    gainers = sorted((r for r in tradable if r["chg_1d"] > 0), key=lambda r: -r["chg_1d"])[:movers]
    losers = sorted((r for r in tradable if r["chg_1d"] < 0), key=lambda r: r["chg_1d"])[:movers]
    active = sorted((r for r in fresh if r.get("value_traded") and not r.get("secondary_of")),
                    key=lambda r: -(_usd(r["value_traded"], r["currency"], rates) or 0))[:movers]

    currencies = []
    for cur in sorted({e.currency for e in EXCHANGES.values()}):
        if rates.get(cur):
            ytd = (jan1[cur] / rates[cur] - 1) if jan1.get(cur) else None
            currencies.append({"currency": cur, "per_usd": rates[cur], "jan1_per_usd": jan1.get(cur),
                               "ytd_vs_usd": None if ytd is None else round(ytd, 6)})
    currencies.sort(key=lambda c: c["ytd_vs_usd"] if c["ytd_vs_usd"] is not None else 0)

    return {"exchanges": tiles, "gainers": [slim(r) for r in gainers], "losers": [slim(r) for r in losers],
            "most_traded": [{**slim(r), "value_traded_usd": _usd(r["value_traded"], r["currency"], rates)} for r in active],
            "sectors": sectors(rows), "currencies": currencies,
            "coverage": {"exchanges": len(tiles), "shares": len(rows), "priced_today": len(fresh),
                         "with_market_cap": sum(1 for r in rows if r.get("mcap_usd"))},
            "fx_as_of": fx.get("as_of"), "captured_at": snapshot.get("captured_at"),
            "method": f"Quotes older than {STALE_DAYS} days are stale and excluded from returns and movers. Exchange "
                      "returns are weighted by market cap over the shares with a cap and a year-to-date figure; "
                      "dollar returns apply the change in the currency's dollar rate since 1 January."}


# The sources label sectors differently (ICB groups, JSE sub-sectors, myStocks' NSE segments); each label is
# mapped to one of twelve groups by its first matching keyword. Funds and unlabelled rows have no sector.
_SECTOR_RULES = (
    (None, r"#n/a|^-$|\betf\b|exchange traded|closed.end"),
    ("Real Estate", r"real estate|reit"),
    ("Financials", r"financ|bank|insur|investment|microfinance|lending|asset manag"),
    ("Telecom", r"telecom|telecommunication"),
    ("Technology", r"technolog|software|computer|\bict\b|media"),
    ("Oil & Gas", r"oil|gas|petroleum"),
    ("Utilities", r"utilit|electricity|power"),
    ("Health Care", r"health|pharma|biotech|medical"),
    ("Agriculture", r"agricult|plantation|forestry"),
    ("Basic Materials", r"basic material|chemical|mining|metal|paper"),
    ("Consumer Goods", r"consumer goods|beverage|food producer|tobacco|personal goods|household|brew"),
    ("Consumer Services", r"consumer services|retail|travel|leisure|hotel|commercial and services|education"),
    ("Industrials", r"industr|construction|engineering|transport|support services|electronic|automobile|"
                    r"manufactur|cement|logistic"),
)
SECTORS = [name for name, _ in _SECTOR_RULES if name]


def _sector(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    label = name.strip().lower()
    for group, pattern in _SECTOR_RULES:
        if re.search(pattern, label):
            return group
    return name.strip()


def sectors(rows: list[dict]) -> list[dict]:
    """Cap-weighted 1-day and dollar year-to-date moves by sector, over fresh quotes with a cap."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        s = _sector(r.get("sector"))
        if s and not r["stale"] and not r.get("secondary_of"):
            groups.setdefault(s, []).append(r)
    out = []
    for s, rs in groups.items():
        capped = [r for r in rs if r.get("mcap_usd")]
        one_day = [r.get("chg_1d") for r in rs if r.get("chg_1d") is not None]
        out.append({"sector": s, "shares": len(rs), "mcap_usd": round(sum(r["mcap_usd"] for r in capped), 2) or None,
                    "chg_1d": _weighted_1d(capped) if capped else (round(statistics.median(one_day), 6) if one_day else None),
                    "ytd_usd": _cap_weighted(capped, "ytd_usd")})
    return sorted(out, key=lambda x: -(x["mcap_usd"] or 0))


def _weighted_1d(rows: list[dict]) -> Optional[float]:
    num = den = 0.0
    for r in rows:
        if r.get("chg_1d") is not None and r.get("mcap_usd"):
            num += r["chg_1d"] * r["mcap_usd"]
            den += r["mcap_usd"]
    return round(num / den, 6) if den else None


_SORTS = {"mcap": lambda r: -(r.get("mcap_usd") or 0), "chg_1d": lambda r: -(r.get("chg_1d") or -9),
          "ytd": lambda r: -(r.get("ytd_usd") if r.get("ytd_usd") is not None else -9),
          "value": lambda r: -(r.get("value_traded_usd") or 0), "name": lambda r: (r.get("name") or "").lower(),
          "pe": lambda r: r.get("pe") or 1e9, "dividend": lambda r: -(r.get("dividend_yield") or 0)}


def screener(snapshot: dict, exchange: Optional[str] = None, sector: Optional[str] = None,
             min_mcap_usd: Optional[float] = None, q: Optional[str] = None, include_stale: bool = False,
             sort: str = "mcap", limit: int = 100, today: Optional[date] = None) -> dict:
    """Filtered, sorted shares across every exchange."""
    every = enrich(snapshot, today)
    rows = every
    if exchange:
        rows = [r for r in rows if r["exchange"] == exchange]
    if sector:
        rows = [r for r in rows if (_sector(r.get("sector")) or "").lower() == sector.lower()]
    if min_mcap_usd:
        rows = [r for r in rows if (r.get("mcap_usd") or 0) >= min_mcap_usd]
    if not include_stale:
        rows = [r for r in rows if not r["stale"]]
    if q:
        rows = [r for _, r in search_rows(rows, q)]
    for r in rows:
        r["sector"] = _sector(r.get("sector")) or r.get("sector")
    total = len(rows)
    rows = sorted(rows, key=_SORTS.get(sort, _SORTS["mcap"])) if not q else rows
    return {"total": total, "rows": rows[:limit],
            "sectors": sorted({s for s in (_sector(r.get("sector")) for r in every) if s})}


# ── Name and symbol search ────────────────────────────────────────────────────

_NAME_NOISE = re.compile(r"(?i)\b(plc|ltd|limited|holdings?|group|share\s+company|company|co|corporation|corp|s\.?a\.?|inc|the|"
                         r"nigeria|kenya|ghana|egypt|tanzania|uganda|zambia|malawi|namibia|rwanda|botswana|"
                         r"mauritius|zimbabwe|morocco|tunisia|maroc)\b\.?")


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _NAME_NOISE.sub(" ", (name or "").lower().replace("&", " and "))).strip()


def search_rows(rows: list[dict], q: str) -> list[tuple[float, dict]]:
    """Rows matching a company name or symbol, best first: exact symbol, exact name, name prefix, all words."""
    query = (q or "").strip()
    if not query:
        return []
    qk, qs, qstrict = _key(query), query.upper().split(".")[0], _strict_key(query)
    words = qk.split()
    scored = []
    for r in rows:
        nk = _key(r.get("name") or "")
        if r.get("symbol") == qs:
            score = 1.0
        elif qstrict and _strict_key(r.get("name") or "") == qstrict:
            score = 0.97                                # "MTN Group" is MTN Group, not MTN Ghana
        elif nk and nk == qk:
            score = 0.95
        elif nk and qk and (nk.startswith(qk + " ") or qk.startswith(nk + " ")):
            score = 0.85
        elif words and all(re.search(r"\b" + re.escape(w), nk) for w in words):
            score = 0.7
        else:
            continue
        # Break ties toward the larger, fresher listing (a share listed on two exchanges).
        scored.append((score + min((r.get("mcap_usd") or 0) / 1e12, 0.01) - (0.02 if r.get("stale") else 0), r))
    return sorted(scored, key=lambda x: -x[0])


def search(snapshot: dict, q: str, limit: int = 10, today: Optional[date] = None) -> list[dict]:
    return [{**r, "match": round(s, 3)} for s, r in search_rows(enrich(snapshot, today), q)[:limit]]


def resolve(snapshot: dict, name: str, country: Optional[str] = None, today: Optional[date] = None) -> Optional[dict]:
    """The listing a company name refers to, when one matches confidently (exact symbol, name or prefix)."""
    rows = enrich(snapshot, today)
    if country:
        rows = [r for r in rows if r["country"] == country.upper()] or rows
    hits = search_rows(rows, name)
    return hits[0][1] if hits and hits[0][0] >= 0.85 else None


def quote(snapshot: dict, exchange: str, symbol: str, today: Optional[date] = None) -> Optional[dict]:
    sym = symbol.upper().split(".")[0]
    return next((r for r in enrich(snapshot, today) if r["exchange"] == exchange and r["symbol"] == sym), None)


# ── Private to public ─────────────────────────────────────────────────────────

# The listed sector a private company's deal sector trades in.
DEAL_SECTOR_TO_LISTED = {
    "fintech": "Financials", "banking": "Financials", "insurance": "Financials", "energy": "Utilities",
    "oil_gas": "Oil & Gas", "mining": "Basic Materials", "telecom": "Telecom", "agriculture": "Agriculture",
    "healthcare": "Health Care", "logistics": "Industrials", "mobility": "Industrials",
    "ecommerce_retail": "Consumer Services", "real_estate": "Real Estate", "infrastructure": "Industrials",
    "education": "Consumer Services", "media_tech": "Technology", "manufacturing": "Industrials",
    "hospitality": "Consumer Services",
}
_MIN_PEERS = 5


def valuation_bridge(snapshot: dict, valuation_usd: Optional[float], deal_sector: Optional[str],
                     country: Optional[str], announced: Optional[str] = None, today: Optional[date] = None) -> Optional[dict]:
    """Where a private valuation mark sits among listed companies in its sector: the peers' caps (in the
    company's country when it has enough of them, else across Africa), the mark's rank among them, and how the
    peer group has moved in dollars this year. A reference point for a mark, not a revaluation."""
    sector = DEAL_SECTOR_TO_LISTED.get(deal_sector or "")
    if not valuation_usd or not sector:
        return None
    rows = [r for r in enrich(snapshot, today) if _sector(r.get("sector")) == sector and r.get("mcap_usd")
            and not r["stale"] and not r.get("secondary_of")]
    local = [r for r in rows if country and r["country"] == country.upper()]
    peers, scope = (local, "country") if len(local) >= _MIN_PEERS else (rows, "africa")
    if len(peers) < _MIN_PEERS:
        return None
    caps = sorted(r["mcap_usd"] for r in peers)
    below = sum(1 for c in caps if c < valuation_usd)
    ytd = _cap_weighted(peers, "ytd_usd")
    top = sorted(peers, key=lambda r: -r["mcap_usd"])[:5]
    return {
        "sector": sector, "scope": scope, "country": country if scope == "country" else None,
        "peers": len(peers), "valuation_usd": valuation_usd, "announced": announced,
        "rank_percentile": round(below / len(caps), 3), "larger_than": below,
        "peer_median_cap_usd": round(statistics.median(caps), 2),
        "peer_ytd_usd": ytd,
        "largest_peers": [{k: r.get(k) for k in ("exchange", "symbol", "name", "mcap_usd", "ytd_usd")} for r in top],
        "note": "Listed caps are equity values on today's prices; a private mark is a negotiated price at the date "
                "of the round, often with preference terms. The comparison places the mark, it does not revalue it.",
    }


def fill_daily_change(snapshot: dict, previous: dict) -> int:
    """A 1-day change for quotes whose source gives none (Uganda), from the previous stored close."""
    filled = 0
    for key, quotes in (snapshot.get("quotes") or {}).items():
        before = {q["symbol"]: q for q in (previous.get("quotes") or {}).get(key) or []}
        for q in quotes:
            p = before.get(q["symbol"])
            if (q.get("chg_1d") is None and q.get("price") and p and p.get("price")
                    and (p.get("date") or "") < (q.get("date") or "")):
                q["chg_1d"] = round(q["price"] / p["price"] - 1, 6)
                filled += 1
    return filled
