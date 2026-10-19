"""Evaluate saved, human-labelled research benchmark runs from JSONL.

Each line must include expected_relevant_ids, retrieved_ids, and optionally
claim_support_labels (true/false labels assigned by a reviewer).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.engines.research_quality import benchmark_metrics


def _macro(rows: list[dict], field: str) -> float | None:
    values = [row[field] for row in rows if row.get(field) is not None]
    return round(sum(values) / len(values), 4) if values else None


def _aggregate_conflicts(rows: list[dict]) -> dict | None:
    values = [row["conflict_detection"] for row in rows if row.get("conflict_detection") is not None]
    if not values:
        return None
    expected = sum(value["expected"] for value in values)
    detected = sum(value["detected"] for value in values)
    # Per-case metrics do not retain conflict IDs, so aggregate counts conservatively from
    # per-case precision/recall and report macro rates instead of fabricating pooled counts.
    return {
        "precision_macro": round(sum(value["precision"] for value in values) / len(values), 4),
        "recall_macro": round(sum(value["recall"] for value in values) / len(values), 4),
        "cases": len(values),
        "expected_conflicts": expected,
        "detected_conflicts": detected,
    }


def evaluate(path: Path) -> dict:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
        if case.get("label_status") != "human_reviewed":
            continue
        for field in ("case_id", "expected_relevant_ids", "retrieved_ids"):
            if field not in case:
                raise ValueError(f"Line {line_number} is missing required field {field!r}")
        label_fields = ("claim_support_labels", "field_accuracy_labels", "unknown_handling_labels")
        for label_field in label_fields:
            labels = case.get(label_field, [])
            if not isinstance(labels, list) or any(type(label) is not bool for label in labels):
                raise ValueError(f"Line {line_number} has invalid labels in {label_field}")
        rows.append({
            "case_id": case["case_id"],
            **benchmark_metrics(
                case["expected_relevant_ids"], case["retrieved_ids"],
                case.get("claim_support_labels"), case.get("field_accuracy_labels"),
                case.get("unknown_handling_labels"), case.get("expected_conflict_ids"),
                case.get("detected_conflict_ids"),
            ),
        })
    if not rows:
        raise ValueError("No reviewed benchmark cases found; independently label cases and set label_status to human_reviewed.")
    return {
        "cases": len(rows),
        "retrieval_precision_macro": round(sum(r["retrieval_precision"] for r in rows) / len(rows), 4),
        "retrieval_recall_macro": round(sum(r["retrieval_recall"] for r in rows) / len(rows), 4),
        "claim_support_rate_macro": _macro(rows, "claim_support_rate"),
        "field_accuracy_rate_macro": _macro(rows, "field_accuracy_rate"),
        "unknown_handling_rate_macro": _macro(rows, "unknown_handling_rate"),
        "conflict_detection": _aggregate_conflicts(rows),
        "per_case": rows,
        "note": "Metrics are only as reliable as the human-reviewed labels in the input file.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", type=Path, help="Human-labelled benchmark results in JSONL format")
    parser.add_argument("--output", type=Path, help="Optional path for a JSON report")
    args = parser.parse_args()
    report = evaluate(args.jsonl)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
