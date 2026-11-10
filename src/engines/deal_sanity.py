"""
Checks that flag a stored deal as likely wrong, so it is held out of the daily post drafts and listed for review.

Each rule encodes a mistake actually found in the data: a sentence read as a party ("Don't Sell Your Votes"), a
figure from the company's history ($397M already lent, read as a round), a place or the company itself recorded
as its investor, an implausible size for the stage, or the same company twice in a week. A flag is a reason to
look, not a verdict: the record stays visible in the app until a person or a later rule decides.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from src.engines import deals as deals_mod

# The most a round of each stage plausibly raises in Africa; above it the figure is usually a misread (a
# valuation, a programme, a company's total funding).
_STAGE_CEILING_USD = {"pre-seed": 5e6, "pre seed": 5e6, "seed": 25e6, "pre-series a": 30e6, "series a": 120e6}
LARGE_SINGLE_SOURCE_USD = 50e6
DUPLICATE_WINDOW_DAYS = 7


def _day(value: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _same_company(a: Optional[str], b: Optional[str]) -> bool:
    wa, wb = set((a or "").lower().split()), set((b or "").lower().split())
    return bool(wa and wb) and (wa <= wb or wb <= wa)


def flags(d: dict, others: list[dict] = ()) -> list[str]:
    """Reasons this deal needs a human look; empty when nothing stands out."""
    out: list[str] = []
    parties = [d.get("target"), d.get("buyer"), d.get("seller"), *(d.get("investors") or [])]
    if any(isinstance(p, str) and deals_mod._not_a_party(p) for p in parties):
        out.append("a party reads like a sentence, not a name")
    for p in parties:
        if isinstance(p, str) and deals_mod._is_place_only(p):
            out.append(f"'{p}' is a place, not a company")
            break
    target = deals_mod.normalise_name(d.get("target"))
    if target and any(deals_mod.normalise_name(i) == target for i in d.get("investors") or []):
        out.append("the company is listed as its own investor")
    usd = d.get("amount_usd") or 0
    rnd = (d.get("round") or "").lower()
    if rnd in _STAGE_CEILING_USD and usd > _STAGE_CEILING_USD[rnd]:
        out.append(f"{usd / 1e6:,.0f}M is unusually large for a {rnd} round")
    stories = d.get("independent_stories") or len({s.get("publisher") for s in d.get("sources") or []})
    if usd >= LARGE_SINGLE_SOURCE_USD and stories < 2:
        out.append(f"a {usd / 1e6:,.0f}M figure from a single source")
    headline = d.get("headline") or ""
    if usd and len(deals_mod.parse_amounts(headline)) > 1:
        out.append("the headline has several figures; check which one is the deal")
    day = _day(d.get("announced"))
    if day:
        for o in others:
            if o.get("id") == d.get("id") or not _same_company(o.get("target"), d.get("target")):
                continue
            od = _day(o.get("announced"))
            if od and abs((od - day).days) <= DUPLICATE_WINDOW_DAYS:
                out.append(f"{d.get('target')} has another deal within a week ({o.get('id')}); possible duplicate")
                break
    return out


def review(deals: list[dict]) -> dict[str, list[str]]:
    """{deal id: reasons} for every flagged deal among those given."""
    return {d["id"]: r for d in deals if (r := flags(d, deals))}
