"""
Score a year's review labels against what the system decided for each sampled headline.

    python -m evaluation.review.score --year 2026 --source automated
    python -m evaluation.review.score --year 2026 --source independent

Sources:
    independent   adjudicated_labels.jsonl / adjudicated_pair_labels.jsonl: the two annotators' labels after
                  adjudication. Only these are the independent review; scoring refuses an incomplete set.
    automated     automated_labels.jsonl / automated_pair_labels.jsonl: an automated review, published as such.
                  It is a check, not independent evidence.

The system's decision for each headline comes from pool.jsonl (matched on the normalised title): a deal
headline not held back is "accepted as a transaction"; an event headline or a held-back deal is not.
Pair decisions come from _pair_system.jsonl. Every rate carries its sample size and a 95% Wilson interval.
Results go to results_<source>.json in the year's folder.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Optional

from evaluation.review.build import HERE, _key
from src.engines import deals as dl

SOURCES = {
    "independent": ("adjudicated_labels.jsonl", "adjudicated_pair_labels.jsonl"),
    "automated": ("automated_labels.jsonl", "automated_pair_labels.jsonl"),
}


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip() and "_pool" not in line]


def wilson(k: int, n: int) -> dict:
    if not n:
        return {"rate": None, "k": 0, "n": 0, "ci95": None}
    p, z = k / n, 1.96
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return {"rate": round(p, 4), "k": k, "n": n, "ci95": [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]}


def _same_name(a: Optional[str], b: Optional[str]) -> bool:
    na, nb = dl.normalise_name(a or ""), dl.normalise_name(b or "")
    if not na or not nb:
        return False
    return na == nb or set(na.split()) <= set(nb.split()) or set(nb.split()) <= set(na.split())


def score(year: int, source: str) -> dict:
    folder = HERE / str(year)
    item_file, pair_file = SOURCES[source]
    if not (folder / item_file).exists() or not (folder / pair_file).exists():
        raise SystemExit(f"No {source} labels for {year} yet ({item_file}, {pair_file}).")
    labels = {r["item_id"]: r for r in _rows(folder / item_file)}
    pair_labels = {r["item_id"]: r for r in _rows(folder / pair_file)}
    items = _rows(folder / "items.jsonl")
    pairs = _rows(folder / "pairs.jsonl")
    if source == "independent" and (len(labels) < len(items) or len(pair_labels) < len(pairs)):
        raise SystemExit("The adjudicated label set is incomplete; the independent review cannot be scored yet.")
    strata = {r["item_id"]: r["stratum"] for r in _rows(folder / "_strata.jsonl")}
    pair_system = {r["item_id"]: r["system"] for r in _rows(folder / "_pair_system.jsonl")}
    pool = {}
    for r in _rows(folder / "pool.jsonl"):
        pool.setdefault(_key(r["title"]), r)

    accepted_true = accepted_n = 0
    random_true = random_n = 0
    missed = negatives = 0
    type_ok = type_n = amount_ok = amount_n = target_ok = target_n = 0
    errors = []
    for it in items:
        label = labels.get(it["item_id"])
        system = pool.get(_key(it["title"]))
        if not label or label.get("is_transaction") is None or not system:
            continue
        accepted = system.get("kind") == "deal" and not system.get("excluded")
        real = bool(label["is_transaction"]) and label.get("in_scope") is not False
        if label["is_transaction"] and label.get("in_scope") is None:
            continue                                       # scope undecided: not counted either way
        if accepted:
            accepted_n += 1
            accepted_true += real
            if strata.get(it["item_id"]) == "random":
                random_n += 1
                random_true += real
            if not real:
                errors.append({"item_id": it["item_id"], "title": it["title"], "error": "accepted, but not an in-scope transaction"})
                continue
            if label.get("deal_type"):
                type_n += 1
                ok = system.get("deal_type") == label["deal_type"]
                type_ok += ok
                if not ok:
                    errors.append({"item_id": it["item_id"], "title": it["title"],
                                   "error": f"deal type {system.get('deal_type')} (label {label['deal_type']})"})
            # A record can merge several reports, so a headline without a figure may sit on a record whose
            # amount came from another report; only a stated deal size in US dollars is compared.
            if label.get("amount_kind") == "deal_size" and label.get("currency") == "USD" and label.get("amount"):
                amount_n += 1
                usd = system.get("usd")
                ok = bool(usd) and abs(usd - label["amount"]) <= 0.05 * label["amount"]
                amount_ok += ok
                if not ok:
                    errors.append({"item_id": it["item_id"], "title": it["title"],
                                   "error": f"amount {usd} (label {label['amount']} USD)"})
            if label.get("target"):
                target_n += 1
                ok = _same_name(system.get("target"), label["target"])
                target_ok += ok
                if not ok:
                    errors.append({"item_id": it["item_id"], "title": it["title"],
                                   "error": f"target {system.get('target')!r} (label {label['target']!r})"})
        else:
            negatives += 1
            missed += real
            if real:
                errors.append({"item_id": it["item_id"], "title": it["title"], "error": "a real transaction the system did not accept"})

    merged_same = merged_n = apart_diff = apart_n = 0
    for p in pairs:
        label = pair_labels.get(p["item_id"])
        if not label or label.get("same_transaction") is None:
            continue
        if pair_system.get(p["item_id"]) == "merged":
            merged_n += 1
            merged_same += bool(label["same_transaction"])
        else:
            apart_n += 1
            apart_diff += not label["same_transaction"]

    return {
        "year": year, "source": source,
        "independent": source == "independent",
        "label": "Independent review (two annotators, adjudicated)" if source == "independent"
                 else "Automated review: a check on the same sample, not independent evidence",
        "transaction_precision": wilson(accepted_true, accepted_n),
        "transaction_precision_random_stratum": wilson(random_true, random_n),
        "missed_transactions_among_rejected": wilson(missed, negatives),
        "deal_type_accuracy": wilson(type_ok, type_n),
        "amount_accuracy": wilson(amount_ok, amount_n),
        "target_accuracy": wilson(target_ok, target_n),
        "merge_precision": wilson(merged_same, merged_n),
        "kept_apart_correct": wilson(apart_diff, apart_n),
        "errors": errors,
        "notes": ("Amounts are compared only where the headline states a deal size in US dollars. Items whose "
                  "scope the reviewer could not decide are left out. Hard strata over-sample difficult cases; the "
                  "random-stratum precision is the unbiased estimate."),
    }


def main(args: list[str]) -> None:
    year = int(args[args.index("--year") + 1])
    source = args[args.index("--source") + 1] if "--source" in args else "automated"
    result = score(year, source)
    out = HERE / str(year) / f"results_{source}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    for k, v in result.items():
        if isinstance(v, dict) and "rate" in v:
            print(f"{k:42s} {v['rate']}  ({v['k']}/{v['n']}, 95% CI {v['ci95']})")
    print(f"-> {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
