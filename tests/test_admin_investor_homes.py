"""The owner's review list for investor home countries."""
import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient


def _client(monkeypatch, homes=()):
    import api.index as api
    import src.hosted_market as hm
    from src.engines import investor_origin
    from datetime import date
    monkeypatch.setattr(hm, "ADMIN_KEY", "owner-key")
    monkeypatch.setattr(hm, "_configured", lambda: True)
    today = date.today().isoformat()
    monkeypatch.setattr(hm, "deals", lambda: [
        {"deal_type": "equity_funding", "investors": ["Madica"], "target": "Acme", "headline": "Acme raises $2m", "announced": today},
        {"deal_type": "equity_funding", "investors": ["Madica"], "target": "Beta", "headline": "Beta raises $1m", "announced": today},
        {"deal_type": "debt_financing", "buyer": "British International Investment", "target": "C", "headline": "BII lends", "announced": today},
    ])
    calls = []

    async def rpc(_client, fn, args):
        calls.append((fn, args))
        if fn == "investor_homes_all":
            return MagicMock(status_code=200, is_success=True, json=lambda: list(homes))
        return MagicMock(status_code=200, is_success=True, json=lambda: {})
    monkeypatch.setattr(hm, "_rpc", rpc)
    hm._homes_cache.update(at=0.0, rows=[])
    investor_origin.use_homes([])
    return TestClient(api.app), calls


def _post(client, path, **body):
    return client.post(path, content=json.dumps({"key": "owner-key", **body}))


def test_review_list_shows_unplaced_investors_most_frequent_first(monkeypatch):
    client, _ = _client(monkeypatch)
    assert client.post("/api/admin/investor-homes", content=json.dumps({"key": "x"})).status_code == 401
    r = _post(client, "/api/admin/investor-homes")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store, private"
    unplaced = r.json()["unplaced"]
    assert [(u["name"], u["deals"]) for u in unplaced] == [("Madica", 2)]           # BII is placed by the registry
    assert r.json()["countries"]["US"] == "United States"


def test_setting_a_country_validates_and_saves(monkeypatch):
    client, calls = _client(monkeypatch)
    assert _post(client, "/api/admin/investor-homes/set", name="Madica", country="Atlantis").status_code == 422
    r = _post(client, "/api/admin/investor-homes/set", name="Madica", country="Kenya")
    assert r.json()["country"] == "KE"
    fn, args = next(c for c in calls if c[0] == "admin_set_investor_home")
    assert args["p_country"] == "KE" and args["p_clear"] is False and args["p_name_key"]
    r = _post(client, "/api/admin/investor-homes/set", name="EDFI", country="none")
    assert r.json()["country"] is None
    r = _post(client, "/api/admin/investor-homes/set", name="Madica", clear=True)
    assert r.json()["cleared"] is True
