from datetime import date

from scripts.corporate_of_week import matched_events, score_deal, select_company


def test_matching_event_requires_company_name_in_headline():
    events = [
        {"headline": "Acme raises a new round", "rule_score": 0.9},
        {"headline": "A new round raises hopes for the sector", "rule_score": 1.0},
    ]
    assert len(matched_events("Acme", events)) == 1


def test_single_source_is_not_described_as_corroborated():
    deal = {
        "target": "Acme",
        "headline": "Acme raises $10m",
        "deal_type": "equity_funding",
        "announced": "2026-10-15",
        "amount_usd": 10_000_000,
        "independent_stories": 1,
        "sources": [{"title": "Acme raises $10m", "url": "https://example.com/story"}],
    }
    score, reasons = score_deal(deal, [], date(2026, 10, 18))
    assert score > 0
    assert any("Only one source link directly matches" in reason for reason in reasons)
    assert not any("Corroborated by" in reason for reason in reasons)


def test_selects_company_using_recent_source_linked_transaction_and_rationale():
    deals = [
        {
            "target": "Acme Holdings",
            "deal_type": "equity_funding",
            "announced": "2026-10-15",
            "amount_usd": 20_000_000,
            "country": "NG",
            "sector": "fintech",
            "headline": "Acme Holdings raises $20m",
            "independent_stories": 2,
            "sources": [
                {"publisher": "News A", "title": "Acme Holdings raises $20m", "url": "https://example.com/a", "date": "2026-10-15"},
                {"publisher": "News B", "title": "Acme Holdings raises $20m funding", "url": "https://example.com/b", "date": "2026-10-15"},
            ],
        },
        {
            "target": "Generic",
            "deal_type": "acquisition",
            "announced": "2026-10-16",
            "sources": [{"url": "https://example.com/generic"}],
        },
    ]
    events = [
        {"headline": "Acme Holdings faces new regulatory action", "day": "2026-10-16", "rule_score": 0.9,
         "url": "https://example.com/event", "publisher": "Regulator"},
    ]
    result = select_company(deals, events, date(2026, 10, 12), date(2026, 10, 18))
    assert result["company"] == "Acme Holdings"
    assert result["score"] > 0
    assert result["related_events"] == 1
    assert len(result["sources"]) == 3
    assert result["sources"][0]["kind"] == "deal"
    assert result["sources"][-1]["kind"] == "corporate_event"
    assert any("Corroborated by 2 independent stories" in reason for reason in result["reasons"])


def test_broader_company_coverage_is_not_counted_as_deal_corroboration():
    deal = {
        "target": "Kenya Airways",
        "headline": "Kenya Airways secures $350m state loan to shore up finances",
        "deal_type": "debt_financing",
        "announced": "2026-10-12",
        "independent_stories": 5,
        "sources": [
            {"title": "Kenya Airways secures $350m state loan to shore up finances", "url": "https://example.com/direct"},
            {"title": "Kenya Airways Secures $1.3 Billion State Rescue Through New Funding and Debt Conversion", "url": "https://example.com/related"},
        ],
    }
    _, reasons = score_deal(deal, [], date(2026, 10, 18))
    assert any("Only one source link directly matches" in reason for reason in reasons)
    assert not any("Corroborated by 5 independent stories" in reason for reason in reasons)
