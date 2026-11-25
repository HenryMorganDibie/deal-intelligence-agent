"""
Daily price history for listed shares from before the platform began keeping daily snapshots (28 October 2026),
back to 2010 where a source has it. Filled once by scripts/backfill_price_history.py and stored packed, one row per
listing per year (public.price_history_years); GET /v1/markets/history reads it with the snapshots.

Sources, chosen by what they hold (checked November 2026):
  - Yahoo Finance chart data: Johannesburg (.JO, quoted in cents, converted to rand) and Cairo (.CA), from 2000.
  - sikafinance.com history: the other markets it lists. BRVM from 2010; Casablanca from about 2016; Ghana from
    2020; most others from 2018 (indices) or 2024 (shares).
  - NGX: the exchange's own daily price lists from mid-2014 (src/engines/ngx_archive.py).
Both report closes adjusted for splits and agree with the daily snapshots on the days they overlap.
"""
from __future__ import annotations

import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable, Optional

import httpx

START = date(2010, 1, 1)
PAUSE = 0.7                      # seconds between requests to one site
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) deal-intelligence/1.0"}

YAHOO_SUFFIX = {"jse": ".JO", "egx": ".CA"}
# The sikafinance market (placeCode) for each exchange it lists.
# NGX is filled from the exchange's own daily price lists instead (src/engines/ngx_archive.py).
SIKA_PLACE = {"brvm": "br", "gse": "gh", "dse": "et", "mse": "mw", "rse": "rw", "bvc": "ma",
              "sem": "mu", "bse": "bw", "luse": "zm", "bvmt": "tn", "nse": "ke", "use": "ug", "sgbv": "dz"}
SOURCE_NAME = {"yahoo": "Yahoo Finance history", "sika": "sikafinance history"}


def exchanges() -> list[str]:
    return sorted(set(YAHOO_SUFFIX) | set(SIKA_PLACE))


# ── Packing ───────────────────────────────────────────────────────────────────

def pack_years(exchange: str, symbol: str, points: Iterable[tuple[date, float]], source: str) -> list[dict]:
    """One row per calendar year: each trading day's day of the year and its close, in date order. A day seen
    twice keeps its last close; non-positive closes are dropped."""
    by_day: dict[date, float] = {}
    for day, close in points:
        # 1 January is a holiday on every African exchange; a row for it is a source artefact. Weekends are kept:
        # Egypt traded Sunday to Thursday.
        if close is not None and close > 0 and (day.month, day.day) != (1, 1):
            by_day[day] = float(close)
    years: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for day in sorted(by_day):
        years[day.year].append(((day - date(day.year, 1, 1)).days + 1, round(by_day[day], 6)))
    return [{"exchange": exchange, "symbol": symbol.upper(), "year": y, "days": [d for d, _ in rows],
             "closes": [c for _, c in rows], "source": source} for y, rows in sorted(years.items())]


# ── Yahoo Finance ─────────────────────────────────────────────────────────────

def parse_yahoo(payload: dict) -> list[tuple[date, float]]:
    """Daily (date, close) from a Yahoo chart response, in the main currency unit: prices quoted in cents (ZAc,
    GBp) are divided by 100. Dates are the exchange's local trading day."""
    result = ((payload or {}).get("chart") or {}).get("result") or []
    if not result:
        return []
    r = result[0]
    meta = r.get("meta") or {}
    currency = str(meta.get("currency") or "")
    divisor = 100.0 if len(currency) == 3 and currency[-1].islower() else 1.0     # ZAc, GBp: minor units
    offset = int(meta.get("gmtoffset") or 0)
    stamps = r.get("timestamp") or []
    closes = (((r.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    out = []
    for ts, close in zip(stamps, closes):
        if close is None:
            continue
        day = datetime.fromtimestamp(int(ts) + offset, tz=timezone.utc).date()
        out.append((day, close / divisor))
    return out


def yahoo_history(client: httpx.Client, exchange: str, symbol: str, start: date, end: date) -> list[tuple[date, float]]:
    ticker = symbol.upper() + YAHOO_SUFFIX[exchange]
    p1 = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
    p2 = int(datetime(end.year, end.month, end.day, tzinfo=timezone.utc).timestamp()) + 86400
    r = client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
                   params={"period1": p1, "period2": p2, "interval": "1d"})
    time.sleep(PAUSE)
    if r.status_code != 200:
        return []
    return [(d, c) for d, c in parse_yahoo(r.json()) if start <= d <= end]


# ── sikafinance ───────────────────────────────────────────────────────────────

_SIKA_TICKER = re.compile(r'href="/marches/cotation_([A-Za-z0-9._&-]+)"')


def sika_tickers(html: str) -> dict[str, str]:
    """Our symbol (the code before the market suffix) -> sikafinance's ticker ('SNTS' -> 'SNTS.sn'), from a market's
    listing page."""
    out = {}
    for t in _SIKA_TICKER.findall(html or ""):
        base = t.split(".")[0].upper()
        if base and "'" not in t:
            out.setdefault(base, t)
    return out


def parse_sika(payload: dict) -> list[tuple[date, float]]:
    rows = (payload or {}).get("lst") or []
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        try:
            day = datetime.strptime(str(row.get("Date")), "%d/%m/%Y").date()
            close = float(row.get("Close"))
        except (TypeError, ValueError):
            continue
        out.append((day, close))
    return out


def _month_start(d: date, back: int) -> date:
    y, m = d.year, d.month - back
    while m <= 0:
        m, y = m + 12, y - 1
    return date(y, m, 1)


def quarters_back(end: date, start: date) -> list[tuple[date, date]]:
    """Three-month windows from `end` back to `start`, newest first (sikafinance refuses longer ranges)."""
    out, hi = [], end
    while hi >= start:
        lo = max(start, _month_start(hi, 2))
        out.append((lo, hi))
        hi = lo - timedelta(days=1)
    return out


def sika_history(fetch: Callable[[date, date], list[tuple[date, float]]], start: date, end: date,
                 give_up_after: int = 8) -> list[tuple[date, float]]:
    """Walk back a quarter at a time until `start`, or until the history runs out: four empty quarters before any
    data means the listing has none; `give_up_after` empty quarters after data means it has ended."""
    points, empty, seen = [], 0, False
    for lo, hi in quarters_back(end, start):
        got = fetch(lo, hi)
        if got:
            points += got
            seen, empty = True, 0
        else:
            empty += 1
            if (not seen and empty >= 4) or (seen and empty >= give_up_after):
                break
    return points


def sika_fetcher(client: httpx.Client, ticker: str) -> Callable[[date, date], list[tuple[date, float]]]:
    def fetch(lo: date, hi: date) -> list[tuple[date, float]]:
        try:
            r = client.post("https://www.sikafinance.com/api/general/GetHistos",
                            json={"ticker": ticker, "datedeb": lo.isoformat(), "datefin": hi.isoformat(), "xperiod": "0"})
        except httpx.HTTPError:
            time.sleep(PAUSE * 4)
            return []
        time.sleep(PAUSE)
        if r.status_code != 200:
            return []
        try:
            return [(d, c) for d, c in parse_sika(r.json()) if lo <= d <= hi]
        except ValueError:
            return []
    return fetch


def history_for(client: httpx.Client, exchange: str, symbol: str, sika_map: Optional[dict[str, str]],
                start: date, end: date) -> tuple[list[tuple[date, float]], str]:
    """(points, source name) for one listing; empty when no source has it."""
    if exchange in YAHOO_SUFFIX:
        return yahoo_history(client, exchange, symbol, start, end), SOURCE_NAME["yahoo"]
    ticker = (sika_map or {}).get(symbol.upper().split(".")[0])
    if not ticker:
        return [], SOURCE_NAME["sika"]
    return sika_history(sika_fetcher(client, ticker), start, end), SOURCE_NAME["sika"]
