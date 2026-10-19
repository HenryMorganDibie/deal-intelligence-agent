from __future__ import annotations

import json

import pytest

from scripts.evaluate_research_benchmark import evaluate
from scripts.run_research_benchmark import load_cases


def test_benchmark_evaluator_refuses_unreviewed_cases(tmp_path):
    path = tmp_path / "unreviewed.jsonl"
    path.write_text(json.dumps({
        "case_id": "candidate-1",
        "label_status": "needs_independent_human_review",
        "expected_relevant_ids": [],
        "retrieved_ids": ["https://example.com"],
        "claim_support_labels": [],
    }) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No reviewed benchmark cases"):
        evaluate(path)


def test_benchmark_evaluator_scores_only_human_reviewed_cases(tmp_path):
    path = tmp_path / "reviewed.jsonl"
    cases = [
        {
            "case_id": "candidate-1",
            "label_status": "human_reviewed",
            "expected_relevant_ids": ["a", "b"],
            "retrieved_ids": ["a", "c"],
            "claim_support_labels": [True, False],
            "latency_seconds": 2.5,
            "mode": "llm",
            "evidence": [
                {"url": "https://news.google.com/rss/articles/a", "publisher_url": "https://publisher.example/a", "content_url": "https://publisher.example/a", "content_status": "article_text_retrieved"},
                {"url": "https://publisher.example/b", "content_status": "snippet_only"},
                {"url": "https://other.example/c", "content_status": "snippet_only"},
            ],
        },
        {
            "case_id": "candidate-2",
            "label_status": "needs_independent_human_review",
            "expected_relevant_ids": [],
            "retrieved_ids": ["x"],
            "claim_support_labels": [],
        },
    ]
    path.write_text("\n".join(json.dumps(case) for case in cases) + "\n", encoding="utf-8")
    result = evaluate(path)
    assert result["cases"] == 1
    assert result["retrieval_precision_macro"] == 0.5
    assert result["retrieval_recall_macro"] == 0.5
    assert result["claim_support_rate_macro"] == 0.5
    assert result["operational_quality"]["latency_seconds_mean"] == 2.5
    assert result["operational_quality"]["latency_seconds_p95"] == 2.5
    assert result["operational_quality"]["distinct_source_domains_mean"] == 2
    assert result["operational_quality"]["direct_article_text_items"] == 1
    assert result["operational_quality"]["snippet_only_items"] == 2
    assert result["operational_quality"]["direct_article_text_share"] == 0.3333
    assert result["operational_quality"]["deterministic_fallback_rate"] == 0


def test_benchmark_evaluator_rejects_non_boolean_claim_labels(tmp_path):
    path = tmp_path / "bad-labels.jsonl"
    path.write_text(json.dumps({
        "case_id": "candidate-1",
        "label_status": "human_reviewed",
        "expected_relevant_ids": ["a"],
        "retrieved_ids": ["a"],
        "claim_support_labels": ["false"],
    }) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid labels"):
        evaluate(path)


def test_benchmark_case_loader_requires_unique_ids(tmp_path):
    path = tmp_path / "questions.jsonl"
    path.write_text(
        '{"case_id":"same","question":"Question one"}\n'
        '{"case_id":"same","question":"Question two"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unique"):
        load_cases(path)



def test_benchmark_metrics_cover_field_accuracy_unknown_handling_and_conflicts():
    from src.engines.research_quality import benchmark_metrics

    result = benchmark_metrics(
        expected_ids=["source-a", "source-b"],
        retrieved_ids=["source-a", "source-c"],
        relevant_claims=[True, False, True],
        field_accuracy_labels=[True, True, False, True],
        unknown_handling_labels=[True, False],
        expected_conflict_ids=["Acme:USD", "Beta:EUR"],
        detected_conflict_ids=["Acme:USD", "Gamma:GBP"],
    )
    assert result["retrieval_precision"] == 0.5
    assert result["retrieval_recall"] == 0.5
    assert result["claim_support_rate"] == 0.6667
    assert result["field_accuracy_rate"] == 0.75
    assert result["unknown_handling_rate"] == 0.5
    assert result["conflict_detection"]["precision"] == 0.5
    assert result["conflict_detection"]["recall"] == 0.5


def test_benchmark_metrics_reject_non_boolean_field_labels():
    from src.engines.research_quality import benchmark_metrics

    with pytest.raises(ValueError, match="true/false booleans"):
        benchmark_metrics(["a"], ["a"], field_accuracy_labels=["yes"])



def test_empty_retrieval_labels_are_not_reported_as_perfect_recall():
    from src.engines.research_quality import benchmark_metrics

    empty = benchmark_metrics([], [])
    assert empty["retrieval_precision"] is None
    assert empty["retrieval_recall"] is None

    missed = benchmark_metrics(["expected-source"], [])
    assert missed["retrieval_precision"] == 0
    assert missed["retrieval_recall"] == 0

    unsupported = benchmark_metrics([], ["irrelevant-source"])
    assert unsupported["retrieval_precision"] == 0
    assert unsupported["retrieval_recall"] is None



def test_benchmark_runner_exports_evidence_for_independent_review(tmp_path, monkeypatch):
    from scripts import run_research_benchmark as runner

    questions = tmp_path / "questions.jsonl"
    output = tmp_path / "review.jsonl"
    questions.write_text(
        json.dumps({"case_id": "case-1", "question": "Verify a funding announcement"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner.deals_mod, "load_deals", lambda: {"deal-1": {"company": "Acme"}})
    monkeypatch.setattr(runner, "load_json", lambda *args, **kwargs: [])
    monkeypatch.setattr(runner.research_mod, "research", lambda *args, **kwargs: {
        "evidence": [{
            "n": 1, "title": "Acme announcement", "url": "https://example.com/announcement",
            "date": "2026-10-01", "source": "Acme", "source_quality": "Official / primary",
            "content_status": "article_text_retrieved", "text": "Acme announced a round.",
        }],
        "answer": "Acme announced a round [1].",
        "mode": "deterministic",
        "model": None,
        "query_plan": ["Acme official announcement"],
        "limitations": ["Search is a bounded sample."],
        "conflicts": [],
    })
    result = runner.run(questions, output, live_news=False)
    row = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
    assert result["cases"] == 1
    assert row["label_status"] == "needs_independent_human_review"
    assert row["retrieved_ids"] == ["https://example.com/announcement"]
    assert row["evidence"][0]["content_status"] == "article_text_retrieved"
    assert row["mode"] == "deterministic"
    assert row["latency_seconds"] >= 0



def test_conflict_metrics_are_undefined_when_no_conflicts_are_labelled():
    from src.engines.research_quality import benchmark_metrics

    result = benchmark_metrics(
        expected_ids=["source-a"],
        retrieved_ids=["source-a"],
        expected_conflict_ids=[],
        detected_conflict_ids=[],
    )
    assert result["conflict_detection"]["precision"] is None
    assert result["conflict_detection"]["recall"] is None


def test_benchmark_runner_records_question_failure_and_continues(tmp_path, monkeypatch):
    from scripts import run_research_benchmark as runner

    questions = tmp_path / "questions.jsonl"
    output = tmp_path / "review.jsonl"
    questions.write_text(
        json.dumps({"case_id": "case-fails", "question": "Question that fails"}) + "\\n"
        + json.dumps({"case_id": "case-works", "question": "Question that works"}) + "\\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner.deals_mod, "load_deals", lambda: {})
    monkeypatch.setattr(runner, "load_json", lambda *args, **kwargs: [])
    calls = {"count": 0}

    def fake_research(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary provider failure")
        return {"evidence": [], "answer": "Insufficient evidence", "mode": "deterministic"}

    monkeypatch.setattr(runner.research_mod, "research", fake_research)
    result = runner.run(questions, output, live_news=False)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert result["cases"] == 2
    assert result["failed_cases"] == 1
    assert rows[0]["run_status"] == "error"
    assert "temporary provider failure" in rows[0]["run_error"]
    assert rows[1]["run_status"] == "completed"
