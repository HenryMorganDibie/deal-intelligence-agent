"""
Development-finance investments in African companies, as the institutions themselves disclose them.

Development-finance institutions publish every investment to IATI, the International Aid Transparency Initiative
standard: the client company, what was provided, the amount and the start date. Many of the mid-sized private
companies they back (lenders, manufacturers, energy and telecom operators) are rarely in the press, so these
records are often the only verified facts about them.

Read from d-portal.org, the IATI public query service (no key; public-sector open data). Publishers:
  IFC                         XM-DAC-903
  British International Investment   GB-COH-03877777   (amounts not disclosed)
  FMO                         NL-KVK-27078545
  European Investment Bank    XM-DAC-918-3
  African Development Bank    XM-DAC-46002      (mostly sovereign; only records naming a company match one)
  US DFC                      US-GOV-22

The committed snapshot is src/data/dfi_disclosures.json, refreshed by scripts/refresh_dfi_disclosures.py. Only
metadata is kept: publisher, title, a short description, start date, commitment in US dollars and countries.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

import httpx

log = logging.getLogger(__name__)

DPORTAL = "https://d-portal.org/q.json"
_REFERENCE = Path(__file__).resolve().parent.parent / "data"      # committed reference data, like merger_filings
SNAPSHOT_PATH = _REFERENCE / "dfi_disclosures.json"
PUBLISHERS = {
    "XM-DAC-903": "IFC",
    "GB-COH-03877777": "British International Investment",
    "NL-KVK-27078545": "FMO",
    "XM-DAC-918-3": "European Investment Bank",
    "XM-DAC-46002": "African Development Bank",
    "US-GOV-22": "US International Development Finance Corporation",
}
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DealIntelligence/1.0; +https://deal-intelligence.app)"}
_PAGE = 2000
_EPOCH = date(1970, 1, 1)
DESCRIPTION_CHARS = 360


def _day(n: object) -> Optional[str]:
    """d-portal dates are days since 1970-01-01."""
    if not isinstance(n, (int, float)) or n <= 0:
        return None
    try:
        return (_EPOCH + timedelta(days=int(n))).isoformat()
    except OverflowError:
        return None


def parse_rows(rows: Iterable[dict], publisher: str) -> dict[str, dict]:
    """{activity id: record}; an activity listed once per country is merged into one record."""
    out: dict[str, dict] = {}
    for r in rows:
        aid = (r.get("aid") or "").strip()
        title = re.sub(r"\s+", " ", (r.get("title") or "")).strip()
        if not aid or not title:
            continue
        rec = out.get(aid)
        country = (r.get("country_code") or "").upper() or None
        commitment = r.get("commitment") if isinstance(r.get("commitment"), (int, float)) else None
        if rec is None:
            desc = re.sub(r"\s+", " ", (r.get("description") or "")).strip()
            rec = out[aid] = {
                "id": aid, "dfi": publisher, "title": title[:200],
                "description": desc[:DESCRIPTION_CHARS] + ("…" if len(desc) > DESCRIPTION_CHARS else ""),
                "date": _day(r.get("day_start")), "amount_usd": None, "countries": [],
                "status": r.get("status_code"),
            }
        if country and country not in rec["countries"]:
            rec["countries"].append(country)
        # A zero commitment means not disclosed (BII withholds amounts), not a zero investment.
        if commitment and commitment > 0:
            rec["amount_usd"] = max(rec["amount_usd"] or 0, round(commitment, 2))
    return out


def fetch(client: Optional[httpx.Client] = None, countries: Optional[Iterable[str]] = None) -> list[dict]:
    """Every disclosed activity of the publishers above in African countries."""
    from src.data.africa_countries import COUNTRIES
    codes = "|".join(sorted(countries or (c.iso2 for c in COUNTRIES)))
    c = client or httpx.Client(timeout=180, headers=_HEADERS, follow_redirects=True)
    records: dict[str, dict] = {}
    for ref, name in PUBLISHERS.items():
        offset = 0
        while True:
            try:
                r = c.get(DPORTAL, params={"from": "act,country", "reporting_ref": ref, "country_code": codes,
                                           "select": "aid,title,description,day_start,commitment,status_code,country_code",
                                           "orderby": "aid", "limit": str(_PAGE), "offset": str(offset)})
                rows = r.json().get("rows", []) if r.status_code == 200 else []
            except (httpx.HTTPError, ValueError) as e:
                log.warning("d-portal %s page at %d failed: %s", name, offset, e)
                break
            for aid, rec in parse_rows(rows, name).items():
                if aid in records:
                    for cc in rec["countries"]:
                        if cc not in records[aid]["countries"]:
                            records[aid]["countries"].append(cc)
                    records[aid]["amount_usd"] = max(records[aid]["amount_usd"] or 0, rec["amount_usd"] or 0) or None
                else:
                    records[aid] = rec
            if len(rows) < _PAGE:
                break
            offset += _PAGE
    return sorted(records.values(), key=lambda r: (r.get("date") or "", r["id"]))


def refresh(path: Optional[Path] = None, client: Optional[httpx.Client] = None) -> dict:
    path = path or SNAPSHOT_PATH
    records = fetch(client)
    if not records:
        raise RuntimeError("d-portal returned no records; the existing snapshot is kept")
    snapshot = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source": "IATI via d-portal.org", "publishers": sorted(PUBLISHERS.values()), "records": records}
    path.write_text(json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False))
    global _SNAPSHOT
    _SNAPSHOT = None
    return {"records": len(records), "by_publisher": {p: sum(r["dfi"] == p for r in records) for p in PUBLISHERS.values()}}


_SNAPSHOT: Optional[dict] = None


def load() -> dict:
    global _SNAPSHOT
    if _SNAPSHOT is None:
        try:
            _SNAPSHOT = json.loads(SNAPSHOT_PATH.read_text())
        except (OSError, ValueError):
            _SNAPSHOT = {"records": []}
    return _SNAPSHOT


def activity_url(aid: str) -> str:
    return f"https://d-portal.org/ctrack.html#view=act&aid={aid}"


_LEGAL = {"plc", "ltd", "limited", "inc", "incorporated", "llc", "lp", "sa", "nv", "bv", "pty", "co", "corp",
          "corporation", "company", "the", "group", "holdings", "holding"}


def _norm(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip() + " "


def name_phrase(company: str) -> Optional[str]:
    """The company's name without legal suffixes, as a phrase to find whole ("Equity Bank Ltd" -> " equity bank "). None
    for a name too short or generic to identify one company, or that is a country's name."""
    from src.data.africa_countries import countries_in_text
    words = [w for w in _norm(company).split() if w not in _LEGAL]
    phrase = " ".join(words)
    if len(phrase) < 4 or (len(words) == 1 and words[0] in {"bank", "capital", "energy", "africa", "finance"}):
        return None
    if countries_in_text(company) and len(words) <= 2 and any(c.name.lower() == phrase for c in countries_in_text(company)):
        return None
    return f" {phrase} "


def records_for(company: str, ticker: Optional[str] = None, records: Optional[Iterable[dict]] = None) -> list[dict]:
    """Disclosed investments naming the company: its full name (legal suffixes aside) as a whole phrase in the
    title, where most institutions name the client, or in the description. A shared word is not enough: "Equity
    Bank" is not "Ethos Private Equity Fund", and "Family Bank" is not a rural family-farming loan."""
    phrase = name_phrase(company)
    if not phrase:
        return []
    out = []
    for r in records if records is not None else load().get("records", []):
        if phrase in _norm(r.get("title") or "") or phrase in _norm(r.get("description") or ""):
            out.append({"kind": "dfi_investment", "authority": r["dfi"], "title": r["title"], "date": r.get("date"),
                        "url": activity_url(r["id"]), "amount_usd": r.get("amount_usd"),
                        "detail": r.get("description") or None, "countries": r.get("countries") or []})
    return out
