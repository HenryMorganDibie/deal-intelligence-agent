"""
Prices for African listings Yahoo Finance does not carry (NGX, NSE Kenya).

Yahoo returns nothing for Nigerian (.LG) or Kenyan (.NR) symbols, so price-based
outcomes need the exchanges' own data:

  * NGX: the daily equities price list and each stock's last ~20 trading days
    (NGX data service), and the All-Share Index back to 1996.
  * NSE Kenya: the daily market price list, including the NSE All-Share Index
    (^NASI), from myStocks (NSE's own site sits behind a captcha).

Neither exchange publishes free per-stock history further back, so a daily
snapshot of both price lists is kept (locally in data/african_prices.json; the
hosted app keeps it in Supabase). Price moves read the snapshot first, then the
exchange's recent-history endpoint.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

import httpx

from src.utils.paths import DATA_DIR
from src.utils.storage import load_json, save_json

log = logging.getLogger(__name__)

SNAPSHOT_PATH = DATA_DIR / "african_prices.json"

NGX_PRICE_LIST = "https://doclib.ngxgroup.com/REST/api/statistics/equities/?market=&sector=&orderby=&pageSize=500&pageNo=0"
NGX_WIDGETS = "https://ngxgroup.com/wp-json/ngx-data-widgets/v1/"
NSE_PRICE_LIST = "https://live.mystocks.co.ke/m/pricelist"

# Benchmark series names inside the snapshot.
NGX_INDEX = "^ASI"
NSE_INDEX = "^NASI"

_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            "Accept": "application/json, text/html"}


def _client() -> httpx.Client:
    return httpx.Client(timeout=30, follow_redirects=True, headers=_HEADERS)


def market_of(symbol: str) -> Optional[str]:
    s = symbol.upper()
    if s.endswith(".LG") or s == NGX_INDEX:
        return "ngx"
    if s.endswith(".NR") or s == NSE_INDEX:
        return "nse"
    return None


def _code(symbol: str) -> str:
    return symbol.upper().rsplit(".", 1)[0] if "." in symbol else symbol.upper()


# ── Fetchers ──────────────────────────────────────────────────────────────────

def fetch_ngx_price_list(client: Optional[httpx.Client] = None) -> tuple[Optional[str], dict[str, float]]:
    """(trade date, {symbol: close}) for every NGX equity."""
    c = client or _client()
    try:
        rows = c.get(NGX_PRICE_LIST).json()
    except Exception as e:
        log.warning("NGX price list unavailable: %s", e)
        return None, {}
    prices: dict[str, float] = {}
    day = None
    for r in rows if isinstance(rows, list) else []:
        sym, close = (r.get("Symbol") or "").strip().upper(), r.get("ClosePrice")
        if sym and isinstance(close, (int, float)) and close > 0:
            prices[sym] = float(close)
            day = day or (r.get("TradeDate") or "")[:10] or None
    return day, prices


def fetch_ngx_index(client: Optional[httpx.Client] = None) -> dict[str, float]:
    """NGX All-Share Index closes since 1996: {iso date: level}."""
    c = client or _client()
    try:
        data = c.get(NGX_WIDGETS + "home/index-chart", params={"index": "ASI"}).json()
        points = data.get("quote", {}).get("IndiciesData") or data.get("points") or []
    except Exception as e:
        log.warning("NGX index unavailable: %s", e)
        return {}
    return {_iso_ms(ms): float(v) for ms, v in points if v}


def fetch_ngx_recent(symbol: str, client: Optional[httpx.Client] = None) -> dict[str, float]:
    """A stock's last ~20 trading days from the NGX data service."""
    c = client or _client()
    try:
        data = c.get(NGX_WIDGETS + "company/chart", params={"symbol": _code(symbol)}).json()
    except Exception as e:
        log.warning("NGX history unavailable for %s: %s", symbol, e)
        return {}
    return {_iso_ms(ms): float(v) for ms, v in data.get("points", []) if v}


# <td class=nm><a href="/m/stock=SCOM">SCOM</a><br>\n<td class=n>35.20<td ...
_NSE_ROW = re.compile(r'<td class=nm><a href="[^"]*">(\^?[A-Z][A-Z0-9&.\-]{0,11})</a>(?:<br>)?\s*<td class=n>([\d,]+(?:\.\d+)?)<')
_NSE_DATE = re.compile(r"Market Pricelist\s*(?:&amp;#8212;|&#8212;|—|-)\s*(\d{1,2} [A-Z][a-z]{2} \d{4})")


def parse_nse_price_list(page: str) -> tuple[Optional[str], dict[str, float]]:
    """(date, {symbol: price}) from the myStocks price list page, indices included (^NASI ...)."""
    m = _NSE_DATE.search(page)
    day = datetime.strptime(m.group(1), "%d %b %Y").date().isoformat() if m else None
    prices = {}
    for sym, price in _NSE_ROW.findall(page):
        try:
            v = float(price.replace(",", ""))
        except ValueError:
            continue
        if v > 0:
            prices.setdefault(html.unescape(sym), v)
    return day, prices


def fetch_nse_price_list(client: Optional[httpx.Client] = None) -> tuple[Optional[str], dict[str, float]]:
    c = client or _client()
    try:
        return parse_nse_price_list(c.get(NSE_PRICE_LIST).text)
    except Exception as e:
        log.warning("NSE price list unavailable: %s", e)
        return None, {}


def _iso_ms(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


# ── Snapshot store ────────────────────────────────────────────────────────────
# {"ngx": {"DANGCEM": {"2026-10-13": 1066.7}}, "nse": {"SCOM": {...}, "^NASI": {...}}}

_SNAPSHOT_OVERRIDE: Optional[dict] = None


def set_snapshot(snapshot: Optional[dict]) -> None:
    """Use this price history instead of the local file (the hosted API loads it from Supabase)."""
    global _SNAPSHOT_OVERRIDE
    _SNAPSHOT_OVERRIDE = snapshot


def load_snapshot() -> dict:
    if _SNAPSHOT_OVERRIDE is not None:
        return _SNAPSHOT_OVERRIDE
    return load_json(SNAPSHOT_PATH, dict)


def snapshot_rows() -> list[dict]:
    """Today's NGX and NSE closes as rows, plus the NGX index's latest year."""
    rows: list[dict] = []
    with _client() as c:
        for market, (day, prices) in (("ngx", fetch_ngx_price_list(c)), ("nse", fetch_nse_price_list(c))):
            if day:
                rows += [{"market": market, "symbol": s, "day": day, "close": v} for s, v in prices.items()]
        cutoff = (date.today() - timedelta(days=400)).isoformat()
        rows += [{"market": "ngx", "symbol": NGX_INDEX, "day": d, "close": v}
                 for d, v in fetch_ngx_index(c).items() if d >= cutoff]
    return rows


def merge_snapshot(store: dict, market: str, day: Optional[str], prices: dict[str, float]) -> int:
    if not day:
        return 0
    series = store.setdefault(market, {})
    for sym, close in prices.items():
        series.setdefault(sym, {})[day] = close
    return len(prices)


def take_snapshot() -> dict:
    """Record today's NGX and NSE closes (and both indices). Returns counts."""
    store = load_snapshot()
    with _client() as c:
        ngx_day, ngx = fetch_ngx_price_list(c)
        nse_day, nse = fetch_nse_price_list(c)
        asi = fetch_ngx_index(c)
    counts = {"ngx": merge_snapshot(store, "ngx", ngx_day, ngx), "nse": merge_snapshot(store, "nse", nse_day, nse)}
    store.setdefault("ngx", {}).setdefault(NGX_INDEX, {}).update(asi)
    save_json(SNAPSHOT_PATH, store)
    return counts


# ── Price moves ───────────────────────────────────────────────────────────────

def moves_from_series(series: dict[str, float], detection_date: str, windows=(5, 10, 30)) -> dict[str, Optional[float]]:
    """Percentage move from the first close on/after detection to the first close on/after +w days."""
    out: dict[str, Optional[float]] = {f"{w}d": None for w in windows}
    if not series:
        return out
    days = sorted(series)
    start = next((d for d in days if d >= detection_date), None)
    if not start or not series[start]:
        return out
    base = series[start]
    d0 = date.fromisoformat(detection_date)
    for w in windows:
        target = (d0 + timedelta(days=w)).isoformat()
        end = next((d for d in days if d >= target), None)
        if end and end > start:
            out[f"{w}d"] = round((series[end] - base) / base * 100, 2)
    return out


def african_price_moves(
    symbol: str, detection_date: str,
    snapshot: Optional[dict] = None,
    recent: Optional[Callable[[str], dict[str, float]]] = None,
    index: Optional[Callable[[], dict[str, float]]] = None,
) -> dict[str, Optional[float]]:
    """Price moves for an NGX/NSE symbol or index: snapshot history, then the exchange's recent window."""
    market = market_of(symbol)
    if market is None:
        return {"5d": None, "10d": None, "30d": None}
    snap = load_snapshot() if snapshot is None else snapshot
    key = symbol.upper() if symbol.startswith("^") else _code(symbol)
    series = dict(snap.get(market, {}).get(key, {}))
    if market == "ngx" and key == NGX_INDEX:
        series.update((index or fetch_ngx_index)())
    elif market == "ngx":
        series.update((recent or fetch_ngx_recent)(symbol))
    return moves_from_series(series, detection_date)
