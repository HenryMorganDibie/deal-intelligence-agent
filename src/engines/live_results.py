"""
Live results for an election announced constituency by constituency (The Gambia, 5 December 2026): each result is
checked when it is entered, and the national and area tallies are built from the results in so far.

A result is the votes per candidate, as the electoral commission reads it out, with the constituency's registered
voters when announced. Checks: a known constituency, known candidates, whole non-negative numbers, votes cast equal
to the candidates' sum (marbles: no rejected ballots), and votes cast within the register. A turnout above 95 per
cent is accepted with a warning, since the commission's figure is what it is.
"""
from __future__ import annotations

import re
from typing import Optional

from src.data import gm_2026 as gm
from src.data.election_profiles import PROFILES


class ResultError(ValueError):
    pass


def candidates(election: str = gm.ELECTION) -> list[dict]:
    """Candidates on the ballot: the profile's confirmed names (statuses are updated as the commission decides)."""
    return [c for c in PROFILES[election].get("candidates", ()) if c.get("status") == "confirmed"]


def _candidate(name: str, election: str) -> Optional[str]:
    """The candidate a name as announced refers to: full name, surname pattern, or party."""
    key = (name or "").strip()
    ballot = candidates(election)
    for c in ballot:
        if key.lower() == c["name"].lower() or (c.get("party") and key.upper() == c["party"]) \
                or re.search(c["pattern"], key):
            return c["name"]
    # a surname alone ("Darboe"), when only one candidate on the ballot has it
    same = [c["name"] for c in ballot if c["name"].split()[-1].lower() == key.lower()]
    return same[0] if len(same) == 1 else None


def check(entry: dict, election: str = gm.ELECTION) -> dict:
    """A clean result from an entry, with any warnings; raises ResultError on a result that cannot stand."""
    con = gm.constituency(str(entry.get("constituency") or ""))
    if not con:
        raise ResultError(f"Unknown constituency: {entry.get('constituency')!r}.")
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
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise ResultError(f"Votes for {cand} must be a whole number of zero or more.")
        votes[cand] = n
    missing = [c["name"] for c in candidates(election) if c["name"] not in votes]
    if missing:
        raise ResultError("Missing votes for: " + ", ".join(missing) + " (enter 0 if none).")
    cast = sum(votes.values())
    stated = entry.get("votes_cast")
    if stated is not None and stated != cast:
        raise ResultError(f"Votes cast ({stated:,}) does not equal the candidates' votes ({cast:,}).")
    registered = entry.get("registered")
    warnings = []
    if registered is not None:
        if isinstance(registered, bool) or not isinstance(registered, int) or registered <= 0:
            raise ResultError("registered must be a positive whole number.")
        if cast > registered:
            raise ResultError(f"Votes cast ({cast:,}) exceed registered voters ({registered:,}).")
        if cast > 0.95 * registered:
            warnings.append(f"Turnout {cast / registered:.1%} is unusually high.")
    status = entry.get("status") or "declared"
    if status not in ("provisional", "declared"):
        raise ResultError("status must be provisional or declared.")
    source = (entry.get("source") or "").strip()[:300] or None
    if source and not re.match(r"https://", source):
        raise ResultError("source must be an https link.")
    return {"constituency": con, "area": gm.CONSTITUENCIES[con], "votes": votes, "votes_cast": cast,
            "registered": registered, "status": status, "source": source, "warnings": warnings}


def _ranked(votes: dict[str, int]) -> list[dict]:
    total = sum(votes.values())
    parties = {c["name"]: c.get("party") for c in candidates()}
    return [{"candidate": n, "party": parties.get(n), "votes": v, "share": round(v / total, 4) if total else 0.0}
            for n, v in sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))]


def tally(rows: list[dict], election: str = gm.ELECTION) -> dict:
    """National, area and constituency results from the constituencies in so far."""
    by_con = {r["constituency"]: r for r in rows if r.get("constituency") in gm.CONSTITUENCIES}
    names = [c["name"] for c in candidates(election)]

    def summarise(results: list[dict], registered: Optional[int], total_cons: int) -> dict:
        votes = {n: sum(r["votes"].get(n, 0) for r in results) for n in names}
        cast = sum(votes.values())
        ranked = _ranked(votes)
        wins: dict[str, int] = {}
        for r in results:
            top = max(r["votes"].items(), key=lambda kv: kv[1], default=(None, 0))
            if top[0] and list(r["votes"].values()).count(top[1]) == 1:
                wins[top[0]] = wins.get(top[0], 0) + 1
        complete = len(results) == total_cons
        return {"reported": len(results), "constituencies": total_cons, "complete": complete,
                "declared": sum(1 for r in results if r["status"] == "declared"),
                "votes_cast": cast, "registered": registered,
                # turnout only once every constituency of the area (or the country) is in
                "turnout": round(cast / registered, 4) if complete and registered else None,
                "results": ranked, "constituencies_won": dict(sorted(wins.items(), key=lambda kv: -kv[1])),
                "leader": ranked[0]["candidate"] if cast else None,
                "margin": ranked[0]["votes"] - ranked[1]["votes"] if cast and len(ranked) > 1 else None}

    areas = []
    for area, a in gm.AREAS.items():
        results = [by_con[c] for c in a["constituencies"] if c in by_con]
        areas.append({"area": area, "region": a["region"], **summarise(results, a["registered"], len(a["constituencies"])),
                      "pending": [c for c in a["constituencies"] if c not in by_con]})
    national = summarise(list(by_con.values()), gm.NATIONAL_REGISTERED, len(gm.CONSTITUENCIES))
    # share of the register in areas that have fully reported, a rough measure of how much is counted
    national["register_reported"] = round(sum(a["registered"] for a in areas if a["complete"]) / gm.NATIONAL_REGISTERED, 4)
    # 2021 national votes for reference (the sourced figures; the 2021 total of all six candidates is not, so no
    # share is derived from them)
    base = gm.BASELINE_2021["votes"]
    for r in national["results"]:
        if r["candidate"] in base:
            r["votes_2021"] = base[r["candidate"]]
    cons = []
    for c, area in gm.CONSTITUENCIES.items():
        r = by_con.get(c)
        ranked = _ranked(r["votes"]) if r else []
        cons.append({"constituency": c, "area": area, "status": r["status"] if r else "pending",
                     "results": ranked, "votes_cast": r["votes_cast"] if r else None,
                     "registered": r.get("registered") if r else None,
                     "turnout": round(r["votes_cast"] / r["registered"], 4) if r and r.get("registered") else None,
                     "winner": ranked[0]["candidate"] if ranked and ranked[0]["votes"] and
                     (len(ranked) < 2 or ranked[0]["votes"] > ranked[1]["votes"]) else None,
                     "source": r.get("source") if r else None, "updated_at": r.get("updated_at") if r else None})
    return {"election": election, "polling_day": gm.POLLING_DAY, "candidates": names, "national": national,
            "areas": areas, "constituencies": cons,
            "notes": "Results as announced by the IEC, constituency by constituency, entered as they are read out. "
                     "Turnout is shown for an area once all its constituencies are in."}
