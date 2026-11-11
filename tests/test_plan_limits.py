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


def test_public_deal_pages_read_one_deal_not_the_whole_store(env, monkeypatch):
    calls = []
    rows = {"old": {"id": "old", "merged_into": "new"},
            "new": {"id": "new", "target": "Shelter Afrique Development Bank", "deal_type": "debt_financing",
                    "sources": [{"url": "https://a"}], "headline": "x"}}

    class R:
        status_code = 200

        def __init__(self, payload):
            self._p = payload

        def json(self):
            return self._p

    def fake_sync(fn, args, timeout=30):
        calls.append(fn)
        return R(rows.get(args.get("p_id")))
    monkeypatch.setattr(hm, "_rpc_sync", fake_sync)
    monkeypatch.setattr(hm, "_load", lambda kind: (_ for _ in ()).throw(AssertionError("full store loaded")))
    hm._cache.pop("deals", None)
    client = TestClient(api.app)
    r = client.get("/api/deals/old?comparables=false", headers=app_headers(user=None) | {CLIENT_HEADER: "api-secret"})
    assert r.status_code == 200 and r.json()["deal"]["id"] == "new" and r.json()["comparables"] == []
    assert calls == ["get_deal_row", "get_deal_row"]
    assert client.get("/api/deals/missing?comparables=false", headers={CLIENT_HEADER: "api-secret"}).status_code == 404


def test_serving_instances_download_visible_rows_only_and_drop_rows_that_become_hidden(env, monkeypatch):
    calls = []
    store = {"changed": "2026-11-11T10:00:00Z", "count": 3}

    class R:
        status_code = 200

        def __init__(self, payload):
            self._p = payload

        def json(self):
            return self._p

        def raise_for_status(self):
            return None

    def fake_sync(fn, args, timeout=30):
        calls.append((fn, args.get("p_kind")))
        if fn == "store_version":
            return R({"deals": dict(store)})
        if fn == "list_visible_page":
            return R({"max_id": "b", "rows": [{"id": "a", "announced": "2026-11-10"}, {"id": "b", "announced": "2026-11-09"}]})
        if fn == "list_changed_rows":
            return R({"rows": [{"id": "b", "merged_into": "a"}], "limit": 2000})
        return R(None)
    monkeypatch.setattr(hm, "_rpc_sync", fake_sync)
    for k in ("deals", "deals:visible"):
        hm._cache.pop(k, None)
    rows = hm._load_visible("deals")
    assert [r["id"] for r in rows] == ["a", "b"]
    assert ("list_visible_page", "deals") in calls and not any(fn == "list_deals_page" for fn, _ in calls)
    # Later, "b" is merged into "a": the next refresh downloads only the change and drops it.
    store.update({"changed": "2026-11-11T11:00:00Z"})
    ts, cached = hm._cache["deals:visible"]
    hm._cache["deals:visible"] = (ts - hm._TTL - 1, cached)
    assert [r["id"] for r in hm._load_visible("deals")] == ["a"]
    assert calls[-1][0] == "list_changed_rows"
