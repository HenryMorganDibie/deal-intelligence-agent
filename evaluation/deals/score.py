"""
Score the deal pipeline against the labelled evaluation sets.

    python -m evaluation.deals.score          # writes evaluation/deals/results.json and errors.jsonl

Labels (*_labels.jsonl) were made from the headline text alone, without access to the extractor's
output; see evaluation/README.md for how they were produced and their limits. Every metric carries
its sample size and a 95% Wilson interval, overall and for high-confidence labels only.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Optional

from src.engines import deals as dl
from src.engines import investors as inv
from src.engines.evaluation_report import wilson

HERE = Path(__file__).resolve().parent


def _load(name: str) -> list[dict]:
    return [json.loads(line) for line in (HERE / name).open()]


def _norm(name: Optional[str]) -> str:
    return dl.normalise_name(name or "")


def _name_match(gold: Optional[str], pred: Optional[str]) -> bool:
    """Same party: equal after normalisation, or one name contains the other ('Moniepoint' / 'Moniepoint Inc')."""
    g, p = _norm(gold), _norm(pred)
    if not g and not p:
        return True
    if not g or not p:
        return False
    return g == p or f" {g} " in f" {p} " or f" {p} " in f" {g} "


def _amount_match(gold: dict, pred: dict) -> bool:
    ga, pa = gold.get("amount"), pred.get("amount")
    if ga is None or pa is None:
        return ga is None and pa is None
    return (gold.get("currency") or "USD") == (pred.get("currency") or "USD") and abs(ga - pa) <= 0.01 * ga


def _group(counter_key: Callable[[dict], str], rows: list[dict], top: int = 8) -> Callable[[dict], str]:
    counts = Counter(counter_key(r) for r in rows)
    keep = {k for k, _ in counts.most_common(top)}
    return lambda r: counter_key(r) if counter_key(r) in keep else "other"


def _slice(rows: list[dict], key: Callable[[dict], str], metric: Callable[[list[dict]], Optional[dict]]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    return {k: metric(v) for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))}


def _raw_headlines() -> dict[str, dict]:
    """The stored feed records, so the extractor gets exactly the inputs it gets in production."""
    root = HERE.parents[1] / "data" / "headlines.jsonl"
    out: dict[str, dict] = {}
    for line in root.open():
        r = json.loads(line)
        out.setdefault(r["title"], r)
    return out


def extraction(prefix: str = "") -> tuple[dict, list[dict]]:
    items = {i["item_id"]: i for i in _load(f"{prefix}extraction_items.jsonl")}
    raw = _raw_headlines()
    rows, errors = [], []
    for g in _load(f"{prefix}extraction_labels.jsonl"):
        it = items[g["item_id"]]
        r = raw.get(it["title"], {})
        d = dl.extract_deal(it["title"], r.get("snippet", ""), published=it.get("date"), publisher=it.get("publisher") or "",
                            url=r.get("url", ""), country_hint=it.get("country_hint"),
                            africa_source=r.get("africa_source", False), rates=lambda c, y: None)
        rows.append({"item": it, "gold": g, "pred": d})

    def detection(rs: list[dict]) -> dict:
        tp = sum(1 for r in rs if r["gold"]["is_transaction"] and r["pred"])
        fp = sum(1 for r in rs if not r["gold"]["is_transaction"] and r["pred"])
        fn = sum(1 for r in rs if r["gold"]["is_transaction"] and not r["pred"])
        return {"n": len(rs), "precision": wilson(tp, tp + fp), "recall": wilson(tp, tp + fn)}

    both = [r for r in rows if r["gold"]["is_transaction"] and r["pred"]]
    fields: dict[str, Callable[[dict, dict], Optional[bool]]] = {
        "deal_type": lambda g, p: g["deal_type"] == p["deal_type"]
        or {g["deal_type"], p["deal_type"]} == {"acquisition", "merger"},
        "stage (announced / completed / rumoured)": lambda g, p: g["stage"] == p.get("stage"),
        "target": lambda g, p: _name_match(g["target"], p.get("target")),
        "buyer, lead investor or lender": lambda g, p: None if not g["acquirer_or_lead"] else (
            _name_match(g["acquirer_or_lead"], p.get("buyer"))
            or any(_name_match(g["acquirer_or_lead"], n) for n in p.get("investors") or [])),
        "amount disclosed or not": lambda g, p: (g["amount"] is None) == (p.get("amount") is None),
        "amount and currency (when disclosed)": lambda g, p: None if g["amount"] is None else _amount_match(g, p),
        "stake %": lambda g, p: None if g["stake_pct"] is None else (
            p.get("stake_pct") is not None and abs(p["stake_pct"] - g["stake_pct"]) < 0.5),
        "country": lambda g, p: None if not g["country"] else g["country"] in ([p.get("country")] + list(p.get("countries") or [])),
    }

    def field_acc(rs: list[dict], fn: Callable[[dict, dict], Optional[bool]]) -> Optional[dict]:
        vals = [v for v in (fn(r["gold"], r["pred"]) for r in rs) if v is not None]
        return wilson(sum(vals), len(vals))

    for r in rows:
        g, p = r["gold"], r["pred"]
        if bool(g["is_transaction"]) != bool(p):
            errors.append({"set": prefix + "extraction", "item_id": g["item_id"], "title": r["item"]["title"],
                           "error": "missed transaction" if g["is_transaction"] else "not a transaction",
                           "gold": g, "pred": p})
        elif p:
            wrong = [f for f, fn in fields.items() if fn(g, p) is False]
            if wrong:
                errors.append({"set": prefix + "extraction", "item_id": g["item_id"], "title": r["item"]["title"],
                               "error": "wrong fields: " + ", ".join(wrong), "gold": g, "pred": p})

    def complete(rs: list[dict]) -> Optional[dict]:
        """A record with every applicable field right."""
        ok = [all(fn(r["gold"], r["pred"]) is not False for fn in fields.values()) for r in rs]
        return wilson(sum(ok), len(ok))

    lang = lambda r: r["gold"].get("language") or "en"
    country = _group(lambda r: r["gold"].get("country") or r["item"].get("country_hint") or "unknown", rows)
    publisher = _group(lambda r: r["item"].get("publisher") or "unknown", rows)
    dtype = lambda r: r["gold"].get("deal_type") or "not a transaction"
    high = [r for r in rows if r["gold"]["confidence"] == "high"]
    out = {
        "items": len(rows), "gold_transactions": sum(r["gold"]["is_transaction"] for r in rows),
        "sample": ("120 headlines the extractor turned into a deal and 40 it rejected that contain transaction "
                   "vocabulary, drawn at random (seed 20261015) from stored raw headlines, excluding the development set; "
                   "built after the development-set fixes and never used to tune.") if prefix else (
                  "160 headlines the extractor turned into a deal and 60 it rejected that contain transaction "
                  "vocabulary, drawn at random (seed 20261014) from the stored raw headlines. Development set: "
                  "fixes were made after looking at its errors, so results after fixes are optimistic."),
        "note_on_recall": "Recall here is measured on a sample enriched for rejected deal-like headlines; it is a "
                          "measure of misses among plausible candidates, not of coverage of all deals that happened.",
        "detection": {"all": detection(rows), "high_confidence_labels": detection(high),
                      "by_language": _slice(rows, lang, detection), "by_country": _slice(rows, country, detection),
                      "by_publisher": _slice(rows, publisher, detection)},
        "fields": {"n_records": len(both),
                   "all": {f: field_acc(both, fn) for f, fn in fields.items()},
                   "high_confidence_labels": {f: field_acc([r for r in both if r["gold"]["confidence"] == "high"], fn)
                                              for f, fn in fields.items()},
                   "fully_correct_record": complete(both),
                   "by_deal_type": _slice(both, dtype, complete),
                   "by_country": _slice(both, country, complete),
                   "by_language": _slice(both, lang, complete)},
    }
    return out, errors


def _dedup_pair_diagnostics(pair: dict) -> dict:
    """Run the production extractor/matcher and explain the first gate that rejects a pair."""
    extracted = []
    for side in ("a", "b"):
        item = pair[side]
        deal = dl.extract_deal(
            item.get("title", ""),
            published=item.get("date"),
            publisher=item.get("publisher") or "",
            country_hint=item.get("country_hint"),
            rates=lambda _currency, _year: None,
        )
        if not deal:
            return {
                "same_deal": False,
                "diagnostics": {"blocked_by": "extraction_failed", "side": side, "title": item.get("title")},
            }
        extracted.append(deal)

    a, b = extracted
    from datetime import date

    try:
        gap = abs((date.fromisoformat(a["announced"][:10]) - date.fromisoformat(b["announced"][:10])).days)
    except (KeyError, TypeError, ValueError):
        gap = None

    types = {a.get("deal_type"), b.get("deal_type")}
    type_compatible = dl._same_transaction_type(a, b)
    name_match = dl._same_transaction_name(a, b)
    ua, ub = a.get("amount_usd"), b.get("amount_usd")
    diagnostics = {
        "a_extracted": {k: a.get(k) for k in ("target", "buyer", "deal_type", "announced", "amount_usd", "headline")},
        "b_extracted": {k: b.get(k) for k in ("target", "buyer", "deal_type", "announced", "amount_usd", "headline")},
        "date_gap_days": gap,
        "type_compatible": type_compatible,
        "name_match": name_match,
        "amount_usd": [ua, ub],
    }

    # Keep this gate order aligned with same_transaction(), so the diagnosis identifies
    # the first reason the production matcher rejects the pair.
    if gap is None:
        diagnostics["blocked_by"] = "invalid_or_missing_date"
        same = False
    elif not type_compatible:
        diagnostics["blocked_by"] = "incompatible_deal_types"
        same = False
    elif not name_match:
        diagnostics["blocked_by"] = "transaction_identity_mismatch"
        same = False
    elif not ua or not ub:
        ta, tb = dl._name_tokens(a.get("target")), dl._name_tokens(b.get("target"))
        ba, bb = dl._name_tokens(a.get("buyer")), dl._name_tokens(b.get("buyer"))
        same_buyer = bool(ba and bb and (ba <= bb or bb <= ba))
        same_target = bool(ta and tb and (ta <= tb or tb <= ta))
        same = gap <= 7 and same_buyer and same_target
        if not same:
            diagnostics["blocked_by"] = "undisclosed_amount_fallback"
    elif gap > 45:
        diagnostics["blocked_by"] = "date_window_exceeded"
        same = False
    elif abs(ua - ub) > 0.20 * max(ua, ub):
        diagnostics["blocked_by"] = "amount_difference_exceeded"
        same = False
    else:
        same = True

    diagnostics["same_deal"] = same
    return {"same_deal": same, "diagnostics": diagnostics}


def _dedup_pair_prediction(pair: dict) -> bool:
    """Compatibility wrapper for callers that only need the binary prediction."""
    return _dedup_pair_diagnostics(pair)["same_deal"]


def dedup() -> tuple[dict, list[dict]]:
    items = {i["item_id"]: i for i in _load("dedup_items.jsonl")}
    labels = _load("dedup_labels.jsonl")
    evaluations = {l["item_id"]: _dedup_pair_diagnostics(items[l["item_id"]]) for l in labels}
    predictions = {item_id: result["same_deal"] for item_id, result in evaluations.items()}
    tp = sum(predictions[l["item_id"]] and l["same_deal"] for l in labels)
    fp = sum(predictions[l["item_id"]] and not l["same_deal"] for l in labels)
    fn = sum(not predictions[l["item_id"]] and l["same_deal"] for l in labels)
    tn = sum(not predictions[l["item_id"]] and not l["same_deal"] for l in labels)

    # The previous published score used the saved _system decision, not a fresh run of the matcher.
    # Keep it for comparison, but report current code's metrics as the primary values.
    baseline_merged = [l for l in labels if items[l["item_id"]]["_system"] == "merged"]
    baseline_separate = [l for l in labels if items[l["item_id"]]["_system"] == "separate"]
    baseline = {
        "merge_precision": wilson(sum(l["same_deal"] for l in baseline_merged), len(baseline_merged)),
        "missed_duplicates_among_lookalikes": wilson(sum(l["same_deal"] for l in baseline_separate), len(baseline_separate)),
    }

    errors = []
    for l in labels:
        predicted_same = predictions[l["item_id"]]
        if predicted_same != l["same_deal"]:
            pair = items[l["item_id"]]
            errors.append({
                "set": "dedup_current",
                "item_id": l["item_id"],
                "error": "merged two different deals" if predicted_same else "missed duplicate",
                "a": pair["a"]["title"], "b": pair["b"]["title"],
                "gold": l, "predicted_same_deal": predicted_same,
                "historical_system_decision": pair.get("_system"),
                "diagnostics": evaluations[l["item_id"]]["diagnostics"],
            })
    return {
        "pairs": len(labels),
        "sample": "100 labelled report pairs. Metrics rerun the current extractor and matcher on each headline/date/publisher pair; historical saved decisions are retained as a baseline. This is a development set, not an unbiased production estimate.",
        "merge_precision": wilson(tp, tp + fp),
        "duplicate_recall": wilson(tp, tp + fn),
        "missed_duplicate_rate": wilson(fn, tp + fn),
        "missed_duplicates_among_lookalikes": wilson(fn, fn + tn),
        "baseline_saved_decisions": baseline,
        "confusion": {"true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn},
    }, errors


def identity() -> tuple[dict, list[dict]]:
    items = {i["item_id"]: i for i in _load("identity_items.jsonl")}
    labels = _load("identity_labels.jsonl")
    tp = fp = fn = 0
    errors = []
    flagged = kept = invalid = valid = 0
    for l in labels:
        it = items[l["item_id"]]
        sa, sb = set(inv.split_names(it["a"])), set(inv.split_names(it["b"]))
        sys_same = bool(sa) and sa == sb
        for name, ok in ((it["a"], l["valid_a"]), (it["b"], l["valid_b"])):
            whole = inv.split_names(name)
            usable = len(whole) == 1 and not re.search(r"\s(and|&)\s", name) or (len(whole) == 1 and whole[0] == name)
            if ok:
                valid += 1
                kept += bool(whole)
            else:
                invalid += 1
                flagged += not (len(whole) == 1 and usable)
        tp += sys_same and l["same_entity"]
        fp += sys_same and not l["same_entity"]
        fn += (not sys_same) and l["same_entity"]
        if sys_same != l["same_entity"]:
            errors.append({"set": "identity", "item_id": l["item_id"], "a": it["a"], "b": it["b"],
                           "error": "joined different entities" if sys_same else "split one entity", "gold": l})
    names = [(l["valid_a"]) for l in labels] + [(l["valid_b"]) for l in labels]
    return {
        "pairs": len(labels),
        "sample": "40 name pairs the resolver joins into one registry entity and 40 look-alike pairs it keeps apart, "
                  "from every buyer, seller and investor string in the deal store.",
        "join_precision": wilson(tp, tp + fp),
        "method": "Each string is split into canonical parties (combined names split, headline fragments and generic "
                  "phrases dropped); two strings are the same entity when they yield the same single party.",
        "join_recall": wilson(tp, tp + fn),
        "valid_party_names_in_sample": wilson(sum(names), len(names)),
        "malformed_names_caught": wilson(flagged, invalid),
        "valid_names_kept": wilson(kept, valid),
        "note": "The name-validity rate is measured on look-alike names, which over-represent extraction fragments; "
                "it is not the rate across all stored names.",
    }, errors


def heldout_names() -> Optional[dict]:
    """Per name: is a malformed string caught, and does a valid one resolve to the right organisation?"""
    if not (HERE / "heldout_names_labels.jsonl").exists():
        return None
    items = {i["item_id"]: i for i in _load("heldout_names_items.jsonl")}
    caught = invalid = resolved = valid = 0
    for l in _load("heldout_names_labels.jsonl"):
        name = items[l["item_id"]]["name"]
        parts = inv.split_names(name)
        if not l["valid"]:
            invalid += 1
            caught += len(parts) != 1 or parts[0] != inv.canonical(name)
            continue
        valid += 1
        golds = [o for o in l["organisations"] if o.get("name")]
        if len(parts) == 1 and golds:
            got = _norm(parts[0])
            names = [_norm(g["name"]) for g in golds] + [_norm(g.get("short")) for g in golds if g.get("short")]
            resolved += any(got == n or (n and (f" {n} " in f" {got} " or f" {got} " in f" {n} ")) for n in names)
    return {"names": invalid + valid,
            "malformed_names_caught": wilson(caught, invalid),
            "valid_names_resolved_to_the_right_organisation": wilson(resolved, valid)}


def main() -> dict:
    ext, e1 = extraction()
    ho, e4 = extraction("heldout_") if (HERE / "heldout_extraction_labels.jsonl").exists() else (None, [])
    ded, e2 = dedup()
    ide, e3 = identity()
    results = {"extraction": ext, "heldout_extraction": ho, "dedup": ded, "identity": ide, "heldout_names": heldout_names(),
               "labels": "Labelled from headline text only, blind to the system's output, by an AI annotator; "
                         "items marked low-confidence are reported separately. Pending independent human review."}
    (HERE / "results.json").write_text(json.dumps(results, indent=1))
    (HERE / "errors.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False, default=str) + "\n" for e in e1 + e2 + e3 + e4))
    return results


if __name__ == "__main__":
    r = main()
    print(json.dumps({"detection": r["extraction"]["detection"]["all"], "fields": r["extraction"]["fields"]["all"],
                      "complete": r["extraction"]["fields"]["fully_correct_record"],
                      "dedup": {k: v for k, v in r["dedup"].items() if k != "sample"},
                      "identity": {k: v for k, v in r["identity"].items() if k not in ("sample", "note")}}, indent=1))
