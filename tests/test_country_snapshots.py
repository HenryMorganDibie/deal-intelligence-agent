"""Tests for historical country risk reconstruction."""
from src.data import africa_countries as ac
from src.engines import country_risk as cr


def test_historical_scores_are_ordered_and_use_only_prior_observations():
    snap = {
        "retrieved": "2026-10-14", "labels": {"FP.CPI.TOTL.ZG": "Inflation"},
        "series": {
            "FP.CPI.TOTL.ZG": {"NGA": {"2018": 10.0, "2020": 20.0, "2022": 30.0}},
            "NY.GDP.MKTP.KD.ZG": {"NGA": {"2019": 2.0, "2021": 4.0}},
        },
    }
    result = cr.historical_scores(ac.get("NG"), snap, since=2018, until=2022)
    assert [row["year"] for row in result["rows"]] == [2018, 2019, 2020, 2021, 2022]
    # A partial component set must not be presented as a complete composite score.
    assert result["rows"][0]["score"] is None
    assert result["rows"][0]["tier"] is None
    assert result["rows"][0]["coverage"] < 1.0
    assert result["rows"][0]["input_years"]["FP.CPI.TOTL.ZG"] == 2018
    assert result["rows"][1]["input_years"]["FP.CPI.TOTL.ZG"] == 2018
    assert result["rows"][2]["input_years"]["FP.CPI.TOTL.ZG"] == 2020
    assert "not a point-in-time archived vintage" in result["method"]
    assert "not an official data-quality or confidence metric" in result["method"]
    assert "all seven components are available" in result["method"]


def test_historical_scores_include_source_and_country_identity():
    snap = {"retrieved":"2026-10-14","labels":{},
            "series":{"FP.CPI.TOTL.ZG":{"KEN":{"2019":5.0,"2020":6.0}}}}
    result = cr.historical_scores(ac.get("KE"), snap, since=2020, until=2020)
    assert result["iso2"] == "KE"
    assert "World Bank" in result["source"]
    assert result["source_url"].startswith("https://api.worldbank.org/")
    assert len(result["rows"]) == 1


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _PaginatedClient:
    def __init__(self):
        self.pages_requested = []

    def get(self, url, params):
        page = params["page"]
        self.pages_requested.append(page)
        rows = [
            {"countryiso3code": "NGA", "date": "1960", "value": 1.0},
            {"countryiso3code": "KEN", "date": "1961", "value": 2.0},
        ] if page == 1 else [
            {"countryiso3code": "NGA", "date": "2025", "value": 3.0},
        ]
        return _FakeResponse([{"pages": 2}, rows])


def test_world_bank_indicator_fetch_reads_every_page():
    client = _PaginatedClient()
    result = cr._fetch_indicator(client, "FP.CPI.TOTL.ZG", None, 1960, 2025)
    assert client.pages_requested == [1, 2]
    assert result["NGA"] == {"1960": 1.0, "2025": 3.0}
    assert result["KEN"] == {"1961": 2.0}


def test_committed_country_indicator_snapshot_reaches_earliest_source_window():
    snap = cr.load_snapshot()
    assert snap["since"] == 1960
    assert len(snap["series"]) == 13
    nigeria_fx = snap["series"]["PA.NUS.FCRF"]["NGA"]
    assert min(int(year) for year in nigeria_fx) == 1960
    assert max(int(year) for year in nigeria_fx) >= 2024


def test_historical_composite_is_published_only_with_all_weighted_components():
    snap = {
        "retrieved": "2026-10-14",
        "labels": {},
        "series": {
            "GOV_WGI_PV.EST": {"NGA": {"2019": 0.1, "2020": 0.2}},
            "GOV_WGI_GE.EST": {"NGA": {"2020": 0.1}},
            "GOV_WGI_RQ.EST": {"NGA": {"2020": 0.1}},
            "GOV_WGI_RL.EST": {"NGA": {"2020": 0.1}},
            "GOV_WGI_CC.EST": {"NGA": {"2020": 0.1}},
            "GOV_WGI_VA.EST": {"NGA": {"2020": 0.1}},
            "FP.CPI.TOTL.ZG": {"NGA": {"2020": 10.0}},
            "NY.GDP.MKTP.KD.ZG": {"NGA": {"2020": 3.0}},
            "PA.NUS.FCRF": {"NGA": {"2019": 300.0, "2020": 330.0}},
            "FI.RES.TOTL.MO": {"NGA": {"2020": 4.0}},
            "BN.CAB.XOKA.GD.ZS": {"NGA": {"2020": -2.0}},
            "DT.DOD.DECT.GN.ZS": {"NGA": {"2020": 35.0}},
        },
    }
    result = cr.historical_scores(ac.get("NG"), snap, since=2020, until=2020)
    row = result["rows"][0]
    assert row["coverage"] == 1.0
    assert row["score"] is not None
    assert row["tier"] is not None
