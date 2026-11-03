"""Report outlet feeds that fail or return no items, so a dead source is noticed within a week.

    python scripts/check_feeds.py          # exits 1 when any feed fails outright
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from src.engines.market_feed import parse_feed  # noqa: E402
from src.tools.africa_tool import AFRICAN_NEWS_FEEDS  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) deal-intelligence-agent/1.0"}


async def check(client: httpx.AsyncClient, sem: asyncio.Semaphore, name: str, url: str) -> tuple[str, int, str]:
    async with sem:
        for attempt in range(2):
            try:
                response = await client.get(url)
                response.raise_for_status()
                return name, len(parse_feed(response.text)), ""
            except Exception as exc:  # noqa: BLE001 - every failure is reported, none is fatal
                error = f"{type(exc).__name__} {getattr(getattr(exc, 'response', None), 'status_code', '')}".strip()
                await asyncio.sleep(3 * (attempt + 1))
        return name, -1, error


async def main() -> int:
    sem = asyncio.Semaphore(6)
    async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers=HEADERS) as client:
        results = await asyncio.gather(*(check(client, sem, n, u) for n, u in AFRICAN_NEWS_FEEDS.items()))
    failed = [r for r in results if r[1] < 0]
    empty = [r for r in results if r[1] == 0]
    for name, _, error in failed:
        print(f"::error::{name} failed: {error} ({AFRICAN_NEWS_FEEDS[name]})")
    for name, _, _ in empty:
        print(f"::warning::{name} returned no items in its window ({AFRICAN_NEWS_FEEDS[name]})")
    print(f"{len(results) - len(failed) - len(empty)}/{len(results)} feeds returned items; "
          f"{len(empty)} empty, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
