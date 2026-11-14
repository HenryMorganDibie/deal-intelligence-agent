"""
Elections with a live results tracker, each described by what its count needs: the units results are declared for
(The Gambia: constituencies; Nigeria: states), the areas they group into, the ballot, whether rejected ballots exist,
any rule on how the winner is decided, and a baseline from the last election for reference.
"""
from __future__ import annotations

import re
from typing import Optional

from src.data import elections_ng_2027 as ng
from src.data import gm_2026 as gm
from src.data.election_profiles import PROFILES

# Nigeria's six geopolitical zones (the FCT is in the North Central).
NG_ZONES: dict[str, list[str]] = {
    "North Central": ["Benue", "Kogi", "Kwara", "Nasarawa", "Niger", "Plateau", "FCT"],
    "North East": ["Adamawa", "Bauchi", "Borno", "Gombe", "Taraba", "Yobe"],
    "North West": ["Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Sokoto", "Zamfara"],
    "South East": ["Abia", "Anambra", "Ebonyi", "Enugu", "Imo"],
    "South South": ["Akwa Ibom", "Bayelsa", "Cross River", "Delta", "Edo", "Rivers"],
    "South West": ["Ekiti", "Lagos", "Ogun", "Ondo", "Osun", "Oyo"],
}


def _gm_ballot() -> list[dict]:
    return [{"name": c["name"], "party": c.get("party"), "pattern": c["pattern"]}
            for c in PROFILES[gm.ELECTION].get("candidates", ()) if c.get("status") == "confirmed"]


def _ng_ballot() -> list[dict]:
    # INEC's final list of presidential tickets; a candidate is matched by full name, party, surname or the names
    # the news uses for them (ALIASES: "Atiku", "Kwankwaso" and so on).
    out = []
    for acr, _, cand, _ in ng.TICKETS:
        names = [cand.split()[-1], *ng.ALIASES.get(cand, ())]
        out.append({"name": cand, "party": acr,
                    "pattern": r"(?i)^(?:" + "|".join(re.escape(n) for n in dict.fromkeys(names)) + r")$"})
    return out


def _ng_unit(name: str) -> Optional[str]:
    key = " ".join((name or "").replace("State", "").split()).lower()
    if key in ("abuja", "fct abuja", "federal capital territory"):
        return "FCT"
    return next((s for s in ng.STATES if s.lower() == key), None)


SPECS: dict[str, dict] = {
    gm.ELECTION: {
        "label": "The Gambia: presidential election, 5 December 2026", "country": "The Gambia",
        "polling_day": gm.POLLING_DAY, "body": "IEC", "unit_word": "constituency", "units_word": "constituencies",
        "area_word": "area", "areas": {a: {"region": v["region"], "registered": v["registered"], "units": v["constituencies"]}
                                       for a, v in gm.AREAS.items()},
        "national_registered": gm.NATIONAL_REGISTERED, "rejected": False, "rule": None,
        "ballot": _gm_ballot, "unit": gm.constituency,
        "baseline": {"year": 2021, "national": gm.BASELINE_2021["votes"], "units": {}},
        "page": "/elections/gambia",
        "notes": "Results as announced by the IEC, constituency by constituency, entered as they are read out. "
                 "Votes are cast with marbles, so there are no rejected ballots.",
    },
    "ng-2027": {
        "label": "Nigeria: presidential election, 16 January 2027", "country": "Nigeria",
        "polling_day": str(ng.PRESIDENTIAL_DAY), "body": "INEC", "unit_word": "state", "units_word": "states",
        "area_word": "zone", "areas": {z: {"region": z, "registered": None, "units": s} for z, s in NG_ZONES.items()},
        "national_registered": None, "rejected": True, "rule": "ng_spread",
        "ballot": _ng_ballot, "unit": _ng_unit,
        "baseline": None,                     # filled from src/data/ng_results_history.py when present
        "page": "/elections/nigeria",
        "notes": "Results as INEC's returning officers declare them at the national collation centre, state by state. "
                 "A candidate wins with the most votes and at least 25% of the votes in two-thirds of the states.",
    },
}


# ── Governorship: 28 races, each its own election, results declared by LGA ───

def _lga_names() -> dict[str, list[str]]:
    import json
    from pathlib import Path
    raw = json.loads((Path(__file__).resolve().parent / "ng_lgas.json").read_text())
    return {st: [_title_lga(x) for x in lgas] for st, lgas in raw.items()}


def _title_lga(name: str) -> str:
    """'AJEROMI/IFELODUN' -> 'Ajeromi/Ifelodun', 'AMUWO-ODOFIN' -> 'Amuwo-Odofin'."""
    name = re.sub(r"\s*/\s*", "/", " ".join(name.split()))
    name = {"YALMALTU/DEBA": "YAMALTU/DEBA"}.get(name.upper(), name)
    return re.sub(r"[A-Za-z']+", lambda m: m.group(0).capitalize(), name.lower())


def _lga_key(name: str) -> str:
    return re.sub(r"[^a-z]", "", (name or "").lower().replace("local government", "").replace("lga", ""))


def gov_slug(state: str) -> str:
    return re.sub(r"[^a-z]+", "-", state.lower()).strip("-")


def _gov_ballot(state: str):
    def ballot() -> list[dict]:
        from src import ng_candidates
        rows = [r for r in ng_candidates._all() if r["office"] == "governorship" and r["state"] == state and r["name"]]
        out = []
        for r in rows:
            words = [w for w in re.findall(r"[A-Za-z'’-]+", r["name"]) if len(w) > 1]
            pairs = [re.escape(a) + r"[\s-]+" + re.escape(b) for i in range(len(words) - 1)
                     for a, b in ((words[i], words[i + 1]), (words[i + 1], words[i]))]
            if len(words) >= 2:
                pairs.append(re.escape(words[-1]) + r"[\s-]+" + re.escape(words[0]))
            out.append({"name": r["name"], "party": r["party"], "running_mate": r.get("running_mate"),
                        "pattern": r"(?i)(?:" + "|".join(pairs or [re.escape(r["name"])]) + r")"})
        return out
    return ballot


def _gov_unit(lgas: list[str]):
    index = {_lga_key(x): x for x in lgas}

    def unit(name: str) -> Optional[str]:
        return index.get(_lga_key(name))
    return unit


def _gov_specs() -> dict[str, dict]:
    from src.data import ng_governorship as gov
    lgas = _lga_names()
    out = {}
    for st in gov.STATES:
        key = f"{gov.ELECTION}-{gov_slug(st)}"
        out[key] = {
            "label": f"{st}: governorship election, 6 February 2027", "country": "Nigeria", "state": st,
            "polling_day": gov.POLLING_DAY, "body": "INEC", "unit_word": "LGA", "units_word": "LGAs",
            "area_word": "state", "areas": {st: {"region": st, "registered": None, "units": lgas[st]}},
            "national_registered": None, "rejected": True, "rule": "ng_gov_spread",
            "ballot": _gov_ballot(st), "unit": _gov_unit(lgas[st]),
            "baseline": {"year": None, "national": {}, "units": {}},
            "store": gov.ELECTION, "alert_election": gov.ELECTION,
            "previous": {"year": 2023, "results": gov.RESULTS_2023.get(st, [])},
            "page": f"/elections/nigeria/governorship/{gov_slug(st)}",
            "notes": f"Results as INEC's returning officer for {st} declares them at the state collation centre, LGA by LGA. "
                     "A candidate wins with the most votes and at least 25% in two-thirds of the state's LGAs.",
        }
    return out


SPECS.update(_gov_specs())


def gov_elections() -> dict[str, str]:
    """State -> election key, for the 28 governorship races."""
    return {v["state"]: k for k, v in SPECS.items() if v.get("store") == "ng-2027-gov"}


def spec(election: str) -> dict:
    s = SPECS[election]
    if election == "ng-2027" and s["baseline"] is None:
        try:
            from src.data import ng_results_history as hist
            s["baseline"] = hist.baseline_2023()
        except ImportError:
            s["baseline"] = {"year": None, "national": {}, "units": {}}
    return s


def units(election: str) -> dict[str, str]:
    """Each unit and the area it belongs to."""
    return {u: a for a, v in spec(election)["areas"].items() for u in v["units"]}
