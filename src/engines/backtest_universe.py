"""
The backtest universe: about 2,000 listed companies, built from public, reproducible sources.

  United States   the largest SEC filers by public float (EDGAR XBRL frames, dei:EntityPublicFloat
                  for mid-2024), mapped to tickers with EDGAR's company_tickers.json.
  Africa          every company listed on the JSE, NGX, Egyptian Exchange, Casablanca, NSE Kenya,
                  BRVM and Ghana Stock Exchange, from African Markets' listed-company tables.
  Original 46     the hand-picked universe, kept so earlier results remain comparable.

    python main.py backtest --universe       # rebuilds docs/backtest_universe.csv

The CSV is committed, so the universe a result was computed on is always on record.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import time
from pathlib import Path
from typing import Optional

import httpx

log = logging.getLogger(__name__)

UNIVERSE_PATH = Path(__file__).resolve().parents[2] / "docs" / "backtest_universe.csv"
N_US = 1000
SEC_HEADERS = {"User-Agent": "DealIntelligence research henrymorgandibie@gmail.com"}
BROWSER = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
# African Markets exchange code -> (Yahoo-style suffix our tools understand, label)
AFRICAN_EXCHANGES = {
    "jse": (".JO", "JSE"), "ngse": (".LG", "NGX"), "egx": (".CA", "EGX"), "bvc": (".CS", "Casablanca"),
    "nse": (".NR", "NSE Kenya"), "brvm": (".BV", "BRVM"), "gse": (".GH", "GSE"),
}
_SUFFIX = re.compile(r"(,?\s+(inc\.?|incorporated|corp\.?|corporation|co\.?|company|ltd\.?|limited|plc|p\.l\.c\.|"
                     r"n\.v\.|s\.a\.|ag|se|holdings?\s+inc\.?|[/\\][a-z]{2}[/\\]|\(the\)))+$", re.IGNORECASE)
_SMALL = {"of", "and", "the", "for", "de", "du", "la", "le", "et", "des", "in", "on", "at"}
COLUMNS = ["company", "ticker", "cik", "market", "exchange", "source", "public_float_usd", "sector"]


def query_name(name: str) -> str:
    """'Apple Inc.' -> 'Apple', 'NVIDIA CORP' -> 'Nvidia': the form a headline uses."""
    n = re.sub(r"\s*[/\\][A-Za-z]{2}[/\\]?\s*$", "", name.strip())
    n = re.sub(r"\s*[/\\][A-Za-z]{2}[/\\]\s*", " ", n)
    n = _SUFFIX.sub("", n).strip(" ,.&")
    n = re.sub(r"\s+(com|&)$", "", n, flags=re.IGNORECASE)
    if n.isupper() and len(n) > 4:
        n = " ".join(w.lower() if w.lower() in _SMALL else w if len(w) <= 3 else w.capitalize() for w in n.split())
    return re.sub(r"\s+", " ", n).strip()


MAX_PLAUSIBLE_FLOAT = 4e12     # above any US company's public float: a filer tagged the wrong scale


def _frame(client: httpx.Client, concept: str, unit: str, period: str) -> list[dict]:
    try:
        return client.get(f"https://data.sec.gov/api/xbrl/frames/dei/{concept}/{unit}/{period}.json").json()["data"]
    except (httpx.HTTPError, ValueError, KeyError):
        return []


def _rescale(value: float, shares: Optional[float]) -> Optional[float]:
    """Fix floats tagged at the wrong scale: an implied price above $10,000 a share means thousands were
    entered as units (repeatedly, for some filers). Without a share count, only the hard ceiling applies."""
    if shares:
        while value / shares > 10_000:
            value /= 1000
    return value if 0 < value <= MAX_PLAUSIBLE_FLOAT else None


def us_companies(client: httpx.Client, n: int = N_US) -> list[dict]:
    """Largest US filers by public float: each company's median across mid-2023, 2024 and 2025, with
    mis-scaled values corrected against shares outstanding."""
    import statistics
    floats: dict[int, list[float]] = {}
    names: dict[int, str] = {}
    for period in ("CY2023Q2I", "CY2024Q2I", "CY2025Q2I"):
        shares = {int(f["cik"]): float(f["val"]) for f in _frame(client, "EntityCommonStockSharesOutstanding", "shares", period)
                  if f.get("val")}
        for f in _frame(client, "EntityPublicFloat", "USD", period):
            cik = int(f["cik"])
            v = _rescale(float(f.get("val") or 0), shares.get(cik))
            if v:
                floats.setdefault(cik, []).append(v)
            if any(ch.islower() for ch in f.get("entityName", "")):
                names[cik] = f["entityName"]
    frames = [{"cik": cik, "val": statistics.median(v)} for cik, v in floats.items()]
    tickers = client.get("https://www.sec.gov/files/company_tickers.json").json().values()
    by_cik: dict[int, dict] = {}
    for t in tickers:
        by_cik.setdefault(int(t["cik_str"]), t)          # first listed ticker is the primary class
    rows = []
    for f in sorted(frames, key=lambda f: -float(f.get("val") or 0)):
        t = by_cik.get(int(f["cik"]))
        if not t or not re.fullmatch(r"[A-Z]{1,5}", t["ticker"]):
            continue
        rows.append({"company": query_name(names.get(int(f["cik"]), t["title"])), "ticker": t["ticker"],
                     "cik": f"{int(f['cik']):010d}", "market": "us", "exchange": "US",
                     "source": "SEC EDGAR public float, median of mid-2023 to mid-2025",
                     "public_float_usd": round(float(f["val"])), "sector": ""})
        if len(rows) >= n:
            break
    return rows


def african_companies(client: httpx.Client) -> list[dict]:
    """JSE from its listed-companies table; the other exchanges from the company index each page embeds."""
    import pandas as pd
    rows = []
    r = client.get("https://www.african-markets.com/en/stock-markets/jse/listed-companies")
    r.raise_for_status()
    table = next(t for t in pd.read_html(io.StringIO(r.text)) if {"Company", "Symbol"} <= set(t.columns))
    for _, x in table.iterrows():
        sym = re.sub(r"[^A-Z0-9]", "", str(x["Symbol"]).upper())
        if sym:
            rows.append({"company": query_name(str(x["Company"])), "ticker": sym + ".JO", "cik": "", "market": "africa",
                         "exchange": "JSE", "source": "African Markets listed companies", "public_float_usd": "",
                         "sector": str(x.get("Sector") or "")})
    index = re.findall(r'"ticker":\s*"([^"]+)",\s*"isin":\s*"[^"]*",\s*"company":\s*"([^"]+)",\s*"lien":\s*"[^"]*?/stock-markets/([a-z]+)/',
                       r.text)
    for ticker, company, code in index:
        if code not in AFRICAN_EXCHANGES or code == "jse":
            continue
        suffix, label = AFRICAN_EXCHANGES[code]
        sym = re.sub(r"[^A-Z0-9]", "", ticker.upper())
        if sym:
            rows.append({"company": query_name(company), "ticker": sym + suffix, "cik": "", "market": "africa",
                         "exchange": label, "source": "African Markets listed companies", "public_float_usd": "", "sector": ""})
    return rows


def build() -> list[dict]:
    from src.engines.historical_backtest import UNIVERSE
    sec = httpx.Client(timeout=60, headers=SEC_HEADERS, follow_redirects=True)
    web = httpx.Client(timeout=60, headers=BROWSER, follow_redirects=True)
    original = [{"company": e[0], "ticker": e[1], "cik": e[2] if len(e) > 2 else "",
                 "market": "us" if "." not in e[1] else "africa", "exchange": "", "source": "original 46",
                 "public_float_usd": "", "sector": ""} for e in UNIVERSE]
    seen = {r["ticker"] for r in original}
    names = {r["company"].lower() for r in original}
    rows = list(original)
    for r in us_companies(sec) + african_companies(web):
        if r["ticker"] in seen or r["company"].lower() in names or len(r["company"]) < 3:
            continue
        seen.add(r["ticker"])
        names.add(r["company"].lower())
        rows.append(r)
    UNIVERSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with UNIVERSE_PATH.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return rows


def load(path: Optional[Path] = None) -> list[tuple]:
    """(company, ticker, cik or None) for every company in the committed universe file."""
    p = path or UNIVERSE_PATH
    if not p.exists():
        from src.engines.historical_backtest import UNIVERSE
        return list(UNIVERSE)
    with p.open() as f:
        return [(r["company"], r["ticker"], r["cik"] or None) for r in csv.DictReader(f)]
