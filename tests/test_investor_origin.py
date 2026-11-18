from src.engines import investor_origin as io


def deal(headline, deal_type="equity_funding", buyer=None, investors=(), target="Acme"):
    return {"headline": headline, "deal_type": deal_type, "buyer": buyer, "investors": list(investors), "target": target}


def test_country_from_code_or_name():
    assert io.country_code("us") == "US" and io.country_code("United Kingdom") == "GB"
    assert io.country_code("Nigeria") == "NG" and io.country_code("Atlantis") is None
    assert io.country_name("AE") == "United Arab Emirates"


def test_registry_head_office_places_a_national_development_bank():
    d = deal("BII backs Côte d'Ivoire SMEs with €30m NSIA Banque loan", "debt_financing", buyer="British International Investment")
    assert "GB" in io.deal_investor_countries(d)


def test_international_institutions_count_for_no_country():
    d = deal("IFC invests $29m in SUNU Group", buyer="International Finance Corporation")
    assert io.deal_investor_countries(d) == set()
    afdb = deal("AfDB lends $60m to TADB", "debt_financing", buyer="African Development Bank")
    assert io.deal_investor_countries(afdb) == set()


def test_headline_descriptor_places_an_unregistered_investor():
    d = deal("Egyptian fintech Paymob raises $35m led by UAE's Kingsway Capital", investors=["Kingsway Capital"], target="Paymob")
    assert io.deal_investor_countries(d) == {"AE"}
    d = deal("Japanese trading house Toyota Tsusho acquires stake in Kenyan solar firm", "acquisition", buyer="Toyota Tsusho")
    assert io.deal_investor_countries(d) == {"JP"}


def test_the_target_s_nationality_is_not_the_investor_s():
    d = deal("US-based Zipline raises $50m from Kenyan investors", investors=["Kenyan investors"], target="Zipline")
    assert "US" not in io.deal_investor_countries(d)


def test_filter_keeps_only_deals_with_an_investor_from_that_country():
    a = deal("BII backs Acme with $10m", buyer="British International Investment")
    b = deal("IFC backs Beta with $10m", buyer="International Finance Corporation", target="Beta")
    assert io.from_country([a, b], "GB") == [a]


def test_market_brief_on_investors_from_one_country(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from fastapi.testclient import TestClient
    import api.index as api
    from src import hosted_market as hm, plans
    from datetime import date

    today = date.today().isoformat()
    bii = {"id": "d1", "deal_type": "debt_financing", "buyer": "British International Investment", "investors": [],
           "target": "NSIA Banque", "country": "CI", "headline": "BII backs NSIA Banque with $30m loan", "announced": today}
    ifc = {"id": "d2", "deal_type": "equity_funding", "buyer": "International Finance Corporation", "investors": [],
           "target": "SUNU", "country": "CI", "headline": "IFC invests in SUNU", "announced": today}
    monkeypatch.setattr(api, "_configured", lambda: True)
    monkeypatch.setattr(plans, "use_ai", AsyncMock())
    monkeypatch.setattr(hm, "deals", lambda: [bii, ifc])
    monkeypatch.setattr(hm, "events", lambda: [])
    monkeypatch.setattr(hm, "_reserve", AsyncMock(return_value="run"))
    monkeypatch.setattr(hm, "_finish", AsyncMock())
    monkeypatch.setattr("src.engines.research.research", MagicMock(return_value={"answer": "", "evidence": [], "mode": "test"}))
    saved = MagicMock(status_code=200)
    saved.json.return_value = "brief-1"
    rpc = AsyncMock(return_value=saved)
    monkeypatch.setattr(api, "_rpc", rpc)
    client = TestClient(api.app)

    assert client.post("/api/market-briefs", json={"lookback_days": 30, "investor_country": "Atlantis"}).status_code == 422
    r = client.post("/api/market-briefs", json={"lookback_days": 30, "investor_country": "GB"})
    assert r.status_code == 200 and r.json()["transaction_count"] == 1
    report = next(c.args[2]["p_report"] for c in rpc.call_args_list if c.args[1] == "save_market_brief")
    assert report["title"].endswith("investors from United Kingdom")
    assert [t["id"] for t in report["key_transactions"]] == ["d1"]
    assert report["investor_coverage"] == {"period_records": 2, "investor_country_known": 1}
    assert "identified for 1 of 2 records" in report["coverage_note"]
