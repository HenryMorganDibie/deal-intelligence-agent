"""Save the IMF World Economic Outlook figures the country pages show (growth, inflation, government debt, current
account) for the 54 African countries, to src/data/imf_outlook.json.

The IMF's DataMapper API refuses requests from the hosting provider's servers, and it updates only twice a year
(April and October), so the figures are kept in the repository and refreshed by a monthly workflow instead of read
live. Run: python scripts/refresh_imf_outlook.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data import africa_countries  # noqa: E402
from src.engines.country_dashboard import IMF_INDICATORS, IMF_URL  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "src" / "data" / "imf_outlook.json"


def main() -> int:
    today = date.today()
    years = {str(y) for y in range(today.year - 6, today.year + 6)}
    iso3 = {c.iso3 for c in africa_countries.COUNTRIES}
    series: dict[str, dict] = {}
    with httpx.Client(timeout=30, headers={"User-Agent": "deal-intelligence/1.0"}) as client:
        for indicator in IMF_INDICATORS:
            r = client.get(IMF_URL.format(indicator=indicator))
            r.raise_for_status()
            values = (r.json().get("values") or {}).get(indicator) or {}
            series[indicator] = {code: {y: v for y, v in row.items() if y in years}
                                 for code, row in values.items() if code in iso3}
            if not series[indicator]:
                print(f"{indicator}: no African series returned", file=sys.stderr)
                return 1
    out = {"retrieved": today.isoformat(), "source": "IMF World Economic Outlook (DataMapper API)", "series": series}
    previous = json.loads(OUT.read_text()) if OUT.exists() else {}
    if previous.get("series") == series:
        print("IMF outlook unchanged")
        return 0
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(f"IMF outlook saved: {sum(len(v) for v in series.values())} country series")
    return 0


if __name__ == "__main__":
    sys.exit(main())
