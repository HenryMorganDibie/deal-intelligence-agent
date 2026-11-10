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
