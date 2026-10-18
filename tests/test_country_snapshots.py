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
    assert result["rows"][0]["score"] is not None
    assert result["rows"][0]["input_years"]["FP.CPI.TOTL.ZG"] == 2018
    assert result["rows"][1]["input_years"]["FP.CPI.TOTL.ZG"] == 2018
    assert result["rows"][2]["input_years"]["FP.CPI.TOTL.ZG"] == 2020
    assert "not a point-in-time archived vintage" in result["method"]


def test_historical_scores_include_source_and_country_identity():
    snap = {"retrieved":"2026-10-14","labels":{},
            "series":{"FP.CPI.TOTL.ZG":{"KEN":{"2019":5.0,"2020":6.0}}}}
    result = cr.historical_scores(ac.get("KE"), snap, since=2020, until=2020)
    assert result["iso2"] == "KE"
    assert "World Bank" in result["source"]
    assert result["source_url"].startswith("https://api.worldbank.org/")
    assert len(result["rows"]) == 1
