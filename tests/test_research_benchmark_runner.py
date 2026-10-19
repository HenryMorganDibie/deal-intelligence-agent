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
    }) + "\\n", encoding="utf-8")
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
        },
        {
            "case_id": "candidate-2",
            "label_status": "needs_independent_human_review",
            "expected_relevant_ids": [],
            "retrieved_ids": ["x"],
            "claim_support_labels": [],
        },
    ]
    path.write_text("\\n".join(json.dumps(case) for case in cases) + "\\n", encoding="utf-8")
    result = evaluate(path)
    assert result["cases"] == 1
    assert result["retrieval_precision_macro"] == 0.5
    assert result["retrieval_recall_macro"] == 0.5
    assert result["claim_support_rate_macro"] == 0.5


def test_benchmark_evaluator_rejects_non_boolean_claim_labels(tmp_path):
    path = tmp_path / "bad-labels.jsonl"
    path.write_text(json.dumps({
        "case_id": "candidate-1",
        "label_status": "human_reviewed",
        "expected_relevant_ids": ["a"],
        "retrieved_ids": ["a"],
        "claim_support_labels": ["false"],
    }) + "\\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid claim support labels"):
        evaluate(path)


def test_benchmark_case_loader_requires_unique_ids(tmp_path):
    path = tmp_path / "questions.jsonl"
    path.write_text(
        '{"case_id":"same","question":"Question one"}\\n'
        '{"case_id":"same","question":"Question two"}\\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unique"):
        load_cases(path)
