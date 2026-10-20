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
