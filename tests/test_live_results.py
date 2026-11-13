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
    assert r["constituency"] == "Banjul North" and r["area"] == "Banjul" and r["votes_cast"] == 6400
    assert r["votes"]["Adama Barrow"] == 3100 and r["votes"]["Talib Ahmed Bensouda"] == 900 and not r["warnings"]
    by_party = lr.check({"constituency": "Jimara", "votes": {"NPP": 5, "UDP": 4, "UNITE": 3, "Isatou Touray": 0, "APC": 1}})
    assert by_party["votes"]["Modou Lamin Sima"] == 1


@pytest.mark.parametrize("entry,message", [
    ({"constituency": "Atlantis", "votes": votes(Barrow=1)}, "Unknown constituency"),
    ({"constituency": "Basse", "votes": {**votes(Barrow=1), "Jammeh": 5}}, "Unknown candidate"),
    ({"constituency": "Basse", "votes": {"Barrow": 1}}, "Missing votes"),
    ({"constituency": "Basse", "votes": votes(Barrow=-1)}, "whole number"),
    ({"constituency": "Basse", "votes": votes(Barrow=10), "votes_cast": 11}, "does not equal"),
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
    assert nat["reported"] == 4 and nat["constituencies"] == 53 and not nat["complete"] and nat["turnout"] is None
    assert nat["leader"] == "Adama Barrow" and nat["margin"] == 10500 - 6500
    assert nat["constituencies_won"] == {"Adama Barrow": 3, "Ousainou Darboe": 1}
    assert nat["results"][0]["votes_2021"] == 457_519
    banjul = next(a for a in t["areas"] if a["area"] == "Banjul")
    assert banjul["complete"] and banjul["turnout"] == round(12000 / 24820, 4) and banjul["pending"] == []
    assert nat["register_reported"] == round(24820 / gm.NATIONAL_REGISTERED, 4)
    north = next(c for c in t["constituencies"] if c["constituency"] == "Banjul North")
    assert north["winner"] == "Ousainou Darboe" and north["turnout"] == round(5100 / 7500, 4)
    assert next(c for c in t["constituencies"] if c["constituency"] == "Basse")["status"] == "pending"


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
    assert out["saved"]["constituency"] == "Kiang West" and out["alerts"] == {"sent": 1}
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
