from scripts.corporate_of_week import is_generic_company, normalise
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
