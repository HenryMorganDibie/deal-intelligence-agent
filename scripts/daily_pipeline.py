#!/usr/bin/env python3
"""Collect review data and evaluate models for the daily learning pipeline."""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import math
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
AUTOMATION_DIR = ROOT / "docs" / "automation"
EVENT_QUEUE = AUTOMATION_DIR / "event_label_queue.jsonl"
INDEPENDENT_EVENT_ITEMS = ROOT / "evaluation" / "attribution" / "independent_items.jsonl"
ENTITY_QUEUE = AUTOMATION_DIR / "entity_match_queue.jsonl"
FINANCIAL_DATA = AUTOMATION_DIR / "financial_observations.jsonl"
FINANCIAL_ATTEMPTS = AUTOMATION_DIR / "financial_collection_attempts.jsonl"
GRAPH_DATA = AUTOMATION_DIR / "relationship_graph.json"
RANKING_REPORT = AUTOMATION_DIR / "ranking_evaluation.json"
RANKER_MODEL = AUTOMATION_DIR / "learned_ranker.json"
PIPELINE_REPORT = AUTOMATION_DIR / "learning_pipeline.json"
SITE_DATA = ROOT / "web" / "data" / "investment_ideas.json"
BACKTEST_DATA = ROOT / "docs" / "backtest_predictions.csv"
UNIVERSE_DATA = ROOT / "docs" / "backtest_universe.csv"
LOG = logging.getLogger("daily_learning_pipeline")

PRICE_ONLY_SIGNALS = {"earnings_surprise", "insider_activity"}
SEVERITY_SCORE = {"low": 0.0, "medium": 1.0, "high": 2.0, "critical": 3.0}
MAX_NEW_EVENT_REVIEWS_PER_RUN = 100
_BUSINESS_CONTEXT = re.compile(
    r"\b(bank|company|companies|firm|group|stock|share|market|finance|financial|fund|loan|credit|debt|"
    r"invest\w*|investor|acquir\w*|acquisition|merger|earnings|profit|revenue|loss|appoint\w*|"
    r"ceo|director|chief|chairman|fine|sanction|regulator|regulatory|investigat\w*|default|"
    r"restructur\w*|bond|capital|dividend|asset|valuation|transaction|deal|lender|borrower|"
    r"bankruptcy|insolvency|layoff|layoffs|shares|shareholder|exchange|audit|auditor|"
    r"croissance|bénéfice|bénéfices|banque|investissement|prêt|dette|acquisition|sanction|"
    r"lucro|banco|investimento|financiamento|aquisição|"
    r"الأسهم|البنك|استثمار|تمويل|صفقة)\b",
    re.IGNORECASE,
)
INVESTMENT_GUIDANCE = [
    {
        "asset": "Money market funds",
        "risk": "Lower risk, not risk-free",
        "suitable_for": "Short-term savings or cash that may be needed soon",
        "benefits": ["Usually liquid", "Typically invests in short-term debt", "Simple way to diversify cash holdings"],
        "disadvantages": ["Returns can fall when interest rates decline", "May not keep pace with inflation",
                         "Fund value, fees, liquidity and deposit protection vary by provider and country"],
        "example": "Compare regulated funds in your country by fees, holdings, withdrawal terms and audited returns.",
    },
    {
        "asset": "Government bills and bonds",
        "risk": "Low to high, depending on issuer and term",
        "suitable_for": "Investors seeking scheduled interest or a defined maturity date",
        "benefits": ["Published maturity and coupon terms", "Can diversify a stock-heavy portfolio",
                     "Short-term bills can have less price sensitivity than long bonds"],
        "disadvantages": ["Issuer can default", "Longer bonds can lose value when rates rise",
                         "Inflation and currency depreciation can reduce real returns"],
        "example": "Compare sovereign credit quality, yield after fees/tax, currency and time to maturity.",
    },
    {
        "asset": "Diversified equity funds",
        "risk": "Medium to high",
        "suitable_for": "Long-term goals where the investor can tolerate market declines",
        "benefits": ["Spreads exposure across companies", "Can participate in long-term business growth",
                     "Broad funds reduce single-company risk"],
        "disadvantages": ["Prices can fall sharply and remain down for years", "Foreign funds add currency risk",
                         "Fees, taxes and tracking error reduce returns"],
        "example": "Compare regulated broad-market index funds or ETFs; check benchmark, holdings, costs and domicile.",
    },
    {
        "asset": "Individual stocks",
        "risk": "High",
        "suitable_for": "Investors who can research a business and tolerate losing some or all of the investment",
        "benefits": ["Direct ownership exposure", "Potential dividends and capital appreciation",
                     "Company disclosures can support independent analysis"],
        "disadvantages": ["Concentrated company and sector risk", "A strong company can still be an overpriced stock",
                         "Trading liquidity, governance and currency risks can be substantial"],
        "example": "Review audited statements, debt, cash flow, valuation, governance, liquidity and downside scenarios.",
    },
    {
        "asset": "Balanced or multi-asset funds",
        "risk": "Low to high, depending on allocation",
        "suitable_for": "People who want diversified exposure managed under one mandate",
        "benefits": ["Combines different asset classes", "Can reduce the need to rebalance manually",
                     "Fund mandate and holdings are usually published"],
        "disadvantages": ["Still exposed to losses", "Allocation and fees vary widely",
                         "A label such as 'balanced' does not guarantee low risk"],
        "example": "Read the mandate, latest holdings, fees, drawdowns and redemption restrictions.",
    },
]


def _stable_id(*parts: str) -> str:
    value = "\x1f".join(p.strip().lower() for p in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            if line.strip():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON in {path}:{line_number}") from exc
                if not isinstance(row, dict):
                    raise ValueError(f"Expected JSON object in {path}:{line_number}")
                rows.append(row)
    return rows


def _merge_jsonl(path: Path, incoming: Iterable[dict[str, Any]], key: str = "id") -> int:
    existing = _read_jsonl(path)
    known = {row[key] for row in existing if row.get(key)}
    additions = [row for row in incoming if row.get(key) and row[key] not in known]
    if additions:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for row in additions:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return len(additions)


def _write_jsonl_by_key(path: Path, rows: Iterable[dict[str, Any]], key: str) -> None:
    indexed = {row[key]: row for row in _read_jsonl(path) if row.get(key)}
    indexed.update({row[key]: row for row in rows if row.get(key)})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in indexed.values()),
        encoding="utf-8",
    )


def _normalise_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _collect_headlines() -> list[dict[str, Any]]:
    from src.engines.market_feed import collect

    return asyncio.run(collect(
        window="when:1d",
        include_feeds=True,
        include_countries=False,
        concurrency=8,
        timeout=20,
    ))


def _event_review_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from src.engines.market_feed import to_events

    event_by_title = {
        _normalise_name(event["headline"]): event
        for event in to_events(items, min_score=0.0)
    }
    rows = []
    for item in items:
        title = item.get("title", "").strip()
        if not title:
            continue
        story_id = _stable_id(title)
        event = event_by_title.get(_normalise_name(title))
        if event is None and not _BUSINESS_CONTEXT.search(f"{title} {item.get('snippet', '')}"):
            continue
        rows.append({
            "id": story_id,
            "title": title,
            "snippet": item.get("snippet", ""),
            "publisher": item.get("publisher", ""),
            "url": item.get("url", ""),
            "published": item.get("date"),
            "country_hint": item.get("country_hint"),
            "rule_candidates": [event["signal_type"]] if event else [],
            "label": None,
            "review_split": "holdout" if int(story_id[:4], 16) % 5 == 0 else "train",
            "reviewed_by": None,
            "reviewed_at": None,
        })
    rows.sort(key=lambda row: (not bool(row["rule_candidates"]), row["id"]))
    return rows[:MAX_NEW_EVENT_REVIEWS_PER_RUN]


def _prune_event_queue() -> int:
    rows = _read_jsonl(EVENT_QUEUE)
    relevant = [
        row for row in rows
        if row.get("label") is not None
        or row.get("rule_candidates")
        or _BUSINESS_CONTEXT.search(f"{row.get('title', '')} {row.get('snippet', '')}")
    ]
    if len(relevant) != len(rows):
        EVENT_QUEUE.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in relevant),
            encoding="utf-8",
        )
    return len(rows) - len(relevant)


def _entity_review_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from src.engines.deals import extract_deal
    from src.engines.investors import REGISTRY

    parties: dict[str, str] = {}
    for item in items:
        deal = extract_deal(item.get("title", ""), item.get("snippet", ""))
        if not deal:
            continue
        for field in ("target", "buyer"):
            name = deal.get(field)
            if name and len(_normalise_name(name)) >= 5:
                parties.setdefault(_normalise_name(name), name)

    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    known_parties = list(parties.items())
    for index, (left_key, left_name) in enumerate(known_parties):
        for right_key, right_name in known_parties[index + 1:]:
            similarity = SequenceMatcher(None, left_key, right_key).ratio()
            if 0.78 <= similarity < 1.0:
                candidates[(left_key, right_key)] = {
                    "left": left_name, "right": right_name, "similarity": round(similarity, 4),
                    "candidate_source": "deal_party_name_similarity",
                }
        for investor in REGISTRY:
            for alias in (investor.name, *investor.aliases):
                alias_key = _normalise_name(alias)
                if not alias_key or left_key == alias_key:
                    continue
                similarity = SequenceMatcher(None, left_key, alias_key).ratio()
                if 0.78 <= similarity < 1.0:
                    candidates[(left_key, alias_key)] = {
                        "left": left_name, "right": alias, "similarity": round(similarity, 4),
                        "candidate_source": "investor_registry_similarity",
                    }

    rows = []
    for pair, candidate in sorted(candidates.items(), key=lambda item: (-item[1]["similarity"], item[0]))[:100]:
        rows.append({
            "id": _stable_id(*pair),
            **candidate,
            "canonical_entity": None,
            "same_entity": None,
            "review_split": "holdout" if int(_stable_id(*pair)[:4], 16) % 5 == 0 else "train",
            "reviewed_by": None,
            "reviewed_at": None,
        })
    return rows


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return words + [f"{left}_{right}" for left, right in zip(words, words[1:])]


def _load_event_test_set() -> list[tuple[str, set[str], str]]:
    sets = (
        (ROOT / "evaluation" / "attribution" / "natural_items.jsonl",
         ROOT / "evaluation" / "attribution" / "natural_labels.jsonl"),
        (ROOT / "evaluation" / "attribution" / "hard_items.jsonl",
         ROOT / "evaluation" / "attribution" / "hard_labels.jsonl"),
    )
    output = []
    for items_path, labels_path in sets:
        items = {row["item_id"]: row for row in _read_jsonl(items_path)}
        for label in _read_jsonl(labels_path):
            item = items.get(label.get("item_id"))
            if item is None:
                raise ValueError(f"No matching attribution item for {label.get('item_id')} in {items_path}")
            expected = set(label.get("expected") or [])
            text = " ".join((item.get("title") or "", item.get("company") or ""))
            output.append((text, expected, label.get("confidence", "")))
    return output


def _event_nb_model(training: list[dict[str, Any]]) -> dict[str, Any]:
    docs: list[tuple[Counter[str], set[str]]] = []
    for row in training:
        label = row.get("label")
        if not isinstance(label, dict) or not isinstance(label.get("expected"), list):
            continue
        expected = set(label["expected"])
        if not all(isinstance(name, str) for name in expected):
            continue
        text = " ".join((row.get("title") or "", row.get("snippet") or ""))
        docs.append((Counter(_tokens(text)), expected))
    categories = sorted({category for _, labels in docs for category in labels})
    vocabulary = sorted({
        token
        for counts, _ in docs
        for token, count in counts.items()
        if count >= 1
    })
    models = {}
    for category in categories:
        positive = [counts for counts, labels in docs if category in labels]
        negative = [counts for counts, labels in docs if category not in labels]
        pos_total = Counter()
        neg_total = Counter()
        for counts in positive:
            pos_total.update(counts)
        for counts in negative:
            neg_total.update(counts)
        vocab_size = max(1, len(vocabulary))
        pos_denominator = sum(pos_total.values()) + vocab_size
        neg_denominator = sum(neg_total.values()) + vocab_size
        prior = math.log((len(positive) + 1) / (len(negative) + 1))
        models[category] = {
            "prior": prior,
            "positive_log_prob": {
                token: math.log((pos_total[token] + 1) / pos_denominator) for token in vocabulary
            },
            "negative_log_prob": {
                token: math.log((neg_total[token] + 1) / neg_denominator) for token in vocabulary
            },
        }
    return {"categories": categories, "models": models, "training_docs": len(docs)}


def _predict_event_nb(model: dict[str, Any], text: str) -> set[str]:
    counts = Counter(_tokens(text))
    predictions = set()
    for category, values in model["models"].items():
        score = values["prior"]
        positive = values["positive_log_prob"]
        negative = values["negative_log_prob"]
        for token, count in counts.items():
            if token in positive:
                score += count * (positive[token] - negative[token])
        if score > 0:
            predictions.add(category)
    return predictions


def _multilabel_metrics(
    expected: list[set[str]],
    predicted: list[set[str]],
    categories: set[str],
) -> dict[str, Any]:
    per_category = {}
    f1_values = []
    total_tp = total_fp = total_fn = 0
    for category in sorted(categories):
        tp = sum(category in actual and category in guess for actual, guess in zip(expected, predicted))
        fp = sum(category not in actual and category in guess for actual, guess in zip(expected, predicted))
        fn = sum(category in actual and category not in guess for actual, guess in zip(expected, predicted))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_category[category] = {
            "support": tp + fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
        f1_values.append(f1)
        total_tp += tp
        total_fp += fp
        total_fn += fn
    precision = total_tp / (total_tp + total_fp) if total_tp + total_fp else 0.0
    recall = total_tp / (total_tp + total_fn) if total_tp + total_fn else 0.0
    return {
        "items": len(expected),
        "micro_f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
        "macro_f1": round(sum(f1_values) / len(f1_values), 4) if f1_values else 0.0,
        "per_category": per_category,
    }


def train_event_classifier() -> dict[str, Any]:
    AUTOMATION_DIR.mkdir(parents=True, exist_ok=True)
    independent_ids = {
        row.get("source_review_id")
        for row in _read_jsonl(INDEPENDENT_EVENT_ITEMS)
        if row.get("source_review_id")
    }
    reviewed = [
        row for row in _read_jsonl(EVENT_QUEUE)
        if row.get("id") not in independent_ids
        and isinstance(row.get("label"), dict)
        and row["label"].get("confidence", "high") != "low"
        and isinstance(row["label"].get("expected"), list)
        and isinstance(row["label"].get("about_target"), bool)
    ]
    heldout = _load_event_test_set()
    if len(reviewed) < 1000 or len(heldout) < 600:
        return {
            "status": "collecting_labels",
            "training_labels": len(reviewed),
            "heldout_items": len(heldout),
            "reason": "Requires at least 1,000 reviewed training headlines and the locked 680-item attribution evaluation set.",
        }
    model = _event_nb_model(reviewed)
    if model["training_docs"] < 1000:
        return {"status": "collecting_labels", "training_labels": model["training_docs"]}
    labels = [expected for _, expected, _ in heldout]
    predictions = [_predict_event_nb(model, text) for text, _, _ in heldout]
    categories = {category for _, expected, _ in heldout for category in expected}
    learned_metrics = _multilabel_metrics(labels, predictions, categories)

    from src.engines.deterministic_engine import _match_rules

    rule_predictions = []
    for text, _, _ in heldout:
        rule_predictions.append({signal_type.value for signal_type, _, _ in _match_rules(text)})
    rule_metrics = _multilabel_metrics(labels, rule_predictions, categories)
    promoted = learned_metrics["macro_f1"] >= rule_metrics["macro_f1"] + 0.02
    result = {
        "status": "promoted" if promoted else "evaluated_not_promoted",
        "promoted": promoted,
        "training_labels": len(reviewed),
        "locked_heldout_items": len(heldout),
        "learned_classifier": learned_metrics,
        "rule_baseline": rule_metrics,
        "promotion_rule": "Promote only when macro-F1 on the locked headline set beats the deterministic rules by at least 2 percentage points.",
        "heldout_set": "evaluation/attribution (natural + hard; unchanged)",
    }
    report_path = AUTOMATION_DIR / "event_classifier_evaluation.json"
    report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if promoted:
        model_path = AUTOMATION_DIR / "event_classifier.json"
        model_path.write_text(json.dumps({
            **model,
            "evaluation": result["learned_classifier"],
            "locked_holdout_size": len(heldout),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2) + "\n", encoding="utf-8")
    return result


def _entity_pair_features(left: str, right: str) -> list[float]:
    a, b = _normalise_name(left), _normalise_name(right)
    tokens_a, tokens_b = set(a.split()), set(b.split())
    union = tokens_a | tokens_b
    return [
        SequenceMatcher(None, a, b).ratio(),
        len(tokens_a & tokens_b) / len(union) if union else 0.0,
        min(len(a), len(b)) / max(len(a), len(b), 1),
        float(a == b),
        float(a.replace(" ", "") == b.replace(" ", "")),
    ]


def train_entity_matcher() -> dict[str, Any]:
    AUTOMATION_DIR.mkdir(parents=True, exist_ok=True)
    reviewed = [
        row for row in _read_jsonl(ENTITY_QUEUE)
        if isinstance(row.get("same_entity"), bool) and row.get("review_split") in ("train", "holdout")
    ]
    training = [row for row in reviewed if row["review_split"] == "train"]
    holdout = [row for row in reviewed if row["review_split"] == "holdout"]
    if len(training) < 500 or len(holdout) < 100:
        return {
            "status": "collecting_labels",
            "training_labels": len(training),
            "holdout_labels": len(holdout),
            "reason": "Requires at least 500 reviewed training pairs and 100 separately held-out pairs.",
        }
    labels = [int(row["same_entity"]) for row in training]
    if min(sum(labels), len(labels) - sum(labels)) < 20:
        return {"status": "collecting_labels", "training_labels": len(training),
                "reason": "Training pairs need at least 20 positive and 20 negative examples."}

    x_train = [_entity_pair_features(row["left"], row["right"]) for row in training]
    y_train = labels
    prevalence = sum(y_train) / len(y_train)
    weights = [math.log(prevalence / (1 - prevalence)), 0.0, 0.0, 0.0, 0.0, 0.0]
    for _ in range(400):
        gradient = [0.0] * len(weights)
        for features, label in zip(x_train, y_train):
            x = [1.0, *features]
            error = _sigmoid(sum(weight * value for weight, value in zip(weights, x))) - label
            for index, value in enumerate(x):
                gradient[index] += error * value
        for index in range(len(weights)):
            weights[index] -= 0.2 * (
                gradient[index] / len(training) + (0.02 * weights[index] if index else 0.0)
            )

    probabilities = [
        _sigmoid(sum(weight * value for weight, value in zip(weights, [1.0, *_entity_pair_features(row["left"], row["right"])])))
        for row in holdout
    ]
    predictions = [score >= 0.5 for score in probabilities]
    actual = [row["same_entity"] for row in holdout]
    tp = sum(pred and truth for pred, truth in zip(predictions, actual))
    fp = sum(pred and not truth for pred, truth in zip(predictions, actual))
    fn = sum(not pred and truth for pred, truth in zip(predictions, actual))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    baseline_predictions = [
        _normalise_name(row["left"]) == _normalise_name(row["right"]) for row in holdout
    ]
    baseline_tp = sum(pred and truth for pred, truth in zip(baseline_predictions, actual))
    baseline_fp = sum(pred and not truth for pred, truth in zip(baseline_predictions, actual))
    baseline_fn = sum(not pred and truth for pred, truth in zip(baseline_predictions, actual))
    baseline_precision = baseline_tp / (baseline_tp + baseline_fp) if baseline_tp + baseline_fp else 0.0
    baseline_recall = baseline_tp / (baseline_tp + baseline_fn) if baseline_tp + baseline_fn else 0.0
    baseline_f1 = (
        2 * baseline_precision * baseline_recall / (baseline_precision + baseline_recall)
        if baseline_precision + baseline_recall else 0.0
    )
    promoted = precision >= 0.98 and f1 >= baseline_f1 + 0.02
    result = {
        "status": "promoted_for_review_suggestions" if promoted else "evaluated_not_promoted",
        "promoted": promoted,
        "training_pairs": len(training),
        "holdout_pairs": len(holdout),
        "classifier": {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)},
        "exact_normalisation_baseline": {"precision": round(baseline_precision, 4),
                                         "recall": round(baseline_recall, 4), "f1": round(baseline_f1, 4)},
        "promotion_rule": "Require at least 98% holdout precision and F1 at least 2 percentage points above exact-normalisation baseline. Suggestions never merge entities automatically.",
    }
    report_path = AUTOMATION_DIR / "entity_match_evaluation.json"
    report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if promoted:
        (AUTOMATION_DIR / "entity_matcher.json").write_text(json.dumps({
            "weights": weights,
            "trained_pairs": len(training),
            "holdout_metrics": result["classifier"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2) + "\n", encoding="utf-8")
    return result


def _financial_collection() -> dict[str, Any]:
    from src.engines.financials import yahoo_financials

    with UNIVERSE_DATA.open(newline="", encoding="utf-8") as f:
        universe = list(csv.DictReader(f))
    tickers = sorted({row["ticker"].strip() for row in universe if row.get("ticker", "").strip()})
    existing = _read_jsonl(FINANCIAL_DATA)
    collected = {row.get("ticker") for row in existing}
    attempts = {row["ticker"]: row for row in _read_jsonl(FINANCIAL_ATTEMPTS) if row.get("ticker")}
    today = date.today()
    pending = [
        ticker for ticker in tickers
        if ticker not in collected
        and (
            ticker not in attempts
            or (today - date.fromisoformat(attempts[ticker]["last_attempt"])).days >= 7
        )
    ]
    if not pending:
        return {
            "universe_tickers": len(tickers),
            "collected_tickers": len(collected),
            "new_rows": 0,
            "failures": [],
            "retry_after_days": 7,
        }

    selected = pending[:4]
    new_rows = []
    failures = []
    attempt_rows = []
    for ticker in selected:
        result = yahoo_financials(ticker, years=4)
        if not result or not result.get("annual"):
            failures.append(ticker)
            attempt_rows.append({
                "ticker": ticker,
                "last_attempt": today.isoformat(),
                "status": "no_annual_data_returned",
            })
            continue
        annual = result["annual"]
        periods = sorted(annual.items(), reverse=True)
        latest_period, latest = periods[0]
        previous = periods[1][1] if len(periods) > 1 else {}
        revenue_change = _relative_change(latest.get("revenue"), previous.get("revenue"))
        income_change = _relative_change(latest.get("profit_after_tax"), previous.get("profit_after_tax"))
        flags = []
        if revenue_change is not None and revenue_change <= -0.25:
            flags.append("revenue_decline_25pct")
        if latest.get("profit_after_tax") is not None and latest["profit_after_tax"] < 0 \
                and previous.get("profit_after_tax", 0) >= 0:
            flags.append("profit_to_loss")
        if latest.get("total_debt") and latest.get("total_equity") and latest["total_equity"] > 0 \
                and latest["total_debt"] / latest["total_equity"] >= 2:
            flags.append("debt_to_equity_at_least_2")
        new_rows.append({
            "id": _stable_id(ticker, latest_period),
            "ticker": ticker,
            "period": latest_period,
            "currency": result.get("unit"),
            "source": result.get("source"),
            "fields": {name: latest.get(name) for name in (
                "revenue", "profit_after_tax", "total_assets", "total_debt", "cash",
                "operating_cash_flow", "free_cash_flow", "total_equity",
            )},
            "annual_history": [
                {"period": period, "fields": values}
                for period, values in periods
            ],
            "revenue_yoy_change": revenue_change,
            "profit_yoy_change": income_change,
            "screening_flags": flags,
            "anomaly_label": None,
            "reviewed_by": None,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        })
        attempt_rows.append({
            "ticker": ticker,
            "last_attempt": today.isoformat(),
            "status": "collected",
        })
    inserted = _merge_jsonl(FINANCIAL_DATA, new_rows)
    _write_jsonl_by_key(FINANCIAL_ATTEMPTS, attempt_rows, "ticker")
    return {
        "universe_tickers": len(tickers),
        "collected_tickers": len(collected) + inserted,
        "new_rows": inserted,
        "failures": failures,
        "retry_after_days": 7,
    }


def _relative_change(current: Any, previous: Any) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((current - previous) / abs(previous), 6)


def _update_graph(items: list[dict[str, Any]]) -> dict[str, Any]:
    from src.engines.deals import extract_deal

    if GRAPH_DATA.exists():
        graph = json.loads(GRAPH_DATA.read_text(encoding="utf-8"))
    else:
        graph = {"nodes": {}, "edges": {}}
    edges: dict[str, dict[str, Any]] = graph.setdefault("edges", {})
    nodes: dict[str, dict[str, Any]] = graph.setdefault("nodes", {})
    for item in items:
        deal = extract_deal(item.get("title", ""), item.get("snippet", ""))
        if not deal:
            continue
        target, buyer = deal.get("target"), deal.get("buyer")
        if not target or not buyer:
            continue
        left, right = _normalise_name(buyer), _normalise_name(target)
        if not left or not right or left == right:
            continue
        nodes.setdefault(left, {"name": buyer, "kind": "organization"})
        nodes.setdefault(right, {"name": target, "kind": "organization"})
        edge_id = _stable_id(left, right, deal.get("deal_type", "transaction"))
        edge = edges.setdefault(edge_id, {
            "id": edge_id,
            "from": left,
            "to": right,
            "type": deal.get("deal_type", "transaction"),
            "first_seen": item.get("date"),
            "sources": [],
        })
        source = {"title": item.get("title", ""), "publisher": item.get("publisher", ""), "url": item.get("url", "")}
        if source["url"] and source not in edge["sources"]:
            edge["sources"].append(source)
    graph["updated_at"] = datetime.now(timezone.utc).isoformat()
    GRAPH_DATA.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_DATA.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    degree: Counter[str] = Counter()
    for edge in edges.values():
        degree[edge["from"]] += 1
        degree[edge["to"]] += 1
    return {
        "nodes": len(nodes),
        "relationships": len(edges),
        "source_links": sum(len(edge.get("sources", [])) for edge in edges.values()),
        "most_connected": [
            {"name": nodes[node]["name"], "degree": count}
            for node, count in degree.most_common(10)
        ],
    }


def _rank_features(row: dict[str, str]) -> dict[str, float]:
    features = {
        "alpha": float(row["alpha"]) / 100.0,
        "severity": SEVERITY_SCORE.get(row["severity"].lower(), 0.0) / 3.0,
    }
    for field in ("signal_type", "source_kind", "market", "direction"):
        value = row.get(field, "").strip().lower()
        if value:
            features[f"{field}={value}"] = 1.0
    return features


def _sigmoid(value: float) -> float:
    if value >= 35:
        return 1.0
    if value <= -35:
        return 0.0
    return 1.0 / (1.0 + math.exp(-value))


def _ranking_metrics(rows: list[dict[str, Any]], scores: list[float]) -> dict[str, float | int | None]:
    if not rows:
        return {"n": 0, "positives": 0, "base_rate": None, "precision_at_20pct": None, "brier": None}
    labels = [int(row["event_confirmed"] == "True") for row in rows]
    k = max(1, math.ceil(len(rows) * 0.2))
    precision_at_k = (
        sum(labels) / len(labels)
        if len(set(scores)) <= 1
        else sum(labels[i] for i in sorted(range(len(rows)), key=lambda i: scores[i], reverse=True)[:k]) / k
    )
    return {
        "n": len(rows),
        "positives": sum(labels),
        "base_rate": round(sum(labels) / len(labels), 6),
        "precision_at_20pct": round(precision_at_k, 6),
        "brier": round(sum((scores[i] - labels[i]) ** 2 for i in range(len(rows))) / len(rows), 6),
    }


def train_learned_ranker(path: Path = BACKTEST_DATA) -> dict[str, Any]:
    AUTOMATION_DIR.mkdir(parents=True, exist_ok=True)
    with path.open(newline="", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))
    eligible = [
        row for row in all_rows
        if row.get("signal_type") not in PRICE_ONLY_SIGNALS
        and row.get("event_confirmed") in ("True", "False")
        and row.get("alpha", "").strip()
    ]
    dates = sorted({row["as_of"] for row in eligible if row.get("as_of")})
    if len(dates) < 5:
        report = {"status": "waiting_for_data", "reason": "Fewer than five distinct as-of dates.",
                  "source_rows": len(all_rows), "eligible_rows": len(eligible)}
        RANKING_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report

    split_at = max(1, math.floor(len(dates) * 0.8))
    cutoff = dates[split_at]
    training = [row for row in eligible if row.get("as_of", "") < cutoff]
    holdout = [row for row in eligible if row.get("as_of", "") >= cutoff]
    y_train = [int(row["event_confirmed"] == "True") for row in training]
    y_test = [int(row["event_confirmed"] == "True") for row in holdout]
    if len(training) < 500 or len(holdout) < 100 or min(sum(y_train), len(y_train) - sum(y_train),
                                                        sum(y_test), len(y_test) - sum(y_test)) < 10:
        report = {
            "status": "waiting_for_data",
            "reason": "Insufficient labelled examples in a chronological train/holdout split.",
            "source_rows": len(all_rows), "eligible_rows": len(eligible),
            "training_rows": len(training), "holdout_rows": len(holdout),
            "cutoff": cutoff,
        }
        RANKING_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report

    train_features = [_rank_features(row) for row in training]
    test_features = [_rank_features(row) for row in holdout]
    feature_names = sorted({name for features in train_features for name in features})
    index = {name: position for position, name in enumerate(feature_names)}
    dimension = len(feature_names) + 1

    def vector(features: dict[str, float]) -> list[float]:
        result = [0.0] * dimension
        result[0] = 1.0
        for name, value in features.items():
            if name in index:
                result[index[name] + 1] = value
        return result

    x_train = [vector(row) for row in train_features]
    x_test = [vector(row) for row in test_features]
    prevalence = sum(y_train) / len(y_train)
    weights = [0.0] * dimension
    weights[0] = math.log(prevalence / (1 - prevalence))
    learning_rate = 0.25
    for _ in range(350):
        gradient = [0.0] * dimension
        for x, label in zip(x_train, y_train):
            error = _sigmoid(sum(weight * value for weight, value in zip(weights, x))) - label
            for j, value in enumerate(x):
                gradient[j] += error * value
        scale = 1.0 / len(x_train)
        for j in range(dimension):
            regularisation = 0.03 * weights[j] if j else 0.0
            weights[j] -= learning_rate * (gradient[j] * scale + regularisation)

    probabilities = [_sigmoid(sum(weight * value for weight, value in zip(weights, x))) for x in x_test]
    alpha_scores = [float(row["alpha"]) / 100.0 for row in holdout]
    learned_metrics = _ranking_metrics(holdout, probabilities)
    alpha_metrics = _ranking_metrics(holdout, alpha_scores)
    prevalence_scores = [prevalence] * len(holdout)
    baseline_metrics = _ranking_metrics(holdout, prevalence_scores)
    good = (
        learned_metrics["precision_at_20pct"] is not None
        and alpha_metrics["precision_at_20pct"] is not None
        and learned_metrics["precision_at_20pct"] >= alpha_metrics["precision_at_20pct"] + 0.02
        and learned_metrics["brier"] is not None
        and baseline_metrics["brier"] is not None
        and learned_metrics["brier"] < baseline_metrics["brier"]
    )
    report = {
        "status": "promoted" if good else "evaluated_not_promoted",
        "promoted": good,
        "source": "docs/backtest_predictions.csv",
        "eligible_rows": len(eligible),
        "training_rows": len(training),
        "holdout_rows": len(holdout),
        "training_positive_labels": sum(y_train),
        "holdout_positive_labels": sum(y_test),
        "train_through": dates[split_at - 1],
        "holdout_from": cutoff,
        "metrics": {
            "learned_ranker": learned_metrics,
            "alpha_baseline": alpha_metrics,
            "prevalence_baseline": baseline_metrics,
        },
        "promotion_rule": "Promote only if holdout precision@top-20% beats alpha by at least 2 percentage points and Brier score beats the prevalence baseline.",
    }
    RANKING_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if good:
        model = {
            "model": "logistic_regression",
            "feature_names": feature_names,
            "weights": weights,
            "trained_through": dates[split_at - 1],
            "holdout_from": cutoff,
            "holdout_metrics": learned_metrics,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        RANKER_MODEL.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    return report


def _pipeline_payload(
    event_added: int,
    entity_added: int,
    financial: dict[str, Any],
    graph: dict[str, Any],
    ranking: dict[str, Any],
    event_model: dict[str, Any],
    entity_model: dict[str, Any],
) -> dict[str, Any]:
    event_labels = [row for row in _read_jsonl(EVENT_QUEUE) if row.get("label") is not None]
    entity_labels = [row for row in _read_jsonl(ENTITY_QUEUE) if row.get("same_entity") is not None]
    financial_rows = _read_jsonl(FINANCIAL_DATA)
    rank_data = ranking.get("metrics", {})
    stages = [
        {
            "id": "event_classifier", "name": "Event classifier",
            "status": event_model.get("status", "collecting_labels"),
            "labels_collected": len(event_labels), "labels_target": 1500,
            "new_review_items_today": event_added,
            "evaluation": event_model,
            "notes": "The current 680-headline attribution set is held out from event-type training; this model uses only reviewed event labels.",
        },
        {
            "id": "entity_resolution", "name": "Entity resolution",
            "status": entity_model.get("status", "collecting_labels"),
            "labels_collected": len(entity_labels), "labels_target": 2000,
            "new_review_items_today": entity_added,
            "evaluation": entity_model,
            "notes": "Fuzzy candidate pairs are queued for human review; ambiguous entities are not merged automatically.",
        },
        {
            "id": "financial_anomalies", "name": "Financial anomalies",
            "status": "collecting_data",
            "observations_collected": len(financial_rows), "new_observations_today": financial["new_rows"],
            "unreviewed_flagged_observations": sum(bool(row.get("screening_flags")) and row.get("anomaly_label") is None
                                                    for row in financial_rows),
            "notes": "Annual filings are collected incrementally and threshold flags remain unreviewed until labelled.",
        },
        {
            "id": "graph_intelligence", "name": "Graph intelligence",
            "status": "collecting_relationships",
            "relationships": graph["relationships"], "entities": graph["nodes"],
            "notes": "Deal-party edges accumulate only when the extractor finds both parties; every edge keeps source links.",
        },
        {
            "id": "learned_ranking", "name": "Learned ranking",
            "status": ranking.get("status", "waiting_for_data"),
            "eligible_backtest_rows": ranking.get("eligible_rows", 0),
            "holdout_metrics": rank_data,
            "promoted": bool(ranking.get("promoted")),
            "notes": "A time-ordered holdout gates promotion; the deployed model is not overwritten when the candidate fails validation.",
        },
    ]
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_phases": len(stages),
            "active_phases": sum(stage["status"] not in ("promoted", "complete") for stage in stages),
            "message": "Daily GitHub Actions collects new review data, incrementally builds financial and deal graphs, and publishes learned ranking only when holdout validation improves.",
        },
        "stages": stages,
    }


def run_pipeline(collect_data: bool = True, collect_financials: bool = True) -> dict[str, Any]:
    AUTOMATION_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DATA.parent.mkdir(parents=True, exist_ok=True)
    items = _collect_headlines() if collect_data else []
    if collect_data and not items:
        raise RuntimeError("The daily feed collection returned no headlines; refusing to publish an empty update.")
    event_added = _merge_jsonl(EVENT_QUEUE, _event_review_rows(items))
    event_pruned = _prune_event_queue()
    entity_added = _merge_jsonl(ENTITY_QUEUE, _entity_review_rows(items))
    financial = _financial_collection() if collect_financials else {
        "universe_tickers": 0, "collected_tickers": len(_read_jsonl(FINANCIAL_DATA)),
        "new_rows": 0, "failures": [],
    }
    graph = _update_graph(items)
    ranking = train_learned_ranker()
    event_model = train_event_classifier()
    entity_model = train_entity_matcher()
    payload = _pipeline_payload(
        event_added, entity_added, financial, graph, ranking, event_model, entity_model
    )
    PIPELINE_REPORT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    site_data = {
        "updated_at": payload["updated_at"],
        "summary": payload["summary"],
        "stages": payload["stages"],
        "ideas": INVESTMENT_GUIDANCE,
        "financial_data_collection": financial,
        "relationship_graph": graph,
        "ranking_evaluation": ranking,
    }
    SITE_DATA.write_text(json.dumps(site_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    LOG.info(
        "collected headlines=%d event_reviews_added=%d event_reviews_pruned=%d entity_reviews_added=%d "
        "financial_rows_added=%d graph_edges=%d ranker=%s",
        len(items), event_added, event_pruned, entity_added, financial["new_rows"], graph["relationships"],
        ranking.get("status", "unknown"),
    )
    if financial["failures"]:
        LOG.warning("No usable annual statement returned for tickers: %s", ", ".join(financial["failures"]))
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily research-data collection and model evaluation.")
    parser.add_argument("--skip-collection", action="store_true", help="Skip network headline collection (for local checks).")
    parser.add_argument("--skip-financials", action="store_true", help="Skip rotating Yahoo Finance collection (for local checks).")
    parser.add_argument("--train-ranker-only", action="store_true", help="Evaluate the learned ranker from the committed backtest CSV.")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    if args.train_ranker_only:
        report = train_learned_ranker()
        print(json.dumps(report, indent=2))
        return
    result = run_pipeline(
        collect_data=not args.skip_collection,
        collect_financials=not args.skip_financials,
    )
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
