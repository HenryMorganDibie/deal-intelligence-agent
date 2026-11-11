import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

import api.index as api
from src import billing
from src import hosted_market as hm
from src.request_identity import CLIENT_HEADER

KEY = "sk_test_" + "x" * 40
USER = "11111111-2222-3333-4444-555555555555"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload, self.status_code, self.text = payload, status_code, json.dumps(payload)

    def json(self):
        return self._payload


@pytest.fixture
def env(monkeypatch):
    """Fake database and Paystack, recording every call."""
    state = {"rpc": [], "paystack": [], "account": {"user_id": USER, "email": "a@example.com", "plan": "free",
                                                     "subscription_code": None, "status": None},
             "plan_code": None, "applied": set()}
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", KEY)
    monkeypatch.setenv("DEAL_INTEL_WEB_SECRET", "web-secret")
    monkeypatch.setattr(hm, "_configured", lambda: True)

    async def fake_rpc(client, fn, args):
        state["rpc"].append((fn, args))
        if fn == "billing_account":
            return FakeResponse(state["account"])
        if fn == "billing_price":
            if args.get("p_currency") == "USD" and not state.get("usd"):
                return FakeResponse({"message": "currency_unavailable"}, 400)
            return FakeResponse({"plan": args["p_plan"], "label": "Pro", "interval": args["p_interval"],
                                 "currency": args.get("p_currency"), "amount_minor": 750000 if args.get("p_currency") != "USD" else 700,
                                 "plan_code": state["plan_code"]})
        if fn == "billing_save_plan_code":
            state["plan_code"] = args["p_code"]
            return FakeResponse(None)
        if fn == "billing_plan_for_code":
            return FakeResponse({"plan": "pro", "interval": "monthly", "currency": "NGN"} if args["p_code"] == "PLN_pro" else None)
        if fn == "billing_apply":
            fresh = args["p_event_key"] not in state["applied"]
            state["applied"].add(args["p_event_key"])
            return FakeResponse({"applied": fresh, "plan": args["p_plan"] if args["p_status"] != "cancelled" else "free"})
        raise AssertionError(fn)

    async def fake_paystack(client, method, path, body=None):
        state["paystack"].append((method, path, body))
        if path == "/plan":
            return {"plan_code": "PLN_pro"}
        if path == "/transaction/initialize":
            return {"authorization_url": "https://checkout.paystack.com/abc", "reference": "ref1"}
        if path.endswith("/manage/link"):
            return {"link": "https://paystack.com/manage/xyz"}
        raise AssertionError(path)

    monkeypatch.setattr(hm, "_rpc", fake_rpc)
    monkeypatch.setattr(billing, "_paystack", fake_paystack)
    return state


def web():
    return {CLIENT_HEADER: "web-secret"}


def sign(body: bytes) -> str:
    return hmac.new(KEY.encode(), body, hashlib.sha512).hexdigest()


def test_checkout_creates_the_paystack_plan_once_and_returns_the_link(env):
    client = TestClient(api.app)
    r = client.post("/api/billing/checkout", json={"user_id": USER, "plan": "pro", "interval": "monthly"}, headers=web())
    assert r.status_code == 200 and r.json()["authorization_url"].startswith("https://checkout.paystack.com/")
    init = next(b for m, p, b in env["paystack"] if p == "/transaction/initialize")
    assert init["plan"] == "PLN_pro" and init["currency"] == "NGN" and init["metadata"]["user_id"] == USER
    client.post("/api/billing/checkout", json={"user_id": USER, "plan": "pro", "interval": "monthly"}, headers=web())
    assert sum(1 for _, p, _ in env["paystack"] if p == "/plan") == 1          # the plan code is reused


def test_checkout_is_for_the_web_app_only_and_refuses_a_second_subscription(env):
    client = TestClient(api.app)
    assert client.post("/api/billing/checkout", json={"user_id": USER, "plan": "pro"}).status_code == 403
    env["account"].update(subscription_code="SUB_1", status="active")
    assert client.post("/api/billing/checkout", json={"user_id": USER, "plan": "team"}, headers=web()).status_code == 409


def test_institutional_is_not_self_serve(env):
    r = TestClient(api.app).post("/api/billing/checkout", json={"user_id": USER, "plan": "institutional"}, headers=web())
    assert r.status_code == 422


def test_webhook_rejects_an_unsigned_or_forged_event(env):
    body = json.dumps({"event": "charge.success", "data": {}}).encode()
    client = TestClient(api.app)
    assert client.post("/api/billing/paystack", content=body).status_code == 401
    assert client.post("/api/billing/paystack", content=body, headers={"x-paystack-signature": "0" * 128}).status_code == 401
    assert not any(fn == "billing_apply" for fn, _ in env["rpc"])


def _send(payload):
    body = json.dumps(payload).encode()
    return TestClient(api.app).post("/api/billing/paystack", content=body, headers={"x-paystack-signature": sign(body)})


def test_a_payment_grants_the_plan_once(env):
    event = {"event": "charge.success", "data": {"id": 99, "reference": "ref1", "paid_at": "2026-11-11T10:00:00Z",
                                                  "metadata": {"user_id": USER, "plan": "pro", "interval": "monthly"},
                                                  "customer": {"email": "a@example.com", "customer_code": "CUS_1"}}}
    assert _send(event).status_code == 200 and _send(event).status_code == 200
    applies = [a for fn, a in env["rpc"] if fn == "billing_apply"]
    assert applies[0]["p_status"] == "active" and applies[0]["p_plan"] == "pro" and applies[0]["p_user"] == USER
    assert len(env["applied"]) == 1                                             # the redelivery used the same key


def test_a_renewal_without_metadata_is_matched_by_plan_code_and_email(env):
    _send({"event": "charge.success", "data": {"id": 100, "paid_at": "2026-12-11T10:00:00Z", "plan": {"plan_code": "PLN_pro"},
                                               "customer": {"email": "a@example.com"}}})
    apply = next(a for fn, a in env["rpc"] if fn == "billing_apply")
    assert apply["p_plan"] == "pro" and apply["p_interval"] == "monthly"
    lookup = next(a for fn, a in env["rpc"] if fn == "billing_account")
    assert lookup == {"p_email": "a@example.com"}


def test_cancellation_and_failure_statuses(env):
    env["account"].update(plan="pro", subscription_code="SUB_1", status="active")
    for event, status in (("subscription.not_renew", "non_renewing"), ("invoice.payment_failed", "attention"),
                          ("subscription.disable", "cancelled")):
        _send({"event": event, "data": {"subscription_code": "SUB_1", "plan": {"plan_code": "PLN_pro"},
                                        "customer": {"email": "a@example.com"}, "updatedAt": event}})
    statuses = [a["p_status"] for fn, a in env["rpc"] if fn == "billing_apply"]
    assert statuses == ["non_renewing", "attention", "cancelled"]


def test_an_old_subscription_ending_does_not_downgrade_a_newer_one(env):
    env["account"].update(plan="team", subscription_code="SUB_NEW", status="active")
    _send({"event": "subscription.disable", "data": {"subscription_code": "SUB_OLD", "plan": {"plan_code": "PLN_pro"},
                                                     "customer": {"email": "a@example.com"}}})
    assert not any(fn == "billing_apply" for fn, _ in env["rpc"])


def test_one_off_payments_and_unknown_events_change_nothing(env):
    _send({"event": "charge.success", "data": {"id": 5, "customer": {"email": "a@example.com"}}})
    _send({"event": "transfer.success", "data": {"id": 6}})
    assert not any(fn == "billing_apply" for fn, _ in env["rpc"])


def test_manage_returns_paystacks_link(env):
    env["account"].update(subscription_code="SUB_1", status="active")
    r = TestClient(api.app).post("/api/billing/manage", json={"user_id": USER}, headers=web())
    assert r.json() == {"link": "https://paystack.com/manage/xyz"}


def test_signature_check():
    assert billing.valid_signature(b"x", hmac.new(b"k", b"x", hashlib.sha512).hexdigest(), key="k")
    assert not billing.valid_signature(b"x", "bad", key="k") and not billing.valid_signature(b"x", None, key="k")
    assert not billing.valid_signature(b"x", "anything", key="")


def test_dollars_only_when_the_account_accepts_them(env):
    client = TestClient(api.app)
    r = client.post("/api/billing/checkout", json={"user_id": USER, "plan": "pro", "currency": "USD"}, headers=web())
    assert r.status_code == 409 and "currency" in r.json()["detail"]
    env["usd"] = True
    r = client.post("/api/billing/checkout", json={"user_id": USER, "plan": "pro", "currency": "USD"}, headers=web())
    assert r.status_code == 200
    plan = next(b for m, p, b in env["paystack"] if p == "/plan")
    init = next(b for m, p, b in env["paystack"] if p == "/transaction/initialize")
    assert plan["currency"] == "USD" and plan["amount"] == 700 and init["currency"] == "USD"
