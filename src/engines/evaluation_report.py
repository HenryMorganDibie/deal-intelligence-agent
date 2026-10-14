"""
Signal evaluation report: every figure with its sample size and a 95% interval.

Built from the walk-forward backtest results (data/historical_backtest.json). Two outcomes are
kept strictly apart:

  event confirmation   did the flagged event happen? (a confirming filing, exchange disclosure or
                       credible report within 90 days). Says nothing about returns.
  market reaction      what did the share price do, net of the market, over the next 10 calendar
                       days? Measures returns, not whether the event happened. No trading costs,
                       position sizing or portfolio simulation is applied, so it is not a P&L.

    python main.py backtest --evaluation  (rewrites docs/evaluation_report.json and the CSV)
"""
from __future__ import annotations

import csv
import io
import json
import math
import statistics
from pathlib import Path
from typing import Optional

from src.engines.historical_backtest import HORIZON_DAYS, LOOKBACK_DAYS, PRICE_ONLY, RESULTS_PATH, UNIVERSE

DOCS = Path(__file__).resolve().parents[2] / "docs"
REPORT_PATH = DOCS / "evaluation_report.json"
CSV_PATH = DOCS / "backtest_predictions.csv"
Z = 1.96

RULES = [
    {"name": "Walk-forward replay",
     "rule": f"On each monthly as-of date the engine sees only sources published in the previous {LOOKBACK_DAYS} days. "
             f"A signal type that was already flagged for the company within the previous {HORIZON_DAYS} days is not a new prediction."},
    {"name": "Event confirmation (confirmable types)",
     "rule": f"Confirmed if, strictly after the as-of date and within {HORIZON_DAYS} calendar days, an SEC filing (8-K item "
             "codes, Forms 4/13D, 15-12B, 25), an NGX or NSE Kenya disclosure, or a credible news report records the event "
             "type for the same company. Refuted if none appears. 'Official only' counts filings and exchange disclosures "
             "and excludes news."},
    {"name": "Market reaction (all types)",
     "rule": "Stock close on the first trading day on or after as-of + 10 calendar days, against the first close on or "
             "after the as-of date, minus the benchmark's return over the same dates (S&P 500 for US, Satrix 40 for JSE, "
             "NGX ASI, NSE NASI). About 7 trading days. Missing prices leave the move unlabelled."},
    {"name": "Price-only types",
     "rule": "Earnings surprises and insider trades are themselves the disclosure, so they are not 'confirmed'; they are "
             "judged only on whether the market-adjusted move went the expected way (source-stated direction when "
             "available, else the type's hypothesised sign)."},
    {"name": "Base rate",
     "rule": f"Share of all company-months (each company on each as-of date) followed within {HORIZON_DAYS} days by a "
             "confirmed event of that type, whether or not anything was flagged. Lift = precision / base rate."},
    {"name": "Recall",
     "rule": f"Share of confirmed events that a prediction of the same type preceded by 1 to {HORIZON_DAYS} days."},
    {"name": "Hosted (live) labelling",
     "rule": f"Hosted briefs are labelled with the same rules: price reaction once a brief is 12 days old (so the day-10 "
             f"close exists even across a weekend or holiday), confirmation once it is 95 days old (the {HORIZON_DAYS}-day "
             f"window plus 5 days for filings and reports to be indexed)."},
    {"name": "Intervals",
     "rule": "95% Wilson score intervals for proportions; lift intervals divide the precision interval by the base rate "
             "(base-rate uncertainty not included); means use a normal approximation (mean ± 1.96·sd/√n)."},
]


def wilson(k: int, n: int) -> Optional[dict]:
    if not n:
        return None
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return {"value": round(p, 3), "low": round(max(0.0, c - h), 3), "high": round(min(1.0, c + h), 3), "k": k, "n": n}


def mean_ci(xs: list[float]) -> Optional[dict]:
    if not xs:
        return None
    m = statistics.mean(xs)
    if len(xs) < 2:
        return {"value": round(m, 2), "low": None, "high": None, "n": len(xs)}
    h = Z * statistics.stdev(xs) / math.sqrt(len(xs))
    return {"value": round(m, 2), "low": round(m - h, 2), "high": round(m + h, 2), "n": len(xs),
            "median": round(statistics.median(xs), 2)}


def _signed(p: dict) -> Optional[float]:
    """Market-adjusted move in the predicted direction (positive = went the predicted way)."""
    r, d = p.get("abnormal_return_10d_pct"), p.get("direction")
    if r is None or d not in ("positive", "negative"):
        return None
    return r if d == "positive" else -r


def _market_rows(rows: list[dict], m: dict, signal_type: str, months: Optional[int] = None) -> dict:
    price_only = signal_type in PRICE_ONLY
    labelled = [p for p in rows if p.get("event_confirmed") is not None] if not price_only else []
    k = sum(p["event_confirmed"] for p in labelled)
    precision = wilson(k, len(labelled))
    base = m.get("base_rate")
    official = [p for p in rows if p.get("confirmed_by_official_filing") is not None] if not price_only else []
    directional = [p["direction_correct"] for p in rows if p.get("direction_correct") is not None]
    signed = [s for s in (_signed(p) for p in rows) if s is not None]
    events = m.get("events", 0)
    caught = m.get("caught", round((m.get("recall") or 0) * events))
    return {
        "predictions": len(rows),
        "event_confirmation": None if price_only else {
            "labelled": len(labelled), "unlabelled": len(rows) - len(labelled), "confirmed": k,
            "precision": precision,
            "precision_official_only": wilson(sum(p["confirmed_by_official_filing"] for p in official), len(official)),
            "base_rate": {"value": base,
                          # Results stored before counts were kept: hits recovered from the 3-decimal rate (exact at these sizes).
                          "hits": m.get("base_hits", round(base * months) if base is not None and months else None),
                          "company_months": m.get("company_months", months)},
            "lift": None if not precision or not base else {
                "value": round(precision["value"] / base, 2), "low": round(precision["low"] / base, 2),
                "high": round(precision["high"] / base, 2)},
            "recall": wilson(caught, events),
        },
        "market_reaction": {
            "moves_n": len(signed),
            "direction_hit_rate": wilson(sum(directional), len(directional)),
            "mean_move_in_predicted_direction_pct": mean_ci(signed),
        },
    }


def build(result: dict) -> dict:
    preds = result["predictions"]
    metrics = result["metrics"]
    months = {}
    for entry in UNIVERSE:
        mk = "us" if "." not in entry[1] else "africa"
        months[mk] = months.get(mk, 0) + result["as_of_dates"]
    confirmable = [p for p in preds if p["signal_type"] not in PRICE_ONLY]
    price_only = [p for p in preds if p["signal_type"] in PRICE_ONLY]
    lab = [p for p in confirmable if p.get("event_confirmed") is not None]
    funnel = {
        "predictions": len(preds),
        "confirmable_predictions": len(confirmable),
        "confirmation_labelled": len(lab),
        "confirmation_unlabelled": len(confirmable) - len(lab),
        "confirmed": sum(p["event_confirmed"] for p in lab),
        "price_only_predictions": len(price_only),
        "direction_labelled": sum(p.get("direction_correct") is not None for p in preds),
        "price_only_direction_labelled": sum(p.get("direction_correct") is not None for p in price_only),
        "with_market_move": sum(p.get("abnormal_return_10d_pct") is not None for p in preds),
        "explanation": (
            "Every flag in the replay is a prediction. Confirmable types (M&A, credit, distress, leadership, regulatory, "
            "restructuring) are judged on whether the event happened; those whose outcome could be checked are "
            "'labelled', and 'confirmed' is the subset where it happened. Earnings surprises and insider trades are the "
            "disclosure itself, so they are judged only on the market move. Market moves are measured for every "
            "prediction with prices, whatever its type."),
    }
    by_type = {}
    for st in sorted(metrics):
        by_type[st] = {"price_only": st in PRICE_ONLY}
        for mk in ("all", "us", "africa"):
            rows = [p for p in preds if p["signal_type"] == st and (mk == "all" or p["market"] == mk)]
            n_months = sum(months.values()) if mk == "all" else months.get(mk)
            by_type[st][mk] = _market_rows(rows, metrics[st].get(mk, {}), st, n_months)
    pooled = {mk: _market_rows([p for p in confirmable if mk == "all" or p["market"] == mk], {}, "pooled")
              for mk in ("all", "us", "africa")}

    av = result.get("alpha_validation") or {}
    cut = av.get("cutoffs")
    bands = {}
    if cut:
        def band(a: float) -> str:
            return "low" if a < cut[0] else "middle" if a < cut[1] else "high"
        for name in ("low", "middle", "high"):
            conf_rows = [p for p in lab if p.get("alpha") is not None and band(p["alpha"]) == name]
            all_rows = [p for p in preds if p.get("alpha") is not None and band(p["alpha"]) == name]
            signed = [s for s in (_signed(p) for p in all_rows) if s is not None]
            bands[name] = {
                "alpha_range": (av.get("bands") or {}).get(name, {}).get("alpha_range"),
                "event_confirmation": wilson(sum(p["event_confirmed"] for p in conf_rows), len(conf_rows)),
                "direction_hit_rate": wilson(sum(p["direction_correct"] for p in all_rows if p.get("direction_correct") is not None),
                                             sum(p.get("direction_correct") is not None for p in all_rows)),
                "mean_move_in_predicted_direction_pct": mean_ci(signed),
            }
    return {
        "design": {"start": result["start"], "end": result["end"], "as_of_dates": result["as_of_dates"],
                   "companies": {"us": sum("." not in e[1] for e in UNIVERSE), "africa": sum("." in e[1] for e in UNIVERSE)},
                   "company_months": months, "lookback_days": LOOKBACK_DAYS, "horizon_days": HORIZON_DAYS,
                   "reproduce": "python main.py backtest --historical (network; responses cached in data/hist_cache), "
                                "then python main.py backtest --evaluation. Data-quality and attribution sets: "
                                "python -m evaluation.deals.score, python -m evaluation.attribution.score [--heldout]"},
        "funnel": funnel,
        "by_type": by_type,
        "pooled_confirmable": pooled,
        "alpha": {
            "what_it_is": "A ranking from declared weights (severity 35, source credibility 25, corroboration 20, recency 10, "
                          "liquidity 10). The weights were not fitted to outcomes.",
            "spearman_alpha_vs_confirmed": av.get("spearman_alpha_vs_confirmed"),
            "bands": bands,
            "by_type": av.get("by_type"),
            "reading": "A rising confirmation rate across alpha thirds shows the ranking orders flags by how often the "
                       "event happened. It does not show that acting on high-alpha flags earns returns: see the market "
                       "reaction columns, which are measured separately and include no costs.",
        },
        "rules": RULES,
    }


def predictions_csv(result: dict) -> str:
    cols = ["company", "ticker", "market", "as_of", "signal_type", "severity", "alpha", "direction", "source_kind",
            "source", "event_confirmed", "confirmed_by_official_filing", "confirmation_source",
            "abnormal_return_10d_pct", "price_change_10d_pct", "direction_correct"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for p in sorted(result["predictions"], key=lambda p: (p["as_of"], p["company"], p["signal_type"])):
        w.writerow(p)
    return buf.getvalue()


def write(result: Optional[dict] = None) -> dict:
    result = result or json.loads(RESULTS_PATH.read_text())
    report = build(result)
    REPORT_PATH.write_text(json.dumps(report, indent=1))
    CSV_PATH.write_text(predictions_csv(result))
    return report
