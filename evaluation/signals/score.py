"""Blind, paired evaluation of baseline vs PR #21 signal patterns.

Requires two independently completed label files and an adjudicated final file.
Run: python -m evaluation.signals.score
"""
from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

from src.engines.deterministic_engine import SIGNAL_RULES as CURRENT_RULES

HERE = Path(__file__).resolve().parent
BASELINE_REF = "8e02ff18bc10b486942050538d2431db8f2f0dd2"
SIGNAL_TYPES = (
    "m_and_a_activity", "credit_risk", "distressed_asset", "earnings_surprise",
    "leadership_change", "regulatory_action", "debt_restructuring", "insider_activity",
)
MARKETS = ("africa", "us", "other", "unclear")


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"Required file missing: {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _wilson(k: int, n: int) -> dict[str, Any]:
    if n == 0:
        return {"value": None, "k": 0, "n": 0, "ci95": None}
    z = 1.96
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {"value": round(p, 4), "k": k, "n": n,
            "ci95": [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]}


def _load_baseline_rules() -> list:
    try:
        source = subprocess.check_output(
            ["git", "show", f"{BASELINE_REF}:src/engines/deterministic_engine.py"],
            cwd=HERE.parents[2], text=True, stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"Cannot read baseline {BASELINE_REF}; fetch it first with "
            f"'git fetch --no-tags origin {BASELINE_REF}'. {exc.stderr}"
        ) from exc
    namespace: dict[str, Any] = {"__name__": "_dealintel_baseline_engine"}
    exec(compile(source, f"{BASELINE_REF}:deterministic_engine.py", "exec"), namespace)
    return namespace["SIGNAL_RULES"]


def _predict(text: str, rules: list) -> set[str]:
    out = set()
    for signal_type, patterns, _score in rules:
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns):
            out.add(signal_type.value)
    return out


def _validate_labels(items: list[dict], labels: list[dict]) -> dict[str, dict]:
    by_id = {r.get("item_id"): r for r in labels}
    expected = {r["item_id"] for r in items}
    if set(by_id) != expected:
        missing, extra = sorted(expected - set(by_id)), sorted(set(by_id) - expected)
        raise SystemExit(f"Adjudicated labels must cover every item exactly once; missing={missing[:5]}, extra={extra[:5]}")
    for item_id, row in by_id.items():
        types = row.get("signal_types")
        if not isinstance(types, list) or any(t not in SIGNAL_TYPES for t in types):
            raise SystemExit(f"{item_id}: signal_types must be a list of canonical labels; [] means no signal")
        if row.get("confidence") not in {"high", "medium", "low"}:
            raise SystemExit(f"{item_id}: confidence must be high, medium or low")
        if row.get("market", "unclear") not in MARKETS:
            raise SystemExit(f"{item_id}: market must be one of {MARKETS}")
    return by_id


def _score(items: list[dict], labels: dict[str, dict], rules: list, *, include_low: bool = False) -> dict:
    usable = [it for it in items if include_low or labels[it["item_id"]]["confidence"] != "low"]
    y_true = {it["item_id"]: set(labels[it["item_id"]]["signal_types"]) for it in usable}
    y_pred = {it["item_id"]: _predict(" ".join([it.get("title") or "", it.get("snippet") or ""]), rules) for it in usable}
    by_type = {}
    errors = []
    for typ in SIGNAL_TYPES:
        tp = fp = fn = 0
        for it in usable:
            ident = it["item_id"]
            actual, pred = typ in y_true[ident], typ in y_pred[ident]
            tp += actual and pred
            fp += (not actual) and pred
            fn += actual and (not pred)
            if pred and not actual:
                errors.append({"item_id": ident, "signal_type": typ, "error": "false_positive", "title": it["title"], "publisher": it.get("publisher"), "date": it.get("date")})
            elif actual and not pred:
                errors.append({"item_id": ident, "signal_type": typ, "error": "false_negative", "title": it["title"], "publisher": it.get("publisher"), "date": it.get("date")})
        p = _wilson(tp, tp + fp)
        r = _wilson(tp, tp + fn)
        f1 = (2 * tp / (2 * tp + fp + fn)) if 2 * tp + fp + fn else None
        by_type[typ] = {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": round(f1, 4) if f1 is not None else None}
    tp = sum(v["tp"] for v in by_type.values())
    fp = sum(v["fp"] for v in by_type.values())
    fn = sum(v["fn"] for v in by_type.values())
    overall = {"tp": tp, "fp": fp, "fn": fn, "precision": _wilson(tp, tp + fp), "recall": _wilson(tp, tp + fn),
               "f1": round(2 * tp / (2 * tp + fp + fn), 4) if 2 * tp + fp + fn else None}
    by_market = {}
    for market in MARKETS:
        subset = [it for it in usable if labels[it["item_id"]].get("market", "unclear") == market]
        if not subset:
            continue
        market_labels = {it["item_id"]: labels[it["item_id"]] for it in subset}
        by_market[market] = {"items": len(subset), "metrics": _score_market(subset, market_labels, rules)}
    return {"items": len(usable), "excluded_low_confidence": len(items) - len(usable), "overall_micro": overall,
            "by_signal_type": by_type, "by_market": by_market, "errors": errors}


def _score_market(items: list[dict], labels: dict[str, dict], rules: list) -> dict:
    tp = fp = fn = 0
    by_type = {}
    for typ in SIGNAL_TYPES:
        t = f = n = 0
        for it in items:
            actual = typ in labels[it["item_id"]]["signal_types"]
            pred = typ in _predict(" ".join([it.get("title") or "", it.get("snippet") or ""]), rules)
            t += actual and pred
            f += (not actual) and pred
            n += actual and (not pred)
        by_type[typ] = {"tp": t, "fp": f, "fn": n, "precision": _wilson(t, t + f), "recall": _wilson(t, t + n)}
        tp += t; fp += f; fn += n
    return {"tp": tp, "fp": fp, "fn": fn, "precision": _wilson(tp, tp + fp), "recall": _wilson(tp, tp + fn), "by_signal_type": by_type}


def main() -> None:
    items = _rows(HERE / "items.jsonl")
    for filename in ("labels_a.jsonl", "labels_b.jsonl"):
        rows = _rows(HERE / filename)
        if len(rows) != len(items) or any(not isinstance(r.get("signal_types"), list) for r in rows):
            raise SystemExit(f"{filename} is incomplete; each reviewer must label every item, using [] for no signal.")
    labels = _validate_labels(items, _rows(HERE / "adjudicated_labels.jsonl"))
    baseline = _load_baseline_rules()
    current = _score(items, labels, CURRENT_RULES)
    previous = _score(items, labels, baseline)
    current_all = _score(items, labels, CURRENT_RULES, include_low=True)
    previous_all = _score(items, labels, baseline, include_low=True)
    delta = {}
    for typ in SIGNAL_TYPES:
        old, new = previous["by_signal_type"][typ], current["by_signal_type"][typ]
        delta[typ] = {
            "baseline": {k: old[k] for k in ("tp", "fp", "fn", "precision", "recall", "f1")},
            "pr21": {k: new[k] for k in ("tp", "fp", "fn", "precision", "recall", "f1")},
            "delta_precision_pp": round(100 * ((new["precision"]["value"] or 0) - (old["precision"]["value"] or 0)), 2),
            "delta_recall_pp": round(100 * ((new["recall"]["value"] or 0) - (old["recall"]["value"] or 0)), 2),
            "delta_f1_pp": round(100 * ((new["f1"] or 0) - (old["f1"] or 0)), 2),
        }
    report = {
        "evaluation": "blind paired deterministic-pattern evaluation",
        "baseline_ref": BASELINE_REF,
        "current_ref": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE.parents[2], text=True).strip(),
        "sample_size": len(items),
        "primary": "medium/high confidence adjudicated labels; low-confidence items excluded",
        "baseline": {k: v for k, v in previous.items() if k != "errors"},
        "pr21": {k: v for k, v in current.items() if k != "errors"},
        "all_confidences_sensitivity_check": {"baseline": {k: v for k, v in previous_all.items() if k != "errors"}, "pr21": {k: v for k, v in current_all.items() if k != "errors"}},
        "delta_by_signal_type": delta,
        "method_limitations": [
            "The sample comes from the monitored business-news feed's pre-existing holdout split and is not a probability sample of all corporate news.",
            "Pattern-only title/snippet scoring is not end-to-end production signal scoring or a replacement for the walk-forward event-outcome backtest.",
            "Use a fresh untouched holdout if this set informs further rule changes."
        ],
    }
    (HERE / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (HERE / "errors.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in current["errors"]), encoding="utf-8")
    print(json.dumps({"sample_size": len(items), "baseline": previous["overall_micro"], "pr21": current["overall_micro"], "delta_by_signal_type": delta}, indent=2))


if __name__ == "__main__":
    main()
