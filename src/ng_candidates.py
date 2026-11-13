"""
Nigeria's 2027 candidates for governorship, Senate and House of Representatives, from INEC's final lists (parsed by
scripts/parse_inec_candidates.py into src/data/ng_candidates_2027.json), with matching for news tagging.

INEC lists names surname first ("Umezurike Doris Uzumma"); the news writes them either way ("Doris Umezurike"), so a
candidate is found by any two of their names side by side, in either order, and only in a story that also names
their state: many Nigerian names are shared, and a "Musa Abubakar" in a Kano story is not Bauchi's candidate.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

PATH = Path(__file__).resolve().parent / "data" / "ng_candidates_2027.json"
OFFICES = ("governorship", "senate", "house_of_representatives")
TAGGED = ("governorship", "senate")            # House candidates are searchable but not tagged in news


@lru_cache(maxsize=1)
def _all() -> list[dict]:
    return json.loads(PATH.read_text())["candidates"]


def source() -> str:
    return json.loads(PATH.read_text())["source"]


def search(office: Optional[str] = None, state: Optional[str] = None, constituency: Optional[str] = None,
           party: Optional[str] = None, q: str = "", limit: int = 100, offset: int = 0) -> dict:
    if office and office not in OFFICES:
        raise ValueError("office must be one of: " + ", ".join(OFFICES) + ".")
    ql = q.strip().lower()
    rows = [r for r in _all()
            if (not office or r["office"] == office) and (not state or r["state"].lower() == state.strip().lower())
            and (not constituency or constituency.strip().lower() in r["constituency"].lower())
            and (not party or r["party"].upper() == party.strip().upper())
            and (not ql or ql in (r["name"] or "").lower() or ql in (r.get("running_mate") or "").lower())]
    return {"total": len(rows), "offset": offset, "candidates": rows[offset:offset + limit], "source": source()}


def _pairs(name: str) -> list[str]:
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'’.-]+", name or "") if len(w.strip(".")) > 1]
    out = []
    for i in range(len(words) - 1):
        for a, b in ((words[i], words[i + 1]), (words[i + 1], words[i])):
            out.append(re.escape(a) + r"\s+" + re.escape(b))
    if len(words) >= 2:                                    # first and last name, the way headlines often shorten
        out += [re.escape(words[1]) + r"\s+" + re.escape(words[0]), re.escape(words[-1]) + r"\s+" + re.escape(words[0])]
    return list(dict.fromkeys(out))


@lru_cache(maxsize=1)
def _patterns() -> dict[str, list[tuple[str, str, re.Pattern]]]:
    by_state: dict[str, list[tuple[str, str, re.Pattern]]] = {}
    for r in _all():
        if r["office"] not in TAGGED or not r["name"]:
            continue
        pairs = _pairs(r["name"])
        if pairs:
            by_state.setdefault(r["state"], []).append(
                (r["office"], r["name"], re.compile(r"(?i)(?<![A-Za-z])(?:" + "|".join(pairs) + r")(?![A-Za-z])")))
    return by_state


def in_text(text: str, states: list[str]) -> dict[str, list[str]]:
    """Governorship and Senate candidates the text names, among those of the states it names."""
    found: dict[str, list[str]] = {}
    for st in states:
        for office, name, pat in _patterns().get(st, ()):
            if pat.search(text) and name not in found.get(office, []):
                found.setdefault(office, []).append(name)
    return {"gov_candidates": found.get("governorship", []), "senate_candidates": found.get("senate", [])}
