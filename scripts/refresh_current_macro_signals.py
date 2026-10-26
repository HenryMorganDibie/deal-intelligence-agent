#!/usr/bin/env python3
"""Refresh higher-frequency country signals into a committed, key-free snapshot.

The free Africa API plan allows five requests per minute. This deliberately
paces one request every 12.2 seconds and batches each country's available
signals into a single request.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.data.africa_countries import COUNTRIES
from src.engines import country_risk

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("refresh-current-macro-signals")
OUTPUT = country_risk.CURRENT_SIGNALS_PATH
API_URL = "https://api.africa-api.com/v1/countries/{code}/signals"
REQUEST_INTERVAL_SECONDS = 12.5


def main() -> int:
    api_key = os.environ.get("AFRICA_API_KEY", "").strip()
    if not api_key:
        log.warning("AFRICA_API_KEY is not set; keeping the existing supplemental snapshot unchanged.")
        return 0

    try:
        old_snapshot = json.loads(OUTPUT.read_text())
        old_countries = old_snapshot.get("countries", {}) if isinstance(old_snapshot, dict) else {}
    except (OSError, ValueError):
        old_snapshot, old_countries = {}, {}

    countries: dict[str, dict] = {}
    failures = 0
    success_count = 0
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client:
        for index, country in enumerate(COUNTRIES):
            if index:
                time.sleep(REQUEST_INTERVAL_SECONDS)
            try:
                response = client.get(API_URL.format(code=country.iso2.lower()))
                response.raise_for_status()
                payload = response.json()
                result = country_risk._normalize_current_macro_payload(country, payload)
                result["country_code"] = country.iso2.upper()
                result["country_name"] = country.name
                countries[country.iso2.upper()] = result
                success_count += 1
                log.info("%s: %s (%d higher-frequency observations)", country.iso2, result["status"],
                         len(result["observations"]))
            except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
                failures += 1
                # Keep the last successful country's snapshot if one exists. Never
                # replace good published data with a transient provider failure.
                previous = old_countries.get(country.iso2.upper())
                if isinstance(previous, dict):
                    countries[country.iso2.upper()] = previous
                else:
                    countries[country.iso2.upper()] = {
                        "status": "unavailable",
                        "source": "Africa API",
                        "source_url": "https://africa-api.com/docs/signals",
                        "generated_at": None,
                        "country_code": country.iso2.upper(),
                        "country_name": country.name,
                        "observations": [],
                        "message": "The supplemental source could not be reached during the last refresh; annual World Bank indicators remain available.",
                    }
                log.warning("%s refresh failed (%s); retained previous data where available",
                            country.iso2, type(exc).__name__)

    if success_count == 0:
        raise RuntimeError("No country signal requests succeeded; existing snapshot was left unchanged.")

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": "Africa API country signals endpoint",
        "source_url": "https://africa-api.com/docs/signals",
        "countries_requested": len(COUNTRIES),
        "countries_refreshed": success_count,
        "countries_failed": failures,
        "countries": countries,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    temporary.replace(OUTPUT)
    log.info("Wrote %s: %d/%d countries refreshed, %d request failures",
             OUTPUT, success_count, len(COUNTRIES), failures)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
