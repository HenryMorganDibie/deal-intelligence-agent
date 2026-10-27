"""
One story, one event.

An event's id is a hash of its headline, so every publisher's wording of the same story was a separate event:
"Helios to acquire up to 49% of Mozambican flour miller Merec Industries", "Helios Investment Partners acquires
49% stake in Merec", "Helios to buy up to 49% of Mozambique's largest flour miller" and "Helios to acquire
Mozambique milling company stake" were four. A later report of a story is marked merged_into the first, and the
product shows the first only.

Ownership events (M&A, stake changes) are compared as deals, with the deal extractor and deals.same_transaction,
so an announcement and its completion months later are one story. Other events are one story when they name the
same company, are of the same type, fall within a week, and share most of their distinctive words.
"""
from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from typing import Iterable, Optional

from src.data.africa_countries import countries_in_text
from src.engines import deals as deals_mod
from src.engines.event_filters import named_company

OWNERSHIP_TYPES = {"m_and_a_activity", "insider_activity"}
_GENERIC = {"ifc", "ipo", "plans", "plan", "investment", "invests", "million", "billion", "stake", "deal", "acquire",
            "acquires", "buy", "buys", "sell", "sells", "raise", "raises", "funding", "bank", "group", "company",
            "announces", "listing", "shares", "africa", "african", "percent", "per", "cent", "usd"}
STORY_WINDOW_DAYS = 7
_STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "with", "as", "by", "at", "from", "its", "after",
         "over", "into", "new", "says", "said", "report", "reports", "amid", "news"}


def _day(event: dict) -> Optional[date]:
    try:
        return date.fromisoformat(str(event.get("day") or "")[:10])
    except ValueError:
        return None


def _words(headline: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (headline or "").lower()) if len(w) > 2 and w not in _STOP}


@lru_cache(maxsize=20000)
def _deal(headline: str, day: str, publisher: str) -> Optional[dict]:
    return deals_mod.extract_deal(headline, published=day or None, publisher=publisher or "")


def same_story(a: dict, b: dict) -> bool:
    """Whether two events report the same story (see the module docstring)."""
    ownership = {a.get("signal_type"), b.get("signal_type")} <= OWNERSHIP_TYPES
    if a.get("signal_type") != b.get("signal_type") and not ownership:
        return False
    da, db = _day(a), _day(b)
    if not da or not db:
        return False
    # Stored countries can come from the search that found the story; the countries the headlines name are
    # the sharper test.
    # (Deals have their own country test, which knows a buyer's home from the deal's market.)
    ownership = {a.get("signal_type"), b.get("signal_type")} <= OWNERSHIP_TYPES
    ca = {c.iso2 for c in countries_in_text(a.get("headline") or "")}
    cb = {c.iso2 for c in countries_in_text(b.get("headline") or "")}
    if not ownership and ca and cb and not ca & cb:
        return False                                    # Malawi's debt relief is not Ethiopia's
    gap = abs((da - db).days)
    if ownership:
        x = _deal(a.get("headline") or "", str(a.get("day") or "")[:10], a.get("publisher") or "")
        y = _deal(b.get("headline") or "", str(b.get("day") or "")[:10], b.get("publisher") or "")
        if x and y:
            return deals_mod.same_transaction(x, y)
    if gap > STORY_WINDOW_DAYS:
        return False
    na, nb = named_company(a.get("headline") or ""), named_company(b.get("headline") or "")
    # Finance vocabulary ("IFC plans investment in IPO") says what kind of story it is, not which one.
    wa = _words(a.get("headline") or "") - _GENERIC
    wb = _words(b.get("headline") or "") - _GENERIC
    if not wa or not wb:
        return False
    overlap = len(wa & wb) / min(len(wa), len(wb))
    if na or nb:                                        # a named company must be the same one in both
        return bool(na and nb) and deals_mod.normalise_name(na) == deals_mod.normalise_name(nb) and overlap >= 0.3
    return overlap >= 0.6


def resolve(new: Iterable[dict], existing: dict[str, dict]) -> list[dict]:
    """New events with merged_into set when an earlier stored or new event reports the same story. A stored
    event keeps the merged_into it already had (a rolling re-scan upserts it again)."""
    # Merged events stay candidates (pointing at their story's first report): a later report may match the
    # wording of a merged one ("...Mozambican flour miller Merec Industries") rather than the first.
    pool = list(existing.values())
    # Candidates share a distinctive word; the index keeps the comparison to a handful per event.
    index: dict[str, list[dict]] = {}

    def add(event: dict) -> None:
        for w in _words(event.get("headline") or ""):
            index.setdefault(w, []).append(event)

    for e in pool:
        add(e)
    out = []
    for e in sorted(new, key=lambda x: (str(x.get("day") or ""), x.get("id") or "")):
        stored = existing.get(e.get("id"))
        if stored and stored.get("merged_into"):
            e = {**e, "merged_into": stored["merged_into"]}
        elif not stored:
            seen: set[str] = set()
            for w in _words(e.get("headline") or ""):
                for c in index.get(w, []):
                    if c["id"] in seen or c["id"] == e.get("id"):
                        continue
                    seen.add(c["id"])
                    if same_story(e, c):
                        e = {**e, "merged_into": c.get("merged_into") or c["id"]}
                        break
                if e.get("merged_into"):
                    break
        out.append(e)
        add(e)
    return out
