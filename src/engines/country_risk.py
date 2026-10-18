"""
Country risk for all 54 African countries.

A transparent, reproducible score built only from public data:

  * World Bank Worldwide Governance Indicators (political stability, government
    effectiveness, regulatory quality, rule of law, control of corruption, voice
    and accountability), estimates on a -2.5 to +2.5 scale.
  * World Bank World Development Indicators: inflation, real GDP growth, official
    exchange rate (annual average, for currency depreciation), reserves in months
    of imports, current account balance, external debt.
  * Live spot FX against the US dollar (open.er-api.com).

Each component maps to a 0-100 risk value with a fixed, documented formula, and
the overall score is their weighted mean over the components that have data.
Every number in a result carries its source year, so a reader can check it.

The indicator snapshot (src/data/country_indicators.json) is committed and
refreshed with `python main.py countries --refresh`; World Bank data are annual,
so a stale-by-days snapshot loses nothing, and the hosted API never waits on the
World Bank's slow responses.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Callable, Optional

import httpx

from src.data.africa_countries import COUNTRIES, Country, get

log = logging.getLogger(__name__)

# Committed reference data (not a runtime store under data/): written only by `countries --refresh`.
_REFERENCE = Path(__file__).resolve().parent.parent / "data"
INDICATORS_PATH = _REFERENCE / "country_indicators.json"
WB_API = "https://api.worldbank.org/v2/country/{codes}/indicator/{indicator}"
FX_API = "https://open.er-api.com/v6/latest/USD"

GOVERNANCE = {
    "GOV_WGI_PV.EST": "Political stability and absence of violence",
    "GOV_WGI_GE.EST": "Government effectiveness",
    "GOV_WGI_RQ.EST": "Regulatory quality",
    "GOV_WGI_RL.EST": "Rule of law",
    "GOV_WGI_CC.EST": "Control of corruption",
    "GOV_WGI_VA.EST": "Voice and accountability",
}
MACRO = {
    "FP.CPI.TOTL.ZG": "Inflation, consumer prices (annual %)",
    "NY.GDP.MKTP.KD.ZG": "Real GDP growth (annual %)",
    "PA.NUS.FCRF": "Official exchange rate (LCU per USD, period average)",
    "FI.RES.TOTL.MO": "Total reserves in months of imports",
    "BN.CAB.XOKA.GD.ZS": "Current account balance (% of GDP)",
    "DT.DOD.DECT.GN.ZS": "External debt stocks (% of GNI)",
    "NY.GDP.PCAP.CD": "GDP per capita (current US$)",
}


def _clamp(x: float) -> float:
    return round(max(0.0, min(100.0, x)), 1)


# name, weight, formula description, function(indicators) -> risk or None
def _governance_risk(ind: dict) -> Optional[float]:
    vals = [ind[k]["value"] for k in GOVERNANCE if k != "GOV_WGI_PV.EST" and k in ind]
    return _clamp((2.5 - sum(vals) / len(vals)) / 5 * 100) if vals else None


def _stability_risk(ind: dict) -> Optional[float]:
    v = ind.get("GOV_WGI_PV.EST")
    return _clamp((2.5 - v["value"]) / 5 * 100) if v else None


def _inflation_risk(ind: dict) -> Optional[float]:
    v = ind.get("FP.CPI.TOTL.ZG")
    return _clamp(v["value"] / 40 * 100) if v else None


def _growth_risk(ind: dict) -> Optional[float]:
    v = ind.get("NY.GDP.MKTP.KD.ZG")
    return _clamp((6 - v["value"]) / 12 * 100) if v else None


def _currency_risk(ind: dict) -> Optional[float]:
    v = ind.get("fx_depreciation")
    return _clamp(v["value"] / 50 * 100) if v else None


def _external_risk(ind: dict) -> Optional[float]:
    parts = []
    if "FI.RES.TOTL.MO" in ind:
        parts.append(_clamp((6 - ind["FI.RES.TOTL.MO"]["value"]) / 6 * 100))
    if "BN.CAB.XOKA.GD.ZS" in ind:
        parts.append(_clamp(-ind["BN.CAB.XOKA.GD.ZS"]["value"] / 10 * 100))
    return round(sum(parts) / len(parts), 1) if parts else None


def _debt_risk(ind: dict) -> Optional[float]:
    v = ind.get("DT.DOD.DECT.GN.ZS")
    return _clamp(v["value"]) if v else None


COMPONENTS: tuple[tuple[str, float, str, Callable[[dict], Optional[float]]], ...] = (
    ("political_stability", 0.20, "(2.5 - WGI political stability) / 5", _stability_risk),
    ("governance", 0.20, "(2.5 - mean of the other five WGI estimates) / 5", _governance_risk),
    ("inflation", 0.15, "CPI inflation / 40% (40% or more = 100)", _inflation_risk),
    ("currency", 0.15, "annual depreciation vs USD / 50% (50% or more = 100)", _currency_risk),
    ("external", 0.10, "mean of (6 - reserve months) / 6 and current-account deficit / 10% of GDP", _external_risk),
    ("growth", 0.10, "(6% - real GDP growth) / 12 points", _growth_risk),
    ("external_debt", 0.10, "external debt / 100% of GNI", _debt_risk),
)

TIERS = ((30, "low"), (45, "moderate"), (60, "elevated"), (75, "high"), (101, "severe"))


def tier(score: float) -> str:
    return next(name for limit, name in TIERS if score < limit)


# ── Data ──────────────────────────────────────────────────────────────────────

def _fetch_indicator(client: httpx.Client, indicator: str, source: Optional[int], since: int, until: int) -> dict:
    """{iso3: {year: value}} for all 54 countries, one request (retried: the API is slow)."""
    codes = ";".join(c.iso3 for c in COUNTRIES)
    params = {"format": "json", "date": f"{since}:{until}", "per_page": 2000}
    if source:
        params["source"] = source
    for attempt in range(3):
        try:
            data = client.get(WB_API.format(codes=codes, indicator=indicator), params=params).json()
            break
        except Exception as e:
            log.warning("World Bank %s attempt %d failed: %s", indicator, attempt + 1, e)
            time.sleep(2 ** attempt)
    else:
        return {}
    out: dict[str, dict[str, float]] = {}
    for row in data[1] if isinstance(data, list) and len(data) > 1 and data[1] else []:
        if row.get("value") is not None:
            out.setdefault(row["countryiso3code"], {})[row["date"]] = float(row["value"])
    return out


def refresh(since: int = 2018, until: Optional[int] = None, path: Path = INDICATORS_PATH) -> dict:
    """Download every indicator for every country and write the committed snapshot."""
    until = until or time.gmtime().tm_year
    series: dict[str, dict] = {}
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for indicator in GOVERNANCE:
            series[indicator] = _fetch_indicator(client, indicator, 3, since, until)
        for indicator in MACRO:
            series[indicator] = _fetch_indicator(client, indicator, None, since, until)
    # Never replace a known-good snapshot with a partial/empty response. The
    # World Bank API can return HTTP-200 error payloads or transiently omit a
    # series; silently publishing that result would erase country risk inputs.
    missing = [indicator for indicator, values in series.items() if not values]
    if missing:
        raise RuntimeError(
            "World Bank refresh returned no observations for: "
            + ", ".join(missing)
            + "; existing snapshot was left unchanged."
        )

    # Record coverage and actual observation years so downstream audits can
    # distinguish refresh date from the latest year actually reported.
    coverage = {}
    for indicator, by_country in series.items():
        country_latest = {
            iso3: max(int(year) for year in years)
            for iso3, years in by_country.items() if years
        }
        coverage[indicator] = {
            "countries_with_data": len(country_latest),
            "latest_observation_year": max(country_latest.values()) if country_latest else None,
            "countries_by_latest_year": {
                str(year): sum(1 for latest in country_latest.values() if latest == year)
                for year in sorted(set(country_latest.values()))
            },
        }

    snapshot = {
        "retrieved": time.strftime("%Y-%m-%d", time.gmtime()),
        "since": since,
        "source": "World Bank API (WDI and Worldwide Governance Indicators)",
        "coverage": coverage,
        "labels": {**GOVERNANCE, **MACRO},
        "series": series,
    }
    path.write_text(json.dumps(snapshot, indent=0, sort_keys=True))
    return snapshot


_SNAPSHOT: Optional[dict] = None


def load_snapshot(path: Path = INDICATORS_PATH) -> dict:
    global _SNAPSHOT
    if _SNAPSHOT is None or path != INDICATORS_PATH:
        try:
            snap = json.loads(path.read_text())
        except (OSError, ValueError):
            snap = {"series": {}, "labels": {**GOVERNANCE, **MACRO}}
        if path != INDICATORS_PATH:
            return snap
        _SNAPSHOT = snap
    return _SNAPSHOT


def latest_indicators(iso3: str, snapshot: Optional[dict] = None) -> dict[str, dict]:
    """{indicator: {"value", "year"}} using each indicator's most recent year, plus FX depreciation."""
    snap = snapshot if snapshot is not None else load_snapshot()
    out: dict[str, dict] = {}
    for indicator, by_country in snap.get("series", {}).items():
        years = by_country.get(iso3) or {}
        if years:
            year = max(years)
            out[indicator] = {"value": round(years[year], 3), "year": int(year)}
    fx = (snap.get("series", {}).get("PA.NUS.FCRF") or {}).get(iso3) or {}
    years = sorted(fx)
    if len(years) >= 2 and fx[years[-2]] > 0:
        dep = (fx[years[-1]] / fx[years[-2]] - 1) * 100
        out["fx_depreciation"] = {"value": round(dep, 2), "year": int(years[-1])}
    return out


_FX_CACHE: dict = {"at": 0.0, "rates": {}}


def spot_fx(currency: str, fetch: Optional[Callable[[], dict]] = None) -> Optional[float]:
    """Units of the currency per US dollar now (cached for an hour)."""
    if fetch is None and time.time() - _FX_CACHE["at"] > 3600:
        try:
            _FX_CACHE["rates"] = httpx.get(FX_API, timeout=10).json().get("rates", {})
            _FX_CACHE["at"] = time.time()
        except Exception as e:
            log.warning("spot FX unavailable: %s", e)
    rates = fetch() if fetch else _FX_CACHE["rates"]
    v = rates.get(currency)
    return float(v) if isinstance(v, (int, float)) else None


def assess(country: Country, snapshot: Optional[dict] = None,
           fx: Optional[Callable[[str], Optional[float]]] = None) -> dict:
    """Country risk profile: score, tier, every component with its formula and inputs."""
    ind = latest_indicators(country.iso3, snapshot)
    components = []
    total = weight = 0.0
    for name, w, formula, fn in COMPONENTS:
        risk = fn(ind)
        components.append({"name": name, "weight": w, "risk": risk, "formula": formula})
        if risk is not None:
            total += w * risk
            weight += w
    coverage = round(weight / sum(w for _, w, _, _ in COMPONENTS), 2)
    score = round(total / weight, 1) if weight else None
    snap = snapshot if snapshot is not None else load_snapshot()
    labels = snap.get("labels", {})
    return {
        "country": country.name, "iso2": country.iso2, "iso3": country.iso3, "region": country.region,
        "currency": country.currency, "exchange": country.exchange, "central_bank": country.central_bank,
        "securities_regulator": country.securities_regulator,
        "score": score, "tier": tier(score) if score is not None else None,
        "coverage": coverage,
        "components": components,
        "indicators": {k: {**v, "label": labels.get(k, "Annual change in official USD exchange rate (%)")}
                       for k, v in sorted(ind.items())},
        "spot_usd_rate": (fx or spot_fx)(country.currency),
        "data_as_of": snap.get("retrieved"),
        "method": "Weighted mean of component risks (0-100) over components with data; "
                  "tiers: <30 low, <45 moderate, <60 elevated, <75 high, else severe.",
    }


def assess_code(code: str, **kw) -> Optional[dict]:
    c = get(code)
    return assess(c, **kw) if c else None


def ranking(snapshot: Optional[dict] = None) -> list[dict]:
    """All 54 countries, riskiest first (spot FX omitted to keep it one request-free pass)."""
    rows = [assess(c, snapshot, fx=lambda _: None) for c in COUNTRIES]
    return sorted(rows, key=lambda r: (r["score"] is None, -(r["score"] or 0)))


def historical_scores(country: Country, snapshot: Optional[dict] = None, since: int = 2018,
                     until: Optional[int] = None) -> dict:
    """Annual risk history reconstructed from current historical source series.

    These are not archived vintage scores: publishers may revise historical observations.
    Each year uses only observations dated in that year or earlier, and exposes the latest
    input year per indicator so stale/missing inputs remain visible.
    """
    snap = snapshot if snapshot is not None else load_snapshot()
    until = until or time.gmtime().tm_year
    rows = []
    for year in range(since, until + 1):
        historical = {
            **{k: v for k, v in snap.items() if k not in ("series", "coverage")},
            "series": {
                indicator: {
                    country_code: {obs_year: value for obs_year, value in years.items() if int(obs_year) <= year}
                    for country_code, years in by_country.items()
                    if any(int(obs_year) <= year for obs_year in years)
                }
                for indicator, by_country in snap.get("series", {}).items()
            },
        }
        result = assess(country, historical, fx=lambda _: None)
        indicators = result["indicators"]
        rows.append({
            "year": year, "score": result["score"], "tier": result["tier"],
            "coverage": result["coverage"],
            "input_years": {key: value["year"] for key, value in indicators.items()},
            "indicator_count": len(indicators),
        })
    return {
        "country": country.name, "iso2": country.iso2, "iso3": country.iso3,
        "source": "World Bank World Development Indicators and Worldwide Governance Indicators",
        "source_url": f"https://api.worldbank.org/v2/country/{country.iso2.lower()}/indicator/FP.CPI.TOTL.ZG?format=json",
        "retrieved": snap.get("retrieved"),
        "method": "Historical reconstruction from currently available annual source observations; not a point-in-time archived vintage. Historical source revisions may change prior scores. Each year uses only observations dated in or before that year.",
        "rows": rows, "available_years": sum(1 for row in rows if row["score"] is not None),
    }
