"""
Showcase briefs for the public site: the full pipeline run daily on a fixed list of
companies chosen by us, never on visitors' searches, so the landing page always shows a
recent real brief without revealing what anyone else analysed.

Each day's cron runs BATCH companies (rotating through the list, so each is refreshed every
two days); the site shows the strongest showcase brief from the last few days, or the latest
one with any signal when the market has been quiet.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

# (company, ticker, market label). A spread of US and African exchanges.
COMPANIES: list[tuple[str, str, str]] = [
    ("Intel", "INTC", "Nasdaq"),
    ("Dangote Cement", "DANGCEM.LG", "NGX"),
    ("MTN Group", "MTN.JO", "JSE"),
    ("Safaricom", "SCOM.NR", "NSE Kenya"),
    ("Boeing", "BA", "NYSE"),
    ("MTN Nigeria", "MTNN.LG", "NGX"),
    ("Naspers", "NPN.JO", "JSE"),
    ("Equity Group", "EQTY.NR", "NSE Kenya"),
]
BATCH = 4
LOOKBACK_DAYS = 90
_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def todays_batch(day: date) -> list[tuple[str, str, str]]:
    start = (day.toordinal() * BATCH) % len(COMPANIES)
    return [COMPANIES[(start + i) % len(COMPANIES)] for i in range(BATCH)]


def market_of(ticker: Optional[str]) -> Optional[str]:
    return next((m for _, t, m in COMPANIES if t == ticker), None)


def _engine_trace(brief: dict) -> dict:
    for step in brief.get("reasoning_trace") or []:
        if step.get("step") == "deterministic_engine" and isinstance(step.get("data"), dict):
            return step["data"]
    return {}


def _origin(sig: dict, brief: dict) -> tuple[str, str]:
    """(text, source label) for a signal, from the reviewed filing or news item it came from."""
    cred = (sig.get("alpha_score") or {}).get("source_credibility")
    tail = f" · {cred:.2f} credibility" if isinstance(cred, (int, float)) else ""
    urls = set(sig.get("source_urls") or [])
    for f in brief.get("filings_reviewed") or []:
        if f.get("document_url") in urls:
            text = f.get("description") or f.get("form_type") or ""
            form = f.get("form_type") or "Filing"
            if "sec.gov" in (f.get("document_url") or ""):
                return text, f"SEC EDGAR · Form {form}{tail}"
            return text, f"{form}{tail}"                     # exchange disclosures: "NGX Disclosure", "SENS"
    for n in brief.get("news_reviewed") or []:
        if n.get("url") in urls:
            title, src = n.get("title") or "", n.get("source") or "News"
            for sep in (" - ", " – ", " | "):        # news titles often end with their publisher
                if title.endswith(f"{sep}{src}"):
                    title = title[: -len(sep + src)]
            return title, f"{src}{tail}"
    ev = (sig.get("evidence") or [sig.get("headline") or ""])[0]
    return ev, f"Source{tail}"


def _strip_publisher(title: Optional[str]) -> Optional[str]:
    """'Headline - Investing.com' -> 'Headline' (news titles carry their publisher)."""
    if not title:
        return title
    head, sep, tail = title.rpartition(" - ")
    return head if sep and head and len(tail) <= 40 and len(tail.split()) <= 4 else title


def summarise(brief: dict, *, brief_id: Optional[str] = None, created_at: Optional[str] = None,
              market: Optional[str] = None) -> dict:
    """What the landing page shows: pipeline counts, top signals and one story dropped as off-target."""
    trace = _engine_trace(brief)
    sigs = sorted(brief.get("detected_signals") or [],
                  key=lambda s: (_SEVERITY_RANK.get(s.get("severity"), 0), (s.get("alpha_score") or {}).get("score") or 0),
                  reverse=True)
    signals = []
    for s in sigs[:2]:
        a = s.get("alpha_score") or {}
        text, source = _origin(s, brief)
        signals.append({
            "signal_type": s.get("signal_type"), "severity": s.get("severity"), "headline": s.get("headline"),
            "evidence": text, "source": source, "alpha": a.get("score"),
            "move_low": a.get("expected_magnitude_pct_low"), "move_high": a.get("expected_magnitude_pct_high"),
            "move_median": a.get("expected_median_pct"), "move_n": a.get("comparable_events_n"),
            "confidence": s.get("confidence"),
        })
    model = brief.get("analyst_model") or ""
    return {
        "id": brief_id, "created_at": created_at or brief.get("brief_date"),
        "company": brief.get("company_name"), "ticker": brief.get("ticker"), "market": market or market_of(brief.get("ticker")),
        "severity": brief.get("overall_severity"), "top_alpha": brief.get("top_alpha_score"),
        "systemic_risk": brief.get("systemic_risk_level"), "liquidity": brief.get("liquidity_tier"),
        "requires_human_review": brief.get("requires_human_review"),
        "llm_used": bool(model) and "unavailable" not in model.lower(),
        "executive_summary": brief.get("executive_summary"),
        "filings": len(brief.get("filings_reviewed") or []), "news": len(brief.get("news_reviewed") or []),
        "total_sources": brief.get("total_sources"),
        "candidates": brief.get("signal_candidates_count", 0),
        "off_target": trace.get("off_target"), "unattributed": trace.get("unattributed"),
        "unattributed_title": _strip_publisher((trace.get("unattributed_titles") or [None])[0]),
        "review_reasons": (brief.get("human_review_reasons") or [])[:3],
        "signal_count": len(brief.get("detected_signals") or []),
        "signals": signals,
    }


def strength(summary: dict) -> tuple:
    """Order for choosing the brief to show: more severe, then higher alpha, then newer."""
    return (_SEVERITY_RANK.get(summary.get("severity") or "", 0) if summary.get("signal_count") else 0,
            summary.get("top_alpha") or 0, summary.get("created_at") or "")


def latest_per_company(summaries: list[dict]) -> list[dict]:
    """Newest run of each company only (summaries arrive newest first), so a superseded run is never shown."""
    seen: set = set()
    out = []
    for s in summaries:
        if s.get("company") not in seen:
            seen.add(s.get("company"))
            out.append(s)
    return out


def pick(summaries: list[dict]) -> Optional[dict]:
    with_signals = [s for s in summaries if s.get("signal_count")]
    return max(with_signals or summaries, key=strength, default=None)
