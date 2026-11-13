import pytest
from fastapi import HTTPException

from src import election_alerts as ea
from src import hosted_market as hm
from src.engines import chat_formats

LAGOS = {"id": "s1", "day": "2026-11-13", "title": "Thugs attack NDC rally in Ikeja", "url": "https://p.example/1",
         "severity": "high", "incident_types": ["violence", "thuggery"], "states": ["Lagos"], "lgas": ["Ikeja, Lagos"],
         "candidates": [], "parties": ["NDC"], "topics": ["security"], "outlets": ["Punch", "Vanguard"]}
KANO = dict(LAGOS, id="s2", severity="low", states=["Kano"], lgas=[], incident_types=["arrest"], title="Police arrest agents")
CALM = dict(LAGOS, id="s3", severity=None, incident_types=[], title="APC unveils manifesto", candidates=["Bola Tinubu"])


def test_filters_select_by_kind_severity_place_and_type():
    f = ea.clean_filters({"min_severity": "medium", "states": ["Lagos"]})
    assert ea.matches(LAGOS, f) and not ea.matches(KANO, f) and not ea.matches(CALM, f)
    assert ea.matches(LAGOS, ea.clean_filters({"lgas": ["ikeja"]}))
    assert not ea.matches(LAGOS, ea.clean_filters({"incident_types": ["vote_buying"]}))
    news = ea.clean_filters({"kind": "news", "candidates": ["Tinubu"]})
    assert ea.matches(CALM, news) and not ea.matches(KANO, news)
    for bad in ({"kind": "results"}, {"min_severity": "extreme"}, {"states": "Lagos"}):
        with pytest.raises(HTTPException):
            ea.clean_filters(bad)


def test_chat_message_reads_as_an_election_alert():
    sub = {"id": "a1", "name": "Lagos violence", "webhook_url": "https://hooks.slack.com/services/x"}
    msg = ea._payload(sub, [LAGOS])
    text = str(msg)
    assert "High severity: violence, thuggery · Ikeja, Lagos · Punch, Vanguard" in text
    assert "API documentation" in text and "election alert" in text and "Open watchlist" not in text
    generic = ea._payload(dict(sub, webhook_url="https://example.org/hook"), [LAGOS])
    assert generic["type"] == "election_alert" and generic["stories"][0]["severity"] == "high"
    assert chat_formats.facts({"kind": "deal", "deal_type": "ipo"}).startswith("Deal")   # watchlists unchanged


def test_delivery_sends_once_skips_backlog_and_retries_failures(monkeypatch):
    sent_db, posts = {}, []
    subs = [{"id": "a1", "owner": "acct", "name": "Lagos", "webhook_url": "https://example.org/hook",
             "created_at": "2026-11-13T09:00:00Z", "filters": {"kind": "incidents", "states": ["Lagos"]}}]

    class R:
        status_code = 200

        def __init__(self, d):
            self._d = d

        def json(self):
            return self._d

    def fake(fn, args, timeout=30):
        if fn == "election_alert_active":
            return R(subs)
        if fn == "election_alert_claim":
            new = [i for i in args["p_story_ids"] if (args["p_sub"], i) not in sent_db]
            for i in new:
                sent_db[(args["p_sub"], i)] = True
            return R(new)
        if fn == "election_alert_release":
            for i in args["p_story_ids"]:
                sent_db.pop((args["p_sub"], i), None)
            return R(len(args["p_story_ids"]))
        raise AssertionError(fn)
    outcome = {"delivered": False}

    async def deliver(url, payload, key):
        posts.append(payload)
        return {"delivered": outcome["delivered"], "error": None if outcome["delivered"] else "http_500"}
    monkeypatch.setattr(hm, "_rpc_sync", fake)
    monkeypatch.setattr(ea.watch, "deliver_webhook", deliver)
    old = dict(LAGOS, id="s0", day="2026-11-10")                     # before the alert existed: not sent
    assert ea.deliver([LAGOS, old, KANO])["failed"] == 1 and sent_db == {}   # failure releases the claim
    outcome["delivered"] = True
    assert ea.deliver([LAGOS, old, KANO])["sent"] == 1
    assert ea.deliver([LAGOS])["sent"] == 0                          # never twice
    assert len(posts) == 2 and posts[-1]["stories"][0]["id"] == "s1"


def test_alerts_never_break_collection(monkeypatch):
    def boom(fn, args, timeout=30):
        raise RuntimeError("db down")
    monkeypatch.setattr(hm, "_rpc_sync", boom)
    assert ea.deliver([LAGOS]) == {"error": "RuntimeError"}


def test_alert_endpoints_are_institutional_and_hide_the_webhook(monkeypatch):
    from fastapi.testclient import TestClient
    import api.index as api
    from src import public_api
    plan = {"plan": "team", "account": "acct"}

    async def auth(request, response, count=True):
        return dict(plan)
    monkeypatch.setattr(public_api, "authorize", auth)
    monkeypatch.setattr(hm, "_public_host", lambda url: True)
    store = {}

    class R:
        def __init__(self, d, status=200):
            self._d, self.status_code, self.text = d, status, ""

        def json(self):
            return self._d

    def fake(fn, args, timeout=30):
        if fn == "election_alert_create":
            row = {"id": "00000000-0000-0000-0000-000000000009", "owner": args["p_owner"], "name": args["p_name"],
                   "webhook_url": args["p_url"], "filters": args["p_filters"], "active": True, "created_at": "2026-11-13"}
            store[row["id"]] = row
            return R(row)
        if fn == "election_alert_list":
            return R([dict(r, sent=0) for r in store.values() if r["owner"] == args["p_owner"]])
        raise AssertionError(fn)
    monkeypatch.setattr(hm, "_rpc_sync", fake)
    c = TestClient(api.app)
    body = {"name": "Lagos", "webhook_url": "https://hooks.slack.com/services/T0/B0/secretpart", "filters": {"states": ["Lagos"]}}
    assert c.post("/v1/elections/alerts", json=body).status_code == 403
    plan["plan"] = "institutional"
    r = c.post("/v1/elections/alerts", json=body).json()
    assert r["destination"] == "Slack" and "secretpart" not in r["webhook"] and r["filters"]["kind"] == "incidents"
    assert c.get("/v1/elections/alerts").json()["alerts"][0]["name"] == "Lagos"
    assert c.post("/v1/elections/alerts", json=dict(body, webhook_url="http://insecure.example")).status_code == 400


def test_backfill_sends_recent_matches_once(monkeypatch):
    from src import election_feed
    sent_db, posts = set(), []
    sub = {"id": "a1", "owner": "acct", "name": "All", "webhook_url": "https://example.org/hook",
           "created_at": "2099-01-01", "filters": {"kind": "incidents", "min_severity": "medium"}}

    class R:
        status_code = 200

        def __init__(self, d):
            self._d = d

        def json(self):
            return self._d

    def fake(fn, args, timeout=30):
        if fn == "election_alert_active":
            return R([sub])
        if fn == "election_alert_claim":
            new = [i for i in args["p_story_ids"] if i not in sent_db]
            sent_db.update(new)
            return R(new)
        raise AssertionError(fn)

    async def deliver(url, payload, key):
        posts.append(payload)
        return {"delivered": True}
    monkeypatch.setattr(hm, "_rpc_sync", fake)
    monkeypatch.setattr(ea.watch, "deliver_webhook", deliver)
    from datetime import date
    today = date.today().isoformat()
    monkeypatch.setattr(election_feed, "_load", lambda since: [dict(LAGOS, day=today), dict(KANO, day=today)])
    assert ea.backfill("acct", "a1", 3)["sent"] == 1                 # the high-severity Lagos story only
    assert ea.backfill("acct", "a1", 3)["sent"] == 0                 # not twice
    with pytest.raises(HTTPException):
        ea.backfill("someone-else", "a1", 3)
