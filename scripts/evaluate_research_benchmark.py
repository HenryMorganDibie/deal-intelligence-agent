"""Evaluate saved, human-labelled research benchmark runs from JSONL.

Each line must include expected_relevant_ids, retrieved_ids, and optionally
claim_support_labels (true/false labels assigned by a reviewer).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.engines.research_quality import benchmark_metrics


def evaluate(path: Path) -> dict:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
        for field in ("case_id", "expected_relevant_ids", "retrieved_ids"):
            if field not in case:
                raise ValueError(f"Line {line_number} is missing required field {field!r}")
        rows.append({
            "case_id": case["case_id"],
            **benchmark_metrics(case["expected_relevant_ids"], case["retrieved_ids"],
                                case.get("claim_support_labels")),
        })
    if not rows:
        raise ValueError("No benchmark cases found.")
    return {
        "cases": len(rows),
        "retrieval_precision_macro": round(sum(r["retrieval_precision"] for r in rows) / len(rows), 4),
        "retrieval_recall_macro": round(sum(r["retrieval_recall"] for r in rows) / len(rows), 4),
        "claim_support_rate_macro": (
            round(sum(r["claim_support_rate"] for r in rows if r["claim_support_rate"] is not None)
                  / sum(r["claim_support_rate"] is not None for r in rows), 4)
            if any(r["claim_support_rate"] is not None for r in rows) else None
        ),
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
