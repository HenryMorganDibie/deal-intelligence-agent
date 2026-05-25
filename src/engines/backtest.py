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

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.schemas.models import SignalType, Severity

BACKTEST_PATH = Path(__file__).resolve().parents[2] / "data" / "backtest_results.json"


def _load_backtest() -> dict:
    BACKTEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not BACKTEST_PATH.exists():
        return {"runs": [], "summary": {}}
    try:
        return json.loads(BACKTEST_PATH.read_text())
    except Exception:
        return {"runs": [], "summary": {}}


def _save_backtest(data: dict) -> None:
    BACKTEST_PATH.write_text(json.dumps(data, indent=2, default=str))


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return round(a / b, 4) if b > 0 else default


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def _max_drawdown(returns: list[float]) -> float:
    """Maximum peak-to-trough drawdown in a returns series."""
    if not returns:
        return 0.0
    peak = returns[0]
    max_dd = 0.0
    for r in returns:
        if r > peak:
            peak = r
        dd = (peak - r) / peak if peak != 0 else 0
        if dd > max_dd:
            max_dd = dd
    return round(max_dd * 100, 2)  # as %


class BacktestEngine:
    """
    Runs historical signal validation against warehouse data and market outcomes.
    """

    def run_from_warehouse(self) -> dict:
        """
        Pull historical signals and outcomes from the warehouse,
        compute full metrics suite, store results.
        """
        try:
            from src.engines.warehouse import get_session, DetectedSignalRecord, MarketOutcomeRecord
            session = get_session()
            signals  = session.query(DetectedSignalRecord).all()
            outcomes = session.query(MarketOutcomeRecord).all()
            session.close()
        except Exception as e:
            return {"error": f"Warehouse query failed: {e}", "metrics": {}}

        # Build outcome lookup: company_name + signal_type → list of outcomes
        outcome_map: dict[str, list] = {}
        for o in outcomes:
            key = f"{o.company_name}::{o.signal_type}"
            outcome_map.setdefault(key, []).append(o)

        # Aggregate per signal type
        per_type: dict[str, dict] = {}
        for sig_type in SignalType:
            type_signals = [s for s in signals if s.signal_type == sig_type.value]
            if not type_signals:
                continue

            tp = 0   # true positives (confirmed events)
            fp = 0   # false positives
            fn = 0   # false negatives (known events not flagged — approx from outcome data)
            excess_returns: list[float] = []
            drawdowns: list[float] = []
            tte_days: list[int] = []  # time to event

            for sig in type_signals:
                key = f"{sig.company_name}::{sig.signal_type}"
                matched_outcomes = outcome_map.get(key, [])

                if not matched_outcomes:
                    fp += 1  # no outcome recorded → treat as false positive
                    continue

                for o in matched_outcomes:
                    if o.event_confirmed:
                        tp += 1
                        # Excess return: 10d price move
                        if o.price_change_10d_pct is not None:
                            excess_returns.append(o.price_change_10d_pct)
                        if o.price_change_5d_pct is not None and o.price_change_10d_pct is not None:
                            drawdowns.append(min(o.price_change_5d_pct, o.price_change_10d_pct, 0))
                        # Time to materialization
                        if o.confirmation_date and o.detection_date:
                            try:
                                det = datetime.strptime(o.detection_date, "%Y-%m-%d")
                                con = datetime.strptime(o.confirmation_date, "%Y-%m-%d")
                                tte_days.append((con - det).days)
                            except Exception:
                                pass
                    else:
                        fp += 1

            total_flagged = tp + fp
            precision = _safe_div(tp, total_flagged)
            # Recall approximation: tp / (tp + fn). fn is unknown without ground truth;
            # we flag it clearly as approximate.
            recall_approx = _safe_div(tp, max(tp + max(fn, 1), 1))
            f1 = _f1(precision, recall_approx)

            avg_excess = sum(excess_returns) / max(len(excess_returns), 1)
            hit_rate   = sum(1 for r in excess_returns if r > 0) / max(len(excess_returns), 1)
            max_dd     = _max_drawdown([abs(d) for d in drawdowns if d < 0])
            median_tte = sorted(tte_days)[len(tte_days)//2] if tte_days else None

            per_type[sig_type.value] = {
                "signals_flagged":          total_flagged,
                "true_positives":           tp,
                "false_positives":          fp,
                "precision":                round(precision, 3),
                "recall_approx":            round(recall_approx, 3),
                "f1":                       round(f1, 3),
                "hit_rate":                 round(hit_rate, 3),
                "avg_excess_return_10d_pct": round(avg_excess, 2) if excess_returns else None,
                "max_drawdown_pct":         max_dd if drawdowns else None,
                "median_days_to_event":     median_tte,
                "false_positive_rate":      round(_safe_div(fp, total_flagged), 3),
                "note": "recall_approx requires ground-truth event database for accuracy",
            }

        result = {
            "run_at":    datetime.utcnow().isoformat(),
            "total_signals_evaluated": len(signals),
            "total_outcomes_available": len(outcomes),
            "metrics_by_signal_type": per_type,
            "overall": self._compute_overall(per_type),
            "data_quality_note": (
                "Backtest accuracy improves with more analyst-confirmed outcomes. "
                "False negatives (missed events) cannot be computed without a complete ground-truth event database. "
                "Precision figures are conservative — unconfirmed signals treated as false positives."
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
        f1s        = [v["f1"]        for v in per_type.values() if v.get("signals_flagged", 0) > 0]
        hit_rates  = [v["hit_rate"]  for v in per_type.values() if v.get("hit_rate") is not None]
        returns    = [v["avg_excess_return_10d_pct"] for v in per_type.values()
                      if v.get("avg_excess_return_10d_pct") is not None]

        return {
            "macro_precision": round(sum(precisions) / max(len(precisions), 1), 3),
            "macro_f1":        round(sum(f1s)        / max(len(f1s),        1), 3),
            "avg_hit_rate":    round(sum(hit_rates)  / max(len(hit_rates),  1), 3),
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
            "run_at": datetime.utcnow().isoformat(),
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
