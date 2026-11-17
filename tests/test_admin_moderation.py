"""The owner's suspend, reinstate and delete endpoints."""
import json
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException
from fastapi.testclient import TestClient

ACCOUNT = {"user_id": "u1", "email": "ada@acme.com", "suspended": False,
           "subscription_code": "SUB_1", "email_token": "tok", "subscription_status": "active"}


def _client(monkeypatch, account=ACCOUNT, fail=()):
    import api.index as api
    import src.billing as billing
    import src.hosted_market as hm
    monkeypatch.setattr(hm, "ADMIN_KEY", "owner-key")
    monkeypatch.setattr(hm, "_configured", lambda: True)
    monkeypatch.setattr(billing, "secret_key", lambda: "sk_test")
    calls = []

    async def rpc(_client, fn, args):
        calls.append((fn, args))
        if fn in fail:
            return MagicMock(is_success=False, status_code=500, text="boom")
        if fn == "admin_account_lookup":
            return MagicMock(is_success=account is not None, status_code=200 if account else 400,
                             text="" if account else "unknown_account", json=lambda: account)
        if fn == "admin_delete_account":
            return MagicMock(is_success=True, json=lambda: {"email": "ada@acme.com", "result": "deleted"})
        return MagicMock(is_success=True, json=lambda: {})

    monkeypatch.setattr(hm, "_rpc", rpc)
    stop = AsyncMock()
    monkeypatch.setattr(billing, "stop_renewal", stop)
    return TestClient(api.app), calls, stop


def _post(client, path, **body):
    return client.post(path, content=json.dumps({"key": "owner-key", **body}))


def test_suspend_needs_the_owner_key(monkeypatch):
    client, calls, _ = _client(monkeypatch)
    r = client.post("/api/admin/accounts/suspend", content=json.dumps({"key": "nope", "email": "ada@acme.com", "suspend": True}))
    assert r.status_code == 401 and calls == []


def test_suspend_bans_and_stops_the_paid_renewal(monkeypatch):
    client, calls, stop = _client(monkeypatch)
    r = _post(client, "/api/admin/accounts/suspend", email="ada@acme.com", suspend=True, reason="scraping")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store, private"
    assert r.json() == {"email": "ada@acme.com", "suspended": True, "renewal": "cancelled", "warning": None}
    assert ("admin_set_account_suspended", {"p_email": "ada@acme.com", "p_suspend": True, "p_reason": "scraping"}) in calls
    stop.assert_awaited_once()
    assert stop.await_args.args[1:] == ("SUB_1", "tok")


def test_suspension_stands_when_paystack_fails_and_says_so(monkeypatch):
    client, _, stop = _client(monkeypatch)
    stop.side_effect = HTTPException(502, "provider down")
    r = _post(client, "/api/admin/accounts/suspend", email="ada@acme.com", suspend=True)
    assert r.status_code == 200 and r.json()["suspended"] is True
    assert "Cancel it in Paystack" in r.json()["warning"]


def test_reinstating_never_touches_billing(monkeypatch):
    client, _, stop = _client(monkeypatch)
    r = _post(client, "/api/admin/accounts/suspend", email="ada@acme.com", suspend=False)
    assert r.json()["suspended"] is False and r.json()["renewal"] is None
    stop.assert_not_awaited()


def test_free_account_has_no_renewal_to_cancel(monkeypatch):
    client, _, stop = _client(monkeypatch, account={**ACCOUNT, "subscription_status": None, "subscription_code": None})
    assert _post(client, "/api/admin/accounts/suspend", email="ada@acme.com", suspend=True).json()["renewal"] is None
    stop.assert_not_awaited()


def test_unknown_account_and_bad_input(monkeypatch):
    client, _, _ = _client(monkeypatch, account=None)
    assert _post(client, "/api/admin/accounts/suspend", email="who@x.com", suspend=True).status_code == 404
    assert _post(client, "/api/admin/accounts/suspend", email="not an email", suspend=True).status_code == 422
    assert _post(client, "/api/admin/accounts/suspend", email="ada@acme.com", suspend="yes").status_code == 422


def test_delete_requires_the_email_typed_again(monkeypatch):
    client, calls, _ = _client(monkeypatch)
    r = _post(client, "/api/admin/accounts/delete", email="ada@acme.com", confirm="ada@acme.co")
    assert r.status_code == 422 and calls == []


def test_delete_cancels_renewal_first_then_deletes(monkeypatch):
    client, calls, stop = _client(monkeypatch)
    r = _post(client, "/api/admin/accounts/delete", email="ada@acme.com", confirm="ADA@acme.com", reason="asked")
    assert r.status_code == 200 and r.json() == {"email": "ada@acme.com", "result": "deleted", "renewal": "cancelled"}
    stop.assert_awaited_once()
    assert calls[-1] == ("admin_delete_account", {"p_email": "ada@acme.com", "p_confirm": "ADA@acme.com", "p_reason": "asked"})


def test_nothing_is_deleted_when_the_renewal_cannot_be_cancelled(monkeypatch):
    client, calls, stop = _client(monkeypatch)
    stop.side_effect = HTTPException(502, "provider down")
    r = _post(client, "/api/admin/accounts/delete", email="ada@acme.com", confirm="ada@acme.com")
    assert r.status_code == 502 and "Nothing was deleted" in r.json()["detail"]
    assert all(fn != "admin_delete_account" for fn, _ in calls)
