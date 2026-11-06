"""Second sources for exchange prices, used automatically when the primary listing site fails.

Every exchange has an ordered list of vetted, credible sources: the exchange's own website first, then reputable
market-data sites. When the primary source returns nothing, each alternative is tried in turn and the first one
that passes two checks is used:

  * coverage: it prices a meaningful share of the companies already known for that exchange;
  * agreement: its prices broadly agree with the last known ones (the median move is within a factor of two), so
    a page in the wrong units, a different instrument list or a garbled table can never be published as prices.

Sources are never discovered at run time: a market price taken from an unvetted site could be wrong, delayed or
fabricated and would be shown as fact. The daily health check (scripts/check_price_sources.py) reports any
source that stops answering so it can be replaced.

Each source returns {symbol: {price, date, chg_1d?, volume?, value?, prev?}}; the last known list of companies
is then repriced (names, sectors and shares outstanding carry over; market cap and year-to-date move with the
price). Companies a source does not price keep their old figures and date, so they still read as stale.
"""
from __future__ import annotations

import html as html_mod
import logging
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

import httpx

log = logging.getLogger(__name__)

_FR_MONTHS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
              "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12}
_EN_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
     "december"], 1)}


def _num(text: object) -> Optional[float]:
    """'4 175', '8,849.88', '0,15', '1 234,5' -> float."""
    if text is None:
        return None
    s = html_mod.unescape(str(text)).replace("\xa0", " ").replace(" ", " ").strip()
    s = re.sub(r"<[^>]+>", "", s).replace("%", "").replace(" ", "")
    if not s or s in {"-", "--"}:
        return None
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if re.fullmatch(r"-?\d+,\d{1,2}", s) else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def latest_session(today: date, now: Optional[datetime] = None, close_utc_hour: int = 16) -> str:
    """The latest trading day whose session has closed: today after the close on a weekday, else the weekday
    before. Used only for sources that publish no date of their own."""
    now = now or datetime.now(timezone.utc)
    d = today if (now.date() > today or now.hour >= close_utc_hour) else today - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def _get(client: httpx.Client, url: str, **kw) -> Optional[httpx.Response]:
    """GET with one retry after a connection error or timeout: exchange sites are often slow or flaky."""
    for attempt in (1, 2):
        try:
            r = client.get(url, **kw)
            return r if r.status_code == 200 and r.text else None
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as e:
            log.info("price source %s attempt %d failed: %s", url, attempt, type(e).__name__)
        except httpx.HTTPError as e:
            log.info("price source %s unavailable: %s", url, type(e).__name__)
            return None
    return None


# ── Sources ───────────────────────────────────────────────────────────────────

def ngx_official(client: httpx.Client, today: date) -> dict[str, dict]:
    """Nigerian Exchange: NGX's own daily equities list (official close, volume, value)."""
    from src.engines.markets import NGX_PRICE_LIST, parse_ngx_doclib
    r = _get(client, NGX_PRICE_LIST)
    try:
        rows = parse_ngx_doclib(r.json()) if r is not None else {}
    except ValueError:
        return {}
    out = {}
    for sym, o in rows.items():
        prev = o.get("prev")
        out[sym] = {"price": o["price"], "date": o.get("date"), "volume": o.get("volume"), "value": o.get("value"),
                    "chg_1d": round(o["price"] / prev - 1, 6) if isinstance(prev, (int, float)) and prev > 0 else None}
    return out


_BRVM_ROW = re.compile(
    r"<tr><td>([A-Z]{3,6})</td><td>([^<]+)</td>"
    r'<td class="text-right">([^<]*)</td><td class="text-right">([^<]*)</td>'
    r'<td class="text-right">([^<]*)</td><td class="text-right">([^<]*)</td>'
    r'<td class="text-right"><span[^>]*>([^<]*)</span>')
_BRVM_DATE = re.compile(r"mise à jour\s*:\s*\w+,\s*(\d{1,2})\s+([a-zéû]+),?\s+(\d{4})", re.I)


def parse_brvm_official(page: str) -> dict[str, dict]:
    m = _BRVM_DATE.search(page)
    day = None
    if m and m.group(2).lower() in _FR_MONTHS:
        day = date(int(m.group(3)), _FR_MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
    out = {}
    for sym, name, vol, prev, _open, close, var in _BRVM_ROW.findall(page):
        price = _num(close)
        if not price or price <= 0:
            continue
        chg = _num(var)
        out[sym] = {"price": price, "date": day, "name": html_mod.unescape(name).strip(), "volume": _num(vol),
                    "prev": _num(prev), "chg_1d": round(chg / 100, 6) if chg is not None else None}
    return out if day else {}


def brvm_official(client: httpx.Client, today: date) -> dict[str, dict]:
    """BRVM: the exchange's own share price page (previous close, close, change, volume, update time)."""
    r = _get(client, "https://www.brvm.org/fr/cours-actions/0")
    return parse_brvm_official(r.text) if r is not None else {}


_SIKA_ROW = re.compile(
    r'<td class="allf"><a href="/marches/cotation_([A-Z]{3,6})\.[a-z]{2}">([^<]+)</a></td>\s*'
    r"<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*"
    r'<td><b>([^<]*)</b></td>\s*<td class="[^"]*">([^<]*)</td>')


def parse_sikafinance(page: str, day: str) -> dict[str, dict]:
    out = {}
    for sym, name, _open, _high, _low, vol, value, last, var in _SIKA_ROW.findall(page):
        price = _num(last)
        if not price or price <= 0:
            continue
        chg = _num(var)
        out[sym] = {"price": price, "date": day, "name": html_mod.unescape(name).strip(), "volume": _num(vol),
                    "value": _num(value), "chg_1d": round(chg / 100, 6) if chg is not None else None}
    return out


def sikafinance_brvm(client: httpx.Client, today: date) -> dict[str, dict]:
    """BRVM: sikafinance.com's list of every quoted share (an established West African market-data site)."""
    r = _get(client, "https://www.sikafinance.com/marches/aaz")
    return parse_sikafinance(r.text, latest_session(today, close_utc_hour=16)) if r is not None else {}


def parse_gse_rows(rows: list) -> dict[str, dict]:
    """Rows of the Ghana Stock Exchange's daily trading table: [id, dd/mm/yyyy, code, year high, year low,
    previous close (VWAP), open, last trade, closing price (VWAP), change, bid, offer, volume, value]."""
    parsed = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, list) or len(r) < 14:
            continue
        try:
            day = datetime.strptime(r[1], "%d/%m/%Y").date().isoformat()
        except (TypeError, ValueError):
            continue
        price = _num(r[8]) or _num(r[7])
        if not price or price <= 0:
            continue
        prev = _num(r[5])
        code = re.sub(r"[^A-Z0-9]", "", str(r[2]).upper())   # the table flags some codes with asterisks
        parsed.append((day, code, {
            "price": price, "date": day, "prev": prev, "volume": _num(r[12]), "value": _num(r[13]),
            "chg_1d": round(price / prev - 1, 6) if prev else None}))
    if not parsed:
        return {}
    latest = max(day for day, _, _ in parsed)
    return {sym: q for day, sym, q in parsed if day == latest}


def gse_official(client: httpx.Client, today: date) -> dict[str, dict]:
    """Ghana Stock Exchange: the exchange's own daily trading table (closing VWAP price, volume, value)."""
    page = _get(client, "https://gse.com.gh/trading-and-data/")
    m = re.search(r'id="wdtNonceFrontendEdit_39"[^>]*value="([0-9a-f]+)"', page.text) if page is not None else None
    if not m:
        return {}
    form = {"draw": "1", "start": "0", "length": "120", "wdtNonce": m.group(1),
            "order[0][column]": "0", "order[0][dir]": "desc"}
    for i in range(14):
        form.update({f"columns[{i}][data]": str(i), f"columns[{i}][orderable]": "true"})
    try:
        r = client.post("https://gse.com.gh/wp-admin/admin-ajax.php?action=get_wdtable&table_id=39", data=form)
        return parse_gse_rows(r.json().get("data")) if r.status_code == 200 else {}
    except (httpx.HTTPError, ValueError, AttributeError):
        return {}


_DSE_TICK = re.compile(r'font-bold text-white">([A-Z][A-Z0-9-]{1,11})</span><span class="[^"]*tabular-nums">([\d,.]+)</span>'
                       r'(?:<span[^>]*>(?:<svg.*?</svg>|<span[^>]*></span>)?(-?[\d.]+)<!-- -->%)?', re.S)


def parse_dse(page: str, day: str) -> dict[str, dict]:
    """The exchange's live ticker; it carries no date of its own, so it is dated by the last completed session."""
    out = {}
    for sym, price, chg in _DSE_TICK.findall(page):
        p = _num(price)
        if p and p > 0 and sym not in out:
            c = _num(chg)
            out[sym] = {"price": p, "date": day, "chg_1d": round(c / 100, 6) if c is not None else None}
    return out


def dse_official(client: httpx.Client, today: date) -> dict[str, dict]:
    """Dar es Salaam Stock Exchange: the exchange's own market ticker."""
    r = _get(client, "https://dse.co.tz/")
    return parse_dse(r.text, latest_session(today, close_utc_hour=13)) if r is not None else {}


_MSE_TICK = re.compile(r'<div class="ticker__item">\s*<span>([A-Z][A-Z0-9]{1,9})</span>\s*'
                       r'<span class="pricedata[^"]*">([\d,.]+)</span>')
_MSE_DATE = re.compile(r"Stats as at (\d{1,2}) ([A-Za-z]+) (\d{4})")


def parse_mse(page: str) -> dict[str, dict]:
    m = _MSE_DATE.search(page)
    if not m or m.group(2).lower() not in _EN_MONTHS:
        return {}
    day = date(int(m.group(3)), _EN_MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
    out = {}
    for sym, price in _MSE_TICK.findall(page):
        p = _num(price)
        if p and p > 0 and sym not in out:
            out[sym] = {"price": p, "date": day}
    return out


def mse_official(client: httpx.Client, today: date) -> dict[str, dict]:
    """Malawi Stock Exchange: the exchange's own price ticker and its 'Stats as at' date."""
    r = _get(client, "https://www.mse.co.mw/")
    return parse_mse(r.text) if r is not None else {}


_RSE_ROW = re.compile(r'<span class="security-name">([^<]+)</span>\s*([A-Z0-9]{2,8})</td>\s*<td>([^<]*)</td>\s*'
                      r"<td>([^<]*)</td>\s*<td>.*?</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>", re.S)


def parse_rse(page: str, day: str) -> dict[str, dict]:
    """Rwanda Stock Exchange market table: Securities, Closing, Previous, Change, Volume, Value."""
    out = {}
    for name, sym, close, prev, vol, value in _RSE_ROW.findall(page):
        p, pv = _num(close), _num(prev)
        if p and p > 0:
            out[sym] = {"price": p, "date": day, "name": html_mod.unescape(name).strip(), "prev": pv,
                        "volume": _num(vol), "value": _num(value),
                        "chg_1d": round(p / pv - 1, 6) if pv else None}
    return out


def rse_official(client: httpx.Client, today: date) -> dict[str, dict]:
    """Rwanda Stock Exchange: the exchange's own market table."""
    r = _get(client, "https://www.rse.rw/")
    return parse_rse(r.text, latest_session(today, close_utc_hour=11)) if r is not None else {}


# Ordered, vetted sources per exchange (used when the primary listing site fails), and the codes a source spells
# differently from the stored list.
SOURCES: dict[str, list[tuple[str, Callable[[httpx.Client, date], dict[str, dict]]]]] = {
    "ngx": [("NGX official list", ngx_official)],
    "brvm": [("BRVM official", brvm_official), ("sikafinance", sikafinance_brvm)],
    "gse": [("GSE official", gse_official)],
    "dse": [("DSE official", dse_official)],
    "mse": [("MSE official", mse_official)],
    "rse": [("RSE official", rse_official)],
}
ALIASES: dict[str, dict[str, str]] = {
    "rse": {"BOK": "BK", "BLR": "BRL"},
    "mse": {"NBS": "NBSMW"},
}


# ── Repricing ─────────────────────────────────────────────────────────────────

def reprice(previous: list[dict], priced: dict[str, dict], source: str,
            aliases: Optional[dict[str, str]] = None) -> tuple[list[dict], str]:
    """(rows, verdict). Rows are the previous list repriced from `priced`; the verdict is "ok" or why the source
    was rejected (too few known companies priced, or prices that disagree with the last known ones)."""
    aliases = aliases or {}
    priced = {aliases.get(sym, sym): q for sym, q in priced.items()}
    known = {q["symbol"]: q for q in previous if q.get("symbol") and isinstance(q.get("price"), (int, float))}
    matched = [s for s in priced if s in known and known[s]["price"] > 0]
    needed = max(2, -(-len(known) // 3))                # at least a third of the known companies, and two
    if len(matched) < min(needed, len(known)):
        return [], f"priced {len(matched)} of {len(known)} known companies"
    ratios = [priced[s]["price"] / known[s]["price"] for s in matched]
    median = statistics.median(ratios)
    if not 0.5 <= median <= 2.0:
        return [], f"prices disagree with the last known ones (median ratio {median:.2f})"
    rows = []
    for sym, old in known.items():
        q = dict(old)
        new = priced.get(sym)
        if new and new.get("date") and (not old.get("date") or new["date"] >= old["date"]):
            ratio = new["price"] / old["price"]
            if not 0.2 <= ratio <= 5.0:                 # one implausible jump: keep the old row, stale
                rows.append(q)
                continue
            q.update({"price": new["price"], "date": new["date"], "source": source})
            for k in ("chg_1d", "volume", "value"):
                if new.get(k) is not None:
                    q[k] = new[k]
            if q.get("shares"):
                q["mcap"] = round(q["shares"] * new["price"], 2)
            elif isinstance(q.get("mcap"), (int, float)):
                q["mcap"] = round(q["mcap"] * ratio, 2)
            if isinstance(q.get("ytd"), (int, float)) and str(old.get("date") or "")[:4] == new["date"][:4]:
                q["ytd"] = round((1 + q["ytd"]) * ratio - 1, 6)
            elif str(old.get("date") or "")[:4] != new["date"][:4]:
                q.pop("ytd", None)
        rows.append(q)
    return rows, "ok"


def fallback(exchange: str, previous: Optional[list[dict]], client: httpx.Client,
             today: Optional[date] = None) -> tuple[list[dict], Optional[str], list[str]]:
    """(rows, source used or None, notes on each source tried) for an exchange whose primary source failed."""
    today = today or date.today()
    notes: list[str] = []
    if not previous:
        return [], None, ["no previous list to reprice"]
    for name, fetch in SOURCES.get(exchange, []):
        try:
            priced = fetch(client, today)
        except Exception as e:                          # a broken source never stops the snapshot
            notes.append(f"{name}: {type(e).__name__}")
            continue
        if not priced:
            notes.append(f"{name}: no prices")
            continue
        rows, verdict = reprice(previous, priced, name, ALIASES.get(exchange))
        notes.append(f"{name}: {verdict}")
        if rows:
            log.warning("market snapshot: %s priced from %s (%s)", exchange, name, verdict)
            return rows, name, notes
    return [], None, notes
