"""
Financial institutions licensed by their central bank, from the regulators' own registers.

Unlisted banks, microfinance banks, mortgage lenders and finance companies are private companies that must be
licensed, and most must publish audited results. The register puts them in the company directory (so they can be
searched, profiled and compared), records who licensed them, and gives the profile their website, from which the
annual report is read on the spot.

  Central Bank of Nigeria   the supervision pages' JSON lists: commercial, non-interest and merchant banks,
                            microfinance banks, primary mortgage institutions, finance companies, development-
                            finance institutions and discount houses
  Bank of Ghana             the registers of banks, savings and loans companies, finance houses, mortgage
                            finance companies, other banks and microfinance institutions (name and website)

Snapshot: src/data/licensed_institutions.json, refreshed weekly by scripts/refresh_licensed_institutions.py.
"""
from __future__ import annotations

import html as html_mod
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import httpx

log = logging.getLogger(__name__)

_REFERENCE = Path(__file__).resolve().parent.parent / "data"      # committed reference data, like merger_filings
SNAPSHOT_PATH = _REFERENCE / "licensed_institutions.json"
_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

CBN = "Central Bank of Nigeria"
CBN_LISTS = {
    "GetDMBs": "Commercial bank", "GetNIBs": "Non-interest bank", "GetMFBs": "Microfinance bank",
    "GetPMIs": "Primary mortgage bank", "GetFCs": "Finance company", "GetDFIs": "Development-finance institution",
    "GetDHs": "Discount house",
}
BOG = "Bank of Ghana"
_BOG = "https://www.bog.gov.gh/supervision-regulation/"
BOG_LISTS = {
    f"{_BOG}registered-institutions/banks/": "Bank",
    f"{_BOG}registered-institutions/microfinance-institutions/": "Microfinance institution",
    f"{_BOG}register-of-licensed-institutions/savings-loans/": "Savings and loans company",
    f"{_BOG}register-of-licensed-institutions/finance-houses/": "Finance house",
    f"{_BOG}register-of-licensed-institutions/mortgage-finance/": "Mortgage finance company",
    f"{_BOG}register-of-licensed-institutions/other-banks/": "Other bank",
}

_ROW = re.compile(r'<tr id="table_\d+_row_\d+"[^>]*>(.*?)</tr>', re.S)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_URL = re.compile(r"(?i)^(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/\S*)?$")


def display_name(name: str) -> str:
    """'3AS MICROFINANCE LIMITED' -> '3AS Microfinance Limited': registers often shout; short tokens (acronyms) stay."""
    name = re.sub(r"\s+", " ", name).strip()
    if not name.isupper():
        return name
    return " ".join(w if len(w) <= 3 or any(ch.isdigit() for ch in w) else w.capitalize() for w in name.split(" "))


def _text(cell: str) -> str:
    return re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", cell))).strip()


def _website(value: Optional[str]) -> Optional[str]:
    v = (value or "").strip().rstrip("/")
    if not v or "@" in v or not _URL.match(v):
        return None
    return v if v.lower().startswith("http") else f"https://{v}"


def parse_cbn(rows: object, licence: str) -> list[dict]:
    out = []
    for r in rows if isinstance(rows, list) else []:
        name = re.sub(r"\s+", " ", (r.get("name") or "") if isinstance(r, dict) else "").strip()
        if len(name) >= 3:
            out.append({"name": display_name(name), "country": "NG", "regulator": CBN, "licence": licence,
                        "website": _website(r.get("website")), "state": (r.get("state") or None)})
    return out


def parse_bog(page: str, licence: str) -> list[dict]:
    """Rows of a Bank of Ghana register table: the institution's name first, its website among the other cells."""
    out = []
    for row in _ROW.findall(page or ""):
        cells = [_text(c) for c in _CELL.findall(row)]
        if not cells or len(cells[0]) < 3 or cells[0].lower() in {"name", "institution"}:
            continue
        site = next((w for w in (_website(c) for c in cells[1:]) if w), None)
        out.append({"name": display_name(cells[0]), "country": "GH", "regulator": BOG, "licence": licence,
                    "website": site})
    return out


def fetch(client: Optional[httpx.Client] = None) -> list[dict]:
    c = client or httpx.Client(timeout=60, headers=_HEADERS, follow_redirects=True)
    out: list[dict] = []
    for endpoint, licence in CBN_LISTS.items():
        try:
            r = c.get(f"https://www.cbn.gov.ng/api/{endpoint}")
            out += parse_cbn(r.json() if r.status_code == 200 else [], licence)
        except (httpx.HTTPError, ValueError) as e:
            log.warning("CBN %s unavailable: %s", endpoint, e)
    for url, licence in BOG_LISTS.items():
        try:
            r = c.get(url)
            out += parse_bog(r.text if r.status_code == 200 else "", licence)
        except httpx.HTTPError as e:
            log.warning("Bank of Ghana %s unavailable: %s", url, e)
    seen, unique = set(), []
    for row in out:
        key = (row["country"], re.sub(r"[^a-z0-9]", "", row["name"].lower()))
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return sorted(unique, key=lambda r: (r["country"], r["name"].lower()))


def refresh(path: Optional[Path] = None, client: Optional[httpx.Client] = None) -> dict:
    path = path or SNAPSHOT_PATH
    rows = fetch(client)
    if len(rows) < 100:
        raise RuntimeError(f"only {len(rows)} licensed institutions read; the existing snapshot is kept")
    path.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "regulators": [CBN, BOG], "institutions": rows}, separators=(",", ":"),
                               ensure_ascii=False))
    global _SNAPSHOT
    _SNAPSHOT = None
    counts: dict[str, int] = {}
    for r in rows:
        counts[f"{r['country']} {r['licence']}"] = counts.get(f"{r['country']} {r['licence']}", 0) + 1
    return {"institutions": len(rows), "by_licence": counts}


_SNAPSHOT: Optional[dict] = None


def load() -> list[dict]:
    global _SNAPSHOT
    if _SNAPSHOT is None:
        try:
            _SNAPSHOT = json.loads(SNAPSHOT_PATH.read_text())
        except (OSError, ValueError):
            _SNAPSHOT = {"institutions": []}
    return _SNAPSHOT.get("institutions", [])


_LEGAL = {"plc", "ltd", "limited", "the", "company", "co", "nigeria", "ghana"}


def _key(name: str) -> str:
    text = re.sub(r"\bmfb\b", "microfinance bank", (name or "").lower())        # the CBN abbreviates: "Lapo MFB"
    return " ".join(w for w in re.sub(r"[^a-z0-9]+", " ", text).split() if w not in _LEGAL)


def lookup(company: str, country: Optional[str] = None, rows: Optional[Iterable[dict]] = None) -> Optional[dict]:
    """The licence record for a company: the same name once legal suffixes and the country are set aside."""
    key = _key(company)
    if len(key) < 3:
        return None
    for r in rows if rows is not None else load():
        if (not country or r["country"] == country) and _key(r["name"]) == key:
            return r
    return None


def records_for(company: str, ticker: Optional[str] = None, country: Optional[str] = None) -> list[dict]:
    hit = lookup(company, country)
    if not hit:
        return []
    return [{"kind": "licence", "authority": hit["regulator"], "title": f"Licensed: {hit['licence'].lower()}",
             "date": None, "url": hit.get("website"), "detail": f"{hit['name']} is on the {hit['regulator']}'s "
             f"register of licensed institutions as a {hit['licence'].lower()}."}]
