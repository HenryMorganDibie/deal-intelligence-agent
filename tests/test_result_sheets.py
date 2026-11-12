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
        if fn == "insert_result_sheet":
            row = dict(args["p_row"], id="00000000-0000-0000-0000-000000000001")
            for r in rows.values():
                if r["image_sha256"] == row["image_sha256"]:
                    return R(dict(r, duplicate=True))
            rows[row["id"]] = row
            return R(row)
        if fn == "get_result_sheet":
            return R(rows.get(args["p_id"]))
        if fn == "review_result_sheet":
            rows[args["p_id"]].update(status=args["p_status"], data=args["p_data"])
            return R(rows[args["p_id"]])
        if fn == "result_totals":
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
    out = er.submit("presidential-2027", "24-11-1-1", upload=b"\x89PNG fake", content_type="image/png")
    assert out["status"] == "needs_review" and out["data"]["unit"]["name"] == "ANIFOWOSHE PRY. SCH."
    assert "party_votes_sum_to_valid" in [c["rule"] for c in out["data"]["checks"] if c["ok"] is False]
    again = er.submit("presidential-2027", "24/11/01/001", upload=b"\x89PNG fake", content_type="image/png")
    assert again.get("duplicate") is True                          # same image: not read twice
    with pytest.raises(Exception) as e:                            # verifying without fixing the sum is refused
        er.review(out["id"], "verified", {"votes": {"APC": 141}}, None)
    assert "still fails" in str(e.value.detail)
    fixed = er.review(out["id"], "verified", {"votes": {"NDC": 118}}, None)
    assert fixed["status"] == "verified" and fixed["data"]["votes"]["NDC"] == 118
    for bad in (dict(pu_code="99/99/99/999"), dict(election="mayor-2027"), dict(pu_code="Ikeja")):
        with pytest.raises(Exception):
            er.submit(**({"election": "presidential-2027", "pu_code": "24/11/01/001"} | bad), upload=b"x",
                      content_type="image/png")
    with pytest.raises(Exception):
        er.submit("presidential-2027", "24/11/01/001", upload=b"x", content_type="application/pdf")


def test_totals_add_turnout_and_coverage(db):
    t = er.totals("presidential-2027", "Lagos", "11")
    assert t["breakdown"] == "wards" and t["turnout"] == round(341 / 612, 4) and t["coverage"] == round(1 / 667, 4)
    assert t["groups"][0]["turnout"] == round(341 / 612, 4)


def test_results_are_institutional_only(db, monkeypatch):
    import api.index as api
    from src import public_api
    plan = {"plan": "pro"}

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
