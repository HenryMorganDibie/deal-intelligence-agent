"""The owner's sign-in trouble list and the help actions (reset link, confirmation email)."""
import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient


def _client(monkeypatch, rpc_result=None, rpc_ok=True, auth_status=200):
    import api.index as api
    import src.hosted_market as hm
    monkeypatch.setattr(hm, "ADMIN_KEY", "owner-key")
    monkeypatch.setattr(hm, "_configured", lambda: True)
    monkeypatch.setattr(hm, "SUPABASE_URL", "https://db.example")
    monkeypatch.setattr(hm, "SITE_URL", "https://site.example")
    calls, posts = [], []

    async def rpc(_client, fn, args):
        calls.append((fn, args))
        return MagicMock(is_success=rpc_ok, status_code=200 if rpc_ok else 404,
                         text="" if rpc_ok else "Could not find the function public.admin_auth_trouble",
                         json=lambda: rpc_result or [])

    async def post(self, url, **kw):
        posts.append((url, kw))
        return MagicMock(status_code=auth_status, is_success=200 <= auth_status < 300, text="")

    monkeypatch.setattr(hm, "_rpc", rpc)
    monkeypatch.setattr(hm.httpx.AsyncClient, "post", post)
    return TestClient(api.app), calls, posts


def _post(client, path, key="owner-key", **body):
    return client.post(path, content=json.dumps({"key": key, **body}))


def test_trouble_list_needs_the_owner_key_and_is_never_cached(monkeypatch):
    rows = [{"email": "sultan@example.com", "attempts": 3, "last_reason": "Form not complete", "has_account": False}]
    client, calls, _ = _client(monkeypatch, rpc_result=rows)
    assert _post(client, "/api/admin/auth-trouble", key="nope").status_code == 401 and calls == []
    r = _post(client, "/api/admin/auth-trouble", days=99)
    assert r.status_code == 200 and r.json() == rows and r.headers["cache-control"] == "no-store, private"
    assert calls == [("admin_auth_trouble", {"p_days": 30})]


def test_trouble_list_says_when_the_migration_has_not_run(monkeypatch):
    client, _, _ = _client(monkeypatch, rpc_ok=False)
    r = _post(client, "/api/admin/auth-trouble")
    assert r.status_code == 503 and "migration" in r.json()["detail"]


def test_reset_link_and_confirmation_go_through_supabase_auth(monkeypatch):
    client, _, posts = _client(monkeypatch)
    r = _post(client, "/api/admin/accounts/help", email="Ada@Acme.com", action="reset")
    assert r.status_code == 200 and r.json() == {"email": "ada@acme.com", "sent": "password-reset link"}
    url, kw = posts[-1]
    assert url == "https://db.example/auth/v1/recover" and kw["json"] == {"email": "ada@acme.com"}
    assert kw["params"]["redirect_to"] == "https://site.example/auth/callback?next=password-reset"
    r = _post(client, "/api/admin/accounts/help", email="ada@acme.com", action="confirm")
    assert r.json()["sent"] == "confirmation email"
    url, kw = posts[-1]
    assert url == "https://db.example/auth/v1/resend" and kw["json"]["type"] == "signup"


def test_help_refuses_bad_input_and_reports_rate_limits(monkeypatch):
    client, _, posts = _client(monkeypatch)
    assert _post(client, "/api/admin/accounts/help", email="ada@acme.com", action="delete").status_code == 422
    assert _post(client, "/api/admin/accounts/help", email="not-an-email", action="reset").status_code == 422
    assert _post(client, "/api/admin/accounts/help", key="nope", email="ada@acme.com", action="reset").status_code == 401
    assert posts == []
    client, _, _ = _client(monkeypatch, auth_status=429)
    assert _post(client, "/api/admin/accounts/help", email="ada@acme.com", action="reset").status_code == 429
