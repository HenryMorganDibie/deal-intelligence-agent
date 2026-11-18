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


def test_companies_that_invest_are_placed_without_joining_the_investor_registry():
    from src.engines import investors
    d = deal("QatarEnergy acquires 25% stake in Namibia exploration block", "acquisition", buyer="QatarEnergy", target="PEL 82")
    assert io.deal_investor_countries(d) == {"QA"}
    assert investors.registry_entry("MTN Group") is None          # research still reads MTN as a company
    assert io.deal_investor_countries(deal("MTN Group invests in Ayoba", buyer="MTN Group", target="Ayoba")) == {"ZA"}


def test_descriptions_in_sentences_place_investors():
    assert io._described_countries("led by Lagos-based Future Africa", "Future Africa") == {"NG"}
    assert io._described_countries("Futureview, a Lagos-based asset manager, invested", "Futureview") == {"NG"}
    assert io._described_countries("San Francisco-based VC Hustle Fund joined", "Hustle Fund") == {"US"}
    assert io._described_countries("Oxano Capital, based in Amsterdam, led", "Oxano Capital") == {"NL"}
    assert io._described_countries("Acme raised money in Lagos", "Acme") == set()
    d = deal("Zrosk backs Acme", investors=["Zrosk"])
    d["investor_evidence"] = [{"name": "Zrosk", "sentence": "The round was led by Kigali-based VC Zrosk."}]
    assert io.deal_investor_countries(d) == {"RW"}


def test_stored_countries_win_and_none_means_no_single_country():
    try:
        io.use_homes([{"name_key": io.name_key("Madica"), "country": "KE"},
                      {"name_key": io.name_key("British International Investment"), "country": None}])
        assert io.deal_investor_countries(deal("Madica backs Acme", investors=["Madica"])) == {"KE"}
        bii = deal("BII backs Acme", buyer="British International Investment")
        assert io.deal_investor_countries(bii) == set()
        assert all(r["name"] != "Madica" for r in io.unplaced_investors([deal("Madica backs Beta", investors=["Madica"])]))
    finally:
        io.use_homes([])


def test_article_reader_records_only_unambiguous_descriptions():
    page = "<html><body><p>The round was led by Madica, a Nairobi-based investment programme. Acme will expand.</p></body></html>"
    mixed = "<p>Saviu, a Paris-based fund, led. Saviu, an Abidjan-based fund, joined.</p>"
    deals = [{**deal("Acme raises $2m", investors=["Madica"]), "sources": [{"url": "https://news.google.com/rss/articles/x"},
                                                                          {"url": "https://example.com/a"}]},
             {**deal("Beta raises $1m", investors=["Saviu"], target="Beta"), "sources": [{"url": "https://example.com/b"}]}]
    fetched, recorded = [], []
    pages = {"https://example.com/a": page, "https://example.com/b": mixed}
    result = io.read_articles(deals, lambda u: fetched.append(u) or pages.get(u), lambda *a: recorded.append(a))
    assert fetched == ["https://example.com/a", "https://example.com/b"]          # Google News links are never followed
    assert [(r[1], r[2]) for r in recorded] == [("Madica", "KE")]                  # conflicting Saviu left to the owner
    assert "Nairobi-based" in recorded[0][3] and result == {"fetched": 2, "recorded": 1}
