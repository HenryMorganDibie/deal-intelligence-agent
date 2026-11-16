import pytest

from src.engines import deals


@pytest.mark.parametrize("headline", [
    "Ugandan Govt Woos Dangote to Invest in Nation's Oil Refining, Fertiliser, Salt Production Sectors",
    "Government seeks strategic investors for national refinery project",
    "Investment opportunity: port expansion project seeking investors",
])
def test_proposed_investment_solicitations_are_not_transactions(headline):
    assert deals.is_investment_opportunity({"headline": headline})


@pytest.mark.parametrize("headline", [
    "Dangote completes acquisition of refinery assets",
    "Company raises $40m Series B funding",
    "Investor commits $100m to renewable energy project",
    "Fintech raises $20m as it seeks fresh capital for expansion",
    "Startup secures $5m seed round, seeks strategic investors for next phase",
    "Kenyan courts block investment in disputed port project",
])
def test_actual_transactions_are_not_misclassified_as_opportunities(headline):
    assert not deals.is_investment_opportunity({"headline": headline})


def test_explicit_opportunity_record_type_is_authoritative():
    assert deals.is_investment_opportunity({"record_type": "investment_opportunity", "headline": "Uganda refinery project"})
    assert not deals.is_investment_opportunity({"record_type": "transaction", "headline": "Company raises $5m"})
