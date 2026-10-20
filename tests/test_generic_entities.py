from scripts.corporate_of_week import is_generic_company, normalise
from src.data.africa_countries import countries_in_text
from src.engines.deals import _recover_target_from_title
from src.engines.investors import split_names


def test_corporate_week_rejects_generic_and_accented_entities():
    assert normalise("Président") == "president"
    for placeholder in ("Public", "First", "Président", "Million", "Billion", "Company", "Unknown", "Fund"):
        assert is_generic_company(placeholder)
    assert not is_generic_company("Kenya Airways")
    assert not is_generic_company("International Finance Corporation")

def test_investor_profiles_reject_placeholder_parties():
    for placeholder in ("Public", "First", "Million", "Président", "Company", "Unknown", "Fund"):
        assert split_names(placeholder) == []
    assert split_names("International Finance Corporation") == ["International Finance Corporation"]


def test_acquisition_target_recovers_after_country_descriptor():
    recovered = _recover_target_from_title(
        "Epiroc acquires South Africa-based parts provider Eventspec Proprietary Limited",
        "acquisition",
    )
    assert recovered == "Eventspec Proprietary Limited"


def test_country_resolver_handles_hyphenated_country_descriptors():
    found = {country.iso2 for country in countries_in_text(
        "Kenya’s Jiji acquires Ghanaian-based classifieds outlet Tonaton"
    )}
    assert found == {"KE", "GH"}
    founded = {country.iso2 for country in countries_in_text(
        "South Africa-founded Refiant AI raises $5 million"
    )}
    assert founded == {"ZA"}

def test_cross_border_acquisition_uses_target_country_and_clean_target_name():
    from src.engines.deals import extract_deal

    deal = extract_deal(
        "Kenya’s Jiji acquires Ghanaian-based classifieds outlet Tonaton",
        published="2026-01-01",
        publisher="Financial Fortune Media",
        url="https://example.com/story",
        africa_source=True,
    )
    assert deal is not None
    assert deal["target"] == "Tonaton"
    assert deal["country"] == "GH"
    assert set(deal["countries"]) == {"KE", "GH"}

def test_backing_snippet_uses_target_country_for_cross_border_investment():
    from src.engines.deals import extract_deal

    deal = extract_deal(
        "Kenya's Jiji backs Ghana-based Tonaton",
        snippet="The company completed a minority equity investment.",
        published="2026-10-20",
        publisher="Example source",
        url="https://example.com/backing",
        africa_source=True,
    )
    assert deal is not None
    assert deal["target"] == "Tonaton"
    assert deal["country"] == "GH"
    assert set(deal["countries"]) == {"KE", "GH"}

def test_demonym_in_target_phrase_sets_primary_country():
    from src.engines.deals import extract_deal

    deal = extract_deal(
        "Kenya's Jiji acquires Ghanaian-based classifieds outlet Tonaton",
        published="2026-01-01",
        publisher="Example source",
        url="https://example.com/story",
        africa_source=True,
    )
    assert deal is not None
    assert deal["country"] == "GH"
    assert "GH" in deal["countries"]

def test_market_size_is_not_the_deal_amount():
    from src.engines.deals import extract_deal

    deal = extract_deal(
        "Native Acquires Frontline Research Group to Build the Agentic Artificial Intelligence (AI) "
        "Data Layer for Africa's $1.7 Trillion Traditional Trade Market",
        published="2026-01-01", publisher="Example source", url="https://example.com/native", africa_source=True,
    )
    assert deal is not None
    assert deal["target"] == "Frontline Research Group"
    assert deal["amount_usd"] is None

def test_implausible_amount_is_dropped_but_deal_kept():
    from src.engines.deals import extract_deal

    deal = extract_deal(
        "Kenya's Acme acquires Beta for $40 billion",
        published="2026-01-01", publisher="Example source", url="https://example.com/cap", africa_source=True,
    )
    assert deal is not None
    assert deal["amount_usd"] is None and deal["amount"] is None

def test_outlooks_gaps_and_planned_spending_are_not_deals():
    from src.engines.deals import extract_deal

    for headline in (
        "Regional Economic Outlook 2026: Southern Africa Must Mobilise Development Finance at Scale "
        "to Close Annual $55 Billion Financing Gap",
        "Dangote raises planned investment in Ethiopia fertiliser project to over $4 billion",
        "World Bank Group raises $200b for Nigeria, others",
    ):
        assert extract_deal(headline, published="2026-01-01", publisher="Example source",
                            url="https://example.com/x", africa_source=True) is None, headline
