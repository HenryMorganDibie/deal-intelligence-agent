import json

import pytest
from fastapi.testclient import TestClient

import api.index as api
from src import hosted_market as hm
from src import plans
from src.request_identity import ACCOUNT_HEADER, CLIENT_HEADER

USER = "11111111-2222-3333-4444-555555555555"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload, self.status_code, self.text = payload, status_code, json.dumps(payload)

    def json(self):
        return self._payload

    @property
    def is_success(self):
        return self.status_code < 400


@pytest.fixture
def env(monkeypatch):
    state = {"limits": {"plan": "free", "exports": False, "ai_monthly": 3, "ai_used": 0, "alerts_max": 3, "alerts_used": 0},
             "calls": []}
    monkeypatch.setenv("DEAL_INTEL_WEB_SECRET", "web-secret")
    monkeypatch.setenv("DEAL_INTEL_API_SECRET", "api-secret")
    monkeypatch.setattr(hm, "_configured", lambda: True)
    plans._cache.clear()

    async def fake_rpc(client, fn, args):
        state["calls"].append((fn, args))
        lim = state["limits"]
        if fn == "plan_limits":
            return FakeResponse(dict(lim))
        if fn == "consume_feature":
            if lim["ai_used"] >= lim["ai_monthly"]:
                return FakeResponse({"ok": False, "limit": lim["ai_monthly"]})
            lim["ai_used"] += 1
            return FakeResponse({"ok": True, "limit": lim["ai_monthly"], "used": lim["ai_used"]})
        if fn == "create_watchlist":
            return FakeResponse("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        if fn == "set_watchlist_owner":
            return FakeResponse(None)
        return FakeResponse(None, 500)
    monkeypatch.setattr(hm, "_rpc", fake_rpc)
    return state


def app_headers(user=USER):
    h = {CLIENT_HEADER: "web-secret"}
    if user:
        h[ACCOUNT_HEADER] = user
    return h


def test_free_accounts_get_three_ai_runs_a_month(env, monkeypatch):
    monkeypatch.setattr(hm.research_mod, "research", lambda *a, **k: {"answer": "ok"})
    monkeypatch.setattr(hm, "deals", lambda: [])
    monkeypatch.setattr(hm, "events", lambda: [])

    async def no_reserve(request, label):
        return None

    async def no_finish(run_id):
        return None
    monkeypatch.setattr(hm, "_reserve", no_reserve)
    monkeypatch.setattr(hm, "_finish", no_finish)
    client = TestClient(api.app)
    codes = [client.post("/api/research", json={"question": "Nigerian fintech rounds this year"}, headers=app_headers()).status_code
             for _ in range(4)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 402


def test_app_requests_without_a_signed_in_account_are_refused_and_internal_jobs_are_not_limited(env):
    assert TestClient(api.app).post("/api/research", json={"question": "Kenya banks"},
                                    headers=app_headers(user=None)).status_code == 401
    # The API's own secret (scheduled jobs) is never counted against a plan.
    import asyncio
    from starlette.requests import Request
    req = Request({"type": "http", "headers": [(CLIENT_HEADER.encode(), b"api-secret")]})
    asyncio.run(plans.use_ai(req))
    assert not any(fn == "consume_feature" for fn, _ in env["calls"])


def test_a_forged_account_header_without_the_app_secret_is_ignored(env):
    from starlette.requests import Request
    from src import request_identity as rid
    req = Request({"type": "http", "headers": [(ACCOUNT_HEADER.encode(), USER.encode())]})
    assert rid.account(req) is None
    req = Request({"type": "http", "headers": [(ACCOUNT_HEADER.encode(), USER.encode()), (CLIENT_HEADER.encode(), b"web-secret")]})
    assert rid.account(req) == USER


def test_alert_allowance_and_owner(env):
    client = TestClient(api.app)
    body = {"name": "Kenya banks", "countries": ["KE"]}
    r = client.post("/api/watchlists", json=body, headers=app_headers())
    assert r.status_code == 200
    assert ("set_watchlist_owner", {"p_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "p_user": USER}) in env["calls"]
    env["limits"]["alerts_used"] = 3
    r = client.post("/api/watchlists", json=body, headers=app_headers())
    assert r.status_code == 402 and "3 alerts" in r.json()["detail"]


def test_csv_export_is_for_paid_plans_and_never_cached(env, monkeypatch):
    monkeypatch.setattr(hm, "_market_snapshot", lambda: {"quotes": {}, "fx": {}})
    client = TestClient(api.app)
    assert client.get("/api/markets/screener?limit=50", headers=app_headers()).status_code == 200
    assert client.get("/api/markets/screener?limit=500", headers=app_headers()).status_code == 402
    env["limits"]["exports"] = True
    plans._cache.clear()
    r = client.get("/api/markets/screener?limit=500", headers=app_headers())
    assert r.status_code == 200 and "no-store" in r.headers["cache-control"]


def test_free_accounts_browse_but_briefs_and_alerts_are_pro(env, monkeypatch):
    env["limits"].update({"ai_monthly": 0, "alerts_max": 0})
    monkeypatch.setattr(hm.research_mod, "research", lambda *a, **k: {"answer": "ok"})
    monkeypatch.setattr(hm, "deals", lambda: [])
    monkeypatch.setattr(hm, "events", lambda: [])
    client = TestClient(api.app)
    r = client.post("/api/research", json={"question": "Nigerian fintech rounds"}, headers=app_headers())
    assert r.status_code == 402 and "part of Pro" in r.json()["detail"] and "stays free" in r.json()["detail"]
    r = client.post("/api/watchlists", json={"name": "Kenya banks", "countries": ["KE"]}, headers=app_headers())
    assert r.status_code == 402 and "Alerts are part of Pro" in r.json()["detail"]


def test_paid_accounts_have_no_daily_cap_and_free_accounts_keep_it(env):
    import asyncio
    from starlette.requests import Request
    def req(headers):
        return Request({"type": "http", "headers": headers})
    account = [(ACCOUNT_HEADER.encode(), USER.encode()), (CLIENT_HEADER.encode(), b"web-secret")]
    env["limits"]["plan"] = "free"
    plans._cache.clear()
    assert asyncio.run(hm.per_client_daily(req(account))) == hm.PER_VISITOR_DAILY
    env["limits"]["plan"] = "pro"
    plans._cache.clear()
    assert asyncio.run(hm.per_client_daily(req(account))) >= 1_000_000
    assert asyncio.run(hm.per_client_daily(req([]))) == hm.PER_VISITOR_DAILY


def test_limits_and_plan_views_are_recorded_for_the_funnel(env, monkeypatch):
    recorded = []

    async def fake_rpc(client, fn, args):
        if fn == "record_plan_event":
            recorded.append((args["p_event"], args.get("p_detail")))
            from tests.test_plan_limits import FakeResponse as R
            return R(None)
        if fn == "plan_limits":
            return FakeResponse({"plan": "free", "exports": False, "ai_monthly": 30, "ai_used": 30,
                                 "alerts_max": 0, "alerts_used": 0})
        if fn == "consume_feature":
            return FakeResponse({"ok": False, "limit": 30})
        return FakeResponse(None, 500)
    monkeypatch.setattr(hm, "_rpc", fake_rpc)
    monkeypatch.setattr(hm, "_market_snapshot", lambda: {"quotes": {}, "fx": {}})
    client = TestClient(api.app)
    assert client.post("/api/research", json={"question": "Kenya banks"}, headers=app_headers()).status_code == 402
    assert client.post("/api/watchlists", json={"name": "K", "countries": ["KE"]}, headers=app_headers()).status_code == 402
    assert client.get("/api/markets/screener?limit=500", headers=app_headers()).status_code == 402
    assert client.post("/api/plan-event", json={"event": "see_plans", "source": "screener"}, headers=app_headers()).json() == {"ok": True}
    assert client.post("/api/plan-event", json={"event": "paid"}, headers=app_headers()).status_code == 422
    assert [e for e, _ in recorded] == ["limit_ai_month", "limit_alert", "limit_export", "see_plans"]
