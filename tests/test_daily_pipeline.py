from __future__ import annotations

import csv
import json
import random
from unittest.mock import patch

from scripts import daily_pipeline as pipeline
from src.engines import alpha_scorer, backtest_universe, historical_backtest
from src.schemas.models import DetectedSignal, Severity, SignalCandidate, SignalType


def test_uncovered_historical_checkpoint_is_retried(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    assert historical_backtest._checkpoint_needs_run(checkpoint)

    checkpoint.write_text(json.dumps({"covered": False}), encoding="utf-8")
    assert historical_backtest._checkpoint_needs_run(checkpoint)

    checkpoint.write_text(json.dumps({"covered": True}), encoding="utf-8")
    assert not historical_backtest._checkpoint_needs_run(checkpoint)


def test_historical_shards_prioritize_african_and_retry_uncovered(tmp_path, monkeypatch):
    run_root = tmp_path / "runs"
    monkeypatch.setattr(historical_backtest, "RUNS_DIR", run_root)
    universe_path = tmp_path / "universe.csv"
    with universe_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["company", "ticker", "market"])
        writer.writeheader()
        writer.writerows([
            {"company": "US Co", "ticker": "US", "market": "us"},
            {"company": "African Co", "ticker": "AF.JO", "market": "africa"},
        ])
    monkeypatch.setattr(backtest_universe, "UNIVERSE_PATH", universe_path)

    start = pipeline.date(2025, 1, 1)
    end = pipeline.date(2025, 6, 1)
    run_dir = run_root / f"{start}_{end}"
    run_dir.mkdir(parents=True)
    (run_dir / "AF.JO.json").write_text(json.dumps({"covered": False}), encoding="utf-8")

    result = historical_backtest.plan_shards(
        start, end, [("US Co", "US", None), ("African Co", "AF.JO", None)], 1
    )

    assert result["remaining"] == 2
    assert result["shards"][0]["tickers"] == "AF.JO,US"


def test_financial_collection_prioritizes_african_tickers(tmp_path, monkeypatch):
    universe_path = tmp_path / "universe.csv"
    rows = [
        {"company": f"US {i}", "ticker": f"US{i}", "market": "us"}
        for i in range(12)
    ] + [
        {"company": "African A", "ticker": "AAA.JO", "market": "africa"},
        {"company": "African B", "ticker": "BBB.LG", "market": "africa"},
        {"company": "African C", "ticker": "CCC.NR", "market": "africa"},
    ]
    with universe_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["company", "ticker", "market"])
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(pipeline, "UNIVERSE_DATA", universe_path)
    monkeypatch.setattr(pipeline, "FINANCIAL_DATA", tmp_path / "financials.jsonl")
    monkeypatch.setattr(pipeline, "FINANCIAL_ATTEMPTS", tmp_path / "attempts.jsonl")
    called = []

    def no_data(ticker, years=4):
        called.append(ticker)
        return None

    with patch("src.engines.financials.yahoo_financials", side_effect=no_data):
        result = pipeline._financial_collection()

    assert called[:3] == ["AAA.JO", "BBB.LG", "CCC.NR"]
    assert len(called) == 12
    assert result["retry_after_days"] == 2


def test_collect_headlines_includes_country_specific_queries(monkeypatch):
    from src.engines import market_feed

    captured = {}

    async def fake_collect(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(market_feed, "collect", fake_collect)
    assert pipeline._collect_headlines() == []
    assert captured["include_countries"] is True


def test_event_review_queue_uses_rules_only_as_candidates():
    items = [{
        "title": "Bank of Ghana revokes licences of three lenders",
        "snippet": "The regulator said the institutions failed to meet requirements.",
        "publisher": "Example News",
        "url": "https://example.test/story",
        "date": "2026-10-15",
        "country_hint": "GH",
    }, {
        "title": "FIFA postpones the youth tournament",
        "snippet": "The football team is preparing for its first match.",
        "publisher": "Sports Desk",
        "url": "https://example.test/sport",
        "date": "2026-10-15",
    }]

    [row] = pipeline._event_review_rows(items)

    assert row["rule_candidates"] == ["regulatory_action"]
    assert row["label"] is None
    assert row["review_split"] in ("train", "holdout")
    assert row["country_hint"] == "GH"
    assert row["market"] == "africa"


def test_merge_jsonl_keeps_manual_labels_and_deduplicates(tmp_path):
    path = tmp_path / "queue.jsonl"
    row = {"id": "story-1", "title": "Headline", "label": {"expected": []}}
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    added = pipeline._merge_jsonl(path, [{"id": "story-1", "title": "Changed"}])

    assert added == 0
    assert pipeline._read_jsonl(path) == [row]


def test_locked_event_evaluation_set_has_680_items():
    heldout = pipeline._load_event_test_set()

    assert len(heldout) == 680
    assert any(expected for _, expected, _ in heldout)


def test_event_classifier_evaluates_manual_labels_against_locked_set(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "AUTOMATION_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "EVENT_QUEUE", tmp_path / "event_queue.jsonl")
    categories = [
        "credit_risk", "debt_restructuring", "distressed_asset", "earnings_surprise",
        "insider_activity", "leadership_change", "m_and_a_activity", "regulatory_action",
    ]
    rows = []
    for index in range(1000):
        category = categories[index % len(categories)]
        rows.append({
            "id": f"event-{index}",
            "title": f"Example company reports {category.replace('_', ' ')} update",
            "snippet": f"Details of {category.replace('_', ' ')}",
            "label": {"about_target": True, "expected": [category], "confidence": "high"},
        })
    pipeline._merge_jsonl(pipeline.EVENT_QUEUE, rows)

    result = pipeline.train_event_classifier()

    assert result["status"] in ("promoted", "evaluated_not_promoted")
    assert result["locked_heldout_items"] == 680
    assert (tmp_path / "event_classifier_evaluation.json").exists()


def test_event_classifier_excludes_independent_attribution_items(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "AUTOMATION_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "EVENT_QUEUE", tmp_path / "event_queue.jsonl")
    monkeypatch.setattr(pipeline, "INDEPENDENT_EVENT_ITEMS", tmp_path / "independent_items.jsonl")
    pipeline.INDEPENDENT_EVENT_ITEMS.write_text(
        json.dumps({"source_review_id": "locked-story"}) + "\n", encoding="utf-8"
    )
    pipeline.EVENT_QUEUE.write_text("".join(json.dumps({
        "id": item_id,
        "title": "Example company reports event",
        "label": {"about_target": True, "expected": [], "confidence": "high"},
    }) + "\n" for item_id in ("locked-story", "train-story")), encoding="utf-8")

    result = pipeline.train_event_classifier()

    assert result["training_labels"] == 1


def test_entity_matcher_evaluates_only_its_separate_holdout(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "AUTOMATION_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "ENTITY_QUEUE", tmp_path / "entity_queue.jsonl")
    rows = []
    for index in range(600):
        same = index % 2 == 0
        left = f"Company {index}"
        right = f"Company {index} Limited" if same else f"Different group {index}"
        rows.append({
            "id": f"pair-{index}",
            "left": left,
            "right": right,
            "same_entity": same,
            "review_split": "holdout" if index >= 500 else "train",
        })
    pipeline._merge_jsonl(pipeline.ENTITY_QUEUE, rows)

    result = pipeline.train_entity_matcher()

    assert result["status"] in ("promoted_for_review_suggestions", "evaluated_not_promoted")
    assert result["training_pairs"] == 500
    assert result["holdout_pairs"] == 100
    assert result["classifier"]["precision"] >= 0.0


def test_rank_metrics_tied_scores_use_expected_base_rate():
    rows = [{"event_confirmed": "True"}] * 2 + [{"event_confirmed": "False"}] * 8

    metrics = pipeline._ranking_metrics(rows, [0.5] * len(rows))

    assert metrics["precision_at_20pct"] == 0.2


def test_learned_ranker_is_trained_on_earlier_dates_and_promoted_only_on_holdout(tmp_path, monkeypatch):
    input_path = tmp_path / "backtest.csv"
    report_path = tmp_path / "report.json"
    model_path = tmp_path / "model.json"
    monkeypatch.setattr(pipeline, "RANKING_REPORT", report_path)
    monkeypatch.setattr(pipeline, "RANKER_MODEL", model_path)
    rng = random.Random(42)
    fields = [
        "company", "ticker", "market", "as_of", "signal_type", "severity", "alpha",
        "direction", "source_kind", "event_confirmed",
    ]
    rows = []
    for day in range(12):
        for index in range(120):
            severity = ("critical", "high", "medium", "low")[index % 4]
            alpha = rng.uniform(40, 95)
            positive = severity in ("critical", "high") and index % 3 != 0
            rows.append({
                "company": f"Company {index}",
                "ticker": f"T{index}",
                "market": "us",
                "as_of": f"2025-{day + 1:02d}-01",
                "signal_type": "m_and_a_activity",
                "severity": severity,
                "alpha": f"{alpha:.1f}",
                "direction": "positive",
                "source_kind": "filing",
                "event_confirmed": str(positive),
            })
    with input_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    report = pipeline.train_learned_ranker(input_path)

    assert report["train_through"] < report["holdout_from"]
    assert report["training_rows"] + report["holdout_rows"] == len(rows)
    assert report["status"] in ("promoted", "evaluated_not_promoted")
    assert report_path.exists()
    if report["promoted"]:
        assert model_path.exists()


def test_entity_match_features_use_name_similarity_and_token_overlap():
    near = pipeline._entity_pair_features("International Finance Corporation", "International Finance Corp")
    different = pipeline._entity_pair_features("International Finance Corporation", "Nairobi Securities Exchange")

    assert near[0] > different[0]
    assert near[1] > different[1]


def test_financial_collection_advances_through_universe_and_records_flags(tmp_path, monkeypatch):
    universe = tmp_path / "universe.csv"
    with universe.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ticker"])
        writer.writeheader()
        writer.writerows({"ticker": f"TICKER{index}"} for index in range(6))
    monkeypatch.setattr(pipeline, "UNIVERSE_DATA", universe)
    monkeypatch.setattr(pipeline, "FINANCIAL_DATA", tmp_path / "observations.jsonl")
    monkeypatch.setattr(pipeline, "FINANCIAL_ATTEMPTS", tmp_path / "attempts.jsonl")

    def financials(ticker, years):
        assert years == 4
        return {
            "source": "test source",
            "unit": "USD",
            "annual": {
                "2024-12-31": {"revenue": 60.0, "profit_after_tax": -2.0, "total_debt": 300.0,
                               "total_equity": 100.0},
                "2023-12-31": {"revenue": 100.0, "profit_after_tax": 5.0},
            },
        }

    from src.engines import financials as financials_engine

    monkeypatch.setattr(financials_engine, "yahoo_financials", financials)
    result = pipeline._financial_collection()
    rows = pipeline._read_jsonl(pipeline.FINANCIAL_DATA)

    assert result["new_rows"] == 6
    assert len(rows) == 6
    assert rows[0]["screening_flags"] == [
        "revenue_decline_25pct", "profit_to_loss", "debt_to_equity_at_least_2",
    ]
    assert len(pipeline._read_jsonl(pipeline.FINANCIAL_ATTEMPTS)) == 6


def test_graph_relationships_keep_source_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "GRAPH_DATA", tmp_path / "graph.json")
    items = [{
        "title": "United Capital acquires 5% stake in Nigerian Exchange Group for N10 billion",
        "publisher": "Example Finance",
        "url": "https://example.test/deal",
        "date": "2026-10-15",
    }]

    summary = pipeline._update_graph(items)
    graph = json.loads(pipeline.GRAPH_DATA.read_text(encoding="utf-8"))

    assert summary["relationships"] >= 1
    assert any(edge["sources"][0]["url"] == items[0]["url"] for edge in graph["edges"].values())


def test_promoted_ranker_probability_is_separate_from_alpha():
    signal = DetectedSignal(
        signal_type=SignalType.MA_ACTIVITY,
        severity=Severity.HIGH,
        headline="Acme announces acquisition",
        evidence=["Company disclosure"],
        confidence=0.8,
        reasoning="A reported acquisition.",
    )
    candidate = SignalCandidate(
        signal_type=SignalType.MA_ACTIVITY,
        matched_patterns=["acquisition"],
        source_text="Acme announces acquisition",
        source_type="filing",
        source_name="Exchange disclosure",
        raw_score=0.8,
    )
    model = {
        "feature_names": [
            "alpha", "severity", "signal_type=m_and_a_activity", "source_kind=filing",
            "market=us",
        ],
        "weights": [-1.0, 0.1, 0.5, 0.8, 0.2, 0.1],
    }

    with patch.object(alpha_scorer, "_load_learned_ranker", return_value=model):
        probability = alpha_scorer._learned_confirmation_probability(
            signal, candidate, 70.0, "ACME", "positive"
        )

    assert probability is not None
    assert 0.0 <= probability <= 1.0


def test_obvious_non_market_headlines_are_not_queued_as_events():
    items = [{
        "title": "OUR CITY NEWS: Herman Mashaba targets illegal immigration in bid for Joburg mayoralty",
        "snippet": "A mayoral candidate discusses immigration policy.",
        "publisher": "Daily Maverick Business",
        "url": "https://example.test/politics",
        "date": "2026-10-16",
    }, {
        "title": "Bank of Ghana revokes licences of three lenders",
        "snippet": "The regulator said the institutions failed to meet requirements.",
        "publisher": "Example News",
        "url": "https://example.test/regulator",
        "date": "2026-10-16",
        "country_hint": "GH",
    }]

    rows = pipeline._event_review_rows(items)

    assert len(rows) == 1
    assert rows[0]["title"].startswith("Bank of Ghana")


def test_locked_evaluation_headlines_are_excluded_from_event_training(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "AUTOMATION_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "EVENT_QUEUE", tmp_path / "event_queue.jsonl")
    locked_items = pipeline._read_jsonl(pipeline.ROOT / "evaluation" / "attribution" / "natural_items.jsonl")
    locked_title = locked_items[0]["title"]
    rows = [{
        "id": pipeline._stable_id(locked_title),
        "title": locked_title,
        "label": {"about_target": True, "expected": [], "confidence": "high"},
    }, {
        "id": "ordinary-reviewed-story",
        "title": "An unrelated company event",
        "label": {"about_target": True, "expected": [], "confidence": "high"},
    }]
    pipeline.EVENT_QUEUE.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    result = pipeline.train_event_classifier()

    assert result["training_labels"] == 1


def test_graph_prunes_generic_policy_concepts_but_keeps_real_counterparties(tmp_path, monkeypatch):
    graph_path = tmp_path / "relationship_graph.json"
    monkeypatch.setattr(pipeline, "GRAPH_DATA", graph_path)
    graph_path.write_text(json.dumps({
        "nodes": {
            "private": {"name": "Private", "kind": "organization"},
            "livestock": {"name": "Livestock", "kind": "organization"},
            "finnfund": {"name": "Finnfund", "kind": "organization"},
            "bisedge": {"name": "Bisedge", "kind": "organization"},
        },
        "edges": {
            "bad": {"id": "bad", "from": "private", "to": "livestock", "type": "equity_funding", "sources": []},
            "good": {"id": "good", "from": "finnfund", "to": "bisedge", "type": "debt_financing", "sources": []},
        },
    }), encoding="utf-8")

    result = pipeline._update_graph([])

    persisted = json.loads(graph_path.read_text(encoding="utf-8"))
    assert result["relationships"] == 1
    assert "bad" not in persisted["edges"]
    assert set(persisted["nodes"]) == {"finnfund", "bisedge"}


def test_prune_event_queue_removes_unreviewed_non_market_false_positives(tmp_path, monkeypatch):
    path = tmp_path / "event_queue.jsonl"
    monkeypatch.setattr(pipeline, "EVENT_QUEUE", path)
    rows = [{
        "id": "politics",
        "title": "Herman Mashaba targets illegal immigration in bid for Joburg mayoralty",
        "snippet": "",
        "label": None,
        "rule_candidates": ["m_and_a_activity"],
    }, {
        "id": "reviewed-politics",
        "title": "Herman Mashaba targets illegal immigration in bid for Joburg mayoralty",
        "snippet": "",
        "label": {"about_target": True, "expected": []},
        "rule_candidates": ["m_and_a_activity"],
    }, {
        "id": "real-event",
        "title": "Bank of Ghana revokes licences of three lenders",
        "snippet": "",
        "label": None,
        "rule_candidates": ["regulatory_action"],
    }]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    removed = pipeline._prune_event_queue()

    persisted = pipeline._read_jsonl(path)
    assert removed == 1
    assert [row["id"] for row in persisted] == ["reviewed-politics", "real-event"]
