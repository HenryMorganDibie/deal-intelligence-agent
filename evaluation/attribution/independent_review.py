"""Build and score a blind, independently reviewed attribution evaluation set.

Build once with:
    python -m evaluation.attribution.independent_review build

After two reviewers independently annotate the separate review files and a
third reviewer adjudicates disagreements, score with:
    python -m evaluation.attribution.independent_review score
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
QUEUE = ROOT / "docs" / "automation" / "event_label_queue.jsonl"
ITEMS = HERE / "independent_items.jsonl"
REVIEW_A = HERE / "independent_review_a.jsonl"
REVIEW_B = HERE / "independent_review_b.jsonl"
LABELS = HERE / "independent_adjudicated_labels.jsonl"
RESULTS = HERE / "independent_results.json"
ERRORS = HERE / "independent_errors.jsonl"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _normalise_title(title: str) -> str:
    return re.sub(r"\W+", " ", title.lower()).strip()


def _existing_keys() -> set[str]:
    keys = set()
    for filename in ("natural_items.jsonl", "hard_items.jsonl"):
        for row in _read_jsonl(HERE / filename):
            keys.add(_normalise_title(row.get("title", "")))
            if row.get("url"):
                keys.add(row["url"])
    return keys


def build() -> dict:
    """Create immutable blind items and independent reviewer templates once."""
    paths = (ITEMS, REVIEW_A, REVIEW_B)
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(
            "Refusing to overwrite independent review work: " + ", ".join(existing)
        )
    if not QUEUE.exists():
        raise FileNotFoundError(f"Fresh review queue not found: {QUEUE}")

    old_keys = _existing_keys()
    candidates = []
    seen = set()
    for row in _read_jsonl(QUEUE):
        title = str(row.get("title") or "").strip()
        url = str(row.get("url") or "").strip()
        normalised = _normalise_title(title)
        if (
            not title
            or row.get("review_split") != "holdout"
            or row.get("label") is not None
            or normalised in old_keys
            or (url and url in old_keys)
            or normalised in seen
        ):
            continue
        seen.add(normalised)
        candidates.append(row)

    candidates.sort(
        key=lambda row: hashlib.sha256(
            _normalise_title(row["title"]).encode("utf-8")
        ).hexdigest()
    )
    items = []
    for row in candidates:
        title = str(row["title"]).strip()
        source_review_id = row.get("id")
        if not isinstance(source_review_id, str) or not source_review_id:
            raise ValueError(f"Holdout review item has no stable id: {title[:80]}")
        item_id = "i" + hashlib.sha256(
            (title + "\n" + str(row.get("url") or "")).encode("utf-8")
        ).hexdigest()[:12]
        items.append({
            "item_id": item_id,
            "source_review_id": source_review_id,
            "title": title,
            "snippet": str(row.get("snippet") or ""),
            "publisher": str(row.get("publisher") or ""),
            "date": row.get("published"),
            "url": str(row.get("url") or ""),
            "source_scope": "African business headline feed",
        })

    def review_template(item: dict) -> dict:
        return {
            "item_id": item["item_id"],
            "target_company": None,
            "ticker": None,
            "expected": None,
            "confidence": None,
            "reviewer": None,
            "note": "",
        }

    _write_jsonl(ITEMS, items)
    _write_jsonl(REVIEW_A, [review_template(item) for item in items])
    _write_jsonl(REVIEW_B, [review_template(item) for item in items])
    return {"status": "awaiting_independent_review", "items": len(items)}


def _validate_review(review: dict, item_ids: set[str], filename: str) -> None:
    if review.get("item_id") not in item_ids:
        raise ValueError(f"Unknown item_id in {filename}: {review.get('item_id')}")
    if not isinstance(review.get("target_company"), str) or not review["target_company"].strip():
        raise ValueError(f"Missing target_company for {review['item_id']} in {filename}")
    expected = review.get("expected")
    if not isinstance(expected, list) or not all(isinstance(x, str) for x in expected):
        raise ValueError(f"expected must be a list of signal types for {review['item_id']} in {filename}")
    if review.get("confidence") not in {"high", "medium", "low"}:
        raise ValueError(f"Invalid confidence for {review['item_id']} in {filename}")
    if review.get("target_company") == "__no_target__" and expected:
        raise ValueError(f"No-target label must have no expected events for {review['item_id']} in {filename}")
    if not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
        raise ValueError(f"Missing reviewer identity for {review['item_id']} in {filename}")


def _stats(rows: list[tuple[set[str], set[str]]]) -> dict:
    from src.engines.evaluation_report import wilson

    tp = sum(len(expected & predicted) for expected, predicted in rows)
    fp = sum(len(predicted - expected) for expected, predicted in rows)
    fn = sum(len(expected - predicted) for expected, predicted in rows)
    negatives = [(expected, predicted) for expected, predicted in rows if not expected]
    exact = sum(expected == predicted for expected, predicted in rows)
    false_alarms = sum(bool(predicted) for _, predicted in negatives)
    return {
        "items": len(rows),
        "exactly_right": wilson(exact, len(rows)),
        "precision": wilson(tp, tp + fp),
        "recall": wilson(tp, tp + fn),
        "false_alarm_rate_on_no_event_items": wilson(false_alarms, len(negatives)),
    }


def score() -> dict:
    """Score only adjudicated labels after verifying reviewer agreement."""
    items = _read_jsonl(ITEMS)
    if not items:
        raise FileNotFoundError(f"No blind review items found; run build first: {ITEMS}")
    labels = _read_jsonl(LABELS)
    if not labels:
        raise ValueError(f"No adjudicated labels found; human review is required: {LABELS}")
    ids = {item["item_id"] for item in items}
    if len(ids) != len(items):
        raise ValueError("Duplicate item_id in independent review items")

    review_a_rows = _read_jsonl(REVIEW_A)
    review_b_rows = _read_jsonl(REVIEW_B)
    review_a = {row.get("item_id"): row for row in review_a_rows}
    review_b = {row.get("item_id"): row for row in review_b_rows}
    if len(review_a) != len(review_a_rows) or len(review_b) != len(review_b_rows):
        raise ValueError("Duplicate item_id in independent reviewer files")
    if set(review_a) != ids or set(review_b) != ids:
        raise ValueError("Both independent reviewer files must cover every item exactly once")
    for row in review_a.values():
        _validate_review(row, ids, REVIEW_A.name)
    for row in review_b.values():
        _validate_review(row, ids, REVIEW_B.name)
    adjudicated = {}
    for label in labels:
        item_id = label.get("item_id")
        if item_id not in ids:
            raise ValueError(f"Unknown item_id in {LABELS.name}: {item_id}")
        if label.get("target_company") == "__no_target__" and label.get("expected"):
            raise ValueError(f"No-target label must have no expected events for {item_id}")
        expected = label.get("expected")
        if not isinstance(expected, list) or not all(isinstance(x, str) for x in expected):
            raise ValueError(f"expected must be a list of signal types for {item_id}")
        if not isinstance(label.get("target_company"), str) or not label["target_company"].strip():
            raise ValueError(f"Missing target_company for {item_id}")
        if label.get("confidence") not in {"high", "medium", "low"}:
            raise ValueError(f"Invalid confidence for {item_id}")
        if not isinstance(label.get("adjudicated_by"), str) or not label["adjudicated_by"].strip():
            raise ValueError(f"Missing adjudicator identity for {item_id}")
        if not isinstance(label.get("reviewer_a"), str) or not isinstance(label.get("reviewer_b"), str):
            raise ValueError(f"Missing reviewer identities for {item_id}")
        if item_id in adjudicated:
            raise ValueError(f"Duplicate adjudicated label for {item_id}")
        if review_a[item_id].get("reviewer") == review_b[item_id].get("reviewer"):
            raise ValueError(f"Reviewers must be independent for {item_id}")
        if label.get("reviewer_a") != review_a[item_id]["reviewer"]:
            raise ValueError(f"reviewer_a does not match independent review for {item_id}")
        if label.get("reviewer_b") != review_b[item_id]["reviewer"]:
            raise ValueError(f"reviewer_b does not match independent review for {item_id}")
        if label.get("adjudicated_by") in {
            review_a[item_id].get("reviewer"), review_b[item_id].get("reviewer")
        }:
            raise ValueError(f"Adjudicator must differ from both reviewers for {item_id}")
        adjudicated[item_id] = label
    if set(adjudicated) != ids:
        raise ValueError(f"Expected labels for every item: {len(ids - set(adjudicated))} items remain")

    from src.engines.deterministic_engine import _company_matchers, match_rules_for_target
    from src.schemas.models import SignalType

    item_by_id = {item["item_id"]: item for item in items}
    rows, errors = [], []
    for item_id, label in adjudicated.items():
        expected = set(label["expected"])
        valid_types = {signal.value for signal in SignalType}
        if not expected <= valid_types:
            raise ValueError(f"Unknown signal type for {item_id}: {sorted(expected - valid_types)}")
        if label["target_company"] == "__no_target__":
            predicted = set()
        else:
            matchers = _company_matchers(label["target_company"], ticker=label.get("ticker"))
            predicted = {
                signal_type.value
                for signal_type, _, score in match_rules_for_target(item_by_id[item_id]["title"], matchers)
                if score * 0.70 >= 0.20
            }
        rows.append((expected, predicted, label["confidence"]))
        if expected != predicted:
            errors.append({
                "item_id": item_id,
                "title": item_by_id[item_id]["title"],
                "publisher": item_by_id[item_id]["publisher"],
                "date": item_by_id[item_id]["date"],
                "url": item_by_id[item_id]["url"],
                "target_company": label["target_company"],
                "expected": sorted(expected),
                "predicted": sorted(predicted),
            })

    disagreement_count = sum(
        review_a[item_id].get("target_company") != review_b[item_id].get("target_company")
        or set(review_a[item_id].get("expected") or []) != set(review_b[item_id].get("expected") or [])
        for item_id in ids
    )
    result = {
        "status": "independently_reviewed",
        "items": len(items),
        "labels": len(labels),
        "reviewers": "Two independent annotators with third-person adjudication of disagreements.",
        "source_scope": "Unlabeled holdout-split headlines from the African business feed, excluding prior evaluation items.",
        "independent_review_disagreements": disagreement_count,
        "results": {
            "all_labels": _stats([(expected, predicted) for expected, predicted, _ in rows]),
            "high_confidence_labels": _stats([
                (expected, predicted) for expected, predicted, confidence in rows if confidence == "high"
            ]),
        },
    }
    RESULTS.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    _write_jsonl(ERRORS, errors)
    return result


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "score"))
    args = parser.parse_args(argv)
    result = build() if args.command == "build" else score()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
