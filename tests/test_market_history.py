import pytest
from fastapi.testclient import TestClient

import api.index as api
from src import hosted_market as hm

KEY = "di_live_" + "ab" * 24
OK = {"ok": True, "plan": "pro", "limit": 3000, "used": 4, "remaining": 2996,
      "resets_at": "2026-12-01T00:00:00", "key_id": "k1"}


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code, self._payload, self.text = status_code, payload, str(payload)

    def json(self):
        return self._payload


STORED = {
    "prices": [
        {"date": "2026-10-13", "close": 1500.0, "source": "daily close archive"},
        {"date": "2026-11-23", "close": 1323.0, "chg_1d": 0.0, "volume": 250440, "value_traded": 3.3e8,
         "mcap": 2.2e13, "source": "NGX official list"},
        {"date": "2026-11-24", "close": 1380.0, "chg_1d": 0.0431, "volume": 649663, "value_traded": 7.7e8,
         "mcap": 2.3e13, "source": "NGX official list"},
        {"date": "2026-11-25", "close": 1400.0, "source": "NGX official list"},
    ],
    "fx": {"2026-11-23": 1367.6, "2026-11-24": 1380.0},
}


@pytest.fixture
def store(monkeypatch):
    state = {"calls": [], "reply": FakeResponse(200, STORED)}
    hm._history_cache.clear()

    def fake_rpc_sync(fn, args, timeout=30):
        state["calls"].append((fn, args))
        return state["reply"]

    async def fake_rpc(client, fn, args):            # API key metering
        return FakeResponse(200, OK)
    monkeypatch.setattr(hm, "_rpc_sync", fake_rpc_sync)
    monkeypatch.setattr(hm, "_rpc", fake_rpc)
    monkeypatch.setattr(hm, "_configured", lambda: True)
    monkeypatch.setattr(hm, "_market_snapshot", lambda: {})
    return state


def test_daily_closes_in_local_currency_and_dollars(store):
    r = TestClient(api.app).get("/v1/markets/history?exchange=NGX&symbol=dangcem",
                                headers={"Authorization": f"Bearer {KEY}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert store["calls"] == [("market_history", {"p_exchange": "ngx", "p_symbol": "dangcem", "p_currency": "NGN",
                                                   "p_since": None})]
    assert (body["exchange"], body["symbol"], body["currency"], body["days"]) == ("ngx", "DANGCEM", "NGN", 4)
    assert [p["date"] for p in body["prices"]] == ["2026-10-13", "2026-11-23", "2026-11-24", "2026-11-25"]
    usd = {p["date"]: p["close_usd"] for p in body["prices"]}
    assert usd["2026-10-13"] is None                          # before rates were kept: no invented dollar figure
    assert usd["2026-11-23"] == round(1323.0 / 1367.6, 6)     # that day's own rate
    assert usd["2026-11-25"] == round(1400.0 / 1380.0, 6)     # no rate stored yet that day: the latest earlier one
    assert body["change"] == round(1400.0 / 1500.0 - 1, 6)
    assert body["change_usd"] == round((1400.0 / 1380.0) / (1323.0 / 1367.6) - 1, 6)   # from the first dollar close


def test_period_filters_and_validation(store):
    client = TestClient(api.app)
    h = {"Authorization": f"Bearer {KEY}"}
    r = client.get("/v1/markets/history?exchange=ngx&symbol=DANGCEM&since=2026-11-23&until=2026-11-24", headers=h)
    # The database applies `since`; `until` is applied here.
    assert r.status_code == 200 and r.json()["to"] == "2026-11-24"
    assert store["calls"][-1][1]["p_since"] == "2026-11-23"
    assert client.get("/v1/markets/history?exchange=ngx&symbol=DANGCEM&since=2026-11-25&until=2026-11-01",
                      headers=h).status_code == 422
    assert client.get("/v1/markets/history?exchange=lse&symbol=VOD", headers=h).status_code == 404
    assert client.get("/v1/markets/history?exchange=ngx&symbol=DANGCEM&since=24-11-2026", headers=h).status_code == 422
    bad = client.get("/v1/markets/history?exchange=ngx&symbol=DANG;DROP", headers=h)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_request"


def test_symbols_with_spaces_and_slashes_are_accepted(store):
    r = TestClient(api.app).get("/v1/markets/history?exchange=use&symbol=AIRTEL%20UGANDA",
                                headers={"Authorization": f"Bearer {KEY}"})
    assert r.status_code == 200 and store["calls"][-1][1]["p_symbol"] == "AIRTEL UGANDA"


def test_unknown_listing_and_missing_function(store):
    client = TestClient(api.app)
    h = {"Authorization": f"Bearer {KEY}"}
    store["reply"] = FakeResponse(200, {"prices": [], "fx": {}})
    r = client.get("/v1/markets/history?exchange=ngx&symbol=NOPE", headers=h)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    hm._history_cache.clear()
    store["reply"] = FakeResponse(404, {"message": "function not found"})
    assert client.get("/v1/markets/history?exchange=ngx&symbol=DANGCEM", headers=h).status_code == 503


def test_needs_a_key_and_counts_as_markets(store):
    from src.public_api import scope_of
    assert TestClient(api.app).get("/v1/markets/history?exchange=ngx&symbol=DANGCEM").status_code == 401
    assert scope_of("/v1/markets/history") == "markets"
