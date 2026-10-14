"""
Score the rule engine's subject attribution on the labelled adversarial cases.

    python -m evaluation.attribution.score     # writes evaluation/attribution/results.json

Each case is a headline (and optional snippet) with a target company and the signal types the
text genuinely reports about that company. The cases were written without access to the
engine, to probe known weaknesses of clause-level matching: pronouns, aliases, subsidiaries and
parents, multi-party deals, omitted subjects, negation, rumours and hypotheticals, and historical
references. The engine is run exactly as on a news item: the company must be named, then the
target-attributed rules fire, then weak hits (score below 0.20 at a typical 0.70 news credibility)
are dropped.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from src.engines.deterministic_engine import _company_matchers, _mentions_company, match_rules_for_target
from src.engines.evaluation_report import wilson

HERE = Path(__file__).resolve().parent
NEWS_CREDIBILITY = 0.70


def predict(case: dict) -> set[str]:
    text = f"{case['title']} {case.get('snippet') or ''}".strip()
    matchers = _company_matchers(case["company"], ticker=case.get("ticker"))
    if not _mentions_company(text, matchers):
        return set()
    return {t.value for t, _, score in match_rules_for_target(text, matchers) if score * NEWS_CREDIBILITY >= 0.20}


def main(prefix: str = "") -> dict:
    cases = json.loads((HERE / f"{prefix}cases.json").read_text())
    per_cat: dict[str, dict] = defaultdict(lambda: {"cases": 0, "exact": 0, "fp_cases": 0, "neg_cases": 0,
                                                    "tp": 0, "fp": 0, "fn": 0})
    errors = []
    tot = {"tp": 0, "fp": 0, "fn": 0}
    for c in cases:
        gold, pred = set(c["expected"]), predict(c)
        s = per_cat[c["category"]]
        s["cases"] += 1
        s["exact"] += gold == pred
        if not gold:
            s["neg_cases"] += 1
            s["fp_cases"] += bool(pred)
        tp, fp, fn = len(gold & pred), len(pred - gold), len(gold - pred)
        for k, v in (("tp", tp), ("fp", fp), ("fn", fn)):
            s[k] += v
            tot[k] += v
        if gold != pred:
            errors.append({"id": c["id"], "category": c["category"], "company": c["company"], "title": c["title"],
                           "snippet": c.get("snippet"), "expected": sorted(gold), "predicted": sorted(pred),
                           "false_positive": sorted(pred - gold), "false_negative": sorted(gold - pred), "note": c["note"]})
    by_category = {}
    for cat, s in sorted(per_cat.items()):
        by_category[cat] = {
            "cases": s["cases"],
            "exactly_right": wilson(s["exact"], s["cases"]),
            "false_alarm_rate_on_no_event_cases": wilson(s["fp_cases"], s["neg_cases"]),
            "precision": wilson(s["tp"], s["tp"] + s["fp"]),
            "recall": wilson(s["tp"], s["tp"] + s["fn"]),
        }
    neg = [c for c in cases if not c["expected"]]
    results = {
        "cases": len(cases),
        "overall": {
            "exactly_right": wilson(sum(by_category[k]["exactly_right"]["k"] for k in by_category), len(cases)),
            "precision": wilson(tot["tp"], tot["tp"] + tot["fp"]),
            "recall": wilson(tot["tp"], tot["tp"] + tot["fn"]),
            "false_alarm_rate_on_no_event_cases": wilson(sum(bool(predict(c)) for c in neg), len(neg)),
        },
        "by_category": by_category,
        "labels": "Cases and gold labels written blind to the engine by an AI annotator; each case carries its "
                  "reasoning. Pending independent human review.",
    }
    results["set"] = ("held-out: written after the rule changes, never used to tune" if prefix else
                      "development: rule changes were made after reading its errors, so post-fix results are optimistic")
    (HERE / f"{prefix}results.json").write_text(json.dumps(results, indent=1))
    (HERE / f"{prefix}errors.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in errors))
    return results


if __name__ == "__main__":
    import sys
    r = main("heldout_" if "--heldout" in sys.argv else "")
    print(json.dumps(r["overall"], indent=1))
    for k, v in r["by_category"].items():
        f = lambda x: f"{x['value']:.2f} ({x['k']}/{x['n']})" if x else "n/a"
        print(f"{k:22} exact {f(v['exactly_right'])}  false-alarm {f(v['false_alarm_rate_on_no_event_cases'])}  "
              f"P {f(v['precision'])}  R {f(v['recall'])}")
