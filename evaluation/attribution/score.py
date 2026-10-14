"""
Score the rule engine's attribution on real headlines.

    python -m evaluation.attribution.score            # writes results.json and errors.jsonl

For each labelled headline the engine is run exactly as on a news item: the target must be named
(by its name or ticker), the target-attributed rules fire, and weak hits (score below 0.20 at a
typical 0.70 news credibility) are dropped. Results are reported for the natural sample (rates as
they occur) and the hard-case sample (by failure mode), each with 95% Wilson intervals.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

from src.engines.deterministic_engine import _company_matchers, _mentions_company, match_rules_for_target
try:
    from src.engines.evaluation_report import wilson
except ImportError:                       # scoring an older engine checkout, before evaluation_report existed
    import math

    def wilson(k: int, n: int) -> Optional[dict]:
        if not n:
            return None
        p, z = k / n, 1.96
        d = 1 + z * z / n
        c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
        return {"value": round(p, 3), "low": round(max(0.0, c - h), 3), "high": round(min(1.0, c + h), 3), "k": k, "n": n}

HERE = Path(__file__).resolve().parent
NEWS_CREDIBILITY = 0.70


def predict(item: dict) -> set[str]:
    matchers = _company_matchers(item["company"], ticker=item.get("ticker"))
    if not _mentions_company(item["title"], matchers):
        return set()
    return {t.value for t, _, s in match_rules_for_target(item["title"], matchers) if s * NEWS_CREDIBILITY >= 0.20}


def _load(name: str) -> list[dict]:
    path = HERE / name
    return [json.loads(line) for line in path.open()] if path.exists() else []


def _stats(rows: list[tuple[dict, set, set]]) -> dict:
    tp = sum(len(g & p) for _, g, p in rows)
    fp = sum(len(p - g) for _, g, p in rows)
    fn = sum(len(g - p) for _, g, p in rows)
    neg = [(g, p) for _, g, p in rows if not g]
    return {
        "items": len(rows),
        "items_with_an_event": sum(1 for _, g, _ in rows if g),
        "exactly_right": wilson(sum(1 for _, g, p in rows if g == p), len(rows)),
        "precision": wilson(tp, tp + fp),
        "recall": wilson(tp, tp + fn),
        "false_alarm_rate_on_no_event_items": wilson(sum(1 for g, p in neg if p), len(neg)),
    }


def score(labels_prefix: str, items_name: str, group_key: str) -> tuple[Optional[dict], list[dict]]:
    items = {i["item_id"]: i for i in _load(items_name)}
    labels = _load(f"{labels_prefix}_labels.jsonl")
    if not labels:
        return None, []
    rows, errors = [], []
    for l in labels:
        it = items[l["item_id"]]
        gold, pred = set(l["expected"]), predict(it)
        rows.append((it | {"confidence": l["confidence"]}, gold, pred))
        if gold != pred:
            errors.append({"item_id": it["item_id"], "category": it["category"], "company": it["company"],
                           "title": it["title"], "publisher": it["publisher"], "date": it["date"], "url": it["url"],
                           "expected": sorted(gold), "predicted": sorted(pred), "label_note": l.get("note", "")})
    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        groups[r[0][group_key]].append(r)
    return {
        "overall": _stats(rows),
        "high_confidence_labels": _stats([r for r in rows if r[0]["confidence"] == "high"]),
        f"by_{group_key}": {k: _stats(v) for k, v in sorted(groups.items())},
    }, errors


def main() -> dict:
    natural, e1 = score("natural", "natural_items.jsonl", "market")
    hard, e2 = score("hard", "hard_items.jsonl", "category")
    results = {
        "natural": natural, "hard": hard,
        "sets": {
            "natural": "400 real headlines naming a tracked company (200 US, 200 African), drawn at random from the news "
                       "fetched for the 46 backtest companies: rates as they occur. The set to quote.",
            "hard": "280 real headlines selected by filters for known failure modes (40 each): denials, references back "
                    "to the company, subsidiaries and parents, two tracked companies, rumours and hypotheticals, historical "
                    "references, short names. Enriched on purpose; read it by category.",
        },
        "labels": "Labelled from the headline text alone, blind to the engine's output, by an AI annotator; every item "
                  "keeps its real publisher, date and link. Pending independent human review. Labelled after the rule "
                  "changes of 14 Oct 2026 and not used to tune them.",
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=1))
    (HERE / "errors.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in e1 + e2))
    return results


if __name__ == "__main__":
    r = main()
    f = lambda x: f"{x['value']:.2f} [{x['low']:.2f}-{x['high']:.2f}] ({x['k']}/{x['n']})" if x else "n/a"
    for name in ("natural", "hard"):
        if not r[name]:
            continue
        print(name, {k: f(v) if isinstance(v, dict) else v for k, v in r[name]["overall"].items()})
        key = "by_market" if name == "natural" else "by_category"
        for k, v in r[name][key].items():
            print(f"  {k:22} exact {f(v['exactly_right'])}  P {f(v['precision'])}  R {f(v['recall'])}  "
                  f"false-alarm {f(v['false_alarm_rate_on_no_event_items'])}")
