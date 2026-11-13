"""
Polling-unit results: result sheets read by a vision model on Groq, checked, reviewed by a person, and added up.

A sheet comes in as an image (uploaded, or a public https link that Groq fetches itself, so this server never
fetches arbitrary addresses). The model's reading is checked (src/engines/result_sheets.py) against arithmetic,
the words written beside the figures and INEC's polling-unit list; a sheet that passes counts as provisional, one
that does not waits for review. Images are not stored: only their SHA-256, so the same sheet sent twice is read once.

Sheets belong to the account that submitted them: a client's sheets, reviews and totals are visible only to that
account and never count in another's.

Groq's vision models change; the first that accepts an image is used, from GROQ_VISION_MODELS if set, else
Groq's own model list.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import time
from typing import Optional

import httpx
from fastapi import HTTPException

from src import hosted_market as hm
from src.engines import result_sheets as rs

log = logging.getLogger("deal_intel.election_results")
GROQ = "https://api.groq.com/openai/v1"
# Groq's vision line-up changes often (Llama 4 Scout and Maverick were retired by November 2026).
_PREFERRED = ("qwen/qwen3.8-27b", "qwen/qwen3.6-27b", "meta-llama/llama-4-maverick-17b-128e-instruct",
              "meta-llama/llama-4-scout-17b-16e-instruct")
_VISION_HINTS = ("llama-4", "vision", "-vl", "scout", "maverick", "gemma-3", "gemma3", "gemma-4", "gemma4",
                 "qwen3.8-27b", "qwen3.6-27b")
_working_model: Optional[str] = None
MAX_IMAGE_BYTES = 3 * 1024 * 1024        # base64 in a JSON body must stay under Vercel's 4.5 MB request limit
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _groq_key() -> str:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "Sheet reading is not configured.")
    return key


def _candidate_models(client: httpx.Client) -> list[str]:
    configured = [m.strip() for m in os.environ.get("GROQ_VISION_MODELS", "").split(",") if m.strip()]
    if configured:
        return configured
    try:
        r = client.get(f"{GROQ}/models", headers={"Authorization": f"Bearer {_groq_key()}"}, timeout=15)
        listed = [m["id"] for m in (r.json().get("data") or []) if m.get("active", True)] if r.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        listed = []
    seen = [m for m in _PREFERRED if not listed or m in listed]
    seen += [m for m in listed if m not in seen and any(h in m.lower() for h in _VISION_HINTS)]
    return seen or list(_PREFERRED)


def read_sheet(image: dict) -> tuple[dict, str]:
    """(parsed reading, model) for {"data_url": ...} or {"url": ...}."""
    global _working_model
    content = [{"type": "text", "text": rs.PROMPT},
               {"type": "image_url", "image_url": {"url": image.get("data_url") or image["url"]}}]
    errors = []
    with httpx.Client(timeout=90) as client:
        models = ([_working_model] if _working_model else []) + [m for m in _candidate_models(client) if m != _working_model]
        for model in models:
            body = {"model": model, "temperature": 0, "max_completion_tokens": 4000,
                    "messages": [{"role": "user", "content": content}], "response_format": {"type": "json_object"}}
            for attempt in range(2):
                r = client.post(f"{GROQ}/chat/completions", json=body,
                                headers={"Authorization": f"Bearer {_groq_key()}", "Content-Type": "application/json"})
                if r.status_code == 400 and "response_format" in r.text and "response_format" in body:
                    body.pop("response_format")          # a model without JSON mode: ask plainly
                    continue
                break
            if r.status_code == 200:
                try:
                    text = r.json()["choices"][0]["message"]["content"]
                    parsed = rs.parse_model_output(text)
                except (KeyError, IndexError, ValueError) as e:
                    errors.append(f"{model}: unreadable answer ({e})")
                    continue
                _working_model = model
                return parsed, model
            if r.status_code == 429:
                raise HTTPException(503, "Sheet reading is busy; try again in a minute.")
            errors.append(f"{model}: {r.status_code} {r.text[:160]}")
            if _working_model == model:
                _working_model = None
    log.error("no vision model read the sheet: %s", errors)
    raise HTTPException(503, "No vision model could read the sheet.")


def _image(upload: Optional[bytes], content_type: Optional[str], url: Optional[str]) -> tuple[dict, str]:
    if upload:
        if len(upload) > MAX_IMAGE_BYTES:
            raise HTTPException(400, "Images must be 3 MB or smaller.")
        kind = (content_type or "").split(";")[0].strip().lower()
        if kind not in IMAGE_TYPES:
            raise HTTPException(400, "Send a JPEG, PNG or WebP image.")
        return ({"data_url": f"data:{kind};base64,{base64.b64encode(upload).decode()}"},
                hashlib.sha256(upload).hexdigest())
    if url:
        if not url.startswith("https://") or len(url) > 1000:
            raise HTTPException(400, "image_url must be an https link.")
        return {"url": url}, hashlib.sha256(url.encode()).hexdigest()
    raise HTTPException(400, "Send an image file or an image_url.")


def _owner(owner: Optional[str]) -> str:
    """Every sheet belongs to the account that submitted it; nothing is read or written without one."""
    if not owner:
        raise HTTPException(503, "The account behind this key could not be identified.")
    return owner


def submit(owner: str, election: str, pu_code: str, upload: Optional[bytes] = None, content_type: Optional[str] = None,
           url: Optional[str] = None) -> dict:
    owner = _owner(owner)
    if election not in rs.ELECTIONS:
        raise HTTPException(400, "election must be one of " + ", ".join(rs.ELECTIONS) + ".")
    code = rs.normalise_code(pu_code)
    if not code:
        raise HTTPException(400, "pu_code must be a polling-unit code, such as 24/11/01/001.")
    image, digest = _image(upload, content_type, url)
    digest = hashlib.sha256(f"{owner}:{digest}".encode()).hexdigest()   # duplicates are per account
    known = _known_unit(code)
    if not known:
        raise HTTPException(404, f"{code} is not in INEC's polling-unit list.")
    started = time.monotonic()
    reading, model = read_sheet(image)
    checks = rs.check(reading, code, known)
    status = rs.status_for(checks, reading.get("legibility"))
    data = {**reading, "election": election, "pu_code": code, "expected_form": rs.ELECTIONS[election],
            "unit": {k: known[k] for k in ("name", "ward", "lga", "state")}, "checks": checks,
            "model": model, "read_seconds": round(time.monotonic() - started, 1),
            "source": {"sha256": digest, "url": url} if url else {"sha256": digest}}
    r = hm._rpc_sync("result_sheet_insert", {"p_owner": owner, "p_row": {"election": election, "pu_code": code,
                                                                          "status": status, "data": data,
                                                                          "image_sha256": digest}})
    if r.status_code != 200:
        raise HTTPException(503, "The reading could not be stored.")
    return _public(r.json())


def _known_unit(code: str) -> Optional[dict]:
    r = hm._rpc_sync("polling_unit_get", {"p_code": code})
    return r.json() if r.status_code == 200 else None


def _public(row: dict) -> dict:
    return {k: row.get(k) for k in ("id", "election", "pu_code", "status", "data", "created_at", "updated_at",
                                     "reviewed_at", "duplicate") if row.get(k) is not None}


def review(owner: str, sheet_id: str, status: str, corrections: Optional[dict]) -> dict:
    owner = _owner(owner)
    if status not in ("verified", "rejected", "needs_review"):
        raise HTTPException(400, "status must be verified, rejected or needs_review.")
    r = hm._rpc_sync("result_sheet_get", {"p_owner": owner, "p_id": sheet_id})
    if r.status_code != 200 or not r.json():
        raise HTTPException(404, "No such sheet.")
    data = r.json()["data"]
    if corrections:
        data = rs.apply_corrections(data, corrections)
        data["pu_code"] = data.get("polling_unit_code") or data["pu_code"]
    if corrections or status == "verified":
        # Checked again whenever it changes or is about to count as verified: a reviewer can correct a misread,
        # but cannot verify figures that do not add up.
        data["checks"] = rs.check(data, data["pu_code"], _known_unit(data["pu_code"]))
        blocking = [c for c in data["checks"] if c["ok"] is False and c["rule"] not in ("signed", "code_matches_submission")]
        if status == "verified" and blocking:
            raise HTTPException(409, "The sheet fails a check, so it cannot be verified: " +
                                "; ".join(c["detail"] for c in blocking) + " Correct it, or reject it.")
    data["review"] = {"status": status, "corrections": corrections or {}}
    r = hm._rpc_sync("result_sheet_review", {"p_owner": owner, "p_id": sheet_id, "p_status": status, "p_data": data})
    if r.status_code != 200:
        raise HTTPException(503, "The review could not be stored.")
    return _public(r.json())


def _scope(state: Optional[str], lga: Optional[str], ward: Optional[str]) -> tuple:
    from src import polling_units as pu
    st = pu.state_code(state) if state else None
    lg = f"{int(lga):02d}" if lga and lga.isdigit() else None
    wd = f"{int(ward):02d}" if ward and ward.isdigit() else None
    if (lga and not lg) or (ward and not wd):
        raise HTTPException(400, "lga and ward are numeric codes, such as 11 and 01.")
    if (lg and not st) or (wd and not lg):
        raise HTTPException(400, "Give the state with the LGA, and the LGA with the ward.")
    return st, lg, wd


def sheets(owner: str, election: str, state: Optional[str] = None, lga: Optional[str] = None,
           ward: Optional[str] = None, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> dict:
    owner = _owner(owner)
    st, lg, wd = _scope(state, lga, ward)
    r = hm._rpc_sync("result_sheet_list", {"p_owner": owner, "p_election": election, "p_state": st, "p_lga": lg, "p_ward": wd,
                                             "p_status": status, "p_limit": limit, "p_offset": offset})
    if r.status_code != 200:
        raise HTTPException(503, "Result sheets are unavailable.")
    out = r.json()
    out["sheets"] = [_public(s) for s in out.get("sheets") or []]
    return out


def totals(owner: str, election: str, state: Optional[str] = None, lga: Optional[str] = None,
           ward: Optional[str] = None, verified_only: bool = False) -> dict:
    """Votes, accreditation and turnout for a scope from this account's sheets, broken down one level below it."""
    owner = _owner(owner)
    if election not in rs.ELECTIONS:
        raise HTTPException(400, "election must be one of " + ", ".join(rs.ELECTIONS) + ".")
    st, lg, wd = _scope(state, lga, ward)
    r = hm._rpc_sync("result_sheet_totals", {"p_owner": owner, "p_election": election, "p_state": st, "p_lga": lg, "p_ward": wd,
                                        "p_verified_only": verified_only})
    if r.status_code != 200:
        raise HTTPException(503, "Result totals are unavailable.")
    t = r.json() or {}

    def turnout(x: dict) -> Optional[float]:
        return round(x["accredited"] / x["registered"], 4) if x.get("registered") and x.get("accredited") is not None else None
    for g in [t, *t.get("groups", [])]:
        g["turnout"] = turnout(g)
        g["coverage"] = round(g["sheets"] / g["polling_units"], 4) if g.get("polling_units") else None
    level = "polling_units" if wd else "wards" if lg else "lgas" if st else "states"
    return {"election": election, "scope": {"state": st, "lga": lg, "ward": wd}, "counted": "verified" if verified_only
            else "verified and provisional", "breakdown": level, **t}



# ── Bulk import: sheets queued for reading ───────────────────────────────────
# Sheet links an account holds (IReV downloads, its own field collection) are queued and read by the scheduled job,
# highest priority first, within a daily budget that keeps the vision model on its free tier. Automated collection
# from IReV itself waits on INEC's permission; INEC publishes no terms or robots rules for it.

DAILY_READS = int(os.environ.get("SHEET_READS_PER_DAY", "400"))
MAX_IMPORT = 2000


def queue(owner: str, election: str, rows: list[dict]) -> dict:
    """Queue sheet links: [{pu_code, image_url, priority?}]. Unknown codes and non-https links are refused up front,
    duplicates skipped."""
    owner = _owner(owner)
    if election not in rs.ELECTIONS:
        raise HTTPException(400, "election must be one of " + ", ".join(rs.ELECTIONS) + ".")
    if not rows or len(rows) > MAX_IMPORT:
        raise HTTPException(400, f"Send between 1 and {MAX_IMPORT} sheets at a time.")
    clean, refused = [], []
    for i, r in enumerate(rows):
        code = rs.normalise_code(str(r.get("pu_code") or ""))
        url = str(r.get("image_url") or "").strip()
        if not code:
            refused.append({"row": i, "reason": "pu_code is not a polling-unit code"})
        elif not url.startswith("https://") or len(url) > 600 or not hm._public_host(url):
            refused.append({"row": i, "reason": "image_url must be an https link on a public host"})
        else:
            prio = r.get("priority", 0)
            clean.append({"election": election, "pu_code": code, "image_url": url,
                          "priority": prio if isinstance(prio, int) and -100 <= prio <= 100 else 0})
    added = 0
    if clean:
        r = hm._rpc_sync("sheet_queue_add", {"p_owner": owner, "p_rows": clean})
        if r.status_code != 200:
            raise HTTPException(503, "The sheets could not be queued.")
        added = int(r.json() or 0)
    return {"queued": added, "duplicates": len(clean) - added, "refused": refused[:50],
            "refused_total": len(refused), "daily_reads": DAILY_READS}


def queue_status(owner: str, election: str) -> dict:
    owner = _owner(owner)
    r = hm._rpc_sync("sheet_queue_status", {"p_owner": owner, "p_election": election})
    if r.status_code != 200:
        raise HTTPException(503, "The queue is unavailable.")
    return {**(r.json() or {}), "daily_reads": DAILY_READS}


def read_queue(limit: int = 20, deadline_seconds: float = 25 * 60) -> dict:
    """Read queued sheets (the scheduled job): each through the same reading and checks as a direct submission."""
    started = time.monotonic()
    r = hm._rpc_sync("sheet_queue_take", {"p_limit": limit, "p_budget": DAILY_READS})
    if r.status_code != 200:
        return {"error": f"queue unavailable: {r.status_code}"}
    taken = r.json() or {}
    done = failed = 0
    for row in taken.get("rows", []):
        if time.monotonic() - started > deadline_seconds:
            break                                       # left as 'reading'; taken again after 30 minutes
        try:
            sheet = submit(str(row["owner"]), row["election"], row["pu_code"], url=row["image_url"])
            hm._rpc_sync("sheet_queue_done", {"p_id": row["id"], "p_status": "read", "p_error": None,
                                              "p_sheet": sheet.get("id")})
            done += 1
        except HTTPException as e:
            hm._rpc_sync("sheet_queue_done", {"p_id": row["id"], "p_status": "failed", "p_error": str(e.detail),
                                              "p_sheet": None})
            failed += 1
    return {"taken": len(taken.get("rows", [])), "read": done, "failed": failed,
            "used_today": taken.get("used_today"), "budget": DAILY_READS}
