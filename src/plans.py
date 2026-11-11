"""
What a signed-in account's plan allows, checked on the server for every limited feature.

  AI runs   briefs, research and market briefs together, counted per month (Free 30, Pro 100, Team 500)
  Alerts    watchlists the account has (Pro and above)
  Exports   bulk CSV export of the screener (paid plans)

Limits live in the api_plans table. The account comes from the web app's proxy (request_identity.account). A
request made with the API's own secret (scheduled jobs, scripts) is never limited. A request from the web app with
no signed-in account is refused for limited features. With the app lock off (tests, local runs) and no account,
nothing is limited.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx
from fastapi import HTTPException, Request

from src import hosted_market as hm
from src import request_identity as rid

log = logging.getLogger("deal_intel.plans")

_cache: dict[str, tuple[float, dict]] = {}
_TTL = 30.0


def _upgrade(message: str) -> HTTPException:
    # 402 tells the app to offer an upgrade rather than show an error.
    return HTTPException(402, message)


PLAN_EVENTS = {"limit_ai_month", "limit_ai_day", "limit_alert", "limit_export", "see_plans", "checkout_started", "paid"}


async def record(user: Optional[str], event: str, detail: Optional[str] = None) -> None:
    """Note a step in the free-to-paid funnel for the owner's admin page. Never fails the request it belongs to."""
    if not user or event not in PLAN_EVENTS or not hm._configured():
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await hm._rpc(client, "record_plan_event", {"p_user": user, "p_event": event,
                                                         "p_detail": (detail or "")[:60] or None})
    except Exception as e:                      # analytics must never break the product
        log.warning("plan event %s not recorded: %s", event, e)


def _who(request: Request) -> Optional[str]:
    """The account to limit, None when the caller is not limited; raises 401 for an app request without one."""
    if rid.internal(request):
        return None
    user = rid.account(request)
    if user:
        return user
    if rid.enforced():
        raise HTTPException(401, "Sign in to use this feature.")
    return None


async def limits(user: str, fresh: bool = False) -> dict:
    hit = _cache.get(user)
    if hit and not fresh and time.monotonic() - hit[0] < _TTL:
        return hit[1]
    async with httpx.AsyncClient(timeout=10) as client:
        r = await hm._rpc(client, "plan_limits", {"p_user": user})
    if r.status_code != 200:
        log.error("plan_limits failed: %s %s", r.status_code, r.text[:200])
        raise HTTPException(503, "Your plan could not be checked. Try again shortly.")
    data = r.json() or {}
    _cache[user] = (time.monotonic(), data)
    return data


async def use_ai(request: Request) -> None:
    """Count one AI run for the account, or refuse with an upgrade message when this month's are used."""
    user = _who(request)
    if not user or not hm._configured():
        return
    async with httpx.AsyncClient(timeout=10) as client:
        r = await hm._rpc(client, "consume_feature", {"p_user": user, "p_feature": "ai"})
    if r.status_code != 200:
        log.error("consume_feature failed: %s %s", r.status_code, r.text[:200])
        raise HTTPException(503, "Your plan could not be checked. Try again shortly.")
    out = r.json() or {}
    _cache.pop(user, None)
    if not out.get("ok"):
        await record(user, "limit_ai_month", str(out.get("limit", 0)))
        if not out.get("limit"):
            raise _upgrade("Briefs and research runs are part of Pro. Browsing deals, companies, markets and "
                           "countries stays free.")
        raise _upgrade(f"You have used this month's {out.get('limit', 0)} briefs and research runs on your plan. "
                       "Upgrade to Pro for 100 a month with no daily limit, or wait until the 1st.")


async def check_alert_slot(request: Request) -> Optional[str]:
    """The account creating an alert (to record as its owner), after checking it has a slot left."""
    user = _who(request)
    if not user or not hm._configured():
        return user
    lim = await limits(user, fresh=True)
    if lim.get("alerts_used", 0) >= lim.get("alerts_max", 0):
        await record(user, "limit_alert", lim.get("plan"))
    if not lim.get("alerts_max"):
        raise _upgrade("Alerts are part of Pro: email, Slack or Teams when a deal or event matches. Browsing stays free.")
    if lim.get("alerts_used", 0) >= lim.get("alerts_max", 0):
        raise _upgrade(f"Your plan includes {lim.get('alerts_max', 0)} alerts and you have used them all. "
                       "Upgrade for more, or delete one you no longer need.")
    return user


async def check_export(request: Request) -> None:
    user = _who(request)
    if not user or not hm._configured():
        return
    if not (await limits(user)).get("exports"):
        await record(user, "limit_export")
        raise _upgrade("CSV export is included in Pro and Team. Upgrade to download the full list.")
