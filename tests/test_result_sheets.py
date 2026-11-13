import json

import pytest
from fastapi.testclient import TestClient

from src import election_results as er
from src import hosted_market as hm
from src.engines import result_sheets as rs

GOOD = {"form": "EC8A(I)", "state": "Lagos", "lga": "Ikeja", "ward": "Anifowoshe/Ikeja",
        "polling_unit": "Anifowoshe Pry. Sch.", "polling_unit_code": "24/11/01/001",
        "figures": {"registered": 612, "accredited": 341, "ballots_issued": 650, "unused": 315, "spoiled": 5,
                    "rejected": 8, "valid": 322, "votes_cast": 330},
        "votes": {"APC": 141, "NDC": 118, "ADC": 47, "PDP": 9, "APM": 4, "SDP": 2, "LP": 1},
        "votes_in_words": {"APC": 141, "NDC": 118, "ADC": 47, "PDP": 9, "APM": 4, "SDP": 2, "LP": 1},
        "signed": True, "legibility": "good", "notes": ""}
UNIT = {"code": "24/11/01/001", "name": "ANIFOWOSHE PRY. SCH.", "ward": "ANIFOWOSHE/IKEJA", "lga": "IKEJA", "state": "LAGOS"}


def reading(**over):
    raw = json.loads(json.dumps(GOOD))
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(raw.get(k), dict):
            raw[k].update(v)
        else:
            raw[k] = v
    return rs.parse_model_output("Here it is:\n```json\n" + json.dumps(raw) + "\n```")


def failed(sheet, code="24/11/01/001", unit=UNIT):
    return [c["rule"] for c in rs.check(sheet, code, unit) if c["ok"] is False]


def test_a_consistent_sheet_passes_every_check_and_is_provisional():
    s = reading()
    assert s["votes"]["APC"] == 141 and s["votes"]["YPP"] is None and s["polling_unit_code"] == "24/11/01/001"
    checks = rs.check(s, "24/11/01/001", UNIT)
    assert all(c["ok"] is not False for c in checks)
    assert rs.status_for(checks, "good") == "provisional"


@pytest.mark.parametrize("over,rule", [
    ({"votes": {"APC": 241}, "votes_in_words": {"APC": 241}}, "party_votes_sum_to_valid"),
    ({"figures": {"votes_cast": 400, "valid": 392}, "votes": {"APC": 211}, "votes_in_words": {"APC": 211}},
     "votes_cast_within_accredited"),
    ({"figures": {"accredited": 700}}, "accredited_within_registered"),
    ({"figures": {"rejected": 18}}, "valid_plus_rejected_is_votes_cast"),
    ({"figures": {"unused": 300}}, "ballots_reconcile"),
    ({"votes_in_words": {"NDC": 181}}, "figures_match_words"),
    ({"figures": {"registered": 6120}}, "plausible_size"),
    ({"signed": False}, "signed"),
])
def test_each_inconsistency_is_caught_and_sends_the_sheet_to_review(over, rule):
    s = reading(**over)
    assert rule in failed(s)
    assert rs.status_for(rs.check(s, "24/11/01/001", UNIT), "good") == "needs_review"


def test_wrong_or_unknown_polling_unit_and_unreadable_totals_need_review():
    s = reading()
    assert "code_matches_submission" in failed(s, "24/11/01/002")
    assert "polling_unit_exists" in failed(s, unit=None)
    blank = reading(figures={"valid": None})
    assert rs.status_for(rs.check(blank, "24/11/01/001", UNIT), "good") == "needs_review"
    assert rs.status_for(rs.check(reading(), "24/11/01/001", UNIT), "poor") == "needs_review"
    with pytest.raises(ValueError):
        rs.parse_model_output("I cannot read this image.")
    thought = rs.parse_model_output("<think>The table {rows} shows...</think>\n" + json.dumps(GOOD))
    assert thought["figures"]["valid"] == 322


@pytest.fixture
def db(monkeypatch):
    rows = {}

    class R:
        def __init__(self, data, status=200):
            self._d, self.status_code, self.text = data, status, ""

        def json(self):
            return self._d

    def fake(fn, args, timeout=30):
        if fn == "polling_unit_get":
            return R(UNIT if args["p_code"] == "24/11/01/001" else None)
        if fn == "polling_unit_areas":
            return R([{"code": "24", "name": "LAGOS"}])
        if fn == "result_sheet_insert":
            assert args["p_owner"]
            row = dict(args["p_row"], owner=args["p_owner"], id=f"00000000-0000-0000-0000-{len(rows) + 1:012d}")
            for r in rows.values():
                if r["owner"] == row["owner"] and r["image_sha256"] == row["image_sha256"]:
                    return R(dict(r, duplicate=True))
            rows[row["id"]] = row
            return R(row)
        if fn == "result_sheet_get":
            r = rows.get(args["p_id"])
            return R(r if r and r["owner"] == args["p_owner"] else None)
        if fn == "result_sheet_review":
            r = rows.get(args["p_id"])
            if not r or r["owner"] != args["p_owner"]:
                return R(None)
            r.update(status=args["p_status"], data=args["p_data"])
            return R(r)
        if fn == "result_sheet_list":
            mine = [r for r in rows.values() if r["owner"] == args["p_owner"]]
            return R({"total": len(mine), "sheets": mine})
        if fn == "result_sheet_totals" and args["p_owner"] != "acct-a":
            return R({"polling_units": 667, "sheets": 0, "verified": 0, "votes": {}, "groups": []})
        if fn == "result_sheet_totals":
            return R({"polling_units": 667, "sheets": 1, "verified": 1, "registered": 612, "accredited": 341,
                      "votes_cast": 330, "valid": 322, "rejected": 8, "votes": {"APC": 141},
                      "groups": [{"code": "01", "name": "ANIFOWOSHE/IKEJA", "polling_units": 47, "sheets": 1,
                                  "verified": 1, "registered": 612, "accredited": 341, "votes_cast": 330}]})
        raise AssertionError(fn)
    monkeypatch.setattr(hm, "_rpc_sync", fake)
    from src import polling_units
    polling_units._cache.clear()
    return rows


def test_submit_reads_checks_stores_and_reviews(db, monkeypatch):
    monkeypatch.setattr(er, "read_sheet", lambda image: (reading(votes={"NDC": 128}, votes_in_words={"NDC": 128}), "test-model"))
    out = er.submit("acct-a", "presidential-2027", "24-11-1-1", upload=b"\x89PNG fake", content_type="image/png")
    assert out["status"] == "needs_review" and out["data"]["unit"]["name"] == "ANIFOWOSHE PRY. SCH."
    assert "party_votes_sum_to_valid" in [c["rule"] for c in out["data"]["checks"] if c["ok"] is False]
    again = er.submit("acct-a", "presidential-2027", "24/11/01/001", upload=b"\x89PNG fake", content_type="image/png")
    assert again.get("duplicate") is True                          # same image: not read twice
    with pytest.raises(Exception) as e:                            # verifying without fixing the sum is refused
        er.review("acct-a", out["id"], "verified", {"votes": {"APC": 141}})
    assert "still fails" in str(e.value.detail)
    fixed = er.review("acct-a", out["id"], "verified", {"votes": {"NDC": 118}})
    assert fixed["status"] == "verified" and fixed["data"]["votes"]["NDC"] == 118
    for bad in (dict(pu_code="99/99/99/999"), dict(election="mayor-2027"), dict(pu_code="Ikeja")):
        with pytest.raises(Exception):
            er.submit(**({"owner": "acct-a", "election": "presidential-2027", "pu_code": "24/11/01/001"} | bad),
                      upload=b"x", content_type="image/png")
    with pytest.raises(Exception):
        er.submit("acct-a", "presidential-2027", "24/11/01/001", upload=b"x", content_type="application/pdf")


def test_totals_add_turnout_and_coverage(db):
    t = er.totals("acct-a", "presidential-2027", "Lagos", "11")
    assert t["breakdown"] == "wards" and t["turnout"] == round(341 / 612, 4) and t["coverage"] == round(1 / 667, 4)
    assert t["groups"][0]["turnout"] == round(341 / 612, 4)


def test_results_are_institutional_only(db, monkeypatch):
    import api.index as api
    from src import public_api
    plan = {"plan": "pro", "account": "acct-a"}

    async def auth(request, response, count=True):
        return dict(plan)
    monkeypatch.setattr(public_api, "authorize", auth)
    client = TestClient(api.app)
    r = client.get("/v1/elections/results", params={"state": "Lagos", "lga": "11"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "plan_required"
    plan["plan"] = "institutional"
    assert client.get("/v1/elections/results", params={"state": "Lagos", "lga": "11"}).json()["breakdown"] == "wards"
    a = client.get("/v1/elections/accreditation", params={"state": "Lagos", "lga": "11"}).json()
    assert a["accredited"] == 341 and "votes" not in a
    monkeypatch.setattr(er, "read_sheet", lambda image: (reading(), "test-model"))
    r = client.post("/v1/elections/results/sheets", json={"pu_code": "24/11/01/001", "image_url": "https://example.org/s.jpg"})
    assert r.status_code == 200 and r.json()["status"] == "provisional"
    assert client.post("/v1/elections/results/sheets", json={"pu_code": "24/11/01/001", "image_url": "http://x"}).status_code == 400
    assert client.post("/v1/elections/results/sheets", json={"pu_code": "24/11/01/001", "image_base64": "%%%"}).status_code == 400


def test_each_account_sees_only_its_own_sheets_and_totals(db, monkeypatch):
    monkeypatch.setattr(er, "read_sheet", lambda image: (reading(), "test-model"))
    a = er.submit("acct-a", "presidential-2027", "24/11/01/001", upload=b"\x89PNG a", content_type="image/png")
    assert er.sheets("acct-a", "presidential-2027")["total"] == 1
    assert er.sheets("acct-b", "presidential-2027")["total"] == 0              # another customer: nothing
    with pytest.raises(Exception) as e:
        er.review("acct-b", a["id"], "rejected", None)                         # cannot review another's sheet
    assert e.value.status_code == 404
    assert er.totals("acct-b", "presidential-2027", "Lagos", "11")["sheets"] == 0
    # The same image from a second account is that account's own sheet, not a duplicate of the first.
    b = er.submit("acct-b", "presidential-2027", "24/11/01/001", upload=b"\x89PNG a", content_type="image/png")
    assert not b.get("duplicate") and b["id"] != a["id"]
    with pytest.raises(Exception) as e:
        er.sheets(None, "presidential-2027")                                   # no account, no data
    assert e.value.status_code == 503


def test_account_is_looked_up_from_the_key_when_not_returned(db, monkeypatch):
    import api.index as api
    from src import public_api

    async def auth(request, response, count=True):
        return {"plan": "institutional", "key_id": "k-1"}

    class R:
        status_code = 200

        def json(self):
            return "acct-a"

    async def fake_rpc(client, fn, args):
        assert fn == "api_key_account" and args == {"p_key_id": "k-1"}
        return R()
    monkeypatch.setattr(public_api, "authorize", auth)
    monkeypatch.setattr(hm, "_rpc", fake_rpc)
    r = TestClient(api.app).get("/v1/elections/results", params={"state": "Lagos", "lga": "11"})
    assert r.status_code == 200 and r.json()["sheets"] == 1              # acct-a's totals
