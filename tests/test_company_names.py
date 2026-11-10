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


def test_an_approval_word_is_not_part_of_the_buyer():
    fix = deals_mod.reclassify({"deal_type": "acquisition", "buyer": "Batian Fund Cleared", "target": "Riverside Towers",
                                "headline": "GenAfrica-Backed Batian Fund Cleared to Buy Riverside Towers in Nairobi"})
    assert fix == {"buyer": "Batian Fund"}


@pytest.mark.parametrize("headline,target,expected", [
    ("YC-backed fintech Numida raises $12.3M led by Serena Ventures to extend loans to MSMEs beyond Uganda", "MSMEs",
     {"target": "Numida"}),
    ("BII backs Côte d'Ivoire SMEs with €30m NSIA Banque loan", "Côte d'Ivoire SMEs", {"target": "NSIA Banque"}),
    ("BDEAC: BADEA Extends €30 Million Loan to Support Central African SMEs", "Support Central African SMEs",
     {"target": "BDEAC"}),
    ("AfDB Approves USD4m Partial Credit Guarantee to Support Tanzania Mortgage Refinance Company",
     "Support Tanzania Mortgage Refinance Company", {"target": "Tanzania Mortgage Refinance Company"}),
    ("Zambia: African Development Bank Approves $20 Million Trade Finance Guarantee to Boost SMEs", "Boost SMEs",
     {"excluded": "reclassified: a development programme for unnamed businesses, not a company transaction"}),
    ("Mauritania: African Development Bank grants $150 million loan to Boost mining sector", "Boost mining sector", None),
])
def test_a_group_of_beneficiaries_is_not_the_company(headline, target, expected):
    deal = {"deal_type": "debt_financing", "target": target, "headline": headline}
    assert deals_mod.beneficiary_target_fix(deal) == expected


def test_a_named_borrower_is_recovered_from_the_headline():
    deal = {"deal_type": "debt_financing", "target": "Boost Output",
            "headline": "Ogun: Afreximbank Grants Veenocks $81.9m Loan To Boost Output"}
    assert deals_mod.beneficiary_target_fix(deal) == {"target": "Veenocks"}


@pytest.mark.parametrize("headline,signal,corporate", [
    ("Word Bank backs infrastructure fund to help Kenya ease debt pressure", "credit_risk", False),
    ("World Bank approves $500m loan for Nigeria power sector", "credit_risk", False),
    ("Central Bank of Nigeria fines Zenith Bank N1bn", "regulatory_action", True),     # the bank fined is a company
    ("Access Bank posts record profit", "earnings_surprise", True),
])
def test_a_public_institution_acting_is_not_a_corporate_event(headline, signal, corporate):
    from src.engines.event_filters import is_corporate_event
    assert is_corporate_event(headline, signal) is corporate
