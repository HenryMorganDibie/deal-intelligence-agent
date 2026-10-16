"""Chronological validation for a simple market-adjusted return forecast.

This module deliberately does not publish a live forecast. A model must beat a
zero-return baseline on a later, date-separated holdout before it can be used.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable


DEFAULT_PREDICTIONS = Path(__file__).resolve().parents[2] / "docs" / "backtest_predictions.csv"
MIN_TRAIN_GROUP = 30
MIN_HOLDOUT_ROWS = 100
MIN_HOLDOUT_DATES = 6
MIN_MAE_IMPROVEMENT = 0.05
MAX_DATA_AGE_DAYS = 180
_T_CRITICAL_95 = {5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
                  11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
                  16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
                  21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
                  26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045}


def _read_predictions(path: Path = DEFAULT_PREDICTIONS) -> list[dict]:
    rows = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                as_of = date.fromisoformat(row["as_of"])
                outcome = float(row["abnormal_return_10d_pct"])
            except (KeyError, TypeError, ValueError):
                continue
            if row.get("market") not in {"us", "africa"}:
                continue
            rows.append({
                "as_of": as_of,
                "market": row["market"],
                "signal_type": row["signal_type"],
                "severity": row["severity"],
                "outcome": outcome,
            })
    return rows


def _forecast(history: list[dict], row: dict) -> float:
    """Median return for comparable earlier flags; back off when a group is small."""
    selectors = (
        lambda x: x["market"] == row["market"]
        and x["signal_type"] == row["signal_type"]
        and x["severity"] == row["severity"],
        lambda x: x["market"] == row["market"] and x["signal_type"] == row["signal_type"],
        lambda x: x["market"] == row["market"],
        lambda x: True,
    )
    for select in selectors:
        values = [x["outcome"] for x in history if select(x)]
        if len(values) >= MIN_TRAIN_GROUP:
            return statistics.median(values)
    return 0.0


def _metrics(pairs: list[tuple[float, float, date]]) -> dict:
    if not pairs:
        return {"holdout_n": 0, "qualified": False, "reason": "No labelled holdout outcomes."}

    improvement_by_date: dict[date, list[float]] = defaultdict(list)
    model_errors, baseline_errors, direction_hits = [], [], []
    for forecast, actual, as_of in pairs:
        model_errors.append(abs(forecast - actual))
        baseline_errors.append(abs(actual))
        improvement_by_date[as_of].append(abs(actual) - abs(forecast))
        if forecast != 0 and actual != 0:
            direction_hits.append((forecast > 0) == (actual > 0))

    model_mae = statistics.mean(model_errors)
    baseline_mae = statistics.mean(baseline_errors)
    improvement = (baseline_mae - model_mae) / baseline_mae if baseline_mae else 0.0
    mean_absolute_improvement = baseline_mae - model_mae
    n_dates = len(improvement_by_date)
    if n_dates >= 6:
        cluster_sums = [
            sum(values) - len(values) * mean_absolute_improvement
            for values in improvement_by_date.values()
        ]
        critical = _T_CRITICAL_95.get(n_dates - 1, 1.96)
        standard_error = (
            (n_dates / (n_dates - 1) * sum(value ** 2 for value in cluster_sums)) ** 0.5
            / len(pairs)
        )
        ci_low = mean_absolute_improvement - critical * standard_error
    else:
        ci_low = None

    reasons = []
    if len(pairs) < MIN_HOLDOUT_ROWS:
        reasons.append(f"fewer than {MIN_HOLDOUT_ROWS} holdout outcomes")
    if n_dates < MIN_HOLDOUT_DATES:
        reasons.append(f"fewer than {MIN_HOLDOUT_DATES} separate holdout dates")
    if improvement < MIN_MAE_IMPROVEMENT:
        reasons.append(f"MAE improvement below {MIN_MAE_IMPROVEMENT:.0%}")
    if ci_low is None or ci_low <= 0:
        reasons.append("95% date-clustered improvement interval includes zero")

    return {
        "holdout_n": len(pairs),
        "holdout_dates": n_dates,
        "candidate_mae_pct": round(model_mae, 4),
        "zero_return_baseline_mae_pct": round(baseline_mae, 4),
        "mae_improvement_pct": round(improvement * 100, 3),
        "absolute_mae_improvement_ci_low_pct_points": (
            round(ci_low, 4) if ci_low is not None else None
        ),
        "direction_n": len(direction_hits),
        "direction_accuracy": round(statistics.mean(direction_hits), 4) if direction_hits else None,
        "qualified": not reasons,
        "reason": "Passed predeclared holdout checks." if not reasons else "; ".join(reasons),
    }


def evaluate(
    rows: Iterable[dict],
    holdout_dates: int = 6,
    evaluation_date: date | None = None,
) -> dict:
    """Evaluate a prior-only grouped-median forecast against a zero-return baseline."""
    rows = sorted(rows, key=lambda r: r["as_of"])
    dates = sorted({r["as_of"] for r in rows})
    evaluated_on = evaluation_date or date.today()
    if holdout_dates < MIN_HOLDOUT_DATES:
        raise ValueError(f"holdout_dates must be at least {MIN_HOLDOUT_DATES}")
    if len(dates) <= holdout_dates:
        return {
            "horizon": "10 calendar days, market-adjusted",
            "candidate": "Prior-only median by market/signal/severity, with hierarchical backoff",
            "qualified": False,
            "reason": "Not enough distinct dates for a chronological train/holdout split.",
            "overall": _metrics([]),
            "by_market": {},
        }

    first_holdout = dates[-holdout_dates]
    latest_as_of = dates[-1]
    train = [r for r in rows if r["as_of"] < first_holdout]
    test = [r for r in rows if r["as_of"] >= first_holdout]
    pairs = [(_forecast(train, row), row["outcome"], row["as_of"]) for row in test]
    overall = _metrics(pairs)
    by_market = {
        market: _metrics([
            (_forecast(train, row), row["outcome"], row["as_of"])
            for row in test if row["market"] == market
        ])
        for market in ("us", "africa")
    }
    qualified = overall["qualified"] and all(
        result["qualified"] for result in by_market.values()
    )
    reasons = [overall["reason"]]
    reasons.extend(f"{market}: {result['reason']}" for market, result in by_market.items()
                   if not result["qualified"])
    data_age_days = (evaluated_on - latest_as_of).days
    fresh = 0 <= data_age_days <= MAX_DATA_AGE_DAYS
    if not fresh:
        reasons.append(
            f"latest labelled as-of date is {data_age_days} days old "
            f"(maximum {MAX_DATA_AGE_DAYS})"
        )
    qualified = qualified and fresh
    return {
        "horizon": "10 calendar days, market-adjusted",
        "candidate": "Prior-only median by market/signal/severity, with hierarchical backoff",
        "train_through": max(r["as_of"] for r in train).isoformat(),
        "holdout_from": first_holdout.isoformat(),
        "holdout_through": dates[-1].isoformat(),
        "train_n": len(train),
        "evaluated_on": evaluated_on.isoformat(),
        "latest_labelled_as_of": latest_as_of.isoformat(),
        "data_age_days": data_age_days,
        "freshness_max_age_days": MAX_DATA_AGE_DAYS,
        "freshness_passed": fresh,
        "qualified": qualified,
        "reason": "Passed overall and market-specific holdout checks." if qualified else "; ".join(reasons),
        "overall": overall,
        "by_market": by_market,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a separate 10-day return forecast.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--holdout-dates", type=int, default=6)
    args = parser.parse_args()
    print(json.dumps(evaluate(_read_predictions(args.csv), args.holdout_dates), indent=2))


if __name__ == "__main__":
    main()
