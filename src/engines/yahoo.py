"""
Yahoo Finance's public JSON endpoints over httpx.

This replaces the yfinance package, which pulled pandas, numpy and a browser-impersonating HTTP client into the
serverless bundle (about 250 MB of the 296 MB the API installed on every cold start). Every call here returns plain
dicts and lists, identifies itself honestly, and returns empty results rather than raising when Yahoo has no data
or rate limits the request.

Endpoints used:
  chart       /v8/finance/chart/{symbol}                         daily history (no session needed)
  quote       /v7/finance/quote                                  price, market cap, currency (session crumb)
  screener    /v1/finance/screener                               every equity on an exchange (session crumb)
  summary     /v10/finance/quoteSummary/{symbol}                 profile and valuation fields (session crumb)
  timeseries  /ws/fundamentals-timeseries/v1/finance/timeseries  annual statement lines (no session needed)
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timezone
from typing import Iterable, Optional

import httpx

log = logging.getLogger(__name__)

BASE = "https://query1.finance.yahoo.com"
# No Accept header: the crumb endpoint answers text/plain and refuses "application/json" with a 406.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DealIntelligence/1.0; +https://deal-intelligence.app)"}

_LOCK = threading.Lock()
_CLIENT: Optional[httpx.Client] = None
_CRUMB: Optional[str] = None
_CRUMB_AT = 0.0
_CRUMB_TTL = 3600.0


def _client() -> httpx.Client:
    global _CLIENT
    with _LOCK:
        if _CLIENT is None:
            _CLIENT = httpx.Client(headers=_HEADERS, timeout=20, follow_redirects=True)
        return _CLIENT


def _crumb(refresh: bool = False) -> Optional[str]:
    """The session crumb the quote, screener and summary endpoints require, cached for an hour."""
    global _CRUMB, _CRUMB_AT
    c = _client()
    with _LOCK:
        if _CRUMB and not refresh and time.time() - _CRUMB_AT < _CRUMB_TTL:
            return _CRUMB
        try:
            c.get("https://fc.yahoo.com")                 # sets the session cookie; the page itself is a 404
            r = c.get(f"{BASE}/v1/test/getcrumb")
            crumb = r.text.strip() if r.status_code == 200 else ""
        except httpx.HTTPError as e:
            log.info("Yahoo crumb unavailable: %r", e)
            crumb = ""
        if not crumb or "<" in crumb or " " in crumb:
            return None
        _CRUMB, _CRUMB_AT = crumb, time.time()
        return _CRUMB


def _json(method: str, path: str, *, crumb: bool = False, **kw) -> Optional[dict]:
    """One request, retried once with a fresh crumb when the session has expired."""
    c = _client()
    base_params = dict(kw.pop("params", None) or {})
    for attempt in range(2 if crumb else 1):
        params = dict(base_params)
        if crumb:
            token = _crumb(refresh=attempt > 0)
            if not token:
                return None
            params["crumb"] = token
        try:
            r = c.request(method, f"{BASE}{path}", params=params, **kw)
        except httpx.HTTPError as e:
            log.info("Yahoo %s failed: %r", path, e)
            return None
        if r.status_code in (401, 403) and crumb and attempt == 0:
            continue
        if r.status_code != 200:
            log.info("Yahoo %s returned %s", path, r.status_code)
            return None
        try:
            return r.json()
        except ValueError:
            return None
    return None


def _epoch(d: date | datetime | str) -> int:
    if isinstance(d, str):
        d = datetime.strptime(d[:10], "%Y-%m-%d")
    if not isinstance(d, datetime):
        d = datetime(d.year, d.month, d.day)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return int(d.timestamp())


def history(symbol: str, start: date | datetime | str | None = None, end: date | datetime | str | None = None,
            range_: str | None = None) -> list[dict]:
    """Daily bars, oldest first: [{"date": date, "close": float, "volume": float|None}]. The close is dividend-
    and split-adjusted where Yahoo provides it, matching yfinance's auto_adjust=True."""
    params: dict = {"interval": "1d", "events": "div,split", "includeAdjustedClose": "true"}
    if start is not None:
        params["period1"] = _epoch(start)
        params["period2"] = _epoch(end) if end is not None else int(time.time())
    else:
        params["range"] = range_ or "1mo"
    data = _json("GET", f"/v8/finance/chart/{symbol}", params=params)
    return parse_chart(data)


def parse_chart(data: Optional[dict]) -> list[dict]:
    try:
        res = (data or {})["chart"]["result"][0]
    except (KeyError, IndexError, TypeError):
        return []
    stamps = res.get("timestamp") or []
    ind = res.get("indicators") or {}
    quote = (ind.get("quote") or [{}])[0]
    adj = (ind.get("adjclose") or [{}])[0].get("adjclose")
    closes = adj if adj and len(adj) == len(stamps) else quote.get("close") or []
    volumes = quote.get("volume") or []
    offset = (res.get("meta") or {}).get("gmtoffset") or 0
    out = []
    for i, ts in enumerate(stamps):
        close = closes[i] if i < len(closes) else None
        if not isinstance(close, (int, float)):
            continue
        vol = volumes[i] if i < len(volumes) else None
        day = datetime.fromtimestamp(ts + offset, tz=timezone.utc).date()
        out.append({"date": day, "close": float(close), "volume": float(vol) if isinstance(vol, (int, float)) else None})
    return out


def quotes(symbols: Iterable[str]) -> dict[str, dict]:
    """{symbol: quote row} with regularMarketPrice, marketCap, currency and the rest of Yahoo's quote fields."""
    syms = [s for s in dict.fromkeys(symbols) if s]
    out: dict[str, dict] = {}
    for i in range(0, len(syms), 50):
        data = _json("GET", "/v7/finance/quote", crumb=True, params={"symbols": ",".join(syms[i:i + 50])})
        for row in ((data or {}).get("quoteResponse") or {}).get("result") or []:
            if row.get("symbol"):
                out[row["symbol"]] = row
    return out


def screen(exchange: str, offset: int = 0, size: int = 250) -> dict:
    """One page of every equity on an exchange, largest first: {"quotes": [...], "total": n}."""
    body = {"offset": offset, "size": size, "sortField": "intradaymarketcap", "sortType": "DESC",
            "quoteType": "EQUITY", "query": {"operator": "eq", "operands": ["exchange", exchange]},
            "userId": "", "userIdType": "guid"}
    data = _json("POST", "/v1/finance/screener", crumb=True, json=body)
    try:
        res = data["finance"]["result"][0]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"Yahoo screener returned no result for {exchange}")
    return {"quotes": res.get("quotes") or [], "total": res.get("total") or 0}


_SUMMARY_MODULES = "assetProfile,price,summaryDetail,defaultKeyStatistics,financialData"


def summary(symbol: str) -> dict:
    """Profile and valuation fields flattened into one dict with yfinance's .info key names."""
    data = _json("GET", f"/v10/finance/quoteSummary/{symbol}", crumb=True, params={"modules": _SUMMARY_MODULES})
    try:
        res = data["quoteSummary"]["result"][0]
    except (KeyError, IndexError, TypeError):
        return {}
    out: dict = {}
    for module in res.values():
        if not isinstance(module, dict):
            continue
        for k, v in module.items():
            if isinstance(v, dict):
                v = v.get("raw", v.get("fmt")) if ("raw" in v or "fmt" in v) else None
            if v is not None and v != {} and k not in out:
                out[k] = v
    if "currentPrice" not in out and "regularMarketPrice" in out:
        out["currentPrice"] = out["regularMarketPrice"]
    return out


def annual_statements(symbol: str, lines: Iterable[str], years: int = 4) -> dict[str, dict[str, float]]:
    """{period end "YYYY-MM-DD": {statement line: value}} for the latest `years` fiscal years. Line names are
    yfinance's ("Total Revenue", "Net Income"), which map one to one onto Yahoo's timeseries keys."""
    names = list(dict.fromkeys(lines))
    keys = {"annual" + n.replace(" ", ""): n for n in names}
    now = int(time.time())
    data = _json("GET", f"/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}",
                 params={"type": ",".join(keys), "period1": now - 8 * 366 * 86400, "period2": now})
    out: dict[str, dict[str, float]] = {}
    for series in ((data or {}).get("timeseries") or {}).get("result") or []:
        for key, line in keys.items():
            for point in series.get(key) or []:
                if not isinstance(point, dict):
                    continue
                period = point.get("asOfDate")
                value = (point.get("reportedValue") or {}).get("raw")
                if period and isinstance(value, (int, float)):
                    out.setdefault(period, {})[line] = float(value)
    latest = sorted(out, reverse=True)[:years]
    return {p: out[p] for p in latest}
