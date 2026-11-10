import pytest

from src.engines.event_filters import is_public_institution, named_company


@pytest.mark.parametrize("headline,name", [
    ("Yewande Olagbende Joins Solad Power Group Board of Directors", "Solad Power Group"),
    ("Sudan Revokes Abu Dhabi Islamic Bank licence", "Abu Dhabi Islamic Bank"),
    ("Chidi Okafor Leaves Lekoil Energy After Nine Years", "Lekoil Energy"),
    ("Regulator Fines Group", None),                     # nothing left but a suffix
])
def test_names_stop_at_the_last_headline_verb(headline, name):
    assert named_company(headline) == name


@pytest.mark.parametrize("name", ["World Bank", "Word Bank", "Wrld Bank", "International Monetary Fund",
                                  "African Development Bank", "Afreximbank", "Central Bank of Nigeria",
                                  "South African Reserve Bank", "Reserve Bank of Zimbabwe", "Bank of Ghana"])
def test_public_institutions_are_recognised_even_misspelt(name):
    assert is_public_institution(name)


@pytest.mark.parametrize("name", ["Zenith Bank", "Wema Bank", "Standard Bank", "Stanbic Bank", "Equity Bank",
                                  "Bank of Africa", "Bank of Kigali", "Access Bank", "Solad Power Group",
                                  "Victoria Falls Hotel", None, ""])
def test_companies_are_not_mistaken_for_institutions(name):
    assert not is_public_institution(name)


from src.engines import deals as deals_mod  # noqa: E402


@pytest.mark.parametrize("headline,buyer", [
    ("Nigerian Fintech Moniepoint Gets Green Light to Acquire Kenyan Microfinance Bank", "Moniepoint"),
    ("BGI Gets Green Light to Finalize Meta Abo Brewery Acquisition", "BGI"),
    ("Batian Gets Greenlight To Acquire Iconic Riverside Towers In Nairobi", "Batian"),
])
def test_an_approval_phrase_is_never_the_buyer(headline, buyer):
    fix = deals_mod.reclassify({"deal_type": "acquisition", "buyer": "Green Light", "headline": headline, "target": "X"})
    assert fix == {"buyer": buyer}


def test_new_green_light_headlines_name_the_real_buyer():
    d = deals_mod.extract_deal("Nigerian Fintech Moniepoint Gets Green Light to Acquire Kenyan Microfinance Bank")
    assert d["buyer"] == "Moniepoint"


def test_compound_firm_names_are_kept_whole():
    assert deals_mod._split_names("Plug and Play, PRC Ventures ICAV and Azur Innovation Fund") == \
        ["Plug and Play", "PRC Ventures ICAV", "Azur Innovation Fund"]
    assert deals_mod.reclassify({"deal_type": "equity_funding", "investors": ["Magic Fund", "Plug", "Play"],
                                 "headline": "Bypa-ss raises $1m pre-seed", "target": "Bypa-ss"}) == \
        {"investors": ["Magic Fund", "Plug and Play"]}
