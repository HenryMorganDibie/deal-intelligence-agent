"""
Per-record verification: for each field of a deal, where the value came from and how far it can be
trusted, so a researcher sees on the record itself what is corroborated, what is single-source,
what is derived, and what is uncertain.

Every source of a deal keeps its own headline. Each headline is extracted on its own, sources are
grouped into independent stories (syndicated copies and near-identical headlines are one story),
and a reported value is "corroborated" when two or more independent stories state it.

Statuses:
  corroborated   stated by two or more independent stories
  reported       stated by one story (or several copies of one story)
  derived        computed from reported values (USD conversion, stake-implied valuation)
  classified     assigned by keyword rules (sector), not stated as such
  uncertain      sources disagree, or the extraction is known to be weak for this form
  not disclosed  no source states it
"""
from __future__ import annotations

import re
from typing import Optional
from src.engines.official_sources import verify_url

from src.engines import deals as dl
from src.engines import investors as inv

_STOP = {"the", "and", "for", "with", "from", "that", "this", "its", "des", "les", "pour", "dans", "une", "sur"}
_WIRE = re.compile(r"\b(reuters|bloomberg|afp|apo\s+group|business\s+wire|pr\s+newswire|globe\s*newswire)\b", re.IGNORECASE)
_PRESENT_ACQUISITION = re.compile(r"\b(acquires|buys|acquiert|rach[eè]te|adquire|compra)\b", re.IGNORECASE)


def _tokens(title: str) -> set[str]:
    return {w for w in re.findall(r"[^\W_]{3,}", (title or "").lower()) if w not in _STOP}


def stories(sources: list[dict]) -> list[list[dict]]:
    """Sources grouped into independent stories."""
    groups: list[tuple[set[str], list[dict]]] = []
    for s in sources:
        toks = _tokens(s.get("title") or "")
        wire = _WIRE.search(f"{s.get('publisher') or ''} {s.get('title') or ''}")
        for gt, members in groups:
            same_wire = wire and any(_WIRE.search(f"{m.get('publisher') or ''} {m.get('title') or ''}") for m in members)
            if (toks and gt and len(toks & gt) / len(toks | gt) >= 0.6) or same_wire:
                members.append(s)
                gt |= toks
                break
        else:
            groups.append((set(toks), [s]))
    return [m for _, m in groups]


def _extract(s: dict) -> Optional[dict]:
    if not s.get("title"):
        return None
    return dl.extract_deal(s["title"], "", published=s.get("date"), publisher=s.get("publisher") or "",
                           africa_source=True, rates=lambda c, y: None)


def _same(field: str, a, b) -> bool:
    if a is None or b is None:
        return False
    if field in ("target", "buyer", "seller"):
        return dl.normalise_name(inv.canonical(a) or a) == dl.normalise_name(inv.canonical(b) or b)
    if field == "amount":
        return abs(a - b) <= 0.01 * max(a, b)
    if field == "stake_pct":
        return abs(a - b) < 0.5
    return a == b


def verify(deal: dict) -> dict:
    sources = list(deal.get("sources") or [])
    groups = stories(sources)
    per_story = [[e for e in (_extract(s) for s in g) if e] for g in groups]
    titled = sum(1 for s in sources if s.get("title"))

    def support(field: str, value) -> int:
        """Independent stories in which some source states this value."""
        return sum(1 for exs in per_story if any(_same(field, ex.get(field), value) for ex in exs))

    def conflicts(field: str, value) -> list:
        """Other values stated by any source, copies included: a disagreement is worth showing either way."""
        return sorted({str(ex.get(field)) for exs in per_story for ex in exs
                       if ex.get(field) is not None and value is not None and not _same(field, ex.get(field), value)})

    def reported(field: str, label: str, value, display=None) -> dict:
        if value in (None, "", []):
            return {"field": label, "value": None, "status": "not disclosed", "basis": "No source states it."}
        n, other = support(field, value), conflicts(field, value)
        if other:
            status, basis = "uncertain", f"Sources disagree: also reported as {', '.join(other[:3])}."
        elif n >= 2:
            status, basis = "corroborated", f"Stated by {n} independent stories."
        else:
            status, basis = "reported", ("Stated by one story." if titled else "Extracted from the headline; per-source "
                                         "headlines were not kept for this record, so agreement cannot be checked.")
        return {"field": label, "value": display if display is not None else value, "status": status, "basis": basis,
                "independent_stories": n}

    fields = []
    fields.append(reported("target", "Target", deal.get("target")))
    lead = deal.get("buyer") or (deal.get("investors") or [None])[0]
    fields.append(reported("buyer", "Buyer, lead investor or lender", lead))
    for f in fields[-2:]:
        if f["value"] and len(inv.split_names(f["value"])) != 1:
            f.update(status="uncertain", basis="The extracted name looks malformed (a combination or a headline fragment).")
    amt = deal.get("amount")
    fields.append(reported("amount", "Amount (as reported)", amt,
                           f"{deal.get('currency') or ''} {amt:,.0f}".strip() if amt else None))
    if deal.get("amount_usd") is not None and deal.get("currency") not in (None, "USD"):
        fields.append({"field": "Amount in USD", "value": deal["amount_usd"], "status": "derived",
                       "basis": f"Converted from {deal['currency']} at the annual average rate for the year announced."})
    elif deal.get("amount_usd") is not None:
        fields.append({"field": "Amount in USD", "value": deal["amount_usd"], "status": "reported",
                       "basis": "Reported in US dollars."})
    fields.append(reported("stake_pct", "Stake", deal.get("stake_pct"),
                           f"{deal['stake_pct']:g}%" if deal.get("stake_pct") is not None else None))
    if deal.get("implied_valuation_usd"):
        fields.append({"field": "Implied valuation", "value": deal["implied_valuation_usd"], "status": "derived",
                       "basis": "Amount divided by the stake percentage; not a reported valuation."})
    if deal.get("reported_valuation_usd"):
        fields.append(reported("reported_valuation_usd", "Reported valuation", deal["reported_valuation_usd"]))
    stage = reported("stage", "Stage", deal.get("stage"))
    if deal.get("deal_type") in ("acquisition", "merger") and stage["status"] != "corroborated" and any(
            _PRESENT_ACQUISITION.search(s.get("title") or "") for s in sources):
        stage.update(status="uncertain", basis="Headlines in the present tense ('X acquires Y') often precede regulatory "
                                               "approval and closing; completion is not confirmed.")
    fields.append(stage)
    fields.append(reported("deal_type", "Deal type", deal.get("deal_type")))
    fields.append({"field": "Country", "value": deal.get("country"),
                   "status": "reported" if deal.get("country") else "not disclosed",
                   "basis": "Named in the headline or snippet." if deal.get("country") else "No African country named."})
    fields.append({"field": "Sector", "value": deal.get("sector"), "status": "classified" if deal.get("sector") else "not disclosed",
                   "basis": "Assigned by keyword rules from the headline; not stated by the source."})

    stage_dates = {}
    for s in sorted(sources, key=lambda s: s.get("date") or ""):
        st = s.get("stage") or (_extract(s) or {}).get("stage")
        if st and st not in stage_dates and s.get("date"):
            stage_dates[st] = s["date"]
    official = []
    official_checks = []
    for source in sources:
        check = verify_url(source.get("url"), deal.get("country"))
        official_checks.append({**check, "publisher": source.get("publisher"), "url": source.get("url")})
        if check["status"] == "official_host_match":
            official.append(source)
    n_stories = len(groups)
    tier = ("official" if official else "corroborated" if n_stories >= 2 else "single source")
    return {
        "tier": tier,
        "tier_label": {"official": "Official disclosure among the sources",
                       "corroborated": f"Corroborated by {n_stories} independent stories",
                       "single source": "Single source: verify before relying on it"}[tier],
        "sources": len(sources), "independent_stories": n_stories,
        "official_source_verification": {
            "status": "official_host_match" if official else "no_official_host_verified",
            "official_host_matched_sources": len(official),
            "checks": official_checks,
            "note": "Official status requires an HTTPS URL matching the explicit source-host registry; publisher text alone is insufficient.",
        },
        "syndicated_copies": len(sources) - n_stories,
        "dates": {"first_reported": min((s.get("date") for s in sources if s.get("date")), default=deal.get("announced")),
                  "announced_or_rumoured": stage_dates.get("announced") or stage_dates.get("rumoured"),
                  "completed_reported": stage_dates.get("completed"),
                  "note": "Dates are when sources reported each stage, not legal signing or closing dates."},
        "fields": fields,
        "story_groups": [[{"publisher": s.get("publisher"), "date": s.get("date"), "title": s.get("title"),
                           "url": s.get("url")} for s in g] for g in groups],
    }
