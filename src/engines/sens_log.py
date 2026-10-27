"""JSE SENS announcements, captured daily going forward.

The free SENS page (Sharenet's republication) lists the current and previous trading day for the whole
market; deeper history is subscription-only and is not read. A weekday capture after the close appends
each new announcement to an append-only log, so a JSE history builds from the first capture onwards and a
missed day is recovered by the next run's overlap.

Only metadata is kept: date, time, issuer, share code, headline and the link to the announcement. The
announcement text itself is never stored. The log is src/data/sens_announcements.jsonl, written by
scripts/capture_sens.py.

Uses: official confirmation of JSE signals in the backtest (only for dates the log covers, so the absence
of an announcement before capture began is "unknown", never "none"), and recent SENS history for a company.
"""
from __future__ import annotations

import html
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

import httpx

log = logging.getLogger(__name__)

SENS_FEED = "https://www.sharenet.co.za/v3/sens.php?scode="
SHARENET_BASE = "https://www.sharenet.co.za"
LOG_PATH = Path(__file__).resolve().parents[1] / "data" / "sens_announcements.jsonl"
_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) deal-intelligence-agent/1.0 (research; SENS headlines)"}

_LINK = re.compile(r'href="(/v3/sens_display\.php\?tdate=(\d{8})(\d{4})\d*&(?:amp;)?seq=(\d+)[^"]*)"')
_STAMP = re.compile(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}\s+\w{3}\s+\d{4}")
_LOG: Optional[tuple[Path, list[dict]]] = None

# SENS headlines follow the JSE Listings Requirements' standard wording, which the news classifier (built
# for full sentences) mostly misses. Completed or committed events only: a cautionary announcement means
# talks are under way, and is not the event.
_SENS_EVENTS: dict[str, list[str]] = {
    "m_and_a_activity": [
        r"\b(acquisition|disposal|sale) of\b", r"\bfirm intention\b", r"\bscheme of arrangement\b",
        r"\b(fulfil+ment|waiver) of (all )?(the )?(outstanding )?conditions precedent\b", r"\bimplementation of the scheme\b",
        r"\bmandatory offer\b", r"\bcategory [12] transaction\b", r"\bterms announcement\b", r"\bmerger\b",
        r"\bcompletion of\b", r"\bunconditional\b", r"\btakeover\b",
    ],
    "leadership_change": [
        r"\bdirectorate change", r"\bchanges? (to|in) the board\b",
        r"\b(resignation|retirement|appointment|departure|passing) of\b.{0,40}\b(director|chief|ceo|cfo|chair(man|person)?|"
        r"managing director|executive)", r"\b(ceo|cfo|chief executive|chief financial officer) (succession|transition)\b",
    ],
    "credit_risk": [r"\bdowngrade", r"\b(negative )?(rating )?watch negative\b", r"\boutlook (revised|changed) to negative\b"],
    "distressed_asset": [
        r"\bbusiness rescue\b", r"\b(provisional )?liquidation\b", r"\bsuspension of (the )?(listing|trading)\b",
        r"\bgoing concern\b", r"\binsolven",
    ],
    "debt_restructuring": [
        r"\bdebt restructur", r"\brestructur\w* of (the |its )?(debt|notes|bonds|facilit|loans?)", r"\bstandstill\b",
        r"\b(covenant|payment) (waiver|breach|default)\b", r"\bevent of default\b",
    ],
    # The JSE's equivalent of a Form 4, and the trading statement the Listings Requirements demand when
    # earnings will differ by at least 20% from the prior period.
    "insider_activity": [r"\bdealings?\s+in\s+securities\b", r"\bdealing\s+by\s+(?:a\s+)?(?:director|prescribed\s+officer)"],
    "earnings_surprise": [r"\btrading\s+statement\b"],
    "regulatory_action": [
        r"\b(public )?censure\b", r"\badministrative penalty\b", r"\b(fine|penalty) (imposed|levied)\b",
        r"\bsanction(s|ed) (by|imposed)\b", r"\bregulatory (action|sanction)\b",
    ],
}
_SENS_COMPILED = {t: [re.compile(p, re.I) for p in ps] for t, ps in _SENS_EVENTS.items()}
_NOT_YET = re.compile(r"\bcautionary\b|\bwithdrawal of\b|\btermination of (the )?(discussions|negotiations)\b", re.I)


def classify_headline(headline: str) -> set[str]:
    """Signal types whose completed event a SENS headline announces."""
    text = " ".join((headline or "").split())
    if not text or _NOT_YET.search(text):
        return set()
    return {t for t, ps in _SENS_COMPILED.items() if any(p.search(text) for p in ps)}


def parse_feed(text: str) -> list[dict]:
    """Announcements on one SENS page, oldest first."""
    out, seen = [], set()
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S):
        link = _LINK.search(row)
        if not link:
            continue
        path, day, hhmm, seq = link.groups()
        ident = f"{day}-{int(seq)}"
        if ident in seen:
            continue
        seen.add(ident)
        cells = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", row)).split())
        parts = _STAMP.split(cells)                 # "<time> - <date> [CODE] <time> - <date> | ISSUER - Headline Price: ..."
        code = parts[1].strip() if len(parts) > 2 and re.fullmatch(r"[A-Z0-9]{2,8}", parts[1].strip()) else None
        after = re.sub(r"\s*Price:.*$", "", parts[-1]).strip(" |")
        issuer, sep, headline = after.partition(" - ")
        if code and issuer.startswith(code + " "):
            issuer = issuer[len(code) + 1:]
        out.append({"id": ident, "date": f"{day[:4]}-{day[4:6]}-{day[6:]}", "time": f"{hhmm[:2]}:{hhmm[2:]}",
                    "issuer": issuer.strip(), "code": code, "headline": (headline if sep else after).strip(),
                    "url": SHARENET_BASE + html.unescape(path)})
    return sorted(out, key=lambda e: (e["date"], e["time"], int(e["id"].split("-")[1])))


def capture(path: Optional[Path] = None, client: Optional[httpx.Client] = None) -> dict:
    """Append announcements not yet in the log. Raises if the page cannot be read or parsed, so a broken
    source shows as a failed run instead of a silent gap."""
    path = path or LOG_PATH
    own = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=True, headers=_HEADERS)
    try:
        r = client.get(SENS_FEED)
        r.raise_for_status()
        entries = parse_feed(r.text)
    finally:
        if own:
            client.close()
    if not entries:
        raise RuntimeError("SENS page returned no announcements; the page layout may have changed")
    known = {e["id"] for e in _read(path)}
    new = [e for e in entries if e["id"] not in known]
    if new:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for e in new:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    global _LOG
    _LOG = None
    return {"added": len(new), "total": len(known) + len(new)}


def _read(path: Path) -> list[dict]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        return []


def load(path: Optional[Path] = None) -> list[dict]:
    global _LOG
    path = path or LOG_PATH
    if _LOG is None or _LOG[0] != path:
        _LOG = (path, _read(path))
    return _LOG[1]


def covered_since(entries: Optional[list[dict]] = None) -> Optional[date]:
    """First day the log holds in full. The first capture also brings the previous trading day, which is
    complete, so coverage starts at the earliest logged day."""
    days = [e["date"] for e in (entries if entries is not None else load())]
    return date.fromisoformat(min(days)) if days else None


def _code(ticker: Optional[str]) -> Optional[str]:
    t = (ticker or "").upper()
    return t[:-3] if t.endswith(".JO") else None


def announcements_for(company: str, ticker: Optional[str] = None, entries: Optional[list[dict]] = None) -> list[dict]:
    """Logged announcements by this issuer: by JSE share code when both sides have one, else by name."""
    from src.engines.deterministic_engine import _company_matchers
    code = _code(ticker)
    ms = _company_matchers(company, ticker=ticker)
    out = []
    for e in entries if entries is not None else load():
        if code and e.get("code"):
            if e["code"] == code:
                out.append(e)
        elif any(m.search(e.get("issuer") or "") for m in ms):
            out.append(e)
    return out


def events_for(company: str, ticker: Optional[str] = None, entries: Optional[list[dict]] = None) -> list[dict]:
    """The company's SENS announcements that report a completed event, as official confirmation events."""
    out = []
    for e in announcements_for(company, ticker, entries):
        types = classify_headline(e.get("headline") or "")
        if types:
            out.append({"date": e["date"], "signal_types": sorted(types), "official": True,
                        "source": f"JSE SENS: {(e.get('headline') or '')[:110]}", "url": e.get("url")})
    return out
