"""
Polling units: INEC's delimitation of Nigeria (state, LGA, ward, polling unit), served one level at a time.

Codes follow INEC: state 2 digits, LGA 2, ward (registration area) 2, unit 3, written SS/LL/WW/UUU. A state may be
given by code ("24") or name ("Lagos"); LGAs and wards by code. Answers are cached per instance for an hour: the
delimitation changes only when INEC revises it.
"""
from __future__ import annotations

import re
import time
from typing import Optional

from fastapi import HTTPException

from src import hosted_market as hm

_TTL = 3600
_cache: dict[tuple, tuple[float, object]] = {}
_CODE = re.compile(r"^\d{1,2}/\d{1,2}/\d{1,3}/\d{1,3}$")


def _rpc(fn: str, args: dict, key: tuple):
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < _TTL:
        return hit[1]
    r = hm._rpc_sync(fn, args)
    if r.status_code != 200:
        if "ward_or_query_required" in r.text:
            raise HTTPException(400, "Give a ward (with its state and LGA) or a search term.")
        raise HTTPException(503, "Polling-unit data is unavailable.")
    data = r.json()
    _cache[key] = (time.monotonic(), data)
    return data


def _two(code: Optional[str], what: str) -> Optional[str]:
    if code is None or code == "":
        return None
    if not code.isdigit() or len(code) > 2:
        raise HTTPException(400, f"{what} must be a numeric code, such as 01.")
    return f"{int(code):02d}"


def state_code(state: Optional[str]) -> Optional[str]:
    """A state code from a code or a name ("Lagos", "FCT", "Federal Capital Territory")."""
    if not state:
        return None
    s = state.strip()
    if s.isdigit():
        return _two(s, "state")
    wanted = s.upper().replace("STATE", "").strip()
    wanted = "FEDERAL CAPITAL TERRITORY" if wanted in ("FCT", "ABUJA") else wanted
    for row in areas():
        if row["name"].upper() == wanted:
            return row["code"]
    raise HTTPException(404, f"No state named {state}.")


def areas(state: Optional[str] = None, lga: Optional[str] = None) -> list[dict]:
    if lga and not state:
        raise HTTPException(400, "Give the state with the LGA.")
    st = state_code(state) if state else None
    lg = _two(lga, "lga")
    return _rpc("polling_unit_areas", {"p_state": st, "p_lga": lg}, ("areas", st, lg))


def units(state: Optional[str] = None, lga: Optional[str] = None, ward: Optional[str] = None, q: str = "",
          limit: int = 100, offset: int = 0) -> dict:
    st = state_code(state) if state else None
    lg, wd = _two(lga, "lga"), _two(ward, "ward")
    if wd and not (st and lg):
        raise HTTPException(400, "Give the state and LGA with the ward.")
    if not wd and len(q.strip()) < 3:
        raise HTTPException(400, "Give a ward (with its state and LGA) or a search term of at least 3 letters.")
    args = {"p_state": st, "p_lga": lg, "p_ward": wd, "p_q": q.strip() or None, "p_limit": limit, "p_offset": offset}
    return _rpc("polling_unit_list", args, ("units", st, lg, wd, q.strip().lower(), limit, offset))


def unit(code: str) -> dict:
    code = code.strip().replace("-", "/")
    if not _CODE.match(code):
        raise HTTPException(400, "A polling-unit code looks like 24/10/05/012 (state/LGA/ward/unit).")
    s, l, w, u = code.split("/")
    code = f"{int(s):02d}/{int(l):02d}/{int(w):02d}/{int(u):03d}"
    row = _rpc("polling_unit_get", {"p_code": code}, ("unit", code))
    if not row:
        raise HTTPException(404, f"No polling unit {code}.")
    return row
