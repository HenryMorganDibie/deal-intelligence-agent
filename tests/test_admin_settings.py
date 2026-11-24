"""The owner's Settings: site switches, plans and prices, checkout currencies, deal corrections, the AI pause."""
import asyncio
import json
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

DEAL = {"id": "921cff0a634d633d", "announced": "2026-10-10", "deal_type": "equity_funding", "stage": "completed",
        "target": "Swoop", "amount_usd": 7300000.0, "country": "NG", "countries": ["NG"], "headline": "Swoop raises $7.3M"}


def _client(monkeypatch, ok=True, text="", deal=DEAL):
    import api.index as api
    import src.hosted_market as hm
    monkeypatch.setattr(hm, "ADMIN_KEY", "owner-key")
    monkeypatch.setattr(hm, "_configured", lambda: True)
    monkeypatch.setattr(hm, "_one_deal", lambda deal_id: dict(deal) if deal and deal_id == deal["id"] else None)
    calls = []

    async def rpc(_client, fn, args):
        calls.append((fn, args))
        return MagicMock(is_success=ok, status_code=200 if ok else 400, text=text, json=lambda: {"site": {}, "plans": []})
    monkeypatch.setattr(hm, "_rpc", rpc)
    return TestClient(api.app), calls


def _post(client, path, key="owner-key", **body):
    return client.post(path, content=json.dumps({"key": key, **body}))


def test_switches_are_cleaned_and_need_the_key(monkeypatch):
    client, calls = _client(monkeypatch)
    assert _post(client, "/api/admin/settings/site", key="nope", setting="ai", value={"on": False}).status_code == 401
    r = _post(client, "/api/admin/settings/site", setting="announcement",
              value={"on": True, "text": "  Results  are live ", "link": "/elections", "tone": "loud"})
    assert r.status_code == 200
    assert calls[-1] == ("admin_set_site_setting", {"p_key": "announcement", "p_value":
                         {"on": True, "text": "Results are live", "link": "/elections", "tone": "info"}})
    assert _post(client, "/api/admin/settings/site", setting="announcement", value={"on": True, "text": ""}).status_code == 422
    assert _post(client, "/api/admin/settings/site", setting="announcement",
                 value={"on": True, "text": "x", "link": "javascript:alert(1)"}).status_code == 422
    assert _post(client, "/api/admin/settings/site", setting="theme", value={}).status_code == 422
    _post(client, "/api/admin/settings/site", setting="signups", value={"open": False, "message": "Back Monday"})
    assert calls[-1][1] == {"p_key": "signups", "p_value": {"open": False, "message": "Back Monday"}}


def test_plan_terms_take_whole_numbers_only(monkeypatch):
    client, calls = _client(monkeypatch)
    r = _post(client, "/api/admin/settings/plan", plan="pro", fields={"price_month_ngn": "9000", "ai_monthly": 150, "exports": True})
    assert r.status_code == 200 and calls[-1] == ("admin_update_plan", {"p_plan": "pro", "p_fields":
                                                  {"price_month_ngn": 9000, "ai_monthly": 150, "exports": True}})
    for bad in ({"price_month_ngn": "9,000"}, {"ai_monthly": -1}, {"max_keys": 1000}, {}):
        assert _post(client, "/api/admin/settings/plan", plan="pro", fields=bad).status_code == 422
    client, _ = _client(monkeypatch, ok=False, text="unknown_plan")
    assert _post(client, "/api/admin/settings/plan", plan="gold", fields={"ai_monthly": 1}).status_code == 404


def test_dollar_checkout_switch(monkeypatch):
    client, calls = _client(monkeypatch)
    assert _post(client, "/api/admin/settings/currencies", usd="yes").status_code == 422
    assert _post(client, "/api/admin/settings/currencies", usd=True).status_code == 200
    assert calls[-1] == ("admin_set_currencies", {"p_usd": True})


def test_settings_say_when_the_migration_has_not_run(monkeypatch):
    client, _ = _client(monkeypatch, ok=False, text="Could not find the function public.admin_settings")
    r = _post(client, "/api/admin/settings")
    assert r.status_code == 503 and "migration" in r.json()["detail"]


def test_a_deal_correction_is_saved_as_reviewed(monkeypatch):
    client, calls = _client(monkeypatch)
    r = _post(client, "/api/admin/deals/update", id=DEAL["id"],
              set={"amount_usd": "7500000", "stage": "announced", "country": "ke", "target": " Swoop  Africa "})
    assert r.status_code == 200
    fn, args = calls[-1]
    row = args["p_rows"][0]
    assert fn == "upsert_deals" and row["amount_usd"] == 7500000.0 and row["stage"] == "announced"
    assert row["country"] == "KE" and row["countries"] == ["KE", "NG"] and row["target"] == "Swoop Africa"
    assert row["reviewed_by"] == "owner" and row["reviewed_on"]


def test_hiding_and_showing_a_deal_and_bad_input(monkeypatch):
    client, calls = _client(monkeypatch)
    _post(client, "/api/admin/deals/update", id=DEAL["id"], hide="duplicate of the April report")
    assert calls[-1][1]["p_rows"][0]["excluded"] == "owner: duplicate of the April report"
    client, calls = _client(monkeypatch, deal={**DEAL, "excluded": "owner: x"})
    _post(client, "/api/admin/deals/update", id=DEAL["id"], unhide=True)
    assert "excluded" not in calls[-1][1]["p_rows"][0]
    client, calls = _client(monkeypatch)
    assert _post(client, "/api/admin/deals/update", id=DEAL["id"], set={"deal_type": "loan"}).status_code == 422
    assert _post(client, "/api/admin/deals/update", id=DEAL["id"], set={"amount_usd": "lots"}).status_code == 422
    assert _post(client, "/api/admin/deals/update", id=DEAL["id"], set={"target": "Swoop"}).status_code == 422  # no change
    assert _post(client, "/api/admin/deals/update", id="0000000000000000", set={"stage": "announced"}).status_code == 404
    assert calls == []


def test_paused_ai_refuses_every_brief(monkeypatch):
    import src.hosted_market as hm
    from src import plans

    async def paused(fresh=False):
        return {"ai": {"on": False, "message": "Back at 3pm"}}
    monkeypatch.setattr(hm, "site_settings", paused)
    with pytest.raises(HTTPException) as e:
        asyncio.run(plans.use_ai(MagicMock()))
    assert e.value.status_code == 503 and e.value.detail == "Back at 3pm"


def test_sources_are_switched_by_name(monkeypatch):
    from src.engines import source_switches
    monkeypatch.setattr(source_switches, "disabled", lambda: frozenset({"TechCabal"}))
    client, calls = _client(monkeypatch)
    r = _post(client, "/api/admin/sources")
    rows = {x["name"]: x["on"] for x in r.json()}
    assert r.status_code == 200 and rows["TechCabal"] is False and rows["BusinessDay Nigeria"] is True
    r = _post(client, "/api/admin/sources/set", name="Nairametrics", on=False)
    assert r.status_code == 200 and calls[-1] == ("admin_set_site_setting", {"p_key": "sources",
                                                  "p_value": {"off": ["Nairametrics", "TechCabal"]}})
    assert _post(client, "/api/admin/sources/set", name="Made Up Daily", on=False).status_code == 422


def test_switched_off_feeds_are_not_read(monkeypatch):
    from src.engines import feed_healing, source_switches
    monkeypatch.setattr(source_switches, "disabled", lambda: frozenset({"B"}))
    assert feed_healing.effective_feeds({"A": "https://a/feed", "B": "https://b/feed"}, {}) == {"A": "https://a/feed"}


def test_seats_are_editable_with_the_plan(monkeypatch):
    client, calls = _client(monkeypatch)
    _post(client, "/api/admin/settings/plan", plan="team", fields={"seats": "8"})
    assert calls[-1][1]["p_fields"] == {"seats": 8}


def test_country_alerts_preview(monkeypatch):
    import src.hosted_market as hm

    async def signals(codes):
        return {"NG": {"name": "Nigeria", "policy": {"rate": 27.0, "date": "2026-11-20", "source": "CBN", "recent": True},
                       "elections": [{"label": "Presidential", "date": "2027-01-16"}]}}
    monkeypatch.setattr(hm, "_country_signals", signals)
    client, _ = _client(monkeypatch)
    r = _post(client, "/api/admin/country-alerts", codes=["ng"])
    body = r.json()
    assert r.status_code == 200 and body["alerts"][0]["title"].startswith("Nigeria: policy rate decision, 27%")
    assert body["elections"] == [{"country": "NG", "label": "Presidential", "date": "2027-01-16"}]
