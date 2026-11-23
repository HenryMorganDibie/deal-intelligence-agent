

def test_money_headlines_that_report_no_company_transaction():
    from src.engines.deals import extract_deal
    for h in ("IIFL Finance Block Deal: FIH Mauritius To Sell 13% Stake In Rs 3,454-Crore Clean-Out Trade; Check Floor Price",
              "Syngenta invests $1.5bn annually in R&D, identifies Egypt as key Middle East market",
              "Novo Invests in Diabetes Screening in Kenya Amid Late Diagnosis Concerns",
              "Ending Energy Poverty: Why South Africa Needs Public Investment in Distributed Renewable Energy",
              "Morocco Players to Receive MAD 8 Million Each in World Cup Bonuses, Ouahbi to Earn MAD 16 Million",
              "UK Investment In Zambia Exceeds £3 Bn As Green Growth Partnership Expands",
              "Nigerian Exchange acquires 10% strategic stake in Kenyan Exchange"):
        assert extract_deal(h, published="2026-11-17", publisher="Test") is None, h


def test_real_deals_still_extracted_and_talks_stay_rumoured():
    from src.engines.deals import extract_deal
    nse = extract_deal("NGX Group acquires 10% stake in Nairobi Securities Exchange", published="2026-11-17", publisher="Test")
    assert (nse["target"], nse["buyer"]) == ("Nairobi Securities Exchange", "NGX Group")
    close = extract_deal("Grounded Investment Company hits €12m interim close", published="2026-11-17", publisher="Test")
    assert close is None or close["deal_type"] == "fund_raise"     # a fund's name containing "Investment" is not a statistic
    from src.engines import deals
    assert not deals._AGGREGATE_STAT.search("Grounded Investment Company hits €12m interim close")
    talks = extract_deal("MTN in talks to acquire Telkom", published="2026-11-17", publisher="Test")
    assert talks["stage"] == "rumoured"
    block = extract_deal("Block deal alert: FIH Mauritius to sell up to 13.25% stake in IIFL Finance for $370 mn",
                         published="2026-11-17", publisher="Test")
    assert block is None                          # Indian market jargon: a Mauritius vehicle selling an Indian company


def test_french_names_built_on_a_nationality_keep_their_article():
    from src.engines.deals import _clean_name, extract_deal
    assert _clean_name("La Marocaine Vie") == "La Marocaine Vie"
    assert _clean_name("La Tunisienne des Assurances") == "La Tunisienne des Assurances"
    assert _clean_name("Le Maroc") is None and _clean_name("La BAD") == "BAD"
    deal = extract_deal("Wafa Assurance Acquires 99.98% of La Marocaine Vie", published="2026-11-17", publisher="Test")
    assert (deal["target"], deal["buyer"]) == ("La Marocaine Vie", "Wafa Assurance")

def test_comparison_country_does_not_assign_an_african_deal_location_to_global_company():
    from src.engines.deals import extract_deal

    headline = "Anthropic raises $81.3 billion, more than Zimbabwe's whole economy produces in a year"
    assert extract_deal(
        headline,
        published="2026-11-19",
        publisher="Disrupt Africa",
        africa_source=True,
    ) is None


def test_real_african_target_country_before_comparison_is_preserved():
    from src.engines.deals import extract_deal

    deal = extract_deal(
        "Nigerian fintech Kuda raises $20m, more than the sector's previous record",
        published="2026-11-19",
        publisher="Test",
    )
    assert deal is not None
    assert deal["country"] == "NG"


# ── Late re-reports, republished articles and buyer aliases (stored duplicates seen in production) ──

from src.engines import deals  # noqa: E402

def _d(**kw):
    base = {"id": kw.pop("id", "x"), "deal_type": "equity_funding", "country": "NG", "countries": ["NG"], "investors": [],
            "buyer": None, "seller": None, "round": None, "stage": "completed"}
    base.update(kw)
    return base


def test_same_round_reported_again_months_later_is_one_deal():
    a = _d(id="a", announced="2026-04-23", target="Swoop", amount_usd=7.3e6, round="seed",
           investors=["Long Journey", "Variant", "Version One"], headline="Swoop raises $7.3 million seed for African super app, food delivery first")
    b = _d(id="b", announced="2026-10-10", target="Swoop", amount_usd=7.3e6, round="seed",
           investors=["Long Journey", "Variant"], headline="Swoop Raises $7.3M, Builds Super App To Compete In Nigeria's Food Delivery Market")
    assert deals.strong_same_report(a, b) and deals.same_transaction(a, b)


def test_same_figure_from_different_backers_is_two_deals():
    bii = _d(id="a", announced="2025-05-22", country="KE", countries=["KE"], target="ARC Ride", amount_usd=5e6,
             investors=["British International Investment"], headline="UK Development Financier BII Backs Kenya's ARC Ride with $5m to Expand")
    ifc = _d(id="b", announced="2026-02-17", country="KE", countries=["KE"], target="Arc Ride", amount_usd=5e6,
             investors=["International Finance Corporation"], headline="Kenya's Arc Ride secures $5 million IFC commitment for regional expansion")
    assert not deals.strong_same_report(bii, ifc)


def test_repeat_issues_and_different_rounds_stay_separate():
    cp1 = _d(id="a", announced="2023-03-08", target="MTN Nigeria", amount_usd=1.9e8, headline="MTN Nigeria raises N125bn via commercial papers")
    cp2 = _d(id="b", announced="2023-08-31", target="MTN Nigeria", amount_usd=1.9e8, headline="MTN Nigeria raises N125bn for short-term working capital")
    assert not deals.strong_same_report(cp1, cp2)
    pre = _d(id="c", announced="2022-04-10", target="Spleet", amount_usd=2.6e6, round="pre-seed", headline="Spleet Raises $2.6m to Spread Rent Offerings")
    seed = _d(id="d", announced="2022-10-04", target="Spleet", amount_usd=2.6e6, round="seed", headline="Spleet raises $2.6 million seed round to provide rent financing")
    assert not deals.strong_same_report(pre, seed)
    # Two placings by a listed junior for the same sum, for different projects.
    p1 = _d(id="e", announced="2026-06-04", target="Tertiary Minerals", amount_usd=1.28e6, country="ZM", countries=["ZM"],
            headline="Tertiary Minerals Raises £1 Million to Progress Zambian Silver Oxide Deposit")
    p2 = _d(id="f", announced="2026-09-29", target="Tertiary Minerals", amount_usd=1.28e6, country="ZM", countries=["ZM"],
            headline="Tertiary Minerals Raises £1 Million for Mushima North Exploration in Zambia")
    assert not deals.strong_same_report(p1, p2)


def test_late_report_needs_the_same_figure_and_a_year_at_most():
    a = _d(id="a", announced="2026-04-23", target="Swoop", amount_usd=7.3e6, round="seed", headline="Swoop raises seed")
    assert not deals.strong_same_report(a, {**a, "id": "b", "announced": "2026-10-10", "amount_usd": 9e6})
    assert not deals.strong_same_report(a, {**a, "id": "b", "announced": "2027-06-01"})


def test_identical_headline_indexed_again_is_one_report():
    a = _d(id="a", deal_type="debt_financing", announced="2026-09-30", target="InfraCredit", amount_usd=5e7, investors=["IFC"],
           headline="InfraCredit Secures $50m IFC Facility to Boost Local-Currency Infrastructure Finance")
    b = {**a, "id": "b", "announced": "2026-11-17", "investors": []}
    assert deals.strong_same_report(a, b)
    # A borrower that signs the same loan every year is not collapsed by the headline alone.
    assert not deals.strong_same_report({**a, "announced": "2018-09-21"}, {**b, "announced": "2019-09-14"})


def test_acquisition_reported_under_the_business_and_its_owner():
    glovo = _d(id="a", deal_type="acquisition", announced="2026-07-17", country="KE", countries=["KE"], target="Glovo", buyer="Uber",
               stage="announced", headline="Uber Buys Out Glovo, Its Biggest Rival in Kenya's Delivery Market")
    dh = _d(id="b", deal_type="acquisition", announced="2026-07-16", country="KE", countries=["KE"], target="Delivery Hero", buyer="Uber",
            stage="announced", headline="Uber to Acquire Delivery Hero's Food Delivery Business Across 50 Markets, Including Glovo Kenya")
    assert deals.strong_same_report(glovo, dh)
    other = {**dh, "buyer": "Bolt"}
    assert not deals.strong_same_report(glovo, other)
    assert not deals.strong_same_report(glovo, {**dh, "announced": "2026-08-30"})
