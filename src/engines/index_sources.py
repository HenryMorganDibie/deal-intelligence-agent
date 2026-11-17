"""
Benchmark index levels from the exchanges' own publications, used since african-markets.com (which supplied the
index table) went down for maintenance on 29 October 2026.

  NGX ASI    NGX's market snapshot API (level only)                    doclib.ngxgroup.com
  NSE ASI    the Nairobi price list's Indices table (level, change)    live.mystocks.co.ke
  DSE ASI    the Dar es Salaam exchange's home page (DSEI close, %)    dse.co.tz
  MSE ASI    the Malawi exchange's index table (MASI open and close)   mse.co.mw
  USE ASI    the Uganda exchange's delayed-data feed (ALSI level)      use.or.ug
  SEM ASI    the Mauritius exchange's home page (SEM-ASI level)        stockexchangeofmauritius.com
  BRVM-CI,   sikafinance's African indices table (level, change,       sikafinance.com
  TUNINDEX   date); its other rows stopped with the listing site

A source that gives a level but no change gets one from the previous stored level, only when that level was
official (not estimated) and set the session before. Every row carries the date the exchange closed at; a level
older than one already held never replaces it.
"""
from __future__ import annotations

import html as html_mod
import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Callable, Optional

import httpx

from src.engines.price_sources import _EN_MONTHS, _MSE_DATE, _get, _num, latest_session

log = logging.getLogger(__name__)

NGX_SNAPSHOT = "https://doclib.ngxgroup.com/REST/api/mrkstat/mrksnapshot"
MYSTOCKS_PRICES = "https://live.mystocks.co.ke/m/pricelist"
DSE_HOME = "https://dse.co.tz/"
MSE_HOME = "https://www.mse.co.mw/"
USE_DATA = "https://www.use.or.ug/api/delayed-data"
SEM_HOME = "https://www.stockexchangeofmauritius.com/"
SIKA_INDICES = "https://www.sikafinance.com/marches/indices_afrique"

# sikafinance row name -> (exchange, index name as stored)
_SIKA_NAMES = {"BRVM COMPOSITE": ("brvm", "BRVM-CI"), "TUNINDEX": ("bvmt", "TUNINDEX")}


def _row(exchange: str, name: str, level: Optional[float], day: Optional[str], chg_1d: Optional[float],
         source: str) -> Optional[dict]:
    if not level or level <= 0 or not day:
        return None
    return {"exchange": exchange, "name": name, "level": round(level, 2),
            "chg_1d": None if chg_1d is None else round(chg_1d, 6), "date": day, "source": source}


def _day(d: str, month: str, year: str) -> Optional[str]:
    """'16', 'Nov' or 'November', '2026' -> '2026-11-16'."""
    m = month.lower()
    num = _EN_MONTHS.get(m) or next((i for name, i in _EN_MONTHS.items() if len(m) >= 3 and name.startswith(m)), None)
    try:
        return date(int(year), num, int(d)).isoformat() if num else None
    except ValueError:
        return None


def _signed_pct(text: str) -> Optional[float]:
    v = _num(text.replace("%", "").replace("+", ""))
    return None if v is None else v / 100


# ── Parsers (pure, tested on saved pages) ─────────────────────────────────────

def parse_ngx_snapshot(data: object, day: str) -> Optional[dict]:
    level = data.get("ASI") if isinstance(data, dict) else None
    return _row("ngx", "NGX ASI", level if isinstance(level, (int, float)) else None, day, None, "NGX market snapshot")


_MYSTOCKS_DATE = re.compile(r"(\d{1,2}) ([A-Z][a-z]{2}) (20\d\d) - myStocks")
_MYSTOCKS_NASI = re.compile(r">\^NASI</a>.*?<td class=n>([\d,.]+)<td class=\"n x(-?1|0)\">[^<]*?([\d.]+)%", re.S)


def parse_mystocks_nasi(page: str) -> Optional[dict]:
    d, m = _MYSTOCKS_DATE.search(page), _MYSTOCKS_NASI.search(page)
    day = _day(d.group(1), d.group(2), d.group(3)) if d else None
    if not day or not m:
        return None
    pct = _num(m.group(3))
    chg = None if pct is None else int(m.group(2)) * pct / 100
    return _row("nse", "NSE ASI", _num(m.group(1)), day, chg, "NSE price list (myStocks)")


_DSE_SERIES = re.compile(r'\\?"name\\?":\\?"DSEI\\?",\\?"close\\?":([\d.]+),\\?"change\\?":(-?[\d.]+),'
                         r'\\?"pct\\?":(-?[\d.]+)')


_DSE_DATE = re.compile(r"Daily Market Report\s*(?:<[^>]+>\s*)*(\d{1,2}) ([A-Z][a-z]{2}) (20\d\d)")


def parse_dse(page: str) -> Optional[dict]:
    """The DSEI entry of the chart data the home page embeds (close, change, percentage), dated by the page's
    Daily Market Report line; the chart's own timestamps run a day ahead of it."""
    m, d = _DSE_SERIES.search(page), _DSE_DATE.search(page)
    day = _day(d.group(1), d.group(2), d.group(3)) if d else None
    if not m or not day:
        return None
    return _row("dse", "DSE ASI", float(m.group(1)), day, float(m.group(3)) / 100, "DSE official")


_MSE_MASI = re.compile(r"<th>MASI</th>\s*<td[^>]*>([\d,.]+)</td>\s*<td[^>]*>([\d,.]+)</td>")


def parse_mse_index(page: str) -> Optional[dict]:
    """MASI's open and close from the index table, dated by the page's 'Stats as at' line. The open is the previous
    close, so the day's change is close over open."""
    d, m = _MSE_DATE.search(page), _MSE_MASI.search(page)
    day = _day(d.group(1), d.group(2), d.group(3)) if d else None
    if not day or not m:
        return None
    opened, close = _num(m.group(1)), _num(m.group(2))
    chg = close / opened - 1 if opened and close else None
    return _row("mse", "MSE ASI", close, day, chg, "MSE official")


def parse_use_index(data: object, day: str) -> Optional[dict]:
    rows = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else None)
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict) and r.get("type") == "INDEX" and r.get("stock") == "ALSI":
            level = r.get("price")
            return _row("use", "USE ASI", level if isinstance(level, (int, float)) else None, day, None,
                        "USE official")
    return None


_SEM_ASI = re.compile(r'<div class="name">SEM-ASI</div>\s*<div class="num[^"]*">(?:<[^>]+>)*\s*([\d,.]+)')


def parse_sem(page: str, day: str) -> Optional[dict]:
    m = _SEM_ASI.search(page)
    return _row("sem", "SEM ASI", _num(m.group(1)), day, None, "SEM official") if m else None


def parse_sika_indices(page: str) -> list[dict]:
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        cells = [html_mod.unescape(re.sub(r"<[^>]+>", "", c)).replace("\xa0", " ").strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) < 5 or cells[1].upper() not in _SIKA_NAMES:
            continue
        ex, name = _SIKA_NAMES[cells[1].upper()]
        m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", cells[4])
        level = _num(cells[2].replace(" ", "").replace(",", "."))
        if not m or level is None:
            continue
        row = _row(ex, name, level, f"{m.group(3)}-{m.group(2)}-{m.group(1)}", _signed_pct(cells[3]), "sikafinance")
        if row:
            out.append(row)
    return out


def with_change_from_previous(row: dict, previous: Optional[dict]) -> dict:
    """A level with no published change: if it equals the previous official level, the exchange did not trade (a
    holiday), so the previous row stands; otherwise the change is taken from it when it was official and at most
    four days earlier."""
    if row.get("chg_1d") is not None or not previous or previous.get("estimated") or not previous.get("level"):
        return row
    if abs(previous["level"] - row["level"]) < 0.005:
        return previous
    try:
        gap = (date.fromisoformat(row["date"]) - date.fromisoformat(previous.get("date") or "")).days
    except ValueError:
        return row
    if 0 < gap <= 4:
        return {**row, "chg_1d": round(row["level"] / previous["level"] - 1, 6)}
    return row


# ── Fetchers ──────────────────────────────────────────────────────────────────

def _json(client: httpx.Client, url: str) -> object:
    r = _get(client, url)
    if r is None:
        return None
    try:
        return r.json()
    except (ValueError, json.JSONDecodeError):
        return None


def _page(client: httpx.Client, url: str) -> str:
    r = _get(client, url)
    return r.text if r is not None else ""


def official_indices(client: httpx.Client, today: date, previous: Optional[list[dict]] = None,
                     now: Optional[datetime] = None) -> list[dict]:
    """Every index the sources above publish, one row per exchange; a source that fails is left out."""
    prev = {i.get("exchange"): i for i in previous or [] if isinstance(i, dict)}
    now = now or datetime.now(timezone.utc)

    def dated(open_utc: int, close_utc: int) -> Optional[str]:
        # These sources give a bare level, so it is dated by the last close; during the session it would be an
        # intraday level under yesterday's date, and is not read at all.
        if today.weekday() < 5 and now.date() == today and open_utc <= now.hour < close_utc:
            return None
        return latest_session(today, now, close_utc)

    def bare(parse: Callable[..., Optional[dict]], fetch: Callable[[], object], open_utc: int, close_utc: int):
        day = dated(open_utc, close_utc)
        return parse(fetch(), day) if day else None

    jobs: list[Callable[[], object]] = [
        lambda: bare(parse_ngx_snapshot, lambda: _json(client, NGX_SNAPSHOT), 8, 14),       # 09:30-14:30 WAT
        lambda: parse_mystocks_nasi(_page(client, MYSTOCKS_PRICES)),
        lambda: parse_dse(_page(client, DSE_HOME)),
        lambda: parse_mse_index(_page(client, MSE_HOME)),
        lambda: bare(parse_use_index, lambda: _json(client, USE_DATA), 7, 12),              # 10:00-15:00 EAT
        lambda: bare(parse_sem, lambda: _page(client, SEM_HOME), 6, 10),                    # 10:00-13:30 MUT
        lambda: parse_sika_indices(_page(client, SIKA_INDICES)),
    ]
    out: dict[str, dict] = {}
    for job in jobs:
        try:
            got = job()
        except Exception as e:                          # one source's failure never sinks the others
            log.info("index source failed: %r", e)
            continue
        for row in got if isinstance(got, list) else [got] if got else []:
            out[row["exchange"]] = with_change_from_previous(row, prev.get(row["exchange"]))
    return sorted(out.values(), key=lambda i: i["exchange"])
