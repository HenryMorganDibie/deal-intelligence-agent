"""
Debt raised on FMDQ Exchange, Nigeria's debt market: commercial paper quoted and bonds listed, as FMDQ announces
them. Most issuers are private companies (manufacturers, lenders, agribusinesses, logistics firms) whose
borrowing is otherwise unpublished; each announcement names the issuer, the instrument, the amount and the date.

Read from FMDQ's public news posts through its site's standard WordPress API (robots.txt allows all). The issuer's
offering documents, which carry its audited accounts, are on FMDQ's member portal and are not read.

Snapshot: src/data/debt_filings.json, refreshed weekly by scripts/refresh_debt_filings.py.
"""
from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import httpx

log = logging.getLogger(__name__)

POSTS = "https://fmdqgroup.com/wp-json/wp/v2/posts"
_REFERENCE = Path(__file__).resolve().parent.parent / "data"      # committed reference data, like merger_filings
SNAPSHOT_PATH = _REFERENCE / "debt_filings.json"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DealIntelligence/1.0; +https://deal-intelligence.app)"}
SEARCHES = ("commercial paper", "bond", "notes")

_AMOUNT = re.compile(r"(?:₦|N|NGN\s?)(\d[\d,]*(?:\.\d+)?)\s*(billion|bn|million|mn|m|trillion|tn)\b", re.I)
_MULT = {"billion": 1e9, "bn": 1e9, "million": 1e6, "mn": 1e6, "m": 1e6, "trillion": 1e12, "tn": 1e12}
_TOKEN = r"(?:[A-Z][\w.&'’\-]*|&|of|and|\(Nigeria\))"
_SUFFIX = (r"(?:PLC|Plc|Limited|Ltd|LTD|Bank|Holdings|Group|Partners|Industries|Corporation|Company|SPV|"
           r"Services|Ventures|Foods|Mills|Estate|Homes)")
# A company name: capitalised words ending in an entity word ("Coleman Technical Industries Limited").
_ENTITY = re.compile(rf"(?<![\w’'])({_TOKEN}(?:\s+{_TOKEN})*?\s+{_SUFFIX})(?![\w])")
# FMDQ's own phrasing around the name, cut out before looking: "FMDQ Exchange Admits the ... on its Platform".
_PHRASING = re.compile(
    r"\b(?:FMDQ(?:\s+(?:Exchange|Group|Securities))?(?:\s+PLC)?|Admits|Welcomes|Registers|Approves|Lists|Quotes|"
    r"Commemorates|Supports|Facilitates|Strengthens|Kicks\s+Off|Market\s+Access|Registration|Quotation|Listing|"
    r"Admission|Programme|Series|Tranches?|Commercial\s+Papers?|Bonds?|Notes|Infrastructure|Development|"
    r"Empowering|MSMEs|Agro-Sector|Financing|Platform|Maiden|Landmark|Additional|Debut|Inaugural)\b|[:,]")
# "X Limited Taps / Secures / Joins ...", for names without an entity word ("AgroEknor Secures FMDQ Approval").
_SUBJECT = re.compile(r"^(?P<i>[A-Z][\w.&'’\- ]{2,70}?)\s+(?:Taps|Secures|Joins|Strengthens|Bolsters|Launches|Becomes|"
                      r"Quotes|Lists|Achieves|Expands|Registers|Debuts|Raises|Issues|Returns|Deepens|Set\s+to)\b")
# "... with A.R.N Foods’ ₦3.86 Billion ..." / "Sujimoto Holdings Limited’s ₦20.00 Billion".
_POSSESSIVE = re.compile(r"(?P<i>[A-Z][\w.&\- ]{1,70}?)[’']s?\s+(?:₦|N\d|NGN|Maiden|Commercial|Series|CP|Bond|Notes)")
_NOT_ISSUER = re.compile(r"(?i)^(fmdq|the|exchange|market|issuers?|corporates?|other|a|an|sec)\b|^nigerian?$|"
                         r"government|\bstate\b|federal|\bfgn\b|treasury|ministry|\bcbn\b")
_SPV = re.compile(r"(?i)\b(funding|finance|financing|issuance)?\s*(spv|special purpose vehicle)\b.*$")
_LEGAL = {"plc", "ltd", "limited", "inc", "llc", "the", "company", "co", "nigeria"}


def instrument_of(title: str) -> str:
    t = title.lower()
    if "commercial paper" in t or re.search(r"\bcps?\b", t):
        return "Commercial paper"
    if "sukuk" in t:
        return "Sukuk"
    if "note" in t:
        return "Notes"
    return "Bond"


def amount_ngn(title: str) -> Optional[float]:
    m = _AMOUNT.search(title)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "")) * _MULT[m.group(2).lower()]
    except (ValueError, KeyError):
        return None


def _clean(name: str) -> Optional[str]:
    name = re.sub(r"\s+", " ", name).strip(" -–—:,.’'")
    # Leading words that are not the name: "of The Wema Bank", "N3.15 Billion LAPO MFB SPV".
    name = re.sub(r"(?i)^(?:(?:of|the|its|a|an)\s+)+", "", name)
    name = re.sub(r"(?i)^(?:₦|N|NGN\s?)?\d[\d,.]*\s*(?:billion|bn|million|mn|trillion|tn)?\s+", "", name)
    name = re.sub(r"[’']s$", "", name).strip()
    if 3 <= len(name) <= 90 and not _NOT_ISSUER.search(name):
        return name
    return None


def issuer_of(title: str) -> Optional[str]:
    """The issuing company an FMDQ announcement names, or None (a state government, a market notice)."""
    if _NOT_ISSUER.search(title.split(" ")[0] if title else "") is None and (m := _SUBJECT.match(title)):
        name = _clean(m.group("i"))
        if name and not _PHRASING.search(name):
            return name
    for part in _PHRASING.split(title):
        for m in _ENTITY.finditer(part):
            name = _clean(m.group(1))
            if name:
                return name
    m = _POSSESSIVE.search(_PHRASING.sub(" | ", title))
    if m:
        name = _clean(m.group("i").split("|")[-1])
        if name:
            return name
    return None


def parse_posts(posts: Iterable[dict]) -> list[dict]:
    out = []
    for p in posts:
        title = html.unescape(re.sub(r"<[^>]+>", "", (p.get("title") or {}).get("rendered") or "")).strip()
        issuer = issuer_of(title)
        if not issuer or not re.search(r"(?i)commercial paper|\bcps?\b|bond|note|sukuk", title):
            continue
        out.append({"id": f"fmdq:{p.get('id')}", "issuer": issuer, "title": title[:220],
                    "instrument": instrument_of(title), "amount_ngn": amount_ngn(title),
                    "date": (p.get("date") or "")[:10] or None, "url": p.get("link")})
    return out


def fetch(client: Optional[httpx.Client] = None) -> list[dict]:
    c = client or httpx.Client(timeout=60, headers=_HEADERS, follow_redirects=True)
    posts: dict[int, dict] = {}
    for term in SEARCHES:
        page = 1
        while page <= 10:
            try:
                r = c.get(POSTS, params={"search": term, "per_page": "100", "page": str(page),
                                         "_fields": "id,date,title,link"})
            except httpx.HTTPError as e:
                log.warning("FMDQ posts %r page %d failed: %s", term, page, e)
                break
            if r.status_code != 200:
                break
            rows = r.json()
            for p in rows:
                posts[p["id"]] = p
            if len(rows) < 100:
                break
            page += 1
    return sorted(parse_posts(posts.values()), key=lambda r: (r["date"] or "", r["id"]))


def refresh(path: Optional[Path] = None, client: Optional[httpx.Client] = None) -> dict:
    path = path or SNAPSHOT_PATH
    records = fetch(client)
    if not records:
        raise RuntimeError("FMDQ returned no announcements; the existing snapshot is kept")
    path.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "source": "FMDQ Exchange announcements", "records": records},
                               separators=(",", ":"), ensure_ascii=False))
    global _SNAPSHOT
    _SNAPSHOT = None
    return {"records": len(records)}


_SNAPSHOT: Optional[dict] = None


def load() -> dict:
    global _SNAPSHOT
    if _SNAPSHOT is None:
        try:
            _SNAPSHOT = json.loads(SNAPSHOT_PATH.read_text())
        except (OSError, ValueError):
            _SNAPSHOT = {"records": []}
    return _SNAPSHOT


def _core(name: str) -> str:
    """'Emzor Pharma Funding SPV PLC' -> 'emzor pharma'; 'C & I Leasing PLC' -> 'c i leasing'."""
    text = re.sub(r"\bmfb\b", "microfinance bank", _SPV.sub("", name).lower())     # FMDQ abbreviates
    words = [w for w in re.sub(r"[^a-z0-9]+", " ", text).split() if w not in _LEGAL]
    return " ".join(words)


def records_for(company: str, ticker: Optional[str] = None, records: Optional[Iterable[dict]] = None) -> list[dict]:
    """The company's FMDQ issues: its name (legal suffixes and funding vehicles aside) equals the issuer's, or one
    contains the other as whole words when the shorter has at least two words ("Emzor Pharma" in "Emzor
    Pharmaceutical Industries" does not count; "Emzor Pharmaceutical" for "Emzor Pharmaceutical Industries" does)."""
    mine = _core(company)
    if len(mine) < 4:
        return []
    out = []
    for r in records if records is not None else load().get("records", []):
        theirs = _core(r.get("issuer") or "")
        if not theirs:
            continue
        short, long_ = sorted((mine, theirs), key=len)
        if mine == theirs or (len(short.split()) >= 2 and f" {short} " in f" {long_} "):
            amount = r.get("amount_ngn")
            out.append({"kind": "debt_issue", "authority": "FMDQ Exchange", "title": r["title"], "date": r.get("date"),
                        "url": r.get("url"), "amount_usd": None, "instrument": r.get("instrument"),
                        "detail": f"{r.get('instrument')} of ₦{amount / 1e9:,.2f}bn" if amount else r.get("instrument")})
    return out
