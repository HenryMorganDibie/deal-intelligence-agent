"""Headlines where a deal verb sits inside ordinary prose: advice, opinion and lifestyle stories are not deals."""
import pytest

from src.engines import deals


@pytest.mark.parametrize("headline", [
    "Don’t Sell Your Votes, Archbishop Kaigama Admonishes Nigerians",
    "Bwala to David Mark-led exco: You took over ADC leadership undemocratically and hoped all is well",
    "Malkiat Singh Makes Sh83 Million As Longhorn Publishers Buy His Books",
    "Take Advantage of Bank Windhoek’s Vehicle Financing Options to Buy Your Dream Car",
    "We acquired LCC in 2014, only requested loan conversion, Lagos govt clarifies",
    "'Davido Leading In Car Competition With Wizkid, As He Acquires Porsche'",
    "2025 Guide: How Diasporas and Foreigners Can Legally Buy Property in Ethiopia",
    "Competing for Africa’s Resources: How the US and China Invest in Critical Minerals",
])
def test_prose_is_not_extracted_as_a_deal(headline):
    assert deals.extract_deal(headline, published="2026-11-09") is None


@pytest.mark.parametrize("headline, party", [
    ("MyBucks sells stake in Opportunity Bank to Mauritius investor", "MyBucks"),
    ("Helios sells stake in Vivo Energy to Vitol", "Helios"),
    ("US Based Fintech Umba Acquires Major Stake in Kenyan Microfinance", "US Based Fintech Umba"),
])
def test_real_names_that_look_like_pronouns_are_kept(headline, party):
    deal = deals.extract_deal(headline, published="2026-11-09")
    assert deal and party in (deal.get("seller"), deal.get("buyer"))


def test_stored_prose_records_are_excluded():
    fix = deals.reclassify({"deal_type": "exit", "target": "Your Votes", "seller": "Don’t",
                            "headline": "Don’t Sell Your Votes, Archbishop Kaigama Admonishes Nigerians"})
    assert fix and "excluded" in fix


def test_a_question_word_is_dropped_from_a_real_party():
    assert deals.reclassify({"deal_type": "exit", "target": "Chivita", "seller": "Why TGI", "buyer": "Coca Cola",
                             "headline": "Nigeria’s Biggest Beverage Acquisition: Why TGI Sold Chivita To Coca Cola"}) \
        == {"seller": "TGI"}


def test_us_is_the_united_states_not_a_pronoun():
    assert deals.reclassify({"deal_type": "equity_funding", "target": "Cassava",
                             "investors": ["US International Development Finance Corporation", "Finnfund"],
                             "headline": "Strive Masiyiwa's Cassava secures $90m equity investment"}) is None


@pytest.mark.parametrize("name", ["85%", "Botswana Still", "Botswana Plans to Double De Beers Stake",
                                  "Botswana to double De Beers stake to 30%", "Angola Makes Bold Move", "Makes Move",
                                  "Botswana Contemplating", "Gulf Help", "UAE and Oman Support", "Line", "Reduced",
                                  "More Diamonds Without De Beers"])
def test_headline_fragments_are_not_parties(name):
    assert deals._not_a_party(name)


@pytest.mark.parametrize("name", ["Anglo American", "Botswana Diamonds", "Global Diamond Consortium", "Moves Africa",
                                  "Help Lesotho", "Majority Holdings", "First Line Ventures", "Eyes on Africa Capital"])
def test_real_names_that_look_like_fragments_stay(name):
    assert not deals._not_a_party(name)


def test_full_control_of_a_company_is_the_company():
    assert deals.reclassify({"deal_type": "acquisition", "target": "Full Control of De Beers", "buyer": "Anglo American",
                             "headline": "x"}) == {"target": "De Beers"}


@pytest.mark.parametrize("raw, clean", [
    ("Kenyan Re-Commerce Startup Badili", "Badili"), ("SA Fintech Yoco", "Yoco"), ("Bedding Maker Dolidol", "Dolidol"),
    ("PAYG Solar Company PEG Africa", "PEG Africa"), ("Arthur Eze’s Oranto Petroleum", "Oranto Petroleum"),
    ("Kenya's Credit Bank", "Credit Bank"), ("Stake In First Mutual Holdings", "First Mutual Holdings"),
    ("Africell Uganda Assets", "Africell Uganda"), ("Acquire Avanz Capital", "Avanz Capital"),
    ("Helios Sports and Entertainment Group Reportedly", "Helios Sports and Entertainment Group"),
    ("Last Tranche of Vodacom Shares", "Vodacom"), ("Pollman's Tours and Safaris", "Pollman's Tours and Safaris"),
    ("Guarantee Company Limited", "Guarantee Company Limited"), ("Zurich Insurance Company South Africa", "Zurich Insurance Company South Africa"),
])
def test_company_names_are_cleaned(raw, clean):
    assert deals.clean_company_name(raw) == clean


@pytest.mark.parametrize("name", ["Egypt", "Fund", "Shares", "Operations", "Arua Airport Upgrade Project",
                                  "Infantino, credits FIFA investment for World Cup breakthrough", "gold miner",
                                  "Kenyan water and recycling company", "Next Billion Edtech Prize", "Nigerian Bank",
                                  "Shallow Water Oil and Gas Fields", "South African Assets"])
def test_non_companies_are_rejected(name):
    assert not deals.is_company_name(deals.clean_company_name(name))


@pytest.mark.parametrize("name", ["First Bank", "Credit Bank", "Apollo Agriculture", "Balwin Properties", "City Lodge",
                                  "Malawi Telecom", "Uganda Airlines", "Coris Investment Group", "TIB Development Bank",
                                  "European Investment Bank", "Dangote Refinery", "iKhokha", "icolo.io", "Carbon Credits"])
def test_real_companies_pass(name):
    assert deals.is_company_name(deals.clean_company_name(name))


def test_a_deal_whose_target_names_no_company_is_excluded():
    assert "excluded" in deals.reclassify({"deal_type": "equity_funding", "target": "Arua Airport Upgrade Project",
                                           "headline": "AfDB backs Arua Airport Upgrade Project"})
    assert deals.reclassify({"deal_type": "equity_funding", "target": "SA Fintech Yoco",
                             "headline": "SA Fintech Yoco Snags $100m"}).get("target") == "Yoco"


@pytest.mark.parametrize("raw, expected", [
    ("25pc", None), ("Land", None), ("100MW", None), ("Shs17.8bn", None), ("OPL257", None), ("Ogun State", None),
    ("Lake Malawi", None), ("Australian", None), ("Chris Kirubi", None), ("Madonna", None), ("Fiscal Year", None),
    ("First Green Bond", None), ("Camerounais Alain Nkontchou", None),
    ("60pc of UUNET Kenya", "UUNET Kenya"), ("Zambian Neobank Lupiya", "Lupiya"), ("Le Consortium Enko Capital", "Enko Capital"),
    ("Quickmart IPO", "Quickmart"), ("Music Streaming Giant Deezer", "Deezer"), ("Kenya-based Charm Industries", "Charm Industries"),
    ("Huawei Helps Telecom Egypt", "Telecom Egypt"), ("Troubled Precision Air Amid Mounting Losses", "Precision Air"),
    ("Lake Harvest", "Lake Harvest"), ("Pioneer Foods", "Pioneer Foods"), ("4G Capital", "4G Capital"), ("54gene", "54gene"),
    ("African Mobile Games Publisher Carry1st", "Carry1st"), ("Iconic Cape Grace Hotel", "Cape Grace Hotel"),
])
def test_company_resolution_after_the_full_review(raw, expected):
    name, reason = deals.resolve_company(raw)
    assert (name if reason is None else None) == expected
