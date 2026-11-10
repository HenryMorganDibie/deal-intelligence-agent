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
