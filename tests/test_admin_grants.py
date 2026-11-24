"""The owner's per-account grants: limits over the plan, an end date, and clearing them."""
import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient


def _client(monkeypatch, ok=True, text=""):
    import api.index as api
    import src.hosted_market as hm
    monkeypatch.setattr(hm, "ADMIN_KEY", "owner-key")
    monkeypatch.setattr(hm, "_configured", lambda: True)
    calls = []

    async def rpc(_client, fn, args):
        calls.append((fn, args))
        return MagicMock(is_success=ok, status_code=200 if ok else 400, text=text, json=lambda: [])

    monkeypatch.setattr(hm, "_rpc", rpc)
    return TestClient(api.app), calls


def _post(client, path, key="owner-key", **body):
    return client.post(path, content=json.dumps({"key": key, **body}))


def test_grant_sets_only_the_limits_given_with_an_end_date(monkeypatch):
    from src import plans
    plans._cache["someone"] = (0.0, {"plan": "free"})
    client, calls = _client(monkeypatch)
    r = _post(client, "/api/admin/grants/set", email="Ada@Acme.com", expires_at="2026-12-31", note="pilot",
              grant={"monthly_requests": "20000", "ai_monthly": 300, "alerts_max": "", "exports": True})
    assert r.status_code == 200
    fn, args = calls[-1]
    assert fn == "admin_set_grant" and args["p_email"] == "ada@acme.com"
    assert args["p_grant"] == {"monthly_requests": 20000, "ai_monthly": 300, "exports": True}
    assert args["p_expires_at"] == "2026-12-31T00:00:00Z" and args["p_note"] == "pilot" and args["p_clear"] is False
    assert plans._cache == {}                       # applies on the next request


def test_grant_refuses_bad_numbers_dates_and_empty_grants(monkeypatch):
    client, calls = _client(monkeypatch)
    assert _post(client, "/api/admin/grants/set", email="ada@acme.com", grant={"max_keys": 500}).status_code == 422
    assert _post(client, "/api/admin/grants/set", email="ada@acme.com", grant={"ai_monthly": -5}).status_code == 422
    assert _post(client, "/api/admin/grants/set", email="ada@acme.com", grant={"ai_monthly": True}).status_code == 422
    assert _post(client, "/api/admin/grants/set", email="ada@acme.com", grant={"ai_monthly": 5}, expires_at="31/12").status_code == 422
    assert _post(client, "/api/admin/grants/set", email="ada@acme.com", grant={}).status_code == 422
    assert _post(client, "/api/admin/grants/set", key="nope", email="ada@acme.com", grant={"ai_monthly": 5}).status_code == 401
    assert calls == []


def test_clearing_a_grant_and_unknown_accounts(monkeypatch):
    client, calls = _client(monkeypatch)
    r = _post(client, "/api/admin/grants/set", email="ada@acme.com", clear=True)
    assert r.status_code == 200 and calls[-1][1]["p_clear"] is True and calls[-1][1]["p_grant"] == {}
    client, _ = _client(monkeypatch, ok=False, text="unknown_account")
    assert _post(client, "/api/admin/grants/set", email="ghost@acme.com", grant={"ai_monthly": 5}).status_code == 404


def test_grant_list_says_when_the_migration_has_not_run(monkeypatch):
    client, _ = _client(monkeypatch, ok=False, text="Could not find the function public.admin_grants")
    r = _post(client, "/api/admin/grants")
    assert r.status_code == 503 and "migration" in r.json()["detail"]


def test_a_granted_election_alert_allowance_replaces_the_plans(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from src import election_alerts
    with pytest.raises(HTTPException) as e:
        election_alerts.create("u1", "x", None, None, plan="free", email=True)
    assert e.value.status_code == 403                # free plan: no election alerts
    seen = {}

    def rpc(fn, args):
        seen.update(args)
        return MagicMock(status_code=200, json=lambda: {"id": "a1"}, text="")
    monkeypatch.setattr(election_alerts.hm, "_rpc_sync", rpc)
    election_alerts.create("u1", "x", None, None, plan="free", email=True, granted=3)
    assert seen["p_max"] == 3
