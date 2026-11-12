"""
Polling-unit result sheets (INEC Form EC8A): what a sheet must say, the checks that catch a misread or a doctored
sheet, and how sheets add up to ward, LGA, state and national totals.

The reading itself is done by a vision model (src/election_results.py); this module never trusts it. Every sheet is
checked arithmetically and against INEC's polling-unit list, and only a person can mark it verified. A sheet that
passes every check counts as provisional until then.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from src.data import elections_ng_2027 as ng

PARTIES = tuple(acr for acr, _, _, _ in ng.TICKETS)
ELECTIONS = {
    "presidential-2027": "EC8A(I)",
    "senate-2027": "EC8A(II)",
    "reps-2027": "EC8A(III)",
    "governorship-2027": "EC8A(IV)",
    "state-assembly-2027": "EC8A(V)",
}
FIGURES = ("registered", "accredited", "ballots_issued", "unused", "spoiled", "rejected", "valid", "votes_cast")
MAX_PLAUSIBLE_VOTERS = 3000          # a polling unit beyond this is almost always a misread digit

PROMPT = f"""You are reading a photograph or scan of a Nigerian INEC polling-unit result sheet (Form EC8A).
Read exactly what is written. Do not guess: use null for anything you cannot read with confidence.

Return one JSON object with these keys:
- "form": the form code printed on the sheet, e.g. "EC8A(I)"
- "state", "lga", "ward", "polling_unit": names as written
- "polling_unit_code": the code as written, digits separated by "/" (state/LGA/ward/unit), e.g. "24/11/01/001"
- "figures": an object with integers or null for "registered" (number of voters on the register),
  "accredited" (number of accredited voters), "ballots_issued" (ballot papers issued to the polling unit),
  "unused" (unused ballot papers), "spoiled" (spoiled ballot papers), "rejected" (rejected ballots),
  "valid" (total valid votes) and "votes_cast" (total used ballot papers / total votes cast)
- "votes": an object mapping each party acronym to the votes in FIGURES (integer, or null if blank/unreadable);
  the parties are {", ".join(PARTIES)}
- "votes_in_words": the same parties mapped to the votes written IN WORDS, converted to integers (null if blank)
- "signed": true if the presiding officer's signature or stamp is visible, false if clearly absent, null if unsure
- "legibility": "good", "fair" or "poor"
- "notes": anything unusual (corrections, overwriting, missing sections, stamps), or ""
"""


def _int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v) if v >= 0 else None
    digits = re.sub(r"[^\d]", "", str(v))
    return int(digits) if digits else None


def parse_model_output(text: str) -> dict:
    """The model's JSON, tolerating code fences or a sentence around it."""
    text = (text or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("The reading did not contain a JSON object.")
    raw = json.loads(m.group(0))
    figures = {k: _int((raw.get("figures") or {}).get(k)) for k in FIGURES}
    votes_raw = {str(k).upper().strip(): v for k, v in (raw.get("votes") or {}).items()}
    words_raw = {str(k).upper().strip(): v for k, v in (raw.get("votes_in_words") or {}).items()}
    return {
        "form": str(raw.get("form") or "").strip() or None,
        "state": raw.get("state"), "lga": raw.get("lga"), "ward": raw.get("ward"),
        "polling_unit": raw.get("polling_unit"),
        "polling_unit_code": normalise_code(raw.get("polling_unit_code")),
        "figures": figures,
        "votes": {p: _int(votes_raw.get(p)) for p in PARTIES},
        "votes_in_words": {p: _int(words_raw.get(p)) for p in PARTIES},
        "signed": raw.get("signed") if isinstance(raw.get("signed"), bool) else None,
        "legibility": raw.get("legibility") if raw.get("legibility") in ("good", "fair", "poor") else None,
        "notes": str(raw.get("notes") or "")[:500],
    }


def normalise_code(code: Any) -> Optional[str]:
    parts = re.findall(r"\d+", str(code or ""))
    if len(parts) != 4:
        return None
    s, l, w, u = (int(p) for p in parts)
    return f"{s:02d}/{l:02d}/{w:02d}/{u:03d}"


def check(sheet: dict, expected_code: Optional[str] = None, known_unit: Optional[dict] = None) -> list[dict]:
    """The checks a sheet must pass, each {"rule", "ok", "detail"}; "ok" is None when the figures needed are missing."""
    f, votes = sheet["figures"], sheet["votes"]
    out: list[dict] = []

    def add(rule: str, ok: Optional[bool], detail: str) -> None:
        out.append({"rule": rule, "ok": ok, "detail": detail})

    total = sum(v for v in votes.values() if v is not None)
    if f["valid"] is None:
        add("party_votes_sum_to_valid", None, "Total valid votes not read.")
    else:
        add("party_votes_sum_to_valid", total == f["valid"], f"Party votes add up to {total}; valid votes {f['valid']}.")
    if None in (f["valid"], f["rejected"], f["votes_cast"]):
        add("valid_plus_rejected_is_votes_cast", None, "Valid, rejected or total votes cast not read.")
    else:
        add("valid_plus_rejected_is_votes_cast", f["valid"] + f["rejected"] == f["votes_cast"],
            f"{f['valid']} valid + {f['rejected']} rejected = {f['valid'] + f['rejected']}; votes cast {f['votes_cast']}.")
    if None in (f["votes_cast"], f["accredited"]):
        add("votes_cast_within_accredited", None, "Votes cast or accredited voters not read.")
    else:
        add("votes_cast_within_accredited", f["votes_cast"] <= f["accredited"],
            f"{f['votes_cast']} votes cast; {f['accredited']} accredited.")
    if None in (f["accredited"], f["registered"]):
        add("accredited_within_registered", None, "Accredited or registered voters not read.")
    else:
        add("accredited_within_registered", f["accredited"] <= f["registered"],
            f"{f['accredited']} accredited; {f['registered']} registered.")
    if None not in (f["ballots_issued"], f["unused"], f["spoiled"], f["votes_cast"]):
        used = f["votes_cast"] + f["unused"] + f["spoiled"]
        add("ballots_reconcile", used == f["ballots_issued"],
            f"{f['votes_cast']} used + {f['unused']} unused + {f['spoiled']} spoiled = {used}; issued {f['ballots_issued']}.")
    mismatched = [p for p in PARTIES if votes[p] is not None and sheet["votes_in_words"].get(p) is not None
                  and votes[p] != sheet["votes_in_words"][p]]
    add("figures_match_words", not mismatched,
        "Figures and words agree." if not mismatched else "Figures and words differ for " + ", ".join(mismatched) + ".")
    big = [k for k in ("registered", "accredited", "votes_cast") if (f[k] or 0) > MAX_PLAUSIBLE_VOTERS]
    add("plausible_size", not big, "Sizes plausible." if not big else
        f"{', '.join(big)} above {MAX_PLAUSIBLE_VOTERS}, more than any polling unit holds: likely a misread digit.")
    if expected_code:
        add("code_matches_submission", sheet["polling_unit_code"] in (None, expected_code),
            f"Sheet reads {sheet['polling_unit_code'] or 'no code'}; submitted for {expected_code}.")
    add("polling_unit_exists", bool(known_unit),
        f"{known_unit['name']}, {known_unit['ward']}, {known_unit['lga']}" if known_unit else
        "The polling-unit code is not in INEC's list.")
    if sheet.get("signed") is False:
        add("signed", False, "No presiding officer's signature or stamp visible.")
    return out


def status_for(checks: list[dict], legibility: Optional[str]) -> str:
    """"provisional" when every check that could be made passed and the sheet was readable; otherwise "needs_review".
    Only a person marks a sheet "verified" or "rejected"."""
    failed = [c for c in checks if c["ok"] is False]
    unknown = [c for c in checks if c["ok"] is None and c["rule"] in ("party_votes_sum_to_valid",
                                                                       "votes_cast_within_accredited")]
    return "provisional" if not failed and not unknown and legibility != "poor" else "needs_review"


def apply_corrections(sheet: dict, corrections: dict) -> dict:
    """A reviewer's corrections: figures and votes by name, e.g. {"figures": {"valid": 412}, "votes": {"APC": 210}}."""
    out = json.loads(json.dumps(sheet))
    for k, v in (corrections.get("figures") or {}).items():
        if k in FIGURES:
            out["figures"][k] = _int(v)
    for k, v in (corrections.get("votes") or {}).items():
        if str(k).upper() in PARTIES:
            out["votes"][str(k).upper()] = _int(v)
            out["votes_in_words"][str(k).upper()] = _int(v)   # the reviewer read both
    if corrections.get("polling_unit_code"):
        out["polling_unit_code"] = normalise_code(corrections["polling_unit_code"])
    return out
