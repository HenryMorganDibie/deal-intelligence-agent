from src.engines.deals import extract_deal


def test_export_percentage_is_not_an_acquisition():
    assert extract_deal(
        "India Acquires More Than 80% of Egypt’s Cotton Exports",
        published="2026-10-14",
        africa_source=True,
    ) is None


def test_asset_financing_product_list_is_not_an_acquisition():
    assert extract_deal(
        "I&M Bank Expands Asset Financing to Help Ugandan Businesses Acquire Pickups,Tractors",
        published="2026-10-15",
        africa_source=True,
    ) is None


def test_personal_luxury_asset_purchase_is_not_a_company_acquisition():
    assert extract_deal(
        "Burna Boy Acquires The “First-ever Lamborghini Revuelto In Nigeria” Worth N1 Billion",
        published="2025-08-29",
        africa_source=True,
    ) is None


def test_real_company_acquisition_still_extracts():
    deal = extract_deal(
        "CreditChek Buys Uganda’s Algosys to Expand in East Africa",
        published="2026-09-16",
        africa_source=True,
    )
    assert deal is not None
    assert deal["deal_type"] == "acquisition"
    assert deal["buyer"] == "CreditChek"
    assert deal["target"] == "Algosys"


def test_weekly_funding_roundup_is_not_a_single_deal():
    assert extract_deal(
        "Africa & Middle East Startups Raise $532M in Week 36",
        published="2026-09-04",
        africa_source=True,
    ) is None


def test_public_skills_program_is_not_private_market_funding():
    assert extract_deal(
        "South Korea backs Tanzania’s AI skills push with $170 million",
        published="2026-08-26",
        africa_source=True,
    ) is None


def test_demonym_is_not_attached_to_ticker_like_target():
    deal = extract_deal(
        "Pan African acquires remaining stake in Australian gold miner TCMG",
        published="2024-11-05",
        africa_source=True,
    )
    assert deal is not None
    assert deal["target"] == "TCMG"

