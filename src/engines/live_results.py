"""
Live results for an election declared unit by unit (The Gambia's constituencies, Nigeria's states): each result is
checked when it is entered, and the national and area tallies are built from the results in so far. What differs
between elections (units, areas, ballot, rejected ballots, the rule deciding the winner, a baseline) comes from
src/data/live_elections.py.

Checks on a result: a known unit, known candidates, whole non-negative numbers, votes cast equal to the candidates'
sum plus rejected ballots (none where votes are cast with marbles), and votes cast within the register. A turnout
above 95 per cent is accepted with a warning: the commission's figure is what it is.
"""
from __future__ import annotations

import re
from typing import Optional

from src.data import live_elections as le


class ResultError(ValueError):
    pass


def candidates(election: str = "gm-2026") -> list[dict]:
    return le.spec(election)["ballot"]()


def _candidate(name: str, election: str) -> Optional[str]:
    """The candidate a name as announced refers to: full name, party, pattern, or a surname unique on the ballot."""
    key = (name or "").strip()
    ballot = candidates(election)
    for c in ballot:
        if key.lower() == c["name"].lower() or (c.get("party") and key.upper() == c["party"].upper()):
            return c["name"]
    for c in ballot:
        if re.search(c["pattern"], key):
            return c["name"]
    same = [c["name"] for c in ballot if c["name"].split()[-1].lower() == key.lower()]
    return same[0] if len(same) == 1 else None


def _whole(value, what: str, positive: bool = False) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < (1 if positive else 0):
        raise ResultError(f"{what} must be a whole number{' above zero' if positive else ' of zero or more'}.")
    return value


def check(entry: dict, election: str = "gm-2026") -> dict:
    """A clean result from an entry, with any warnings; raises ResultError on a result that cannot stand."""
    s = le.spec(election)
    named = entry.get("unit") or entry.get("constituency") or entry.get("state")
    unit = s["unit"](str(named or ""))
    if not unit:
        raise ResultError(f"Unknown {s['unit_word']}: {named!r}.")
    raw = entry.get("votes")
    if not isinstance(raw, dict) or not raw:
        raise ResultError("votes must map each candidate to a number.")
    votes: dict[str, int] = {}
    for name, n in raw.items():
        cand = _candidate(str(name), election)
        if not cand:
            raise ResultError(f"Unknown candidate: {name!r}.")
        if cand in votes:
            raise ResultError(f"{cand} is entered twice.")
        votes[cand] = _whole(n, f"Votes for {cand}")
    ballot = [c["name"] for c in candidates(election)]
    missing = [c for c in ballot if c not in votes]
    # On a long ballot (Nigeria: 18 tickets) the commission reads the minor candidates too, but an operator may enter
    # the leading ones first; those left out count as zero only when the entry says so.
    if missing and not (entry.get("others_zero") and len(missing) < len(ballot)):
        raise ResultError("Missing votes for: " + ", ".join(missing) + " (enter 0 if none).")
    for c in missing:
        votes[c] = 0
    valid = sum(votes.values())
    rejected = _whole(entry.get("rejected"), "Rejected ballots")
    if rejected and not s["rejected"]:
        raise ResultError("This election has no rejected ballots.")
    cast = valid + (rejected or 0)
    stated = _whole(entry.get("votes_cast"), "Votes cast")
    if stated is not None and stated != cast:
        raise ResultError(f"Votes cast ({stated:,}) does not equal valid votes plus rejected ballots ({cast:,}).")
    registered = _whole(entry.get("registered"), "registered", positive=True)
    accredited = _whole(entry.get("accredited"), "accredited")
    warnings = []
    if accredited is not None and cast > accredited:
        raise ResultError(f"Votes cast ({cast:,}) exceed accredited voters ({accredited:,}).")
    if registered is not None:
        if cast > registered:
            raise ResultError(f"Votes cast ({cast:,}) exceed registered voters ({registered:,}).")
        if accredited is not None and accredited > registered:
            raise ResultError(f"Accredited voters ({accredited:,}) exceed registered voters ({registered:,}).")
        if cast > 0.95 * registered:
            warnings.append(f"Turnout {cast / registered:.1%} is unusually high.")
    status = entry.get("status") or "declared"
    if status not in ("provisional", "declared"):
        raise ResultError("status must be provisional or declared.")
    source = (entry.get("source") or "").strip()[:300] or None
    if source and not re.match(r"https://", source):
        raise ResultError("source must be an https link.")
    return {"unit": unit, "area": le.units(election)[unit], "votes": votes, "valid": valid, "rejected": rejected,
            "votes_cast": cast, "accredited": accredited, "registered": registered, "status": status,
            "source": source, "warnings": warnings}


def _ranked(votes: dict[str, int], election: str) -> list[dict]:
    total = sum(votes.values())
    parties = {c["name"]: c.get("party") for c in candidates(election)}
    return [{"candidate": n, "party": parties.get(n), "votes": v, "share": round(v / total, 4) if total else 0.0}
            for n, v in sorted(votes.items(), key=lambda kv: (-kv[1], kv[0])) if v or total == 0]


def _spread(by_unit: dict[str, dict], election: str) -> dict:
    """Nigeria: the winner needs at least 25% of the votes in two-thirds of the 36 states (24); whether the FCT is
    also required is disputed, so it is reported on its own."""
    names = [c["name"] for c in candidates(election)]
    states = [u for u in le.units(election) if u != "FCT"]
    out = {}
    for n in names:
        reached = [u for u in states if u in by_unit and by_unit[u]["valid"] and by_unit[u]["votes"].get(n, 0) / by_unit[u]["valid"] >= 0.25]
        fct = by_unit.get("FCT")
        out[n] = {"states_at_25": len(reached), "needed": 24, "met": len(reached) >= 24,
                  "fct_at_25": (fct["votes"].get(n, 0) / fct["valid"] >= 0.25) if fct and fct["valid"] else None}
    return {k: v for k, v in sorted(out.items(), key=lambda kv: -kv[1]["states_at_25"]) if v["states_at_25"] or v["fct_at_25"]}


def tally(rows: list[dict], election: str = "gm-2026") -> dict:
    """National, area and unit results from the units in so far."""
    s = le.spec(election)
    unit_area = le.units(election)
    by_unit = {}
    for r in rows:
        u = r.get("unit") or r.get("constituency")
        if u in unit_area:
            by_unit[u] = {**r, "unit": u, "valid": r.get("valid", sum(r["votes"].values()))}
    names = [c["name"] for c in candidates(election)]
    base = s.get("baseline") or {"national": {}, "units": {}}

    def summarise(results: list[dict], registered: Optional[int], total_units: int) -> dict:
        votes = {n: sum(r["votes"].get(n, 0) for r in results) for n in names}
        valid = sum(votes.values())
        cast = sum(r["votes_cast"] for r in results)
        ranked = _ranked(votes, election)
        wins: dict[str, int] = {}
        for r in results:
            top = max(r["votes"].items(), key=lambda kv: kv[1], default=(None, 0))
            if top[0] and top[1] and list(r["votes"].values()).count(top[1]) == 1:
                wins[top[0]] = wins.get(top[0], 0) + 1
        complete = len(results) == total_units
        unit_reg = [r.get("registered") for r in results]
        reg = registered if registered else (sum(unit_reg) if results and all(unit_reg) else None)
        return {"reported": len(results), "units": total_units, "complete": complete,
                "declared": sum(1 for r in results if r["status"] == "declared"),
                "valid": valid, "rejected": sum(r.get("rejected") or 0 for r in results), "votes_cast": cast,
                "registered": reg,
                # turnout only once every unit of the area (or the country) is in
                "turnout": round(cast / reg, 4) if complete and reg else None,
                "results": ranked, "units_won": dict(sorted(wins.items(), key=lambda kv: -kv[1])),
                "leader": ranked[0]["candidate"] if valid else None,
                "margin": ranked[0]["votes"] - ranked[1]["votes"] if valid and len(ranked) > 1 else None}

    areas = []
    for area, a in s["areas"].items():
        results = [by_unit[u] for u in a["units"] if u in by_unit]
        areas.append({"area": area, "region": a["region"], **summarise(results, a["registered"], len(a["units"])),
                      "pending": [u for u in a["units"] if u not in by_unit]})
    national = summarise(list(by_unit.values()), s["national_registered"], len(unit_area))
    if s["national_registered"]:
        national["register_reported"] = round(sum(a["registered"] for a in areas if a["complete"] and a["registered"])
                                              / s["national_registered"], 4)
    for r in national["results"]:
        if r["candidate"] in base["national"]:
            r[f"votes_{base['year']}"] = base["national"][r["candidate"]]
    if s["rule"] == "ng_spread":
        national["spread"] = _spread(by_unit, election)
    out_units = []
    for u, area in unit_area.items():
        r = by_unit.get(u)
        ranked = _ranked(r["votes"], election) if r else []
        prior = base["units"].get(u) or {}
        prior_total = sum(prior.values())
        for x in ranked:
            if x["candidate"] in prior and prior_total:
                x[f"share_{base['year']}"] = round(prior[x["candidate"]] / prior_total, 4)
        out_units.append({"unit": u, "area": area, "status": r["status"] if r else "pending", "results": ranked,
                          "valid": r["valid"] if r else None, "rejected": r.get("rejected") if r else None,
                          "votes_cast": r["votes_cast"] if r else None, "registered": r.get("registered") if r else None,
                          "accredited": r.get("accredited") if r else None,
                          "turnout": round(r["votes_cast"] / r["registered"], 4) if r and r.get("registered") else None,
                          "winner": ranked[0]["candidate"] if ranked and ranked[0]["votes"] and
                          (len(ranked) < 2 or ranked[0]["votes"] > ranked[1]["votes"]) else None,
                          "source": r.get("source") if r else None, "updated_at": r.get("updated_at") if r else None})
    return {"election": election, "label": s["label"], "polling_day": s["polling_day"], "body": s["body"],
            "unit_word": s["unit_word"], "units_word": s["units_word"], "area_word": s["area_word"],
            "candidates": names, "national": national, "areas": areas, "units": out_units,
            "baseline_year": base.get("year"), "notes": s["notes"] + " Turnout is shown for an area once all of it is in."}
