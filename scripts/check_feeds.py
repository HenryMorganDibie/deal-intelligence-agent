"""Check every outlet feed and replace the ones that died.

    python scripts/check_feeds.py          # report only
    python scripts/check_feeds.py --heal   # also save replacements to src/data/feed_overrides.json

A replacement always comes from the same outlet (its advertised feed, a standard feed address on its site, or
Google News limited to its site), and is dropped as soon as the preferred feed works again. Exits 1 only when an
outlet has no working feed at all.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.engines import feed_healing  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--heal", action="store_true", help="save replacements for dead feeds")
    args = parser.parse_args()
    before = feed_healing.load_overrides()
    overrides, changes, unresolved, dormant = asyncio.run(feed_healing.heal_all(overrides=before))
    for line in changes:
        print(f"::notice::{line}")
    for line in dormant:
        print(f"::warning::{line}")
    for line in unresolved:
        print(f"::error::{line}")
    for name, entry in sorted(overrides.items()):
        print(f"{name}: reading {entry['url']} since {entry.get('since', '?')} ({entry.get('reason', '')})")
    if args.heal and overrides != before:
        feed_healing.save_overrides(overrides)
        print(f"Saved {len(overrides)} replacement(s).")
    from src.tools.africa_tool import AFRICAN_NEWS_FEEDS
    print(f"{len(AFRICAN_NEWS_FEEDS) - len(unresolved)}/{len(AFRICAN_NEWS_FEEDS)} outlets have a working feed; "
          f"{len(overrides)} on a replacement, {len(dormant)} dormant.")
    return 1 if unresolved else 0


if __name__ == "__main__":
    sys.exit(main())
