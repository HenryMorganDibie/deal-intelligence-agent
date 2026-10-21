from datetime import date

import pytest

from src.engines.return_forecast import evaluate


def _row(as_of, market, outcome, signal_type="leadership_change", severity="medium"):
    return {
        "as_of": date.fromisoformat(as_of),
        "market": market,
        "signal_type": signal_type,
        "severity": severity,
        "outcome": outcome,
    }


def test_evaluation_uses_only_prior_dates_and_gates_unproven_returns():
    rows = []
    for month in range(1, 7):
        # Training outcomes vary around zero; the zero-return baseline is the benchmark.
        rows.extend(_row(f"2024-{month:02d}-01", "us", value)
                    for value in (-1.0, 1.0) * 20)
    for month in range(1, 7):
        rows.extend(_row(f"2025-{month:02d}-01", "us", value)
                    for value in (-1.0, 1.0) * 20)

    result = evaluate(rows, evaluation_date=date(2025, 7, 1))
    assert result["train_n"] == 240
    assert result["overall"]["holdout_n"] == 240
    assert result["overall"]["candidate_mae_pct"] == result["overall"]["zero_return_baseline_mae_pct"]
    assert result["overall"]["absolute_mae_improvement_ci_low_pct_points"] <= 0
    assert result["qualified"] is False
    assert "MAE improvement below 5%" in result["reason"]
    assert result["freshness_passed"] is True


def test_forecast_is_not_qualified_when_africa_has_too_few_holdout_rows():
    rows = []
    for year, months in ((2024, range(1, 7)), (2025, range(1, 7))):
        for month in months:
            rows.extend(_row(f"{year}-{month:02d}-01", "us", 1.0) for _ in range(30))
            if year == 2025:
                rows.append(_row(f"{year}-{month:02d}-01", "africa", 1.0))

    result = evaluate(rows, evaluation_date=date(2025, 7, 1))
    assert result["by_market"]["us"]["holdout_n"] == 180
    assert result["by_market"]["africa"]["holdout_n"] == 6
    assert result["qualified"] is False
    assert "fewer than 100 holdout outcomes" in result["reason"]


def test_stale_holdout_cannot_qualify_as_a_live_return_forecast():
    rows = []
    for year, months in ((2024, range(1, 7)), (2025, range(1, 7))):
        for month in months:
            rows.extend(_row(f"{year}-{month:02d}-01", "us", 1.0) for _ in range(30))

    result = evaluate(rows, evaluation_date=date(2026, 10, 16))
    assert result["data_age_days"] > result["freshness_max_age_days"]
    assert result["freshness_passed"] is False
    assert "latest labelled as-of date is" in result["reason"]


def test_requires_six_or_more_holdout_dates():
    with pytest.raises(ValueError, match="at least 6"):
        evaluate([], holdout_dates=5)


def test_clustered_interval_measures_the_change_in_error_not_the_size_of_returns():
    from src.engines.return_forecast import _metrics

    # A forecast of 0.1 against large returns barely changes each absolute error, so the
    # interval must be narrow; using |return| - |forecast| would make it as wide as the returns.
    pairs = []
    for day in range(1, 13):
        for actual in (-8.0, 8.0, -6.0, 6.0):
            pairs.append((0.1, actual, date(2025, 1, day)))
    m = _metrics(pairs)
    assert m["mae_improvement_pct"] == 0.0
    assert abs(m["absolute_mae_improvement_ci_low_pct_points"]) < 0.05


def test_walk_forward_scores_every_date_after_the_training_window_without_lookahead():
    rows = []
    for month in range(1, 13):
        # Each month's outcomes equal the month number, so any forecast that saw the
        # month's own outcomes would be exact; prior-only forecasts cannot be.
        rows.extend(_row(f"2024-{month:02d}-01", "us", float(month)) for _ in range(40))
    result = evaluate(rows, evaluation_date=date(2024, 12, 15))
    assert result["holdout_from"] == "2024-07-01" and result["overall"]["holdout_dates"] == 6
    assert result["method"].startswith("walk-forward")
    assert result["overall"]["candidate_mae_pct"] > 0


def test_published_report_is_rechecked_for_freshness_and_gates_estimates():
    from src.engines.return_forecast import current_status, estimate

    report = {"qualified": True, "latest_labelled_as_of": "2026-06-15", "freshness_max_age_days": 180,
              "horizon": "10 calendar days, market-adjusted", "candidate": "c", "evaluated_on": "2026-07-01",
              "overall": {"candidate_mae_pct": 3.0}, "reason": "Passed"}
    assert current_status(report, date(2026, 9, 1))["qualified"] is True
    stale = current_status(report, date(2027, 3, 1))
    assert stale["qualified"] is False and "days old" in stale["reason"]
    refused = estimate({**report, "qualified": False, "reason": "MAE improvement below 5%"}, "us", "m_and_a_activity", "high")
    assert refused == {"issued": False, "reason": "MAE improvement below 5%"}
    assert estimate(report, "us", "m_and_a_activity", "high", today=date(2027, 3, 1))["issued"] is False
