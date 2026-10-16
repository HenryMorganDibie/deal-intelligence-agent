from __future__ import annotations

import json

import pytest

from evaluation.attribution import independent_review as review


def test_build_creates_blind_items_and_separate_reviewer_templates(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "HERE", tmp_path)
    monkeypatch.setattr(review, "QUEUE", tmp_path / "queue.jsonl")
    monkeypatch.setattr(review, "ITEMS", tmp_path / "independent_items.jsonl")
    monkeypatch.setattr(review, "REVIEW_A", tmp_path / "review_a.jsonl")
    monkeypatch.setattr(review, "REVIEW_B", tmp_path / "review_b.jsonl")
    rows = [
        {"id": "fresh-1", "title": "Acme appoints a new CFO", "url": "https://example.test/1",
         "review_split": "holdout", "label": None, "rule_candidates": ["leadership_change"]},
        {"id": "train-1", "title": "Train example", "review_split": "train", "label": None},
        {"id": "labeled-1", "title": "Labeled example", "review_split": "holdout",
         "label": {"expected": []}},
    ]
    review.QUEUE.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (tmp_path / "natural_items.jsonl").write_text(
        json.dumps({"title": "Previously evaluated headline", "url": "https://example.test/old"}) + "\n",
        encoding="utf-8",
    )

    result = review.build()

    [item] = review._read_jsonl(review.ITEMS)
    [review_a] = review._read_jsonl(review.REVIEW_A)
    [review_b] = review._read_jsonl(review.REVIEW_B)
    assert result == {"status": "awaiting_independent_review", "items": 1}
    assert "rule_candidates" not in item
    assert review_a["item_id"] == review_b["item_id"] == item["item_id"]
    assert review_a["expected"] is None
    with pytest.raises(FileExistsError):
        review.build()


def test_score_refuses_to_publish_without_adjudicated_human_labels(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "HERE", tmp_path)
    monkeypatch.setattr(review, "ITEMS", tmp_path / "items.jsonl")
    monkeypatch.setattr(review, "REVIEW_A", tmp_path / "review_a.jsonl")
    monkeypatch.setattr(review, "REVIEW_B", tmp_path / "review_b.jsonl")
    monkeypatch.setattr(review, "LABELS", tmp_path / "adjudicated.jsonl")
    review.ITEMS.write_text(json.dumps({"item_id": "i1", "title": "Headline"}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="human review is required"):
        review.score()
