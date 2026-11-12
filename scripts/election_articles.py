"""Full-article tagging for election news, with web-harvester doing the fetching.

    python scripts/election_articles.py prepare crawl.json pages.jsonl   # which articles to read
    <web-harvester>/crawl -config crawl.json -i-have-reviewed-tos        # fetch them (robots.txt, rate limits)
    python scripts/election_articles.py apply pages.jsonl                # re-tag the stories, store the tags

Runs in the hourly election-news job (.github/workflows/scheduled-api-jobs.yml). The database is reached as the
API reaches it, through the shared-secret functions; the article text is used for tagging and not stored.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DEAL_INTEL_DATA_DIR", "/tmp/deal-intel-data")
for _name in ("DEAL_INTEL_API_SECRET", "SUPABASE_PUBLISHABLE_KEY"):
    if os.environ.get(_name):
        os.environ[_name] = os.environ[_name].strip()


def main(argv: list[str]) -> int:
    from src import election_feed

    if len(argv) >= 3 and argv[0] == "prepare":
        cfg = election_feed.crawl_config(argv[2])
        Path(argv[1]).write_text(json.dumps(cfg, indent=2))      # JSON is valid YAML for web-harvester
        pages = sum(len(t["start_urls"]) for t in cfg["targets"])
        print(json.dumps({"articles_to_read": pages, "outlets": [t["name"] for t in cfg["targets"]]}))
        return 0
    if len(argv) >= 2 and argv[0] == "apply":
        path = Path(argv[1])
        pages = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
        print(json.dumps(election_feed.apply_crawl(pages)))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
