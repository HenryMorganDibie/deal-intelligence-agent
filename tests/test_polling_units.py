import csv
import gzip
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src import hosted_market as hm
from src import polling_units as pu

DATA = Path(__file__).resolve().parents[1] / "scripts" / "data" / "polling_units_2025-09-27.csv.gz"


def test_bundled_delimitation_matches_inec_structure():
    rows = list(csv.DictReader(gzip.open(DATA, "rt")))
    assert len(rows) == 176_623                                   # INEC publishes 176,846
    assert len({r["state_code"] for r in rows}) == 37
    assert len({(r["state_code"], r["lga_code"]) for r in rows}) == 774
    assert len({(r["state_code"], r["lga_code"], r["ward_code"]) for r in rows}) == 8_809   # INEC: 8,809
    assert len({r["code"] for r in rows}) == len(rows)
    assert all(r["code"] == f'{r["state_code"]}/{r["lga_code"]}/{r["ward_code"]}/{r["unit_code"]}' for r in rows)
    assert {r["kind"] for r in rows} == {"existing", "new"}
    names = {}
    for r in rows:                                                # one name per ward code
        assert names.setdefault((r["state_code"], r["lga_code"], r["ward_code"]), r["ward"]) == r["ward"]


class R:
    def __init__(self, data, status=200, text=""):
        self._d, self.status_code, self.text = data, status, text

    def json(self):
        return self._d


STATES = [{"code": "24", "name": "LAGOS", "lgas": 20, "wards": 245, "polling_units": 13325},
          {"code": "37", "name": "FEDERAL CAPITAL TERRITORY", "lgas": 6, "wards": 62, "polling_units": 2822}]


@pytest.fixture
def db(monkeypatch):
    calls = []

    def fake(fn, args, timeout=30):
        calls.append((fn, args))
        if fn == "polling_unit_areas":
            if args["p_state"] is None:
                return R(STATES)
            if args["p_lga"] is None:
                return R([{"code": "10", "name": "IKEJA", "wards": 10, "polling_units": 574}])
            return R([{"code": "05", "name": "OJODU", "polling_units": 61, "new_units": 20}])
        if fn == "polling_unit_list":
            return R({"total": 1, "units": [{"code": "24/10/05/012", "name": "OJODU GRAMMAR SCHOOL I"}]})
        if fn == "polling_unit_get":
            return R({"code": args["p_code"], "name": "OJODU GRAMMAR SCHOOL I"} if args["p_code"] == "24/10/05/012" else None)
        raise AssertionError(fn)
    monkeypatch.setattr(hm, "_rpc_sync", fake)
    pu._cache.clear()
    return calls


def test_areas_one_level_at_a_time_with_state_by_name_or_code(db):
    assert [s["code"] for s in pu.areas()] == ["24", "37"]
    assert pu.areas("Lagos")[0]["name"] == "IKEJA" and db[-1][1] == {"p_state": "24", "p_lga": None}
    assert pu.areas("FCT", None) and db[-1][1]["p_state"] == "37"
    assert pu.areas("24", "10")[0]["name"] == "OJODU" and db[-1][1] == {"p_state": "24", "p_lga": "10"}
    with pytest.raises(HTTPException) as e:
        pu.areas(None, "10")
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        pu.areas("Atlantis")
    assert e.value.status_code == 404


def test_units_need_a_ward_or_a_search_and_codes_are_normalised(db):
    assert pu.units("lagos", "10", "5")["total"] == 1 and db[-1][1]["p_ward"] == "05"
    assert pu.units(q="grammar")["units"]
    for bad in ({}, {"q": "ab"}, {"ward": "05"}):
        with pytest.raises(HTTPException) as e:
            pu.units(**bad)
        assert e.value.status_code == 400
    assert pu.unit("24-10-5-12")["name"] == "OJODU GRAMMAR SCHOOL I"          # hyphens, short parts
    with pytest.raises(HTTPException) as e:
        pu.unit("24/10/05/999")
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        pu.unit("Ikeja")
    assert e.value.status_code == 400


def test_v1_endpoints_serve_areas_units_and_one_unit(db, monkeypatch):
    import api.index as api
    from src import public_api

    async def ok(request, response, count=True):
        return {"plan": "pro"}
    monkeypatch.setattr(public_api, "authorize", ok)
    client = TestClient(api.app)
    r = client.get("/v1/elections/areas")
    assert r.status_code == 200 and r.json()["level"] == "states" and r.json()["count"] == 2
    assert client.get("/v1/elections/areas", params={"state": "Lagos", "lga": "10"}).json()["level"] == "wards"
    r = client.get("/v1/elections/polling-units", params={"state": "24", "lga": "10", "ward": "05"})
    assert r.json()["units"][0]["code"] == "24/10/05/012"
    assert client.get("/v1/elections/polling-units/24/10/05/012").json()["name"] == "OJODU GRAMMAR SCHOOL I"
    assert client.get("/v1/elections/polling-units").status_code == 400
    assert "elections/polling-units" in " ".join(client.get("/v1").json()["endpoints"])
