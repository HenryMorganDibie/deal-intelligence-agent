"""Run candidate research benchmark questions and export evidence for human review.

This creates an unlabelled review packet. It does not claim accuracy or compute benchmark
scores. Reviewers must independently label relevant sources and material claims.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from src.engines import deals as deals_mod
from src.engines import research as research_mod
from src.utils.paths import DATA_DIR
from src.utils.storage import load_json


def load_cases(path: Path) -> list[dict]:
    cases = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
        if not row.get("case_id") or not row.get("question"):
            raise ValueError(f"Line {line_number} requires case_id and question")
        cases.append(row)
    if not cases:
        raise ValueError("No benchmark questions found")
    if len({row["case_id"] for row in cases}) != len(cases):
        raise ValueError("case_id values must be unique")
    return cases


def run(path: Path, output: Path, live_news: bool = True) -> dict:
    cases = load_cases(path)
    deals = list(deals_mod.load_deals().values())
    events = load_json(DATA_DIR / "events.json", list)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        for case in cases:
            started = time.monotonic()
            result = research_mod.research(
                case["question"], deals=deals, events=events, live_news=live_news
            )
            evidence = result.get("evidence", [])
            retrieved_ids = [
                str(item.get("url") or f"title:{item.get('title', '')}").strip()
                for item in evidence
            ]
            record = {
                "case_id": case["case_id"],
                "question": case["question"],
                "label_status": "needs_independent_human_review",
                "retrieved_ids": retrieved_ids,
                "expected_relevant_ids": [],
                "claim_support_labels": [],
                "field_accuracy_labels": [],
                "unknown_handling_labels": [],
                "expected_conflict_ids": [],
                "detected_conflict_ids": [str(conflict.get("company", "")) + ":" + str(conflict.get("currency", ""))
                                          for conflict in result.get("conflicts", [])],
                "answer": result.get("answer"),
                "mode": result.get("mode"),
                "model": result.get("model"),
                "query_plan": result.get("query_plan", []),
                "limitations": result.get("limitations", []),
                "conflicts": result.get("conflicts", []),
                "latency_seconds": round(time.monotonic() - started, 3),
                "evidence": [{
                    "id": str(item.get("url") or f"title:{item.get('title', '')}").strip(),
                    "n": item.get("n"),
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "date": item.get("date"),
                    "publisher": item.get("source"),
                    "source_quality": item.get("source_quality"),
                    "content_status": item.get("content_status"),
                    "text": item.get("text"),
                } for item in evidence],
                "review_instructions": (
                    "Before evaluation, independently mark relevant source IDs, review material claims "
                    "against the cited text, and set label_status to human_reviewed. Do not treat "
                    "citation presence as proof of support."
                ),
            }
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"cases": len(cases), "output": str(output), "live_news": live_news,
            "note": "Unlabelled candidate run only; not an accuracy benchmark until independently reviewed."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions", type=Path, help="JSONL file with case_id and question")
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL review packet")
    parser.add_argument("--no-live-news", action="store_true", help="Use local structured data only")
    args = parser.parse_args()
    print(json.dumps(run(args.questions, args.output, live_news=not args.no_live_news), indent=2))


if __name__ == "__main__":
    main()
