from src import hosted_market as hm
from src.engines import deals as d

HEADLINE = "Afreximbank Grants $30M NEXIM Facility To Boost Nigeria’s Non-oil Exports"


def test_the_name_on_a_facility_is_the_borrower_not_its_purpose():
    deal = d.extract_deal(HEADLINE, published="2026-11-11")
    assert deal["target"] == "NEXIM" and deal["buyer"] == "Afreximbank"
    stored = {"target": "Non-oil Exports", "deal_type": "debt_financing", "sector": "oil_gas", "buyer": "Afreximbank",
              "investors": ["Afreximbank"], "headline": HEADLINE, "announced": "2026-11-11"}
    assert d.reclassify(stored)["target"] == "NEXIM"


def test_non_oil_is_not_oil_and_gas():
    assert d.classify_sector("Boost to non-oil exports") != "oil_gas"
    assert d.classify_sector("Seplat buys oil blocks") == "oil_gas"


def test_instrument_words_are_not_a_borrower():
    stored = {"target": "Support SMEs", "deal_type": "debt_financing", "buyer": "Afreximbank",
              "headline": "Afreximbank Approves $500M Trade Facility To Support SMEs", "announced": "2026-11-11"}
    assert (d.beneficiary_target_fix(stored) or {}).get("target") != "Trade"


def test_abbreviations_made_from_word_starts():
    assert d.abbreviates("ShafDB", "Shelter Afrique Development Bank")
    assert d.abbreviates("CFM", "Climate Fund Managers")
    assert not d.abbreviates("Shelter", "Shelter Afrique")
    assert not d.abbreviates("Ecobank", "Equity Group")


def test_one_bond_reported_under_a_name_and_its_abbreviation_is_one_deal():
    base = {"amount": 6e10, "currency": "XOF", "amount_usd": 103105454.0, "announced": "2026-11-10", "stage": "completed",
            "countries": [], "investors": [], "buyer": None, "seller": None}
    a = {**base, "id": "226eed7e2e2101b4", "target": "ShafDB", "deal_type": "equity_funding",
         "headline": "ShafDB secures FCFA 60bn for affordable housing", "sources": [{"url": "a"}]}
    b = {**base, "id": "1a3dc266731d79d1", "target": "Shelter Afrique Development Bank", "deal_type": "debt_financing",
         "headline": "UEMOA | Logement : la Shelter Afrique Development Bank lève 60 milliards de FCFA en obligations durables",
         "sources": [{"url": "b"}]}
    out: dict = {}
    hm._merge_stored_duplicates([a, b], out)
    kept = next(v for v in out.values() if not v.get("merged_into"))
    assert kept["target"] == "Shelter Afrique Development Bank" and kept["deal_type"] == "debt_financing"
    assert len(kept["sources"]) == 2 and sum(1 for v in out.values() if v.get("merged_into")) == 1


def test_an_aircraft_purchase_is_not_a_company_acquisition():
    rec = {"target": "Cessna", "deal_type": "acquisition", "buyer": "Uganda Aviation Academy",
           "headline": "Uganda Aviation Academy Acquires Cessna 421 In Fleet Expansion Drive"}
    assert "aircraft" in d.reclassify(rec)["excluded"]
    assert d.extract_deal("Airtel Africa acquires Telkom Kenya", published="2026-11-10")["target"] == "Telkom Kenya"


def test_a_nationality_and_a_scene_is_not_a_company_but_brand_names_are():
    assert d.not_a_deal("Celebrity Boxing Takes Over Nigerian Showbiz", "Nigerian Showbiz", "acquisition")
    assert not d.not_a_deal("Tencent buys Boomplay Music", "Boomplay Music", "acquisition")
    assert not d.not_a_deal("MultiChoice acquires Kwese Sports", "Kwese Sports", "acquisition")


def test_building_a_mill_is_capital_spending_not_an_investment_in_a_company():
    assert d.extract_deal("Olam Agri invests $70m in Delta feed mill", published="2026-11-10") is None


def _deal(headline, publisher="Some Africa Desk", **kw):
    return {"headline": headline, "sources": [{"title": headline, "publisher": publisher, "url": "https://x"}], **kw}


def test_foreign_deals_are_recognised_and_african_ones_kept():
    assert d.foreign_only(_deal("Proparco backs green finance in Türkiye with €75m loan"))
    assert d.foreign_only(_deal("Japan’s Umios acquires High Liner Foods, expanding its footprint into Canada"))
    assert d.foreign_only(_deal("Agilent completes acquisition of Proscia By Investing.com", "Investing.com South Africa"))
    for keep in ("SOGUIPAL secures US$5.6M loan to expand yogurt facility",
                 "Family Bank Secures KSh 2.6B from British DFI to Boost MSME Trade Finance",
                 "Amalgamated Brands launches US$20M IPO on Victoria Falls Stock Exchange",
                 "China’s CCECC to invest $1.4 billion in Tanzania-Zambia railway",
                 "Emerald Group adquire Forbes Portugal e lança Forbes África Lusófona",
                 "US private equity firm Advent to acquire Vermeg in strategic deal"):
        assert not d.foreign_only(_deal(keep)), keep


def test_a_foreign_deal_by_a_known_african_company_stays():
    yellow_card_round = _deal("Nigeria's Yellow Card raises $33m", id="a", target="Yellow Card", deal_type="equity_funding",
                              announced="2026-01-01")
    gomoney = _deal("Yellow Card Acquires Brazil’s GoMoney to Secure Direct LatAm Foothold", id="b", target="GoMoney",
                    buyer="Yellow Card", deal_type="acquisition", announced="2026-10-01")
    turkiye = _deal("Proparco backs green finance in Türkiye with €75m loan", id="c", target="Türkiye green finance",
                    buyer="Proparco", deal_type="debt_financing", announced="2026-10-01")
    out = hm._reclassify_stored({x["id"]: x for x in (yellow_card_round, gomoney, turkiye)}, {})
    assert "b" not in out or not out["b"].get("excluded")
    assert out["c"]["excluded"].startswith("reclassified: no African")


def test_a_facility_is_not_a_fund_close_and_the_borrower_is_named():
    r = d.extract_deal("Afreximbank commits $75 million finance facility to DBN SMEs funding", published="2026-11-11")
    assert (r["deal_type"], r["target"], r["buyer"]) == ("debt_financing", "DBN", "Afreximbank")
    fund = {"id": "z", "target": "Helios Fund V", "deal_type": "fund_raise", "investors": ["IFC"],
            "headline": "Helios closes Fund V at $750m with IFC facility", "announced": "2026-11-11"}
    assert d.reclassify(fund) is None


def test_who_a_facility_is_for_does_not_make_a_second_deal():
    a = {"id": "2c5b", "target": "Nigerian Exporters", "deal_type": "debt_financing", "buyer": "Afreximbank",
         "investors": ["Afreximbank"], "amount_usd": 30e6, "announced": "2026-11-11", "country": "NG", "countries": ["NG"],
         "headline": "Afreximbank Backs Nigerian Exporters with $30m Facility to Deepen AfCFTA Trade", "sources": [{"url": "a"}]}
    b = {"id": "8b7b", "target": "NEXIM", "deal_type": "debt_financing", "buyer": "Afreximbank", "investors": ["Afreximbank"],
         "amount_usd": 30e6, "announced": "2026-11-07", "country": "NG", "countries": ["NG"],
         "headline": "NEXIM secures $30m Afreximbank facility to boost SME exports", "sources": [{"url": "b"}, {"url": "c"}]}
    assert d.is_beneficiary("Nigerian Exporters") and not d.is_beneficiary("NEXIM")
    out: dict = {}
    hm._merge_stored_duplicates([a, b], out)
    assert out["2c5b"]["merged_into"] == "8b7b" and out["8b7b"]["target"] == "NEXIM"
    # A different lender or a different figure stays a separate deal.
    assert not d.strong_same_report({**a, "buyer": "AfDB", "investors": ["AfDB"]}, b)
    assert not d.strong_same_report({**a, "amount_usd": 45e6}, b)
