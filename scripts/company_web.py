"""Company websites read with web-harvester, for company profiles.

    python scripts/company_web.py prepare crawl.json pages.jsonl companies.json   # which sites to read
    <web-harvester>/crawl -config crawl.json -i-have-reviewed-tos                # fetch them (robots.txt, rate limits)
    python scripts/company_web.py apply pages.jsonl companies.json               # read and store the facts

Runs in the hourly job (.github/workflows/scheduled-api-jobs.yml), after the election articles. The database is
reached as the API reaches it, through the shared-secret functions.
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
    from src import company_web

    if len(argv) >= 4 and argv[0] == "prepare":
        cfg, companies = company_web.crawl_config(argv[2])
        Path(argv[1]).write_text(json.dumps(cfg, indent=2))      # JSON is valid YAML for web-harvester
        Path(argv[3]).write_text(json.dumps(companies))
        print(json.dumps({"sites": [c["website"] for c in companies]}))
        return 0 if companies else 3                             # 3: nothing queued, skip the crawl
    if len(argv) >= 3 and argv[0] == "apply":
        pages_path, companies_path = Path(argv[1]), Path(argv[2])
        pages = [json.loads(ln) for ln in pages_path.read_text().splitlines() if ln.strip()] if pages_path.exists() else []
        companies = json.loads(companies_path.read_text()) if companies_path.exists() else []
        print(json.dumps(company_web.apply_crawl(companies, pages)))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
