"""Fill daily price history back to 2010 for every listed share the platform prices (see src/engines/price_history.py).

    python scripts/backfill_price_history.py                     # every exchange a source covers
    python scripts/backfill_price_history.py --exchanges brvm ngx
    python scripts/backfill_price_history.py --exchanges jse --limit 5 --dry-run

Resumable: a listing that already has saved history is skipped, and each listing is saved as soon as it is read,
so a run that stops part-way continues where it left off. One request every 0.7 seconds per site.
Needs SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY and DEAL_INTEL_API_SECRET.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import hosted_market as hm  # noqa: E402
from src.engines import price_history as ph  # noqa: E402


def listings() -> dict[str, list[str]]:
    """Every exchange's symbols in the latest daily quotes snapshot, largest first."""
    r = hm._rpc_sync("list_market_snapshots", {"p_kind": "quotes"}, 60)
    r.raise_for_status()
    out = {}
    for row in r.json() or []:
        rows = (row.get("payload") or {}).get("rows") or []
        rows = sorted(rows, key=lambda x: -(x.get("mcap") or 0))
        out[row["scope"]] = [x["symbol"] for x in rows if x.get("symbol")]
    return out


def saved(exchange: str) -> set[str]:
    r = hm._rpc_sync("price_history_years_saved", {"p_exchange": exchange}, 60)
    r.raise_for_status()
    return {s.upper() for s in (r.json() or {})}


def save(rows: list[dict]) -> int:
    total = 0
    for i in range(0, len(rows), 20):
        r = hm._rpc_sync("upsert_price_history", {"p_rows": rows[i:i + 20]}, 60)
        if r.status_code != 200:
            print(f"::error::saving failed: {r.status_code} {r.text[:200]}", flush=True)
            return total
        total += int(r.json() or 0)
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exchanges", nargs="*", default=ph.exchanges())
    parser.add_argument("--limit", type=int, default=0, help="at most this many listings per exchange")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--minutes", type=float, default=330, help="stop cleanly after this long")
    args = parser.parse_args()
    if not hm._configured():
        print("::error::SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY and DEAL_INTEL_API_SECRET are required.")
        return 1
    deadline = time.monotonic() + args.minutes * 60
    end = date.today() - timedelta(days=1)
    by_exchange = listings()
    summary = []
    with httpx.Client(headers=ph.HEADERS, timeout=30, follow_redirects=True) as client:
        for ex in args.exchanges:
            if ex not in ph.YAHOO_SUFFIX and ex not in ph.SIKA_PLACE:
                print(f"::warning::{ex}: no history source", flush=True)
                continue
            symbols = by_exchange.get(ex) or []
            done = saved(ex) if not args.dry_run else set()
            todo = [s for s in symbols if s.upper() not in done]
            if args.limit:
                todo = todo[:args.limit]
            sika_map = None
            if ex in ph.SIKA_PLACE:
                page = client.get(f"https://www.sikafinance.com/marches/aaz?placeCode={ph.SIKA_PLACE[ex]}")
                time.sleep(ph.PAUSE)
                sika_map = ph.sika_tickers(page.text if page.status_code == 200 else "")
            filled = empty = 0
            first_year = None
            print(f"{ex}: {len(symbols)} listings, {len(done)} already saved, {len(todo)} to read", flush=True)
            for sym in todo:
                if time.monotonic() > deadline:
                    print("Time limit reached; the next run continues from here.", flush=True)
                    break
                points, source = ph.history_for(client, ex, sym, sika_map, ph.START, end)
                rows = ph.pack_years(ex, sym, points, source)
                if not rows:
                    empty += 1
                    continue
                filled += 1
                first_year = min(first_year or 9999, rows[0]["year"])
                n = len(points) if args.dry_run else save(rows)
                print(f"  {sym}: {len(points)} days from {rows[0]['year']} ({n} {'days' if args.dry_run else 'years saved'})",
                      flush=True)
            summary.append(f"{ex}: {filled} listings filled, {empty} with no history found, earliest {first_year}")
            if time.monotonic() > deadline:
                break
    for line in summary:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
