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
