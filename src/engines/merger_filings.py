"""Official merger-control filings: decisions and notices published by competition authorities.

A competition authority reviewing or clearing a named transaction is official evidence that the deal is
real, independent of the press. These records confirm African M&A signals in the backtest and in live
outcome labelling, where few exchange disclosures are machine-readable.

Sources (public-sector publications, read from the authorities' own sites):
  COMESA Competition Commission   merger notices, decisions and summaries for its 21 member states
                                  (each document's own date is read from its first page, because the site's
                                  upload dates reflect a 2026 migration, not the decision)
  Competition Commission of South Africa   the quarterly Government Gazette lists of merger decisions
                                  (dated by the filing month in each case number) and its media statements

The committed snapshot is src/data/merger_filings.json, refreshed by scripts/refresh_merger_filings.py;
each refresh reads only documents it has not seen. Only metadata is kept: authority, parties, date, a
short excerpt naming the parties, and the link to the authority's document.
"""
from __future__ import annotations

import html
import io
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

import httpx

log = logging.getLogger(__name__)

_REFERENCE = Path(__file__).resolve().parent.parent / "data"
FILINGS_PATH = _REFERENCE / "merger_filings.json"

COMESA_MEDIA = "https://www.comesacompetition.org/wp-json/wp/v2/media"
SA_MEDIA = "https://www.compcom.co.za/wp-json/wp/v2/media"
COMESA = "COMESA Competition Commission"
SOUTH_AFRICA = "Competition Commission of South Africa"
# COMESA member states (ISO2): a COMESA filing evidences deals touching these markets.
COMESA_MEMBERS = {"BI", "KM", "CD", "DJ", "EG", "ER", "SZ", "ET", "KE", "LY", "MG", "MW", "MU", "RW", "SC", "SO",
                  "SD", "TN", "UG", "ZM", "ZW"}
_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) deal-intelligence-agent/1.0 (research; merger filings)"}

_MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                                        "september", "october", "november", "december"), 1)}
_MON = {k[:3]: v for k, v in _MONTHS.items()}
_COMESA_KEEP = re.compile(r"(?i)merger|website[-\s_]*notice|summary|decision|statement[-\s_]*of[-\s_]*merger|acquisition")
_COMESA_SKIP = re.compile(r"(?i)warning|investigation|regulation|guideline|statistic|review\b|practice[-\s_]*note|"
                          r"form[-\s_]?\d|consumer|funeral|press|newsletter|template|application")


# ── Dates ─────────────────────────────────────────────────────────────────────

def _valid(y: int, m: int, d: int) -> Optional[str]:
    try:
        return date(y, m, d).isoformat() if 2005 <= y <= 2100 else None
    except ValueError:
        return None


def date_in_name(name: str) -> Optional[str]:
    """A date written into a file name: 20210817, 2021-08-17, 23.9.19, 10.08.26."""
    m = re.search(r"(?<!\d)(20[0-3]\d)[-_.]?(0[1-9]|1[0-2])[-_.]?([0-3]\d)(?!\d)", name)
    if m:
        return _valid(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"(?<!\d)([0-3]?\d)[._-](0?[1-9]|1[0-2])[._-](20)?(\d\d)(?!\d)", name)
    if m:
        return _valid(2000 + int(m[4]), int(m[2]), int(m[1]))
    return None


def date_in_text(text: str) -> Optional[str]:
    """The first written date in a document: "12 March 2025", "12th March, 2025", "March 12, 2025", "12/03/2025"."""
    t = " ".join(text.split())
    candidates = []
    for m in re.finditer(r"\b([0-3]?\d)(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]{3,9})\.?,?\s+(20\d\d)\b", t):
        mon = _MONTHS.get(m[2].lower()) or _MON.get(m[2].lower()[:3])
        if mon:
            candidates.append((m.start(), _valid(int(m[3]), mon, int(m[1]))))
    for m in re.finditer(r"\b([A-Za-z]{3,9})\.?\s+([0-3]?\d)(?:st|nd|rd|th)?,?\s+(20\d\d)\b", t):
        mon = _MONTHS.get(m[1].lower()) or _MON.get(m[1].lower()[:3])
        if mon:
            candidates.append((m.start(), _valid(int(m[3]), mon, int(m[2]))))
    for m in re.finditer(r"\b([0-3]?\d)/([01]?\d)/(20\d\d)\b", t):
        candidates.append((m.start(), _valid(int(m[3]), int(m[2]), int(m[1]))))
    found = [d for _, d in sorted(candidates) if d]
    return found[0] if found else None


def date_from_case_number(case: str) -> Optional[str]:
    """South African case numbers carry the filing month: "2026Mar0016" (spaces are common in the gazette)."""
    m = re.search(r"(20\d\d)\s*([A-Za-z]{3})\s*[a-z]?\s*(\d{3,4})", case.replace(" ", ""))
    if not m:
        return None
    mon = _MON.get(m[2].lower())
    return _valid(int(m[1]), mon, 15) if mon else None


# ── Parties ───────────────────────────────────────────────────────────────────

_TITLE_NOISE = re.compile(
    r"(?i)\b(summary|of|merger|transaction|website|notice|for|the|executive|cid|decision|statement|no|redacted|"
    r"non[-\s]?confidential|version|stamped|compressed|panel|final|updated?|and|involving|proposed|inquiry|into|"
    r"phase|\d+)\b")


def parties_from_title(title: str) -> list[str]:
    """Party names from a COMESA document title: "Summary-of-Merger-Transaction-TCCC_CCBA" -> ["TCCC", "CCBA"]."""
    t = re.sub(r"[_]+", " | ", title)
    t = re.sub(r"(?<=[A-Za-z])-(?=[A-Za-z])", " ", t)
    t = re.sub(r"\s+-\s+", " | ", t)
    t = re.sub(r"(?i)\s+and\s+", " | ", t)
    t = _TITLE_NOISE.sub(" ", t)
    parts = [" ".join(re.sub(r"[-.,;:]+(?=\s|$)", " ", p).split()) for p in t.split("|")]
    return [p for p in parts if len(p) >= 2 and not p.isdigit()]


# ── Fetching ──────────────────────────────────────────────────────────────────

def _media(client: httpx.Client, base: str, term: str) -> list[dict]:
    out, page = [], 1
    while page <= 10:
        r = client.get(base, params={"search": term, "per_page": 100, "page": page,
                                     "_fields": "id,date,title,source_url,mime_type"})
        if r.status_code != 200:
            break
        rows = r.json()
        if not rows:
            break
        out += rows
        page += 1
    return out


def _pdf_text(client: httpx.Client, url: str, pages: int = 1) -> str:
    from pypdf import PdfReader
    r = client.get(url, timeout=60)
    r.raise_for_status()
    reader = PdfReader(io.BytesIO(r.content))
    return " ".join((reader.pages[i].extract_text() or "") for i in range(min(pages, len(reader.pages))))


def fetch_comesa(client: httpx.Client, seen: set[str]) -> list[dict]:
    items: dict[int, dict] = {}
    for term in ("merger", "notice", "decision", "summary", "statement", "acquisition"):
        for row in _media(client, COMESA_MEDIA, term):
            items[row["id"]] = row
    out = []
    for row in items.values():
        title = html.unescape(row["title"]["rendered"])
        url = row.get("source_url") or ""
        key = f"comesa:{row['id']}"
        if key in seen or not url.lower().endswith(".pdf") or not _COMESA_KEEP.search(title) or _COMESA_SKIP.search(title + url):
            continue
        try:
            text = _pdf_text(client, url)
        except Exception as e:
            log.info("COMESA document unreadable %s: %s", url, e)
            continue
        when = date_in_name(title) or date_in_name(url.rsplit("/", 1)[-1]) or date_in_text(text)
        out.append({"id": key, "authority": COMESA, "title": title, "parties": parties_from_title(title),
                    "date": when, "date_basis": "document" if when else None, "url": url,
                    "excerpt": " ".join(text.split())[:400], "markets": sorted(COMESA_MEMBERS)})
    return out


_SA_CASE = re.compile(r"Case\s+number:\s*([0-9A-Za-z ]{8,16}?)\s*[–—-]\s*(.+?)(?=\s*\d+\.\s+Case\s+number:|\Z)", re.S)


def sa_gazette_entries(text: str, url: str) -> list[dict]:
    """Entries of one South African gazette list: "Case number: 2026Mar0016 – Acquirer and Target"."""
    out = []
    for m in _SA_CASE.finditer(" ".join(text.split())):
        case, body = m[1].strip(), m[2].strip()
        parties = [p.strip(" ,.;") for p in re.split(r"\s+and\s+", body, maxsplit=1) if p.strip()]
        out.append({"id": f"za:{re.sub(r'[^0-9A-Za-z]', '', case)}", "authority": SOUTH_AFRICA, "title": body[:240],
                    "parties": parties, "date": date_from_case_number(case), "date_basis": "case number filing month",
                    "case_number": re.sub(r"\s+", "", case), "url": url, "excerpt": body[:400], "markets": ["ZA"]})
    return out


def fetch_south_africa(client: httpx.Client, seen: set[str]) -> list[dict]:
    rows: dict[int, dict] = {}
    for term in ("merger notices", "approves", "merger"):
        for row in _media(client, SA_MEDIA, term):
            rows[row["id"]] = row
    out = []
    for row in rows.values():
        title = html.unescape(row["title"]["rendered"])
        url = row.get("source_url") or ""
        if not url.lower().endswith(".pdf"):
            continue
        if re.search(r"(?i)merger\s*notices", title) and f"za-list:{row['id']}" not in seen:
            try:
                text = _pdf_text(client, url, pages=20)
            except Exception as e:
                log.info("South African gazette list unreadable %s: %s", url, e)
                continue
            entries = [e for e in sa_gazette_entries(text, url) if e["id"] not in seen]
            out += entries + [{"id": f"za-list:{row['id']}", "authority": SOUTH_AFRICA, "title": title, "list": True,
                               "url": url, "parties": [], "date": None, "markets": ["ZA"]}]
        elif re.search(r"(?i)\b(approves|approved|prohibits|clears)\b", title) and f"za:{row['id']}" not in seen:
            out.append({"id": f"za:{row['id']}", "authority": SOUTH_AFRICA, "title": title,
                        "parties": parties_from_title(re.sub(r"(?i).*?\b(approves|approved|prohibits|clears)\b", "", title)),
                        "date": row["date"][:10], "date_basis": "media statement", "url": url,
                        "excerpt": title[:400], "markets": ["ZA"]})
    return out


def refresh(path: Optional[Path] = None, client: Optional[httpx.Client] = None) -> dict:
    """Add documents not yet in the snapshot; keep everything already read."""
    path = path or FILINGS_PATH
    current = load(path)
    seen = {r["id"] for r in current.get("filings", [])}
    c = client or httpx.Client(timeout=60, headers=_HEADERS, follow_redirects=True)
    added = []
    for name, fetch in (("COMESA", fetch_comesa), ("South Africa", fetch_south_africa)):
        try:
            new = fetch(c, seen)
        except Exception as e:                       # one authority being down never loses the other
            log.warning("%s merger filings unavailable: %s", name, e)
            continue
        added += new
        seen |= {r["id"] for r in new}
    snapshot = {"generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "sources": [COMESA, SOUTH_AFRICA],
                "filings": sorted(current.get("filings", []) + added, key=lambda r: (r.get("date") or "", r["id"]))}
    path.write_text(json.dumps(snapshot, indent=0, ensure_ascii=False))
    global _SNAPSHOT
    _SNAPSHOT = None
    return {"added": len(added), "total": len(snapshot["filings"])}


# ── Reading ───────────────────────────────────────────────────────────────────

_SNAPSHOT: Optional[dict] = None


def load(path: Optional[Path] = None) -> dict:
    global _SNAPSHOT
    if path and path != FILINGS_PATH:
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return {"filings": []}
    if _SNAPSHOT is None:
        try:
            _SNAPSHOT = json.loads(FILINGS_PATH.read_text())
        except (OSError, ValueError):
            _SNAPSHOT = {"filings": []}
    return _SNAPSHOT


def events_for(company: str, ticker: Optional[str] = None, filings: Optional[Iterable[dict]] = None,
               matchers: Optional[list] = None) -> list[dict]:
    """Dated merger-control filings naming this company, as confirmation events for M&A."""
    from src.engines.deterministic_engine import _company_matchers
    ms = matchers if matchers is not None else _company_matchers(company, ticker=ticker)
    if not ms:
        return []
    out, seen = [], set()
    for f in filings if filings is not None else load().get("filings", []):
        if f.get("list") or not f.get("date"):
            continue
        # Judge on the parties and filing text when they name the company; the slug title is a fallback.
        prose = "\n".join([*(f.get("parties") or []), f.get("excerpt") or ""])
        verdict = _names_company(prose, ms)
        if verdict is None:
            verdict = _names_company(f.get("title") or "", ms)
        # One deal often has a notice and a decision on the same day, or several gazette rows.
        key = (f["date"], re.sub(r"[^a-z0-9]", "", (f.get("title") or "").lower()))
        if verdict and key not in seen:
            seen.add(key)
            out.append({"date": f["date"], "signal_types": ["m_and_a_activity"], "official": True,
                        "source": f"{f['authority']} merger filing: {(f.get('title') or '')[:120]}",
                        "url": f.get("url")})
    return out


# A name followed by one of these is still the company ("Access Bank Plc", "MTN Group Limited").
_ENTITY_SUFFIXES = {
    "ag", "bank", "bhd", "capital", "co", "company", "corp", "corporation", "financial", "global", "group",
    "holding", "holdings", "inc", "incorporated", "international", "limited", "llc", "lp", "ltd", "nv",
    "plc", "proprietary", "pty", "sa", "trust",
}
_NEXT_WORD = re.compile(r"[ \t]+([A-Z][\w&'.-]*)")


def _names_company(text: str, matchers: list) -> Optional[bool]:
    """True if the text names the company, False if it only names a namesake, None if neither.

    A match immediately followed by another proper noun is a different entity: "Paramount Aerospace",
    "Coca Cola Sabco". Country subsidiaries are already excluded by the matchers themselves.
    """
    found = False
    for m in matchers:
        pos = 0
        while (hit := m.search(text, pos)) is not None:
            found, pos = True, max(hit.end(), pos + 1)
            nxt = _NEXT_WORD.match(text, hit.end())
            if not nxt or nxt.group(1).lower().strip(".") in _ENTITY_SUFFIXES:
                return True
    return False if found else None


def coverage(markets: Callable[[str], bool] = lambda iso2: True) -> list[str]:
    """Markets with official merger-filing coverage."""
    return sorted(m for m in COMESA_MEMBERS | {"ZA"} if markets(m))
