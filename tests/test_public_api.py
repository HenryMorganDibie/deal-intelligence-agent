import hashlib

import httpx
import pytest
from fastapi import HTTPException
from fastapi.params import Query as QueryParam
from fastapi.testclient import TestClient

import api.index as api
from src import hosted_market as hm
from src import public_api

KEY = "di_live_" + "ab" * 24
OK = {"ok": True, "plan": "free", "limit": 30, "used": 4, "remaining": 26,
      "resets_at": "2026-12-01T00:00:00", "key_id": "k1"}


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code, self._payload, self.text = status_code, payload, str(payload)

    def json(self):
        return self._payload


@pytest.fixture
def metering(monkeypatch):
    """Records each metering call and answers with whatever the test puts in state['reply']."""
    state = {"calls": [], "reply": FakeResponse(200, OK)}

    async def fake_rpc(client, fn, args):
        state["calls"].append((fn, args))
        reply = state["reply"]
        if isinstance(reply, Exception):
            raise reply
        return reply
    monkeypatch.setattr(hm, "_rpc", fake_rpc)
    monkeypatch.setattr(hm, "_configured", lambda: True)
    return state


def auth(key=KEY):
    return {"Authorization": f"Bearer {key}"}


def test_index_needs_no_key():
    r = TestClient(api.app).get("/v1")
    assert r.status_code == 200 and "GET /v1/deals" in r.json()["endpoints"]


def test_missing_and_malformed_keys_are_rejected_without_a_database_call(metering):
    client = TestClient(api.app)
    r = client.get("/v1/deals")
    assert r.status_code == 401 and r.json()["error"]["code"] == "missing_key"
    assert r.headers["www-authenticate"] == "Bearer" and r.headers["cache-control"] == "no-store"
    assert client.get("/v1/deals", headers=auth("not-a-key")).json()["error"]["code"] == "invalid_key"
    assert metering["calls"] == []


def test_a_valid_key_is_counted_and_gets_quota_headers(metering, monkeypatch):
    seen = {}

    async def fake_search(**kwargs):
        seen.update(kwargs)
        return {"deals": [{"id": "d1"}], "count": 1}
    monkeypatch.setattr(hm, "deal_search", fake_search)
    r = TestClient(api.app).get("/v1/deals?country=NG&limit=5", headers={"X-API-Key": KEY})
    assert r.status_code == 200 and r.json()["deals"] == [{"id": "d1"}]
    assert r.headers["x-ratelimit-limit"] == "30" and r.headers["x-ratelimit-remaining"] == "26"
    assert r.headers["x-ratelimit-reset"] == "1796083200" and r.headers["cache-control"] == "no-store"
    fn, args = metering["calls"][0]
    assert fn == "api_key_consume" and args == {"p_hash": hashlib.sha256(KEY.encode()).hexdigest(), "p_count": True}
    # Every argument reaches the handler as a value, never as a FastAPI Query default object.
    assert seen["country"] == "NG" and seen["limit"] == 5
    assert not any(isinstance(v, QueryParam) for v in seen.values())


def test_an_exhausted_allowance_returns_429_with_retry_after(metering):
    metering["reply"] = FakeResponse(200, {"ok": False, "reason": "quota_exceeded", "plan": "free", "limit": 30,
                                           "used": 30, "remaining": 0, "resets_at": "2099-01-01T00:00:00"})
    r = TestClient(api.app).get("/v1/events", headers=auth())
    assert r.status_code == 429 and r.json()["error"]["code"] == "quota_exceeded"
    assert "30 requests this month" in r.json()["error"]["message"]
    assert int(r.headers["retry-after"]) > 60 and r.headers["x-ratelimit-remaining"] == "0"


def test_revoked_or_unknown_keys_get_401(metering):
    metering["reply"] = FakeResponse(200, {"ok": False, "reason": "invalid_key"})
    r = TestClient(api.app).get("/v1/countries", headers=auth())
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_key"


@pytest.mark.parametrize("reply", [FakeResponse(500, {}), httpx.ConnectError("down")])
def test_requests_are_refused_not_served_free_when_metering_fails(metering, reply, monkeypatch):
    called = []

    async def fake_overview():
        called.append(1)
        return {}
    monkeypatch.setattr(hm, "markets_overview", fake_overview)
    metering["reply"] = reply
    r = TestClient(api.app).get("/v1/markets/overview", headers=auth())
    assert r.status_code == 503 and r.headers["retry-after"] == "30" and called == []


def test_usage_is_not_counted(metering):
    r = TestClient(api.app).get("/v1/usage", headers=auth())
    assert r.status_code == 200 and r.json() == {"plan": "free", "limit": 30, "used": 4, "remaining": 26,
                                                 "resets_at": "2026-12-01T00:00:00"}
    assert metering["calls"][0][1]["p_count"] is False


def test_handler_errors_use_the_public_error_shape(metering, monkeypatch):
    async def missing(deal_id):
        raise HTTPException(404, "Deal not found.")
    monkeypatch.setattr(hm, "deal", missing)
    r = TestClient(api.app).get("/v1/deals/nope", headers=auth())
    assert r.status_code == 404
    assert r.json()["error"] == {"code": "not_found", "message": "Deal not found.", "docs": public_api.DOCS_URL}


def test_investor_registry_is_left_out(metering, monkeypatch):
    async def board(**kwargs):
        return {"investors": [], "registry": [{"name": "x"}] * 500}
    monkeypatch.setattr(hm, "investor_board", board)
    assert "registry" not in TestClient(api.app).get("/v1/investors", headers=auth()).json()


def test_v1_is_never_edge_cached():
    assert not api._is_public_cacheable_get("/v1/deals")
    assert api._public_market_cache_ttl("/v1/markets/overview") is None


def test_country_names_are_accepted(metering, monkeypatch):
    seen = {}

    async def fake_feed(**kwargs):
        seen.update(kwargs)
        return {"events": []}
    monkeypatch.setattr(hm, "event_feed", fake_feed)
    TestClient(api.app).get("/v1/events?country=Ivory%20Coast", headers=auth())
    assert seen["country"] == "CI"
