"""
Historical Backtesting Engine.
Validates that detected signals have real predictive power by running
deterministic detection against historical warehouse data and comparing
against recorded market outcomes.

Metrics computed per signal type:
  - Precision (of flagged events, how many materialised?)
  - Recall (of known events, how many were flagged?)
  - F1 score
  - Hit rate (direction accuracy)
  - Average excess return (post-signal price move)
  - Max drawdown after signal
  - Time-to-materialization (median days to event confirmation)
  - False positive rate
  - Signal density (signals per 100 company-days)

Usage:
  python main.py backtest --run
  python main.py backtest --report
  python main.py backtest --signal credit_risk
"""
from __future__ import annotations

from src.utils.storage import load_json, save_json
import json
import statistics
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from src.schemas.models import SignalType, Severity
from src.utils.clock import utcnow
from src.utils.paths import DATA_DIR

BACKTEST_PATH = DATA_DIR / "backtest_results.json"


def _load_backtest() -> dict:
    return load_json(BACKTEST_PATH, lambda: {"runs": [], "summary": {}})


def _save_backtest(data: dict) -> None:
    save_json(BACKTEST_PATH, data)


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return round(a / b, 4) if b > 0 else default


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def _max_drawdown(prices: list[float]) -> float:
    """Maximum peak-to-trough drawdown (%) of a price or value series."""
    if not prices:
        return 0.0
    peak = prices[0]
    max_dd = 0.0
    for r in prices:
        if r > peak:
            peak = r
        dd = (peak - r) / peak if peak != 0 else 0
        if dd > max_dd:
            max_dd = dd
    return round(max_dd * 100, 2)


# A confirmed outcome supports a signal flagged within this many days of its detection date.
OUTCOME_MATCH_DAYS = 7


def _parse_day(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _within_days(outcome_day, signal_day, days: int = OUTCOME_MATCH_DAYS) -> bool:
    a, b = _parse_day(outcome_day), _parse_day(signal_day)
    return a is not None and b is not None and abs((a - b).days) <= days


def _days_between(start, end) -> Optional[int]:
    a, b = _parse_day(start), _parse_day(end)
    return (b - a).days if a and b else None


class BacktestEngine:
    """
    Runs historical signal validation against warehouse data and market outcomes.
    """

    def run_from_warehouse(self) -> dict:
        """
        Score historical signals (warehouse) against recorded market outcomes.

        Outcomes come from the market-impact store, which is where
        `outcomes --record` and `marketdata --auto-outcome` write them.

        Each prediction is counted once: repeated runs that flag the same
        company and signal type on the same day are one prediction. A
        prediction is a true positive if a confirmed outcome for that
        company and type was detected within OUTCOME_MATCH_DAYS of it.
        """
        try:
            from src.engines.warehouse import get_session, DetectedSignalRecord
            from src.engines.market_impact import _load as load_outcomes
            session = get_session()
            signals = session.query(DetectedSignalRecord).all()
            session.close()
            outcomes = load_outcomes()
        except Exception as e:
            return {"error": f"Backtest data load failed: {e}", "metrics": {}}

        outcome_map: dict[str, list[dict]] = {}
        for o in outcomes:
            outcome_map.setdefault(f"{o.get('company_name')}::{o.get('signal_type')}", []).append(o)

        # One prediction per (company, signal type, day).
        predictions: dict[tuple, object] = {}
        for sig in signals:
            day = sig.detected_at.date() if sig.detected_at else None
            predictions.setdefault((sig.company_name, sig.signal_type, day), sig)

        per_type: dict[str, dict] = {}
        for sig_type in SignalType:
            preds = [(k, v) for k, v in predictions.items() if k[1] == sig_type.value]
            if not preds:
                continue

            tp = fp = 0
            used: dict[str, dict] = {}
            tte_days: list[int] = []
            for (company, stype, day), _sig in preds:
                matched = [
                    o for o in outcome_map.get(f"{company}::{stype}", [])
                    if o.get("event_confirmed") and _within_days(o.get("detection_date"), day)
                ]
                if not matched:
                    fp += 1      # conservative: no confirmed outcome counts against the signal
                    continue
                tp += 1
                for o in matched:
                    used[o.get("outcome_id") or id(o)] = o
                    tte = _days_between(o.get("detection_date"), o.get("confirmation_date"))
                    if tte is not None:
                        tte_days.append(tte)

            outs = list(used.values())
            returns = [o["price_change_10d_pct"] for o in outs if o.get("price_change_10d_pct") is not None]
            directional = [o["direction_correct"] for o in outs if o.get("direction_correct") is not None]
            drawdowns = [
                abs(min([o.get(k) for k in ("price_change_5d_pct", "price_change_10d_pct", "price_change_30d_pct")
                         if o.get(k) is not None] + [0.0]))
                for o in outs
            ]
            total_flagged = tp + fp

            per_type[sig_type.value] = {
                "signals_flagged":           total_flagged,
                "true_positives":            tp,
                "false_positives":           fp,
                "precision":                 round(_safe_div(tp, total_flagged), 3),
                # Recall and F1 need a ground-truth list of events the engine missed; we do not have one.
                "recall_approx":             None,
                "f1":                        None,
                # Hit = price moved the way the signal predicted (negative signals predict a fall).
                "hit_rate":                  round(sum(directional) / len(directional), 3) if directional else None,
                "avg_excess_return_10d_pct": round(sum(returns) / len(returns), 2) if returns else None,
                "max_drawdown_pct":          round(max(drawdowns), 2) if drawdowns else None,
                "median_days_to_event":      statistics.median(tte_days) if tte_days else None,
                "false_positive_rate":       round(_safe_div(fp, total_flagged), 3),
                "note": "Returns are raw 10-day price moves, not benchmark-adjusted.",
            }

        result = {
            "run_at":    utcnow().isoformat(),
            "total_signals_evaluated": len(predictions),
            "total_outcomes_available": len(outcomes),
            "metrics_by_signal_type": per_type,
            "overall": self._compute_overall(per_type),
            "data_quality_note": (
                "Precision is conservative: signals without a confirmed outcome count as false positives. "
                "Recall and F1 are not computed: they need a ground-truth database of missed events."
            ),
        }

        data = _load_backtest()
        data["runs"].append(result)
        data["summary"] = result
        _save_backtest(data)
        return result

    def _compute_overall(self, per_type: dict) -> dict:
        if not per_type:
            return {}
        precisions = [v["precision"] for v in per_type.values() if v.get("signals_flagged", 0) > 0]
        f1s        = [v["f1"]        for v in per_type.values() if v.get("f1") is not None]
        hit_rates  = [v["hit_rate"]  for v in per_type.values() if v.get("hit_rate") is not None]
        returns    = [v["avg_excess_return_10d_pct"] for v in per_type.values()
                      if v.get("avg_excess_return_10d_pct") is not None]

        return {
            "macro_precision": round(sum(precisions) / max(len(precisions), 1), 3),
            "macro_f1":        round(sum(f1s) / len(f1s), 3) if f1s else None,
            "avg_hit_rate":    round(sum(hit_rates) / len(hit_rates), 3) if hit_rates else None,
            "avg_excess_return_pct": round(sum(returns) / max(len(returns), 1), 2) if returns else None,
        }

    def run_synthetic(self) -> dict:
        """
        Run a synthetic backtest using seeded historical data when warehouse is empty.
        This simulates what real backtest output looks like and validates the framework.
        """
        import random
        random.seed(42)

        synthetic_per_type = {}
        for sig_type in SignalType:
            n = random.randint(15, 80)
            tp = int(n * random.uniform(0.45, 0.82))
            fp = n - tp
            returns = [random.gauss(
                6 if sig_type in {SignalType.MA_ACTIVITY} else -8, 10
            ) for _ in range(tp)]
            precision = _safe_div(tp, n)
            recall    = round(random.uniform(0.40, 0.75), 3)
            synthetic_per_type[sig_type.value] = {
                "signals_flagged":           n,
                "true_positives":            tp,
                "false_positives":           fp,
                "precision":                 round(precision, 3),
                "recall_approx":             recall,
                "f1":                        _f1(precision, recall),
                "hit_rate":                  round(sum(1 for r in returns if r > 0) / max(len(returns), 1), 3),
                "avg_excess_return_10d_pct": round(sum(returns) / max(len(returns), 1), 2) if returns else None,
                "max_drawdown_pct":          round(random.uniform(3, 25), 1),
                "median_days_to_event":      random.randint(5, 45),
                "false_positive_rate":       round(_safe_div(fp, n), 3),
                "synthetic":                 True,
                "note": "Synthetic data — run with real outcomes for validated metrics",
            }

        result = {
            "run_at": utcnow().isoformat(),
            "mode": "synthetic",
            "total_signals_evaluated": sum(v["signals_flagged"] for v in synthetic_per_type.values()),
            "metrics_by_signal_type": synthetic_per_type,
            "overall": self._compute_overall(synthetic_per_type),
            "data_quality_note": "SYNTHETIC — replace with real outcomes via `python main.py outcomes --record`",
        }

        data = _load_backtest()
        data["runs"].append(result)
        data["summary"] = result
        _save_backtest(data)
        return result


def get_latest_backtest() -> Optional[dict]:
    data = _load_backtest()
    return data.get("summary")


def get_backtest_history() -> list[dict]:
    data = _load_backtest()
    return data.get("runs", [])
