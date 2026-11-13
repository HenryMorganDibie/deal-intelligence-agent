"""The Gambia's live results tracker: checks on entry, tallies, operator-only writes, results alerts."""
import pytest
from fastapi import HTTPException

from src import election_alerts, election_live
from src.data import gm_2026 as gm
from src.engines import live_results as lr

FIVE = {"Barrow": 0, "Darboe": 0, "Bensouda": 0, "Isatou Touray": 0, "Modou Lamin Sima": 0}


def votes(**kw):
    out = dict(FIVE)
    out.update(kw)
    return out


def test_reference_data_matches_the_commissions_figures():
    assert len(gm.CONSTITUENCIES) == 53
    assert sum(a["registered"] for a in gm.AREAS.values()) == gm.NATIONAL_REGISTERED == 1_146_474
    assert {k: len(a["constituencies"]) for k, a in gm.AREAS.items()}["Brikama"] == 12
    assert gm.constituency("Serrekunda") == "Serekunda" and gm.constituency("ILLIASA") == "Illiasa"
    assert gm.constituency("Kombo North") is None


def test_a_result_is_checked_and_names_are_resolved():
    r = lr.check({"constituency": "banjul north", "votes": votes(Barrow=3100, Darboe=2400, Bensouda=900),
                  "registered": 9000, "source": "https://iec.gm/results"})
    assert r["unit"] == "Banjul North" and r["area"] == "Banjul" and r["votes_cast"] == 6400
    assert r["votes"]["Adama Barrow"] == 3100 and r["votes"]["Talib Ahmed Bensouda"] == 900 and not r["warnings"]
    by_party = lr.check({"constituency": "Jimara", "votes": {"NPP": 5, "UDP": 4, "UNITE": 3, "Isatou Touray": 0, "APC": 1}})
    assert by_party["votes"]["Modou Lamin Sima"] == 1


@pytest.mark.parametrize("entry,message", [
    ({"constituency": "Atlantis", "votes": votes(Barrow=1)}, "Unknown constituency"),
    ({"constituency": "Basse", "votes": {**votes(Barrow=1), "Jammeh": 5}}, "Unknown candidate"),
    ({"constituency": "Basse", "votes": {"Barrow": 1}}, "Missing votes"),
    ({"constituency": "Basse", "votes": votes(Barrow=-1)}, "whole number"),
    ({"constituency": "Basse", "votes": votes(Barrow=10), "votes_cast": 11}, "does not equal"),
    ({"constituency": "Basse", "votes": votes(Barrow=10), "rejected": 2}, "no rejected ballots"),
    ({"constituency": "Basse", "votes": votes(Barrow=10), "registered": 9}, "exceed registered"),
    ({"constituency": "Basse", "votes": votes(Barrow=10), "source": "http://x"}, "https"),
])
def test_results_that_cannot_stand_are_refused(entry, message):
    with pytest.raises(lr.ResultError, match=message):
        lr.check(entry)


def test_high_turnout_is_accepted_with_a_warning():
    assert lr.check({"constituency": "Basse", "votes": votes(Barrow=97), "registered": 100})["warnings"]


def test_tally_builds_national_and_area_results_and_turnout_only_when_complete():
    rows = [lr.check({"constituency": c, "votes": votes(Barrow=b, Darboe=d), "registered": reg})
            for c, b, d, reg in (("Banjul Central", 3000, 2000, 7000), ("Banjul North", 2500, 2600, 7500),
                                 ("Banjul South", 1000, 900, 2500), ("Jimara", 4000, 1000, 9000))]
    t = lr.tally(rows)
    nat = t["national"]
    assert nat["reported"] == 4 and nat["units"] == 53 and not nat["complete"] and nat["turnout"] is None
    assert nat["leader"] == "Adama Barrow" and nat["margin"] == 10500 - 6500
    assert nat["units_won"] == {"Adama Barrow": 3, "Ousainou Darboe": 1}
    assert nat["results"][0]["votes_2021"] == 457_519
    banjul = next(a for a in t["areas"] if a["area"] == "Banjul")
    assert banjul["complete"] and banjul["turnout"] == round(12000 / 24820, 4) and banjul["pending"] == []
    assert nat["register_reported"] == round(24820 / gm.NATIONAL_REGISTERED, 4)
    north = next(c for c in t["units"] if c["unit"] == "Banjul North")
    assert north["winner"] == "Ousainou Darboe" and north["turnout"] == round(5100 / 7500, 4)
    assert next(c for c in t["units"] if c["unit"] == "Basse")["status"] == "pending"


def test_only_operators_enter_results_and_declared_results_are_alerted(monkeypatch):
    store, delivered = {}, []

    def fake_rpc(name, payload):
        class R:
            status_code = 200
        r = R()
        if name == "live_result_upsert":
            versions = store.get(payload["p_area"], {}).get("versions", 0) + 1
            store[payload["p_area"]] = {**payload["p_data"], "versions": versions}
            r.json = lambda: store[payload["p_area"]]
        else:
            r.json = lambda: list(store.values())
        return r
    from src import hosted_market as hm
    monkeypatch.setattr(hm, "_rpc_sync", fake_rpc)
    monkeypatch.setattr(election_alerts, "deliver", lambda stories: delivered.extend(stories) or {"sent": len(stories)})
    monkeypatch.setenv("DEAL_INTEL_OPERATORS", "op-1")
    election_live._cache.clear()
    entry = {"constituency": "Kiang West", "votes": votes(Barrow=2000, Darboe=1500), "registered": 5000}
    with pytest.raises(HTTPException) as e:
        election_live.submit("someone-else", entry)
    assert e.value.status_code == 403
    out = election_live.submit("op-1", entry)
    assert out["saved"]["unit"] == "Kiang West" and out["alerts"] == {"sent": 1}
    story = delivered[0]
    assert story["kind"] == "result" and story["title"].startswith("Kiang West: Adama Barrow (NPP) wins with 2,000 votes")
    assert "Lower River, The Gambia" in story["facts_line"] and "margin 500" in story["facts_line"]
    election_live.submit("op-1", dict(entry, status="provisional"))
    assert len(delivered) == 1                                    # provisional figures are not pushed
    assert election_live.results()["national"]["reported"] == 1


def test_results_alerts_receive_results_and_nothing_else():
    f = election_alerts.clean_filters({"election": "gm-2026", "kind": "results"})
    result = {"id": "r", "kind": "result", "election": "gm-2026", "states": ["Lower River"], "title": "x"}
    incident = {"id": "i", "election": "gm-2026", "incident_types": ["violence"], "severity": "high", "title": "y"}
    assert election_alerts.matches(result, f) and not election_alerts.matches(incident, f)
    news = election_alerts.clean_filters({"election": "gm-2026", "kind": "news"})
    assert not election_alerts.matches(result, news)
    assert election_alerts._alert_item(dict(result, facts_line="Barrow 2,000"))["facts_line"] == "Barrow 2,000"


# ── Nigeria ──

NG_TOP = {"Tinubu": 0, "Atiku": 0, "Obi": 0}


def test_nigeria_results_take_rejected_ballots_and_the_leading_candidates_first():
    r = lr.check({"state": "Lagos State", "votes": {"Tinubu": 600_000, "Atiku": 90_000, "Obi": 550_000},
                  "others_zero": True, "rejected": 20_000, "accredited": 1_300_000, "registered": 7_000_000}, "ng-2027")
    assert r["unit"] == "Lagos" and r["area"] == "South West" and r["valid"] == 1_240_000 and r["votes_cast"] == 1_260_000
    assert r["votes"]["Bola Tinubu"] == 600_000 and len(r["votes"]) == 18
    with pytest.raises(lr.ResultError, match="Missing votes"):
        lr.check({"state": "Lagos", "votes": {"Tinubu": 1}}, "ng-2027")
    with pytest.raises(lr.ResultError, match="exceed accredited"):
        lr.check({"state": "Kano", "votes": {"Tinubu": 100}, "others_zero": True, "accredited": 50}, "ng-2027")
    assert lr.check({"state": "Abuja", "votes": {"APC": 1}, "others_zero": True}, "ng-2027")["unit"] == "FCT"


def test_nigeria_tally_reports_the_spread_rule_zones_and_2023_shares():
    rows = []
    states = [s for s in lr.le.units("ng-2027") if s != "FCT"]
    for i, st in enumerate(states):
        # Tinubu reaches 25% in the first 24 states only; Obi in the first 10
        t = 300 if i < 24 else 100
        o = 300 if i < 10 else 50
        rows.append(lr.check({"state": st, "votes": {"Tinubu": t, "Atiku": 400, "Obi": o}, "others_zero": True}, "ng-2027"))
    rows.append(lr.check({"state": "FCT", "votes": {"Tinubu": 100, "Atiku": 100, "Obi": 800}, "others_zero": True}, "ng-2027"))
    t = lr.tally(rows, "ng-2027")
    spread = t["national"]["spread"]
    assert spread["Bola Tinubu"]["states_at_25"] == 24 and spread["Bola Tinubu"]["met"] is True
    assert spread["Bola Tinubu"]["fct_at_25"] is False and spread["Peter Obi"]["fct_at_25"] is True
    assert spread["Atiku Abubakar"]["states_at_25"] == 36
    assert t["national"]["complete"] and t["unit_word"] == "state" and t["baseline_year"] == 2023
    assert {a["area"] for a in t["areas"]} == {"North Central", "North East", "North West", "South East", "South South", "South West"}
    assert t["national"]["results"][0].get("votes_2023") in (6_984_520, 8_794_726, 6_101_533)
    lagos = next(u for u in t["units"] if u["unit"] == "Lagos")
    assert next(x for x in lagos["results"] if x["candidate"] == "Peter Obi")["share_2023"] == round(582_454 / 1_239_252, 4)


def test_historical_results_reconcile_with_inecs_national_totals():
    from src.data import ng_results_history as h
    for year, nat in ((2019, h.NATIONAL_2019), (2015, h.NATIONAL_2015)):
        for party, total in nat["declared"].items():
            assert sum(r[party] for r in h.RESULTS[year].values()) == total
    d = h.NATIONAL_2023
    for party in ("PDP", "NNPP"):
        assert sum(r[party] for r in h.RESULTS[2023].values()) == d["declared"][party]
    for party, off in d["state_sums_differ"].items():
        assert sum(r[party] for r in h.RESULTS[2023].values()) - d["declared"][party] == off
    assert len(h.RESULTS[2023]) == 37 and h.state_result(2023, "Kano")["results"][0]["party"] == "NNPP"


def test_imported_sheets_are_checked_queued_and_read_within_the_budget(monkeypatch):
    from src import election_results as er
    from src import hosted_market as hm
    calls = {"added": [], "done": []}

    def fake_rpc(name, payload):
        class R:
            status_code = 200
        r = R()
        if name == "sheet_queue_add":
            calls["added"] = payload["p_rows"]
            r.json = lambda: len(payload["p_rows"]) - 1          # one already queued
        elif name == "sheet_queue_take":
            r.json = lambda: {"rows": [{"id": "q1", "owner": "u1", "election": "presidential-2027", "pu_code": "24/11/01/001",
                                        "image_url": "https://example.org/a.jpg"},
                                       {"id": "q2", "owner": "u1", "election": "presidential-2027", "pu_code": "24/11/01/002",
                                        "image_url": "https://example.org/b.jpg"}], "used_today": 10}
        elif name == "sheet_queue_done":
            calls["done"].append((payload["p_id"], payload["p_status"]))
            r.json = lambda: True
        return r
    monkeypatch.setattr(hm, "_rpc_sync", fake_rpc)
    monkeypatch.setattr(hm, "_public_host", lambda url: True)
    out = er.queue("00000000-0000-0000-0000-000000000001", "presidential-2027", [
        {"pu_code": "24-11-01-001", "image_url": "https://example.org/a.jpg", "priority": 5},
        {"pu_code": "24/11/01/002", "image_url": "https://example.org/b.jpg"},
        {"pu_code": "nonsense", "image_url": "https://example.org/c.jpg"},
        {"pu_code": "24/11/01/003", "image_url": "http://example.org/d.jpg"}])
    assert out["queued"] == 1 and out["duplicates"] == 1 and out["refused_total"] == 2
    assert calls["added"][0] == {"election": "presidential-2027", "pu_code": "24/11/01/001",
                                 "image_url": "https://example.org/a.jpg", "priority": 5}

    def fake_submit(owner, election, code, url=None, **kw):
        if code.endswith("002"):
            raise HTTPException(404, f"{code} is not in INEC's polling-unit list.")
        return {"id": "s1"}
    monkeypatch.setattr(er, "submit", fake_submit)
    res = er.read_queue()
    assert res["read"] == 1 and res["failed"] == 1 and calls["done"] == [("q1", "read"), ("q2", "failed")]


def test_governorship_races_share_one_store_and_alert_once_a_state_is_complete(monkeypatch):
    from src.data import live_elections as le
    from src.data import ng_governorship as gov
    store, delivered, seen = {}, [], set()

    def fake_rpc(name, payload):
        class R:
            status_code = 200
        r = R()
        seen.add(payload.get("p_election"))
        if name == "live_result_upsert":
            store[payload["p_area"]] = payload["p_data"]
            r.json = lambda: store[payload["p_area"]]
        else:
            r.json = lambda: list(store.values())
        return r
    from src import hosted_market as hm
    monkeypatch.setattr(hm, "_rpc_sync", fake_rpc)
    monkeypatch.setattr(election_alerts, "deliver", lambda stories: delivered.extend(stories) or {"sent": len(stories)})
    monkeypatch.setenv("DEAL_INTEL_OPERATORS", "op-1")
    election_live._cache.clear()
    races = le.gov_elections()
    assert len(races) == 28 and "Anambra" not in races and "Lagos" in races
    gombe, lagos = races["Gombe"], races["Lagos"]
    assert "Yamaltu/Deba" in le.units(gombe)
    lgas = list(le.units(gombe))
    for i, lga in enumerate(lgas):
        votes = {"APC": 3000 if i else 900, "PDP": 1000, "NNPP": 200}
        out = election_live.submit("op-1", {"unit": lga, "votes": votes, "others_zero": True}, gombe)
        assert out["saved"]["state"] == "Gombe"
        assert (out["alerts"] is None) == (i < len(lgas) - 1)     # one alert, when the last LGA is in
    assert seen == {gov.ELECTION} and set(store) == {f"Gombe|{u}" for u in lgas}
    story = delivered[0]
    assert story["election"] == "ng-2027-gov" and story["states"] == ["Gombe"]
    assert story["title"].startswith("Gombe governorship:") and f"all {len(lgas)} LGAs in" in story["title"]
    t = election_live.results(gombe)
    spread = t["national"]["spread"][t["national"]["leader"]]
    assert spread == {"states_at_25": len(lgas), "needed": 8, "met": True, "fct_at_25": None, "of": len(lgas)}
    assert t["previous"]["year"] == 2023 and t["state"] == "Gombe"
    assert election_live.results(lagos)["national"]["reported"] == 0       # races do not leak into each other
    summary = election_live.governorship()
    row = next(r for r in summary["races"] if r["state"] == "Gombe")
    assert row["complete"] and row["leader"]["party"] == "APC" and summary["complete_states"] == 1
    assert next(r for r in summary["races"] if r["state"] == "Lagos")["won_2023"]["party"] == "APC"


def test_governorship_ballot_matches_names_as_announced():
    from src.data import live_elections as le
    lagos = le.gov_elections()["Lagos"]
    assert lr._candidate("Rhodes-Vivour", lagos) == lr._candidate("ADC", lagos) == "Gbadebo Rhodes Vivour"
    assert lr._candidate("Obafemi Hamzat", lagos) == lr._candidate("APC", lagos)
    with pytest.raises(lr.ResultError, match="Unknown LGA"):
        lr.check({"unit": "Ikeja North", "votes": {"APC": 1}, "others_zero": True}, lagos)
    assert lr.check({"unit": "IKEJA", "votes": {"APC": 1}, "others_zero": True}, lagos)["unit"] == "Ikeja"


def test_public_api_serves_the_governorship_summary(monkeypatch):
    from fastapi.testclient import TestClient
    from api.index import app
    from src import public_api
    monkeypatch.setattr(public_api, "authorize", lambda *a, **k: _plan("pro"))
    monkeypatch.setattr(election_live, "governorship", lambda: {"races": [], "election": "ng-2027-gov"})
    r = TestClient(app).get("/v1/elections/governorship")
    assert r.status_code == 200 and r.json()["election"] == "ng-2027-gov"
    assert "GET /v1/elections/governorship" in TestClient(app).get("/v1").json()["endpoints"]


async def _plan_coro(plan):
    return {"plan": plan}


def _plan(plan):
    return _plan_coro(plan)


def test_every_2023_governorship_result_names_a_winner_with_a_party():
    from src.data import ng_governorship as gov
    assert len(gov.STATES) == 28
    for st in gov.STATES:
        w = gov.winner_2023(st)
        assert w and w["party"], st
    assert gov.winner_2023("Taraba")["name"] == "Agbu Kefas"
