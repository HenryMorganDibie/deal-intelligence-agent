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
from datetime import date, datetime
from typing import Callable, Optional

import httpx

from src.data.africa_countries import COUNTRIES, Country, get

log = logging.getLogger(__name__)

# Committed reference data (not a runtime store under data/): written only by `countries --refresh`.
_REFERENCE = Path(__file__).resolve().parent.parent / "data"
INDICATORS_PATH = _REFERENCE / "country_indicators.json"
CURRENT_SIGNALS_PATH = _REFERENCE / "current_macro_signals.json"
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
    """Fetch every World Bank API page into {iso3: {year: value}} for all 54 countries."""
    codes = ";".join(c.iso3 for c in COUNTRIES)
    params = {"format": "json", "date": f"{since}:{until}", "per_page": 2000, "page": 1}
    if source:
        params["source"] = source
    out: dict[str, dict[str, float]] = {}
    page = 1
    page_count = 1
    while page <= page_count:
        request_params = {**params, "page": page}
        for attempt in range(3):
            try:
                response = client.get(WB_API.format(codes=codes, indicator=indicator), params=request_params)
                response.raise_for_status()
                data = response.json()
                if not (isinstance(data, list) and len(data) > 1 and isinstance(data[0], dict)):
                    raise ValueError("Unexpected World Bank API response shape")
                metadata = data[0]
                page_count = max(1, int(metadata.get("pages") or 1))
                rows = data[1] or []
                for row in rows:
                    if row.get("value") is not None:
                        out.setdefault(row["countryiso3code"], {})[row["date"]] = float(row["value"])
                break
            except Exception as e:
                log.warning("World Bank %s page %d attempt %d failed: %s", indicator, page, attempt + 1, e)
                if attempt == 2:
                    return {}
                time.sleep(2 ** attempt)
        page += 1
    return out

def refresh(since: int = 1960, until: Optional[int] = None, path: Path = INDICATORS_PATH) -> dict:
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


# An input more than this many years older than the latest year in the data is not scored: a 2015 growth rate
# says little about a country's risk today. It is still listed, marked stale.
MAX_INPUT_AGE_YEARS = 3


def fx_series_after_break(series: dict) -> tuple[dict, Optional[int]]:
    """An LCU-per-USD series from its last currency redenomination on, and that year (or None).

    A fall of 90% or more in local currency per dollar in one year is a new currency (Zimbabwe's ZWL to ZiG
    in 2024: 3,266 to 26.6), not an appreciation; values before it are in a different unit and are dropped."""
    years = sorted(series, key=int)
    start, broke = 0, None
    for i in range(1, len(years)):
        prev, cur = series[years[i - 1]], series[years[i]]
        if prev and prev > 0 and cur / prev <= 0.1:
            start, broke = i, int(years[i])
    return {y: series[y] for y in years[start:]}, broke


def reference_year(snapshot: dict) -> Optional[int]:
    """The latest year with any observation in the snapshot: the 'now' that input ages are measured from."""
    return max((int(y) for by_country in snapshot.get("series", {}).values() for years in by_country.values()
                for y in years), default=None)


def latest_indicators(iso3: str, snapshot: Optional[dict] = None) -> dict[str, dict]:
    """{indicator: {"value", "year", "stale"}} using each indicator's most recent year, plus FX depreciation
    over consecutive years within the current currency."""
    snap = snapshot if snapshot is not None else load_snapshot()
    ref = reference_year(snap)
    out: dict[str, dict] = {}
    for indicator, by_country in snap.get("series", {}).items():
        years = by_country.get(iso3) or {}
        if years:
            year = max(years, key=int)
            out[indicator] = {"value": round(years[year], 3), "year": int(year)}
    fx, broke = fx_series_after_break((snap.get("series", {}).get("PA.NUS.FCRF") or {}).get(iso3) or {})
    years = sorted(fx, key=int)
    if len(years) >= 2 and int(years[-1]) - int(years[-2]) == 1 and fx[years[-2]] > 0:
        dep = (fx[years[-1]] / fx[years[-2]] - 1) * 100
        out["fx_depreciation"] = {"value": round(dep, 2), "year": int(years[-1])}
    if broke is not None:
        out.setdefault("fx_depreciation", {"value": None, "year": broke})["redenominated"] = broke
    for v in out.values():
        v["stale"] = bool(ref and v.get("year") and ref - v["year"] > MAX_INPUT_AGE_YEARS)
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



def _normalize_current_macro_payload(country: Country, payload: dict) -> dict:
    """Keep only source-attributed, higher-frequency macro and FX observations."""
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        raise ValueError("Unexpected current-signals response")
    observations = data.get("observations") or []
    keep = {
        "inflation_cpi_latest_yoy_pct",
        "policy_rate_pct",
        "official_exchange_rate_latest_lcu_per_usd",
        "overnight_interbank_rate_pct",
        "interbank_7d_rate_pct",
    }
    normalized = []
    for item in observations:
        if not isinstance(item, dict) or item.get("metric_key") not in keep:
            continue
        value = item.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        frequency = str(item.get("frequency") or "").lower()
        # Never relabel annual observations as more current just because the API
        # returned them in its compact country snapshot.
        if frequency == "annual":
            continue
        normalized.append({
            "metric_key": item.get("metric_key"),
            "name": item.get("name") or item.get("metric_key"),
            "value": value,
            "unit": item.get("unit"),
            "frequency": frequency or "unspecified",
            "source": item.get("source"),
            "freshness": item.get("freshness"),
            "as_of_period": item.get("as_of_period"),
            "retrieved_at": item.get("retrieved_at"),
            "location_name": item.get("location_name"),
        })
    for item in data.get("fx_rates") or []:
        if not isinstance(item, dict) or item.get("quote_currency") != country.currency:
            continue
        value = item.get("rate")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        normalized.append({
            "metric_key": "fx_usd_daily",
            "name": f"USD to {country.currency} exchange rate",
            "value": value,
            "unit": f"{country.currency} per USD",
            "frequency": "daily",
            "source": item.get("source"),
            "freshness": item.get("freshness"),
            "as_of_period": item.get("date") or item.get("rate_date"),
            "retrieved_at": item.get("retrieved_at") or item.get("created_at"),
            "location_name": None,
        })
    normalized.sort(key=lambda row: (row.get("metric_key") or "", row.get("name") or ""))
    return {
        "status": "available" if normalized else "no_observations",
        "source": "Africa API (source attribution retained per observation)",
        "source_url": "https://africa-api.com/docs/signals",
        "generated_at": data.get("generated_at"),
        "observations": normalized,
        "message": None if normalized else "No higher-frequency macro or FX observations are available for this country from the supplemental source.",
    }


_CURRENT_SIGNALS_SNAPSHOT: Optional[dict] = None


def load_current_signals_snapshot(path: Optional[Path] = None) -> dict:
    """Read the committed supplemental snapshot; the hosted API needs no provider key."""
    global _CURRENT_SIGNALS_SNAPSHOT
    path = path or CURRENT_SIGNALS_PATH
    if _CURRENT_SIGNALS_SNAPSHOT is None or path != CURRENT_SIGNALS_PATH:
        try:
            value = json.loads(path.read_text())
            snapshot = value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            snapshot = {}
        if path != CURRENT_SIGNALS_PATH:
            return snapshot
        _CURRENT_SIGNALS_SNAPSHOT = snapshot
    return _CURRENT_SIGNALS_SNAPSHOT


SIGNAL_LABELS = {
    "fx_usd_daily": "Exchange rate, daily",
    "official_exchange_rate_latest_lcu_per_usd": "Official exchange rate",
    "policy_rate_pct": "Central bank policy rate",
    "inflation_cpi_latest_yoy_pct": "Consumer price inflation, year on year",
    "overnight_interbank_rate_pct": "Overnight interbank rate",
    "interbank_7d_rate_pct": "7-day interbank rate",
}
# How old an observation can be, by frequency, before it is flagged as out of date.
_STALE_AFTER_DAYS = {"daily": 14, "weekly": 45, "monthly": 120, "quarterly": 200}


def _period_age_days(period: Optional[str], today: date) -> Optional[int]:
    try:
        text = str(period or "")
        d = date.fromisoformat(text[:10]) if len(text) >= 10 else date.fromisoformat(text[:7] + "-01")
    except ValueError:
        return None
    return (today - d).days


def annotate_current_signals(country: Country, stored: dict, run_at: Optional[str] = None,
                             today: Optional[date] = None) -> dict:
    """Stored signals with a readable label per observation, an out-of-date flag (the provider's own
    "historical" tag, or older than its frequency allows), official exchange rates that disagree with the daily
    rate (or, with no daily rate, the World Bank's latest annual rate) by more than half flagged as inconsistent,
    and countries whose figures were kept from an earlier refresh marked as retained."""
    today = today or date.today()
    rows = [dict(o) for o in stored.get("observations") or []]
    daily = next((o["value"] for o in rows if o.get("metric_key") == "fx_usd_daily" and o.get("value")), None)
    if daily is None:
        annual = ((load_snapshot().get("series", {}).get("PA.NUS.FCRF") or {}).get(country.iso3) or {})
        annual, _ = fx_series_after_break(annual)
        daily = annual[max(annual, key=int)] if annual else None
    for o in rows:
        o["label"] = SIGNAL_LABELS.get(o.get("metric_key"), str(o.get("name") or o.get("metric_key")).replace("_", " "))
        age = _period_age_days(o.get("as_of_period"), today)
        limit = _STALE_AFTER_DAYS.get(str(o.get("frequency") or ""))
        if o.get("metric_key") == "policy_rate_pct":
            # A policy rate holds until the next decision, so its date is the last decision; only a decision
            # more than a year old suggests the figure has not been kept up to date.
            o["out_of_date"] = bool(age is not None and age > 365)
        else:
            o["out_of_date"] = o.get("freshness") == "historical" or bool(age is not None and limit and age > limit)
        if o.get("metric_key") == "official_exchange_rate_latest_lcu_per_usd" and daily and o.get("value"):
            ratio = o["value"] / daily
            o["inconsistent"] = not (2 / 3 <= ratio <= 1.5)
    retained = bool(stored.get("retained"))
    if not retained and run_at and stored.get("generated_at"):
        try:
            gap = datetime.fromisoformat(run_at.replace("Z", "+00:00")) - datetime.fromisoformat(
                str(stored["generated_at"]).replace("Z", "+00:00"))
            retained = gap.total_seconds() > 6 * 3600
        except ValueError:
            pass
    return {**stored, "observations": rows, "retained": retained,
            "retained_since": stored.get("retained_since") or (stored.get("generated_at") if retained else None)}


def current_macro_signals(country: Country, fetch: Optional[Callable[[Country], dict]] = None) -> dict:
    """Return committed high-frequency signals, separate from annual risk scoring.

    The scheduled GitHub Actions workflow fetches and commits this snapshot. The
    hosted API only reads the snapshot, so Africa API credentials stay in Actions.
    ```fetch``` is retained as an injection point for unit tests and refresh tooling.
    """
    if fetch is not None:
        try:
            return _normalize_current_macro_payload(country, fetch(country))
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            log.info("Current macro signals unavailable for %s (%s)", country.iso2, type(exc).__name__)
            return {
                "status": "unavailable", "source": "Africa API",
                "source_url": "https://africa-api.com/docs/signals", "generated_at": None,
                "observations": [],
                "message": "The supplemental source could not be reached. Annual World Bank indicators remain available; this does not affect the country risk score.",
            }

    snapshot = load_current_signals_snapshot()
    countries = snapshot.get("countries", {}) if isinstance(snapshot, dict) else {}
    stored = countries.get(country.iso2.upper()) if isinstance(countries, dict) else None
    if isinstance(stored, dict):
        return annotate_current_signals(country, stored, snapshot.get("generated_at"))
    return {
        "status": "not_configured" if not snapshot else "no_observations",
        "source": "Africa API",
        "source_url": "https://africa-api.com/docs/signals",
        "generated_at": snapshot.get("generated_at") if isinstance(snapshot, dict) else None,
        "observations": [],
        "message": "Supplemental country signals have not yet been refreshed by GitHub Actions. Annual World Bank indicators remain available; this does not affect the country risk score.",
    }


def assess(country: Country, snapshot: Optional[dict] = None,
           fx: Optional[Callable[[str], Optional[float]]] = None) -> dict:
    """Country risk profile: score, tier, every component with its formula and inputs."""
    ind = latest_indicators(country.iso3, snapshot)
    # Stale inputs and a missing post-redenomination change are not scored.
    usable = {k: v for k, v in ind.items() if not v.get("stale") and v.get("value") is not None}
    components = []
    total = weight = 0.0
    for name, w, formula, fn in COMPONENTS:
        risk = fn(usable)
        components.append({"name": name, "weight": w, "risk": risk, "formula": formula})
        if risk is not None:
            total += w * risk
            weight += w
    coverage = round(weight / sum(w for _, w, _, _ in COMPONENTS), 2)
    score = round(total / weight, 1) if weight else None
    missing = [c["name"] for c in components if c["risk"] is None]
    snap = snapshot if snapshot is not None else load_snapshot()
    labels = snap.get("labels", {})
    return {
        "country": country.name, "iso2": country.iso2, "iso3": country.iso3, "region": country.region,
        "currency": country.currency, "exchange": country.exchange, "central_bank": country.central_bank,
        "securities_regulator": country.securities_regulator,
        "score": score, "tier": tier(score) if score is not None else None,
        "coverage": coverage,
        # A partial score averages only the components with recent data, so it can understate the risk of a
        # country whose missing inputs are the weak ones.
        "partial": bool(missing), "missing_components": missing,
        "stale_inputs": sorted(k for k, v in ind.items() if v.get("stale")),
        "redenominated": (ind.get("fx_depreciation") or {}).get("redenominated"),
        "components": components,
        "indicators": {k: {**v, "label": labels.get(k, "Annual change in official USD exchange rate (%)")}
                       for k, v in sorted(ind.items())},
        "spot_usd_rate": (fx or spot_fx)(country.currency),
        "data_as_of": snap.get("retrieved"),
        "method": "Weighted mean of component risks (0-100) over components with data from the last "
                  f"{MAX_INPUT_AGE_YEARS} years; tiers: <30 low, <45 moderate, <60 elevated, <75 high, else severe. "
                  "Older inputs are listed but not scored, and the year after a currency redenomination has no "
                  "depreciation figure.",
    }


def assess_code(code: str, **kw) -> Optional[dict]:
    c = get(code)
    return assess(c, **kw) if c else None


def ranking(snapshot: Optional[dict] = None) -> list[dict]:
    """All 54 countries, riskiest first (spot FX omitted to keep it one request-free pass)."""
    rows = [assess(c, snapshot, fx=lambda _: None) for c in COUNTRIES]
    return sorted(rows, key=lambda r: (r["score"] is None, -(r["score"] or 0)))


def historical_scores(country: Country, snapshot: Optional[dict] = None, since: int = 1960,
                     until: Optional[int] = None) -> dict:
    """Annual risk history reconstructed from current historical source series.

    These are not archived vintage scores: publishers may revise historical observations.
    Each year uses only observations dated in that year or earlier, and exposes the latest
    input year per indicator so stale/missing inputs remain visible.
    """
    snap = snapshot if snapshot is not None else load_snapshot()
    available_years = [
        int(obs_year)
        for by_country in snap.get("series", {}).values()
        for years in by_country.values()
        for obs_year in years
    ]
    until = until or max(available_years, default=time.gmtime().tm_year)
    # Use years in which this country has at least one source observation. Years with no
    # observation are omitted rather than presented as measured annual changes.
    country_observation_years = sorted({
        int(obs_year)
        for by_country in snap.get("series", {}).values()
        for obs_year in (by_country.get(country.iso3) or {})
        if since <= int(obs_year) <= until
    })
    rows = []
    for year in country_observation_years:
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
        # Do not publish a composite historical score from a partial component set.
        # This is a completeness rule, not a statistically validated confidence threshold.
        complete_components = result["coverage"] == 1.0
        rows.append({
            "year": year, "score": result["score"] if complete_components else None,
            "tier": result["tier"] if complete_components else None,
            "coverage": result["coverage"],
            "input_years": {key: value["year"] for key, value in indicators.items()},
            "indicator_count": len(indicators),
        })
    return {
        "country": country.name, "iso2": country.iso2, "iso3": country.iso3,
        "source": "World Bank World Development Indicators and Worldwide Governance Indicators",
        "source_url": f"https://api.worldbank.org/v2/country/{country.iso2.lower()}/indicator/FP.CPI.TOTL.ZG?format=json",
        "retrieved": snap.get("retrieved"),
        "method": "Historical reconstruction from currently available annual source observations; not a point-in-time archived vintage. Historical source revisions may change prior scores. Each year uses only observations dated in or before that year. Coverage is the share of the seven weighted risk components with usable inputs; it is an internal component-availability measure, not an official data-quality or confidence metric. A historical composite score/tier is shown only when all seven components are available (100% component coverage); otherwise only coverage and input years are shown. Component observation years can differ and are exposed per row.",
        "rows": rows, "available_years": sum(1 for row in rows if row["score"] is not None),
    }
