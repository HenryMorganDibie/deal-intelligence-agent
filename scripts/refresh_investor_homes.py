"""Weekly: read source articles for investors whose home country is unknown, and record unambiguous descriptions
("X, a London-based fund") in the investor_homes table for the owner to review. Only direct publisher links are read,
each site's robots.txt is honoured, and the owner's own choices are never overwritten."""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib import robotparser
from urllib.parse import urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import hosted_market as hm  # noqa: E402
from src.engines import investor_origin as io  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("investor-homes")


def main() -> dict:
    if not hm._configured():
        return {"skipped": "database not configured"}
    r = hm._rpc_sync("investor_homes_all", {})
    io.use_homes(r.json() if r.status_code == 200 and isinstance(r.json(), list) else [])
    since = (date.today() - timedelta(days=365)).isoformat()
    deals = sorted((d for d in hm.deals() if (d.get("announced") or "") >= since),
                   key=lambda d: d.get("announced") or "", reverse=True)
    client = httpx.Client(headers={"User-Agent": io.USER_AGENT}, follow_redirects=True, timeout=12)
    robots: dict[str, robotparser.RobotFileParser | None] = {}
    last_hit: dict[str, float] = {}

    def allowed(url: str) -> bool:
        host = urlparse(url).netloc
        if host not in robots:
            rp = robotparser.RobotFileParser()
            try:
                resp = client.get(f"https://{host}/robots.txt")
                rp.parse(resp.text.splitlines() if resp.status_code == 200 else [])
                robots[host] = rp
            except httpx.HTTPError:
                robots[host] = None                  # robots.txt unreachable: do not read the site
        rp = robots[host]
        return bool(rp and rp.can_fetch(io.USER_AGENT, url))

    def fetch(url: str) -> str | None:
        if not allowed(url):
            return None
        host = urlparse(url).netloc
        wait = 1.0 - (time.monotonic() - last_hit.get(host, 0))
        if wait > 0:
            time.sleep(wait)                         # one request a second per site
        last_hit[host] = time.monotonic()
        try:
            resp = client.get(url)
        except httpx.HTTPError:
            return None
        return resp.text if resp.status_code == 200 and "html" in resp.headers.get("content-type", "") else None

    def record(key: str, name: str, country: str, sentence: str, url: str) -> None:
        resp = hm._rpc_sync("record_investor_home_from_article", {"p_name_key": key, "p_name": name,
                                                                  "p_country": country, "p_evidence": sentence,
                                                                  "p_url": url})
        if resp.status_code != 200:
            log.warning("could not record %s: %s", name, resp.text[:200])

    return io.read_articles(deals, fetch, record)


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
