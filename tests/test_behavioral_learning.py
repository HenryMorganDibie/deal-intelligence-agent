from src.hosted_market import (
    _behavioral_interest_scores_from_stats,
    _rerank_with_behavioral_interest,
)


def test_behavioral_scores_require_minimum_audience_and_smooth_small_samples():
    scores = _behavioral_interest_scores_from_stats({
        "top_deals": [
            {"deal_id": "small", "impressions": 4, "unique_impression_visitors": 4,
             "unique_openers": 3, "opens": 4},
            {"deal_id": "one_opener", "impressions": 10, "unique_impression_visitors": 5,
             "unique_openers": 1, "opens": 1},
            {"deal_id": "qualified", "impressions": 20, "unique_impression_visitors": 10,
             "unique_openers": 5, "opens": 5},
        ]
    })
    assert "small" not in scores
    assert "one_opener" not in scores
    assert scores["qualified"] == 0.5


def test_behavioral_reranking_is_stable_without_signals():
    items = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    assert _rerank_with_behavioral_interest(items, {}) == items


def test_behavioral_reranking_preserves_all_items_and_only_uses_known_ids():
    items = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}]
    ranked = _rerank_with_behavioral_interest(items, {"d": 1.0, "unknown": 1.0})
    assert {item["id"] for item in ranked} == {"a", "b", "c", "d"}
    assert len(ranked) == len(items)
    assert ranked.index({"id": "d"}) < items.index({"id": "d"})
