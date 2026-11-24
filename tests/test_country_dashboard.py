"""Country pages beyond deal history: markets, rates, investor origin, benchmarks, elections, IMF outlook, compare,
and country alerts."""
from datetime import date
from unittest.mock import MagicMock

from src.engines import country_dashboard as cd
from src.engines import watch

TODAY = date(2026, 11, 24)


def _deal(i, country, amount=None, sector="fintech", day="2026-10-01", investors=None, headline="X raises"):
    return {"id": f"d{i}", "announced": day, "country": country, "countries": [country], "amount_usd": amount,
            "sector": sector, "investors": investors or [], "headline": headline, "deal_type": "equity_funding"}


def test_market_block_picks_the_countrys_exchange_and_largest_companies():
    overview = {"exchanges": [{"exchange": "ngx", "country": "NG", "name": "Nigerian Exchange", "ytd_usd": 0.64, "mcap_usd": 1.17e11},
                              {"exchange": "jse", "country": "ZA", "mcap_usd": 5e11}]}
    rows = [{"symbol": "MTNN", "name": "MTN Nigeria", "mcap_usd": 9e9}]
    m = cd.market_block("NG", overview, rows)
    assert m["exchanges"][0]["exchange"] == "ngx" and m["largest"][0]["symbol"] == "MTNN" and m["mcap_usd"] == 1.17e11
    assert cd.market_block("TD", overview, []) is None


def test_rates_block_dates_every_figure():
    r = cd.rates_block("KE", [{"country": "KE", "rate": 9.25, "date": "2026-10-08", "source": "CBK"}],
                       [{"country": "KE", "source": "CBK", "rows": [{"tenor_days": 91, "rate": 8.1, "auction_date": "2026-11-20"}]}],
                       [{"country": "KE", "pair": "USDT/KES", "rate": 131, "official_per_usd": 129, "premium": 0.0155}])
    assert r["policy_rate"]["rate"] == 9.25 and r["tbills"]["date"] == "2026-11-20" and r["stablecoin"]["premium"] == 0.0155
    assert cd.rates_block("TD", [], [], []) == {"policy_rate": None, "tbills": None, "stablecoin": None}


def test_investor_origin_counts_known_homes_and_marks_local(monkeypatch):
    from src.engines import investor_origin
    homes = {"d1": {"US"}, "d2": {"US", "KE"}, "d3": set()}
    monkeypatch.setattr(investor_origin, "deal_investor_countries", lambda d: homes.get(d["id"], set()))
    out = cd.investor_origin("KE", [_deal(1, "KE"), _deal(2, "KE"), _deal(3, "KE"), _deal(4, "NG")], TODAY)
    assert out["deals"] == 3 and out["deals_with_known_origin"] == 2
    us = next(o for o in out["origins"] if o["country"] == "US")
    assert us["deals"] == 2 and not us["local"] and next(o for o in out["origins"] if o["country"] == "KE")["local"]
    assert out["foreign_share"] == round(2 / 3, 4)


def test_benchmarks_rank_and_compare_with_africa():
    ds = [_deal(1, "KE", 1e6), _deal(2, "KE", 3e6, "energy"), _deal(3, "NG", 10e6), _deal(4, "NG"), _deal(5, "NG"),
          _deal(6, "KE", 2e6, day="2024-01-01")]
    b = cd.benchmarks("KE", ds, TODAY)
    assert b["deals"] == 2 and b["rank"] == 2 and b["countries_ranked"] == 2
    assert b["median_size_usd"] == 2e6 and b["africa_median_size_usd"] == 3e6
    assert b["disclosed_share"] == 1.0 and b["africa_disclosed_share"] == 0.6
    assert {s["sector"] for s in b["sectors"]} == {"fintech", "energy"}


def test_elections_include_nigeria_and_monitored_profiles():
    ng = cd.elections("NG", TODAY)
    assert ng and ng[0]["page"] == "/elections/nigeria" and ng[0]["dates"][0]["date"] == "2027-01-16"
    gm = cd.elections("GM", TODAY)
    assert gm and gm[0]["dates"][0] == {"date": "2026-12-05", "label": "Presidential election", "past": False}
    assert cd.elections("BW", TODAY) == []


def test_imf_outlook_reads_three_years_and_marks_projections():
    cd._imf_cache.clear()
    client = MagicMock()

    def get(url):
        indicator = url.rsplit("/", 1)[-1]
        series = {"NGA": {"2025": 3.4, "2026": 3.6, "2027": 3.8}} if indicator != "BCA_NGDPD" else {}
        return MagicMock(status_code=200, json=lambda: {"values": {indicator: series}})
    client.get.side_effect = get
    out = cd.imf_outlook("NGA", TODAY, client=client)
    assert out["years"] == ["2025", "2026", "2027"] and out["projected_from"] == "2026"
    assert [r["indicator"] for r in out["rows"]] == ["NGDP_RPCH", "PCPIPCH", "GGXWDG_NGDP"]
    assert out["rows"][0]["values"] == {"2025": 3.4, "2026": 3.6, "2027": 3.8}
    cd._imf_cache.clear()
    client.get.side_effect = None
    client.get.return_value = MagicMock(status_code=500, json=lambda: {})
    assert cd.imf_outlook("NGA", TODAY, client=client) is None


def test_country_alerts_fire_once_per_fact():
    wl = {"countries": ["ke"]}
    sig = {"KE": {"name": "Kenya", "risk": {"tier": "high", "previous_tier": "elevated", "date": "2026-11-24"},
                  "policy": {"rate": 9.0, "date": "2026-11-20", "source": "CBK", "recent": True},
                  "fx": {"currency": "KES", "change": 0.061, "date": "2026-11-24"},
                  "elections": [{"label": "General election", "date": "2026-11-29", "page": None}]}}
    alerts = watch.country_signals(wl, sig, "2026-11-24")
    titles = [a["title"] for a in alerts]
    assert "Kenya: country risk moved from elevated to high" in titles
    assert any("policy rate 9%" in t for t in titles) and any("weakened 6.1%" in t for t in titles)
    assert any("General election in 5 days" in t for t in titles)
    assert all(a["kind"] == "country" and a["facts_line"].startswith("Country signal") for a in alerts)
    assert len({watch.alert_fingerprint(a) for a in alerts}) == len(alerts)
    quiet = {"KE": {"risk": {"tier": "high", "previous_tier": "high"}, "policy": {"rate": 9.0, "date": "2026-09-01", "recent": False},
                    "fx": {"change": 0.01}, "elections": [{"label": "x", "date": "2027-08-10"}]}}
    assert watch.country_signals(wl, quiet, "2026-11-24") == []
    assert watch.country_signals({"countries": []}, sig, "2026-11-24") == []


def _stub(monkeypatch):
    import src.hosted_market as hm
    overview = {"exchanges": [{"exchange": "ngx", "country": "NG", "ytd_usd": 0.6, "mcap_usd": 1e11}]}

    async def parts(codes):
        return {}, [overview], [{"country": "NG", "rate": 27.0, "date": "2026-11-20"}], [], []

    async def homes(fresh=False):
        return []
    monkeypatch.setattr(hm, "_country_parts", parts)
    monkeypatch.setattr(hm, "investor_homes", homes)
    monkeypatch.setattr(hm, "deals", lambda: [_deal(1, "NG", 5e6), _deal(2, "KE", 1e6)])
    monkeypatch.setattr(cd, "imf_outlook", lambda iso3, today, client=None: None)
    monkeypatch.setattr(hm.country_risk, "assess", lambda c, **kw: {"score": 60, "tier": "elevated"})
    monkeypatch.setattr(hm.market_risk, "currency_risk", lambda cur: {"last_year_depreciation_pct": 12.0})


def test_dashboard_and_compare_endpoints(monkeypatch):
    import api.index as api
    from fastapi.testclient import TestClient
    _stub(monkeypatch)
    client = TestClient(api.app)
    dash = client.get("/api/countries/nigeria/dashboard").json()
    assert dash["market"]["exchanges"][0]["exchange"] == "ngx" and dash["rates"]["policy_rate"]["rate"] == 27.0
    assert dash["benchmarks"]["deals"] == 1 and dash["elections"][0]["key"] == "ng-2027"
    cmp = client.get("/api/countries/compare?codes=NG,KE").json()["countries"]
    assert [r["iso2"] for r in cmp] == ["NG", "KE"] and cmp[0]["policy_rate"] == 27.0 and cmp[0]["risk_tier"] == "elevated"
    assert cmp[1]["currency_depreciation_last_year_pct"] == 12.0
    assert client.get("/api/countries/compare?codes=NG").status_code == 400
