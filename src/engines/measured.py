"""
Measured outcome tables: what past signals actually led to.

Built from the walk-forward historical backtest (docs/BACKTEST.md), never typed
in by hand. For every signal type, and for each type and severity where the
sample allows, the table holds:

  confirmation   how often a flag was followed within 90 days by a confirming
                 filing, exchange disclosure or credible report
                 (confirmable types only)
  direction      how often the market-adjusted 10-day move went the way the
                 signal type implies (price-only types: earnings, insider)
  moves          the distribution of market-adjusted 10-day returns after a
                 flag: count, median, interquartile range, share negative

Every figure carries its sample size. Callers smooth small samples toward the
type-level (or overall) rate and say "insufficient history" below MIN_N.

The committed file is src/data/measured_outcomes.json, rewritten by
`python main.py backtest --historical` (or `--tables` from saved results).
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Optional

_REFERENCE = Path(__file__).resolve().parent.parent / "data"
TABLES_PATH = _REFERENCE / "measured_outcomes.json"

PRICE_ONLY = {"earnings_surprise", "insider_activity"}
# The sign each signal type is hypothesised to move a stock. The backtest tests these; they are not
# outputs of the data, so the live expected direction comes from the measured moves instead.
DIRECTION_HYPOTHESIS = {
    "m_and_a_activity": "positive", "credit_risk": "negative", "distressed_asset": "negative",
    "earnings_surprise": "negative", "leadership_change": "negative", "regulatory_action": "negative",
    "debt_restructuring": "negative", "insider_activity": "positive",
}
MIN_N = 10            # below this a figure is reported as insufficient history
SMOOTHING = 5         # pseudo-observations pulling a small sample toward its parent rate


def _rate(k: int, n: int) -> Optional[float]:
    return round(k / n, 4) if n else None


def _moves(values: list[float]) -> Optional[dict]:
    if not values:
        return None
    q = statistics.quantiles(values, n=4) if len(values) >= 2 else [values[0]] * 3
    return {"n": len(values), "median": round(statistics.median(values), 2), "p25": round(q[0], 2),
            "p75": round(q[2], 2), "share_negative": round(sum(v < 0 for v in values) / len(values), 3)}


def build(predictions: list[dict], meta: Optional[dict] = None) -> dict:
    """Tables from backtest predictions (each with signal_type, severity, event_confirmed,
    direction_correct, abnormal_return_10d_pct)."""
    by_type: dict[str, dict] = {}
    for st in sorted({p["signal_type"] for p in predictions}):
        rows = [p for p in predictions if p["signal_type"] == st]
        entry = {"type": _summary(st, rows), "by_severity": {}}
        for sev in sorted({p["severity"] for p in rows}):
            entry["by_severity"][sev] = _summary(st, [p for p in rows if p["severity"] == sev])
        by_type[st] = entry
    confirmable = [p for p in predictions if p["signal_type"] not in PRICE_ONLY and p.get("event_confirmed") is not None]
    overall = {"labelled": len(confirmable), "confirmed": sum(p["event_confirmed"] for p in confirmable),
               "rate": _rate(sum(p["event_confirmed"] for p in confirmable), len(confirmable))}
    return {"source": "walk-forward historical backtest (docs/BACKTEST.md)", **(meta or {}),
            "overall_confirmation": overall, "signals": by_type,
            "method": f"Confirmation: share of flags followed within 90 days by a confirming filing, disclosure or "
                      f"credible report. Moves: market-adjusted return over 10 trading days after the flag. Figures "
                      f"with fewer than {MIN_N} observations are reported as insufficient history; smaller groups are "
                      f"smoothed toward their parent rate with {SMOOTHING} pseudo-observations."}


def _summary(signal_type: str, rows: list[dict]) -> dict:
    out: dict = {"predictions": len(rows)}
    if signal_type in PRICE_ONLY:
        d = [p["direction_correct"] for p in rows if p.get("direction_correct") is not None]
        out["direction"] = {"labelled": len(d), "correct": sum(d), "rate": _rate(sum(d), len(d))}
    else:
        c = [p["event_confirmed"] for p in rows if p.get("event_confirmed") is not None]
        out["confirmation"] = {"labelled": len(c), "confirmed": sum(c), "rate": _rate(sum(c), len(c))}
    out["moves"] = _moves([p["abnormal_return_10d_pct"] for p in rows if p.get("abnormal_return_10d_pct") is not None])
    return out


def write(tables: dict, path: Optional[Path] = None) -> None:
    (path or TABLES_PATH).write_text(json.dumps(tables, indent=1, sort_keys=True))


_CACHE: Optional[dict] = None


def load() -> dict:
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = json.loads(TABLES_PATH.read_text())
        except (OSError, ValueError):
            _CACHE = {"signals": {}, "overall_confirmation": {"labelled": 0, "confirmed": 0, "rate": None}}
    return _CACHE


def set_tables(tables: Optional[dict]) -> None:
    """Use these tables instead of the committed file (tests; None reloads the file)."""
    global _CACHE
    _CACHE = tables


def _smoothed(k: int, n: int, prior: float) -> float:
    return (k + SMOOTHING * prior) / (n + SMOOTHING)


def confirmation_rate(signal_type: str, severity: str) -> dict:
    """
    Measured probability that a flag of this type and severity is confirmed (confirmable types), or
    that its move goes the hypothesised way (price-only types): smoothed severity -> type -> overall.
    """
    t = load()
    sig = t.get("signals", {}).get(signal_type)
    key = "direction" if signal_type in PRICE_ONLY else "confirmation"
    overall_rate = (t.get("overall_confirmation") or {}).get("rate")
    parent_default = 0.5 if key == "direction" else (overall_rate if overall_rate is not None else 0.1)
    if not sig:
        return {"rate": parent_default, "n": 0, "basis": "no history for this signal type: overall rate"}
    type_stats = sig["type"].get(key) or {}
    tn, tk = type_stats.get("labelled", 0), type_stats.get("confirmed", type_stats.get("correct", 0))
    type_rate = _smoothed(tk, tn, parent_default)
    sev_stats = (sig.get("by_severity", {}).get(severity) or {}).get(key) or {}
    sn, sk = sev_stats.get("labelled", 0), sev_stats.get("confirmed", sev_stats.get("correct", 0))
    if sn:
        return {"rate": round(_smoothed(sk, sn, type_rate), 4), "n": sn,
                "basis": f"{sk} of {sn} {severity} flags" + (" (smoothed toward the type rate)" if sn < 30 else "")}
    return {"rate": round(type_rate, 4), "n": tn,
            "basis": f"{tk} of {tn} flags of this type (no {severity} history)" if tn else "no labelled history"}


def expected_move(signal_type: str, severity: str) -> Optional[dict]:
    """Measured market-adjusted 10-day move after this kind of flag, or None (insufficient history)."""
    sig = load().get("signals", {}).get(signal_type)
    if not sig:
        return None
    sev = (sig.get("by_severity", {}).get(severity) or {}).get("moves")
    if sev and sev["n"] >= 2 * MIN_N:
        return {**sev, "basis": f"{severity} {signal_type.replace('_', ' ')} flags"}
    typ = sig["type"].get("moves")
    if typ and typ["n"] >= MIN_N:
        return {**typ, "basis": f"all {signal_type.replace('_', ' ')} flags"}
    return None


def measured_direction(move: Optional[dict]) -> Optional[str]:
    """'negative' or 'positive' when at least 60% of measured moves went that way, else 'mixed'."""
    if not move:
        return None
    if move["share_negative"] >= 0.6:
        return "negative"
    if move["share_negative"] <= 0.4:
        return "positive"
    return "mixed"


def signed_range(direction: Optional[str], low: Optional[float], high: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    """(low, high) as signed percentages. Briefs stored before measured moves held unsigned magnitudes
    with a separate direction; a non-negative range on a negative call is one of those."""
    if low is None or high is None:
        return low, high
    if direction == "negative" and low >= 0 and high >= 0:
        return -high, -low
    return low, high


def magnitude_error(actual: Optional[float], direction: Optional[str], low: Optional[float],
                    high: Optional[float]) -> Optional[float]:
    """Distance in points between the actual move and the middle of the expected range."""
    lo, hi = signed_range(direction, low, high)
    if actual is None or lo is None or hi is None:
        return None
    return round(abs(actual - (lo + hi) / 2), 2)


def describe_move(low: Optional[float], high: Optional[float], median: Optional[float], n: int) -> Optional[str]:
    """'-2.8% to +1.3% (median -1.3%, n=53)'."""
    if low is None or high is None:
        return None
    text = f"{low:+.1f}% to {high:+.1f}%"
    if median is not None:
        text += f" (median {median:+.1f}%, n={n})"
    return text


def move_confidence(n: int) -> str:
    return "insufficient" if n < MIN_N else "low" if n < 30 else "medium" if n < 100 else "high"
