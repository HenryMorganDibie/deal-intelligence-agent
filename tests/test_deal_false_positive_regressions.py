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


def test_grant_is_not_private_market_funding():
    assert extract_deal(
        "Solarise Africa secures $1.15M EEP Africa Grant for expansion into Uganda and Zambia",
        published="2026-10-16",
        africa_source=True,
    ) is None


def test_commercial_supply_contract_is_not_equity_funding():
    assert extract_deal(
        "Wabtec lands $400M South African rail deal to support diesel locomotives",
        published="2026-10-16",
        africa_source=True,
    ) is None


def test_multi_startup_funding_roundup_is_not_a_single_deal():
    assert extract_deal(
        "Six African Startups Secure $400,000 in FINCA Ventures Funding to Scale Innovative Solutions",
        published="2026-10-16",
        africa_source=True,
    ) is None

def test_lender_grants_a_loan_is_still_a_real_debt_deal():
    deal = extract_deal(
        "African Development Bank Group grants $100 million loan to Emerging Africa and Asia Infrastructure Fund (EAAIF) to support development of sustainable infrastructure",
        published="2025-11-12",
        africa_source=True,
    )
    assert deal is not None
    assert deal["deal_type"] == "debt_financing"

def test_public_infrastructure_capex_is_not_equity_funding():
    for headline in (
        "ECG invests GH¢710,965 in infrastructure replacement across Greater Accra",
        "GoldBod invests GH¢8.4 million in restoring three water treatment plants",
        "MTN Nigeria invests ₦202bn in Q1 to boost connectivity, service quality",
        "Govt invests GH¢50bn in road sector in 16 months",
    ):
        assert extract_deal(headline, published="2026-10-18", africa_source=True) is None


def test_fund_raise_uses_the_named_fund_not_roman_numeral():
    deal = extract_deal(
        "Ventures Platform's Pan-African Fund II secures $84mn, targets pre-seeds to Series A investments",
        published="2026-08-26",
        africa_source=True,
    )
    assert deal is not None
    assert deal["deal_type"] == "fund_raise"
    assert deal["target"] == "Ventures Platform's Pan-African Fund II"


def test_currency_and_sentence_fragments_are_not_targets():
    for headline in (
        "Farmer invests GH¢20,000 Telecel prize in farm",
        "Maroc : TV5MONDE investit 1M€ dans le secteur de l'animation",
        "Emmanuel Mwamba says we obtain a loan of about $10million from AfDB",
    ):
        assert extract_deal(headline, published="2026-10-18", africa_source=True) is None



def test_institutional_raises_roundups_and_non_company_targets_are_not_deals():
    from src.engines import deals as d

    for headline in (
        "Afrique : la BAD lève 2,5 milliards USD sur les marchés",
        "BoI secures €2.22bn, N250bn funding for Nigerian industries",
        "Afreximbank Backs African Auto Industry With $1 Billion",
        "Logistics Attracts $780 Million, Overtaking Fintech in African Startup Funding",
        "Nigerian Startups Lead Africa With $624m Funding As Continent Raises $2.49bn In 2026",
        "Dangote, Djibouti and Ethiopia commit USD 660m to a Red Sea fuel pipeline hub",
        "MIDYAN Developments invests EGP 12bn across three sectors over four years",
    ):
        assert d.extract_deal(headline, published="2026-10-20") is None, headline
    for headline, target in (
        ("Moniepoint raises $110 million Series C led by Development Partners International", "Moniepoint"),
        ("Standard Bank Group announces strategic investment in OPay", "OPay"),
        ("Kenyan fintech 4G Capital raises $18.5M from Lightrock to scale lending to MSMEs", "4G Capital"),
    ):
        assert (d.extract_deal(headline, published="2026-10-20") or {}).get("target") == target, headline


def test_stored_records_are_reclassified_without_touching_real_deals():
    from src.engines import deals as d

    excluded = [
        ("equity_funding", "BAD", "Afrique : la BAD lève 2,5 milliards USD sur les marchés"),
        ("debt_financing", "AfDB", "AfDB raises $2.5 billion in global bond as orders hit $4.8 billion"),
        ("equity_funding", "Maritime Sector", "APM Terminals Pledges $600 Million Investment in Nigeria’s Maritime Sector"),
        ("equity_funding", "USD 40M", "Vodacom Lesotho Invests USD 40M to Boost Connectivity and Digital Inclusion"),
        ("equity_funding", "65MDH", "Lesieur Cristal Maroc investit 65MDH dans une nouvelle savonnerie au Sénégal"),
    ]
    for deal_type, target, headline in excluded:
        change = d.reclassify({"deal_type": deal_type, "target": target, "headline": headline})
        assert change and change["excluded"].startswith("reclassified:"), headline
    kept = [
        ("equity_funding", "54Gene", "Biotech startup, 54Gene raises $500,000 to boost COVID-19 testing in Nigeria"),
        ("equity_funding", "Undisclosed startup", "Buying Used Cars In Kenya Is Trouble. This Startup Just Raised USD 11 M"),
        ("joint_venture", "Yusen Logistics", "Africa Global and Yusen Logistics Launch Joint Venture"),
        ("fund_raise", "USD 180m", "CFM raises over USD 180m at first close of South Africa H2 fund"),
        ("debt_financing", "Kenya Airways", "Kenya Airways secures $350m state loan to shore up finances"),
        ("acquisition", "10X Investments", "Old Mutual acquires 10X Investments in R2.2 billion deal"),
    ]
    for deal_type, target, headline in kept:
        assert d.reclassify({"deal_type": deal_type, "target": target, "headline": headline}) is None, headline
    bond = d.reclassify({"deal_type": "equity_funding", "target": "Seplat", "headline": "Seplat raises $650m bond"})
    assert bond == {"deal_type": "debt_financing", "round": None}


def test_pulse_reports_median_concentration_and_value_by_kind():
    from datetime import date

    from src.engines import pulse

    rows = [{"id": str(i), "deal_type": t, "amount_usd": a, "announced": "2026-10-20", "country": "NG"}
            for i, (t, a) in enumerate([("debt_financing", 900e6), ("equity_funding", 10e6), ("equity_funding", 20e6),
                                        ("acquisition", 50e6), ("fund_raise", 20e6)])]
    out = pulse.build(rows, [], {}, today=date(2026, 10, 28))["deals"]
    assert out["recent_disclosed_usd"] == 1_000_000_000 and out["recent_disclosed_median_usd"] == 20_000_000
    assert out["recent_top3_share"] == 0.97
    assert out["recent_value_by_kind"] == {"debt": 900_000_000, "m_and_a": 50_000_000, "equity": 30_000_000,
                                           "funds": 20_000_000}


def test_ingest_reclassification_merges_a_retyped_record_into_its_twin_and_spares_reviewed_ones():
    import src.hosted_market as hm

    stored = {
        "a": {"id": "a", "deal_type": "debt_financing", "target": "Seplat", "amount_usd": 650e6,
              "announced": "2026-10-14", "country": "NG", "headline": "Seplat prices $650m bond"},
        "b": {"id": "b", "deal_type": "equity_funding", "target": "Seplat", "amount_usd": 650e6,
              "announced": "2026-10-15", "country": "NG", "headline": "Seplat raises $650 million bond"},
        "c": {"id": "c", "deal_type": "equity_funding", "target": "Maritime Sector", "reviewed_on": "2026-10-20",
              "headline": "APM Terminals Pledges $600 Million Investment in Nigeria’s Maritime Sector"},
    }
    out = hm._reclassify_stored(stored, {})
    assert set(out) == {"b"}
    assert out["b"]["deal_type"] == "debt_financing" and out["b"]["merged_into"] == "a"
