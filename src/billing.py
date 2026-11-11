"""
Paid plans through Paystack, in naira.

  POST /api/billing/checkout  (web app only)  start a Paystack checkout for a signed-in account's chosen plan
  POST /api/billing/manage    (web app only)  a Paystack link where the account cancels or changes its card
  POST /api/billing/paystack  (Paystack)      webhook: payment and subscription events, verified by signature

Each self-serve plan and interval is a Paystack plan, created here the first time it is sold at its current price
(prices live in the api_plans table). A checkout is a Paystack transaction on that plan, so a successful payment
also starts the subscription and Paystack charges each renewal itself. Webhook events move the account's plan:
a payment or a new subscription grants it, a failed renewal keeps it while Paystack retries, a cancellation keeps it
to the end of the paid period, and a disabled subscription returns the account to Free. The database applies each
event once, so a redelivered event changes nothing.

The secret key (PAYSTACK_SECRET_KEY) lives in the API's environment only and signs nothing the browser sees.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src import hosted_market as hm

log = logging.getLogger("deal_intel.billing")
router = APIRouter()

PAYSTACK = "https://api.paystack.co"
APP_URL = (os.environ.get("DEAL_INTEL_APP_URL") or "https://deal-intelligence.app").rstrip("/")


def secret_key() -> str:
    return os.environ.get("PAYSTACK_SECRET_KEY", "").strip()


def _paystack_headers() -> dict:
    return {"Authorization": f"Bearer {secret_key()}", "Content-Type": "application/json"}


def valid_signature(body: bytes, signature: Optional[str], key: Optional[str] = None) -> bool:
    """Paystack signs each webhook body with HMAC-SHA512 of the secret key (x-paystack-signature)."""
    key = key if key is not None else secret_key()
    if not key or not signature:
        return False
    expected = hmac.new(key.encode(), body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


async def _db(client: httpx.AsyncClient, fn: str, args: dict) -> object:
    r = await hm._rpc(client, fn, args)
    if r.status_code != 200:
        log.error("billing rpc %s failed: %s %s", fn, r.status_code, r.text[:300])
        raise HTTPException(502, "Billing is temporarily unavailable.")
    return r.json()


async def _paystack(client: httpx.AsyncClient, method: str, path: str, body: Optional[dict] = None) -> dict:
    r = await client.request(method, f"{PAYSTACK}{path}", headers=_paystack_headers(), json=body, timeout=20)
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code >= 300 or not data.get("status"):
        log.error("paystack %s %s failed: %s %s", method, path, r.status_code, str(data)[:300])
        raise HTTPException(502, "The payment provider could not be reached. Try again shortly.")
    return data.get("data") or {}


async def plan_code(client: httpx.AsyncClient, plan: str, interval: str) -> tuple[str, int, str]:
    """(Paystack plan code, amount in kobo, label) for a plan and interval at today's price, creating the Paystack
    plan the first time that price is sold."""
    price = await _db(client, "billing_price", {"p_plan": plan, "p_interval": interval})
    if price.get("plan_code"):
        return price["plan_code"], price["amount_kobo"], price["label"]
    created = await _paystack(client, "POST", "/plan", {
        "name": f"Deal Intelligence {price['label']} ({interval})", "interval": interval,
        "amount": price["amount_kobo"], "currency": "NGN",
        "description": f"{price['label']} plan, billed {interval}.", "send_invoices": True, "send_sms": False})
    await _db(client, "billing_save_plan_code", {"p_plan": plan, "p_interval": interval,
                                                 "p_amount_kobo": price["amount_kobo"], "p_code": created["plan_code"]})
    return created["plan_code"], price["amount_kobo"], price["label"]


class CheckoutBody(BaseModel):
    user_id: str = Field(..., min_length=36, max_length=36)
    plan: Literal["pro", "team"]
    interval: Literal["monthly", "annually"] = "monthly"


@router.post("/api/billing/checkout")
async def checkout(body: CheckoutBody) -> dict:
    """A Paystack checkout link for the signed-in account (the web app passes the account from its verified
    session). An account already paying for a plan manages it instead of buying a second subscription."""
    if not secret_key() or not hm._configured():
        raise HTTPException(503, "Payments are not configured yet.")
    async with httpx.AsyncClient(timeout=20) as client:
        account = await _db(client, "billing_account", {"p_user": body.user_id})
        if not account:
            raise HTTPException(404, "Account not found.")
        if account.get("status") in ("active", "attention") and account.get("subscription_code"):
            raise HTTPException(409, "You already have a subscription. Manage it from your account to change plans.")
        code, amount, label = await plan_code(client, body.plan, body.interval)
        tx = await _paystack(client, "POST", "/transaction/initialize", {
            "email": account["email"], "amount": amount, "currency": "NGN", "plan": code,
            "callback_url": f"{APP_URL}/account/billing?checkout=done",
            "metadata": {"user_id": body.user_id, "plan": body.plan, "interval": body.interval,
                         "custom_fields": [{"display_name": "Plan", "variable_name": "plan",
                                            "value": f"{label} ({body.interval})"}]},
        })
    return {"authorization_url": tx.get("authorization_url"), "reference": tx.get("reference")}


class ManageBody(BaseModel):
    user_id: str = Field(..., min_length=36, max_length=36)


@router.post("/api/billing/manage")
async def manage(body: ManageBody) -> dict:
    """Paystack's own page for the account's subscription: cancel it or change the card."""
    if not secret_key() or not hm._configured():
        raise HTTPException(503, "Payments are not configured yet.")
    async with httpx.AsyncClient(timeout=20) as client:
        account = await _db(client, "billing_account", {"p_user": body.user_id})
        if not account or not account.get("subscription_code"):
            raise HTTPException(404, "There is no subscription to manage.")
        link = await _paystack(client, "GET", f"/subscription/{account['subscription_code']}/manage/link")
    return {"link": link.get("link")}


# ── Webhook ───────────────────────────────────────────────────────────────────

_STATUS = {"charge.success": "active", "subscription.create": "active", "subscription.enable": "active",
           "invoice.update": None, "invoice.payment_failed": "attention", "subscription.not_renew": "non_renewing",
           "subscription.disable": "cancelled", "subscription.expiring_cards": None}


def event_key(event: str, data: dict) -> str:
    """One key per real-world event, so Paystack's retries of the same delivery are applied once."""
    ident = data.get("id") or data.get("reference") or data.get("subscription_code") or data.get("invoice_code") or ""
    stamp = data.get("paid_at") or data.get("updatedAt") or data.get("createdAt") or data.get("next_payment_date") or ""
    return f"{event}:{ident}:{stamp}"


async def apply_event(payload: dict, client: httpx.AsyncClient) -> dict:
    event, data = payload.get("event") or "", payload.get("data") or {}
    status = _STATUS.get(event)
    if status is None:
        return {"ignored": event or "unknown"}
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    customer = data.get("customer") or {}
    plan_obj = data.get("plan") if isinstance(data.get("plan"), dict) else {}
    subscription = data.get("subscription") if isinstance(data.get("subscription"), dict) else {}
    code = plan_obj.get("plan_code") or (subscription.get("plan") or {}).get("plan_code")

    plan, interval = meta.get("plan"), meta.get("interval")
    if code and not plan:
        found = await _db(client, "billing_plan_for_code", {"p_code": code}) or {}
        plan, interval = found.get("plan"), found.get("interval")
    if event == "charge.success" and not plan:
        return {"ignored": "a payment that is not for a plan"}        # a one-off charge, not a subscription
    account = await _db(client, "billing_account", {"p_user": meta.get("user_id")} if meta.get("user_id")
                        else {"p_email": customer.get("email")})
    if not account:
        log.warning("paystack %s for an unknown account", event)
        return {"ignored": "unknown account"}
    sub_code = data.get("subscription_code") or subscription.get("subscription_code")
    if status in ("non_renewing", "cancelled") and account.get("subscription_code") and sub_code \
            and sub_code != account["subscription_code"]:
        return {"ignored": "an earlier subscription"}                  # the account has moved to a newer one
    if not plan:
        plan = account.get("plan") if account.get("plan") != "free" else None
    if not plan:
        return {"ignored": "no plan"}
    result = await _db(client, "billing_apply", {
        "p_event_key": event_key(event, data), "p_user": account["user_id"], "p_plan": plan, "p_status": status,
        "p_interval": interval, "p_customer": customer.get("customer_code"),
        "p_subscription": sub_code,
        "p_email_token": data.get("email_token") or subscription.get("email_token"),
        "p_next": data.get("next_payment_date") or subscription.get("next_payment_date")})
    return {"event": event, **(result or {})}


@router.post("/api/billing/paystack")
async def paystack_webhook(request: Request) -> JSONResponse:
    body = await request.body()
    if not valid_signature(body, request.headers.get("x-paystack-signature")):
        return JSONResponse({"detail": "Invalid signature."}, status_code=401)
    try:
        payload = json.loads(body)
    except ValueError:
        return JSONResponse({"detail": "Invalid body."}, status_code=400)
    async with httpx.AsyncClient(timeout=15) as client:
        outcome = await apply_event(payload, client)
    log.info("paystack webhook: %s", outcome)
    return JSONResponse({"received": True})


def install(app: FastAPI) -> None:
    app.include_router(router)
