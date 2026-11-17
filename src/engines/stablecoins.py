"""
Dollar stablecoin rates in local currency, against the official exchange rate.

Where dollars are scarce, the local price of USDT works as a live parallel-market rate, and its premium over the
official rate is a figure investors watch. Only markets with a liquid local order book published through a
documented public API are covered: Nigeria (Quidax, USDT/NGN) and South Africa (VALR, USDT/ZAR). Elsewhere the
available prices are converted from the official rate and would show no premium, so none is shown.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx

log = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DealIntelligence/1.0; +https://deal-intelligence.app)"}
MIN_VOLUME_USDT = 5_000          # a thinner day's book is not a usable rate


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def parse_quidax(data: dict) -> Optional[dict]:
    t = ((data or {}).get("data") or {}).get("ticker") or {}
    last, bid, ask, vol = _num(t.get("last")), _num(t.get("buy")), _num(t.get("sell")), _num(t.get("vol"))
    at = (data.get("data") or {}).get("at")
    if not last:
        return None
    return {"currency": "NGN", "country": "NG", "pair": "USDT/NGN", "rate": last, "bid": bid, "ask": ask,
            "volume_usdt_24h": vol, "source": "Quidax", "source_url": "https://www.quidax.com/",
            "at": datetime.fromtimestamp(at, tz=timezone.utc).isoformat() if isinstance(at, (int, float)) else None}


def parse_valr(data: dict) -> Optional[dict]:
    last = _num((data or {}).get("lastTradedPrice"))
    if not last:
        return None
    return {"currency": "ZAR", "country": "ZA", "pair": "USDT/ZAR", "rate": last, "bid": _num(data.get("bidPrice")),
            "ask": _num(data.get("askPrice")), "volume_usdt_24h": _num(data.get("baseVolume")), "source": "VALR",
            "source_url": "https://www.valr.com/", "at": data.get("created")}


SOURCES: list[tuple[str, Callable[[dict], Optional[dict]]]] = [
    ("https://app.quidax.io/api/v1/markets/tickers/usdtngn", parse_quidax),
    ("https://api.valr.com/v1/public/USDTZAR/marketsummary", parse_valr),
]


def with_premium(row: dict, official_per_usd: dict) -> dict:
    """The row with the official rate and the stablecoin premium over it (0.06 = 6% more local currency per dollar)."""
    official = _num((official_per_usd or {}).get(row["currency"]))
    spread = (row["ask"] - row["bid"]) / row["rate"] if row.get("bid") and row.get("ask") else None
    return {**row, "official_per_usd": round(official, 4) if official else None,
            "premium": round(row["rate"] / official - 1, 4) if official else None,
            "spread": round(spread, 4) if spread is not None else None}


def fetch(official_per_usd: dict, client: Optional[httpx.Client] = None) -> dict:
    """Every covered market's rate, its official rate and premium. A source that fails or trades too little that
    day is left out rather than shown with a stale or unreliable figure."""
    own = client is None
    c = client or httpx.Client(headers=_HEADERS, timeout=10)

    def one(src):
        url, parse = src
        try:
            r = c.get(url)
            return parse(r.json()) if r.status_code == 200 else None
        except (httpx.HTTPError, ValueError) as e:
            log.info("stablecoin rate %s unavailable: %r", url, e)
            return None
    try:
        with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
            rows = [r for r in pool.map(one, SOURCES) if r]
    finally:
        if own:
            c.close()
    rows = [with_premium(r, official_per_usd) for r in rows
            if (r.get("volume_usdt_24h") or 0) >= MIN_VOLUME_USDT]
    return {"rates": rows, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "method": ("Last traded price of USDT, a dollar stablecoin, on a local exchange's public order book, "
                       "against the day's official rate. The premium is how much more local currency a dollar costs "
                       "there. Covered where a liquid local book publishes its prices: Nigeria and South Africa.")}
