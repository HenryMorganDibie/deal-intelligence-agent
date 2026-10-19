"""Tests for deterministic research planning, evidence conflicts, and evaluation metrics."""
from src.engines.research_quality import (
    benchmark_metrics, build_query_plan, detect_evidence_conflicts, research_limitations,
)


def test_query_plan_uses_distinct_company_and_primary_source_queries():
    plan = build_query_plan(
        "What funding did Acme raise in Kenya?",
        {"companies": ["Acme"], "countries": ["Kenya"], "deal_types": ["equity_funding"]},
        "Kenya Acme funding",
    )
    assert len(plan) >= 3
    assert len({q.lower() for q in plan}) == len(plan)
    assert any("investor relations" in q for q in plan)
    assert any(q.startswith("Kenya (") for q in plan)


def test_amount_conflicts_are_flagged_for_named_company_only():
    items = [
        {"n": 1, "title": "Acme raises $20 million", "text": "Acme funding round", "url": "https://a.test"},
        {"n": 2, "title": "Acme funding round at $25 million", "text": "Acme raised funds", "url": "https://b.test"},
        {"n": 3, "title": "OtherCo raises $99 million", "text": "OtherCo round", "url": "https://c.test"},
    ]
    conflicts = detect_evidence_conflicts(items, ["Acme"])
    assert len(conflicts) == 1
    assert conflicts[0]["currency"] == "USD"
    assert len(conflicts[0]["values"]) == 2
    assert detect_evidence_conflicts(items, []) == []


def test_same_reported_amount_is_not_a_conflict():
    items = [
        {"n": 1, "title": "Acme raises $20 million", "text": "Acme funding"},
        {"n": 2, "title": "Acme raised $20 million", "text": "Acme financing"},
    ]
    assert detect_evidence_conflicts(items, ["Acme"]) == []


def test_research_limitations_disclose_unknown_dates_and_bounded_coverage():
    notes = research_limitations({"since": "2026-01-01"}, [{"url": "https://x.test", "date": None}], [])
    assert any("unknown date" in note for note in notes)
    assert any("bounded sample" in note for note in notes)


def test_benchmark_metrics_are_reproducible():
    metrics = benchmark_metrics(["a", "b"], ["a", "c"], [True, False])
    assert metrics["retrieval_precision"] == 0.5
    assert metrics["retrieval_recall"] == 0.5
    assert metrics["claim_support_rate"] == 0.5



def test_research_result_exposes_limits_and_query_plan_without_live_news():
    from src.engines.research import research

    result = research("What happened to Acme?", live_news=True, news=lambda query, country: [])
    assert result["query_plan"]
    assert result["limitations"]
    assert "bounded sample" in " ".join(result["limitations"])
    assert result["conflicts"] == []



def test_single_article_with_raise_and_valuation_is_not_treated_as_source_conflict():
    items = [
        {"n": 1, "title": "Acme raises $20 million at a $100 million valuation", "text": "Acme financing"},
        {"n": 2, "title": "Acme raises $20 million", "text": "Acme funding"},
    ]
    assert detect_evidence_conflicts(items, ["Acme"]) == []



def test_query_plan_expands_iso_country_codes_to_names():
    plan = build_query_plan(
        "Funding activity in Kenya",
        {"companies": [], "countries": ["KE"], "deal_types": ["equity_funding"]},
        "Kenya funding",
    )
    assert any("Kenya" in query for query in plan)



def test_company_research_uses_structured_transaction_and_valuation_context():
    from src.engines.research import retrieve

    deals = [{
        "id": "acme-raise-1",
        "deal_type": "equity_funding",
        "stage": "announced",
        "round": "Series A",
        "target": "Acme",
        "buyer": "Example Capital",
        "seller": None,
        "investors": ["Example Capital"],
        "amount_usd": 20_000_000,
        "reported_valuation_usd": 100_000_000,
        "implied_valuation_usd": None,
        "stake_pct": None,
        "sector": "fintech",
        "country": "KE",
        "countries": ["KE"],
        "announced": "2025-03-01",
        "headline": "Acme raises $20 million in Series A",
        "sources": [{"url": "https://example.com/acme", "publisher": "Example News"}],
        "verification": "single source",
        "independent_stories": 1,
    }]
    _, items = retrieve("Acme funding history", deals=deals, live_news=False)
    kinds = {item["kind"] for item in items}
    assert "company_activity" in kinds
    assert "valuation_context" in kinds
