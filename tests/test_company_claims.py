"""The owner's review endpoints for company-submitted facts."""
import json
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient


def _client(monkeypatch, rpc_reply):
    import api.index as api
    import src.hosted_market as hm
    monkeypatch.setattr(hm, "ADMIN_KEY", "owner-key")
    monkeypatch.setattr(hm, "_configured", lambda: True)
    rpc = AsyncMock(return_value=rpc_reply)
    monkeypatch.setattr(hm, "_rpc", rpc)
    return TestClient(api.app), rpc


def test_review_list_needs_the_owner_key_and_is_never_cached(monkeypatch):
    claims = [{"id": "c1", "company": "Acme", "email": "ada@acme.com", "status": "pending", "facts": {"employees": "11-50"}}]
    client, rpc = _client(monkeypatch, MagicMock(is_success=True, json=lambda: claims))
    assert client.post("/api/admin/claims", content=json.dumps({"key": "wrong"})).status_code == 401
    r = client.post("/api/admin/claims", content=json.dumps({"key": "owner-key", "status": "pending"}))
    assert r.status_code == 200 and r.json() == claims
    assert r.headers["cache-control"] == "no-store, private"
    assert rpc.call_args.args[1:] == ("admin_company_claims", {"p_status": "pending"})


def test_status_change_is_validated(monkeypatch):
    client, rpc = _client(monkeypatch, MagicMock(is_success=True))
    claim = "00000000-0000-0000-0000-000000000001"
    bad = client.post("/api/admin/claims/status", content=json.dumps({"key": "owner-key", "id": claim, "status": "deleted"}))
    assert bad.status_code == 422
    assert client.post("/api/admin/claims/status",
                       content=json.dumps({"key": "owner-key", "id": "x; drop", "status": "removed"})).status_code == 422
    ok = client.post("/api/admin/claims/status", content=json.dumps({"key": "owner-key", "id": claim, "status": "removed"}))
    assert ok.json() == {"id": claim, "status": "removed"}
    assert rpc.call_args.args[1:] == ("admin_set_company_claim", {"p_id": claim, "p_status": "removed"})
