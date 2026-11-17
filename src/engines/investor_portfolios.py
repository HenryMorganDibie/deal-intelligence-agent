"""
African investors' published portfolios: the companies each firm lists on its own portfolio page.

A firm's portfolio page names companies it backs that often never announced a round, so it maps a private company
to its investors where the press has nothing. Each page is read only where its robots.txt allows, under an agent
that names this product. Names are taken from the page's logo captions and headings; a company is linked to a
firm only when its name equals a portfolio entry (legal suffixes aside), so page furniture ("Facebook link",
"site logo") can never attach to a company.

Snapshot: src/data/investor_portfolios.json, refreshed weekly by scripts/refresh_investor_portfolios.py.
"""
from __future__ import annotations

import html as html_mod
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger(__name__)

_REFERENCE = Path(__file__).resolve().parent.parent / "data"      # committed reference data, like merger_filings
SNAPSHOT_PATH = _REFERENCE / "investor_portfolios.json"
USER_AGENT = "Mozilla/5.0 (compatible; DealIntelligence/1.0; +https://deal-intelligence.app)"

FIRMS = {
    "TLcom Capital": "https://tlcomcapital.com/portfolio",
    "Novastar Ventures": "https://www.novastarventures.com/portfolio",
    "Ventures Platform": "https://venturesplatform.com/portfolio",
    "4DX Ventures": "https://www.4dxventures.com/portfolio",
    "AfricInvest": "https://www.africinvest.com/portfolio",
    "Phatisa": "https://phatisa.com/portfolio",
    "Partech": "https://partechpartners.com/companies",
}
# Not read: Kepple Africa Ventures and Algebra Ventures (their pages carry headings and filler text, not a company
# list), Microtraction (no names survive the furniture filter); Future Africa, P1, Launch Africa, Janngo, Helios,
# DPI, Flat6Labs and Savannah Fund (no portfolio page at the address); LoftyInc, CRE, Enza, Raba (unreachable).

_FURNITURE = re.compile(
    r"(?i)\b(logo|link|photo|image|thumbnail|icon|arrow|close|menu|portfolio|home|contact|about|team|news|"
    r"read more|learn more|search|cookie|subscribe|newsletter|key figures|our |call us|card|new tab|lorem)\b|\.(?:png|jpe?g|svg|webp)$")


def candidates(page: str) -> list[str]:
    """Company names a portfolio page shows: logo alt text and short headings, page furniture left out."""
    alts = re.findall(r'<img[^>]+alt="([^"]{2,60})"', page or "")
    heads = [re.sub(r"<[^>]+>", "", h) for h in re.findall(r"<h[2-5][^>]*>(.*?)</h[2-5]>", page or "", re.S)]
    out, seen = [], set()
    for raw in alts + heads:
        name = re.sub(r"\s+", " ", html_mod.unescape(raw)).strip(" -–|")
        if not (2 <= len(name) <= 50) or len(name.split()) > 6 or _FURNITURE.search(name):
            continue
        if name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


def _allowed(client: httpx.Client, url: str) -> bool:
    root = "/".join(url.split("/")[:3])
    rp = RobotFileParser()
    try:
        r = client.get(f"{root}/robots.txt")
        rp.parse(r.text.splitlines() if r.status_code == 200 else [])
    except httpx.HTTPError:
        return False                                    # robots.txt unreachable: do not read the page
    return rp.can_fetch(USER_AGENT, url)


def fetch(client: Optional[httpx.Client] = None) -> dict[str, dict]:
    c = client or httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    out: dict[str, dict] = {}
    for firm, url in FIRMS.items():
        try:
            if not _allowed(c, url):
                log.info("%s: robots.txt does not allow %s", firm, url)
                continue
            r = c.get(url)
            names = candidates(r.text) if r.status_code == 200 else []
        except httpx.HTTPError as e:
            log.warning("%s portfolio unavailable: %s", firm, e)
            continue
        if names:
            out[firm] = {"url": url, "companies": names}
    return out


def refresh(path: Optional[Path] = None, client: Optional[httpx.Client] = None) -> dict:
    path = path or SNAPSHOT_PATH
    firms = fetch(client)
    previous = load()
    for firm, block in previous.items():              # a page that failed this time keeps its last read
        firms.setdefault(firm, block)
    if not firms:
        raise RuntimeError("no portfolio page could be read; the existing snapshot is kept")
    path.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "firms": firms}, separators=(",", ":"), ensure_ascii=False))
    global _SNAPSHOT
    _SNAPSHOT = None
    return {"firms": len(firms), "companies": sum(len(b["companies"]) for b in firms.values())}


_SNAPSHOT: Optional[dict] = None


def load() -> dict[str, dict]:
    global _SNAPSHOT
    if _SNAPSHOT is None:
        try:
            _SNAPSHOT = json.loads(SNAPSHOT_PATH.read_text())
        except (OSError, ValueError):
            _SNAPSHOT = {"firms": {}}
    return _SNAPSHOT.get("firms", {})


_LEGAL = {"plc", "ltd", "limited", "inc", "llc", "the", "group", "holdings", "co", "sa"}


def _key(name: str) -> str:
    return " ".join(w for w in re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).split() if w not in _LEGAL)


def records_for(company: str, ticker: Optional[str] = None, firms: Optional[dict] = None) -> list[dict]:
    key = _key(company)
    if len(key) < 3:
        return []
    out = []
    for firm, block in (firms if firms is not None else load()).items():
        if any(_key(n) == key for n in block.get("companies", [])):
            out.append({"kind": "portfolio", "authority": firm, "title": f"In {firm}'s portfolio", "date": None,
                        "url": block.get("url"), "detail": f"Listed on {firm}'s own portfolio page."})
    return out
