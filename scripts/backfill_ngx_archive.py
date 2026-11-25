"""Fill NGX's daily price history from the exchange's own daily price lists (mid-2014 onwards; see
src/engines/ngx_archive.py).

    python scripts/backfill_ngx_archive.py                 # every year not yet filled from NGX's lists
    python scripts/backfill_ngx_archive.py --years 2015 2016
    python scripts/backfill_ngx_archive.py --years 2014 --limit 5 --dry-run

A year is read whole and then saved, replacing any third-party history for it. Years already filled from NGX's own
lists are skipped, except the current one. One request every 0.7 seconds. Needs SUPABASE_URL,
SUPABASE_PUBLISHABLE_KEY and DEAL_INTEL_API_SECRET.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import hosted_market as hm  # noqa: E402
from src.engines import ngx_archive as na  # noqa: E402
from src.engines import price_history as ph  # noqa: E402


def library_files(client: httpx.Client) -> list[str]:
    """Every file path in NGX's DownloadsContent library, following its pages."""
    url, refs = na.LIST_ITEMS, []
    while url:
        r = client.get(url, headers={"Accept": "application/atom+xml"})
        r.raise_for_status()
        refs += re.findall(r"<d:FileRef>([^<]*)<", r.text)
        nxt = re.search(r'<link rel="next" href="([^"]+)"', r.text)
        url = nxt.group(1).replace("&amp;", "&") if nxt else None
        time.sleep(1)
    return refs


def years_done() -> set[int]:
    r = hm._rpc_sync("price_history_year_sources", {"p_exchange": "ngx"}, 60)
    if r.status_code != 200:
        return set()
    return {int(y) for y, sources in (r.json() or {}).items() if na.SOURCE in (sources or {})}


def save(rows: list[dict]) -> int:
    total = 0
    for i in range(0, len(rows), 25):
        r = hm._rpc_sync("upsert_price_history", {"p_rows": rows[i:i + 25]}, 90)
        if r.status_code != 200:
            print(f"::error::saving failed: {r.status_code} {r.text[:200]}", flush=True)
            return total
        total += int(r.json() or 0)
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="*", type=int)
    parser.add_argument("--limit", type=int, default=0, help="at most this many days per year (testing)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not hm._configured():
        print("::error::SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY and DEAL_INTEL_API_SECRET are required.")
        return 1
    end = date.today() - timedelta(days=1)
    with httpx.Client(headers=ph.HEADERS, timeout=90, follow_redirects=True) as client:
        files = na.zip_refs(library_files(client))
        by_year: dict[int, list[date]] = defaultdict(list)
        for day in sorted(files):
            if day <= end:
                by_year[day.year].append(day)
        done = set() if args.dry_run else years_done()
        wanted = args.years or sorted(by_year)
        print(f"NGX library: {len(files)} daily price lists, {min(files)} to {max(files)}", flush=True)
        for year in wanted:
            if year in done and year != end.year and not args.years:
                print(f"{year}: already filled from NGX's lists", flush=True)
                continue
            days = by_year.get(year, [])
            if args.limit:
                days = days[:args.limit]
            series: dict[str, list[tuple[date, float]]] = defaultdict(list)
            read = missing = 0
            for day in days:
                r = client.get(na.LIBRARY + quote(files[day]))
                time.sleep(ph.PAUSE)
                parsed_day, rows = na.parse_zip(r.content) if r.status_code == 200 else (None, {})
                if not rows:
                    missing += 1
                    continue
                if parsed_day and parsed_day != day:
                    print(f"  {day}: the list inside says {parsed_day}; using {parsed_day}", flush=True)
                read += 1
                for sym, row in rows.items():
                    series[sym].append((parsed_day or day, row["close"]))
            packed = [row for sym, points in series.items()
                      for row in ph.pack_years("ngx", sym, points, na.SOURCE) if row["year"] == year]
            n = len(packed) if args.dry_run else save(packed)
            print(f"{year}: {read} trading days read, {missing} unreadable, {len(series)} shares, "
                  f"{n} {'rows packed' if args.dry_run else 'rows saved'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
