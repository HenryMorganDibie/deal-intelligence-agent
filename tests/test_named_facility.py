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
