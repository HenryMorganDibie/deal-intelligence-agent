

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
