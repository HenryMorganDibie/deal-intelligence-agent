"""
Deterministic Replay Engine (#3).

Reproduces historical analysis decisions as-of a specific date.
Loads only information available at that timestamp from the warehouse,
applies exact rule/prompt/scoring versions, regenerates brief.

Usage:
    python main.py replay --company "Credit Suisse" --date "2023-02-01"
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

RULESET_VERSION  = "1.0.0"
MODEL_VERSION    = "claude-sonnet-4-20250514"
PROMPT_VERSION   = "1.0.0"
SCORING_VERSION  = "1.0.0"

CONFIG_SNAPSHOT = {
    "ruleset_version":  RULESET_VERSION,
    "model_version":    MODEL_VERSION,
    "prompt_version":   PROMPT_VERSION,
    "scoring_version":  SCORING_VERSION,
    "critical_min_corroboration": 2,
    "alpha_weights": {
        "severity":       0.35,
        "source_cred":    0.25,
        "corroboration":  0.20,
        "recency":        0.10,
        "liquidity":      0.10,
    }
}


class ReplayEngine:
    """
    Loads historical data from the warehouse, filtered to a specific
    as-of date, and re-runs the full deterministic pipeline.
    Stores the replay result alongside the original for comparison.
    """

    def __init__(self, warehouse_session: Any = None):
        self._session = warehouse_session

    def get_config_snapshot(self) -> dict:
        """Return current system configuration for version-locking a run."""
        return {
            **CONFIG_SNAPSHOT,
            "snapshot_at": datetime.utcnow().isoformat(),
        }

    def list_replayable_runs(self, company_name: str) -> list[dict]:
        """List historical runs available for replay."""
        if self._session is None:
            return []
        try:
            from src.engines.warehouse import AnalystBriefRecord
            rows = (
                self._session.query(AnalystBriefRecord)
                .filter(AnalystBriefRecord.company_name.ilike(f"%{company_name}%"))
                .order_by(AnalystBriefRecord.created_at.desc())
                .limit(20)
                .all()
            )
            return [
                {
                    "run_id": r.run_id,
                    "company_name": r.company_name,
                    "brief_date": str(r.brief_date),
                    "severity": r.overall_severity,
                    "signal_count": r.signal_count,
                }
                for r in rows
            ]
        except Exception:
            return []

    def load_run_data(self, run_id: str) -> Optional[dict]:
        """Load all data from a historical run by run_id."""
        if self._session is None:
            return None
        try:
            from src.engines.warehouse import (
                AnalystBriefRecord, FilingRecord,
                NewsRecord, DetectedSignalRecord
            )
            brief_row = (
                self._session.query(AnalystBriefRecord)
                .filter(AnalystBriefRecord.run_id == run_id)
                .first()
            )
            if not brief_row:
                return None

            filings = (
                self._session.query(FilingRecord)
                .filter(FilingRecord.run_id == run_id)
                .all()
            )
            news = (
                self._session.query(NewsRecord)
                .filter(NewsRecord.run_id == run_id)
                .all()
            )
            signals = (
                self._session.query(DetectedSignalRecord)
                .filter(DetectedSignalRecord.run_id == run_id)
                .all()
            )

            return {
                "run_id": run_id,
                "brief": json.loads(brief_row.brief_json),
                "filings_count": len(filings),
                "news_count": len(news),
                "signals_count": len(signals),
                "original_date": str(brief_row.brief_date),
                "company_name": brief_row.company_name,
            }
        except Exception as e:
            return {"error": str(e)}

    async def replay(
        self,
        company_name: str,
        as_of_date: str,
        original_run_id: Optional[str] = None,
    ) -> dict:
        """
        Replay analysis as-of a specific date.

        Loads historical filings and news available before as_of_date,
        re-runs deterministic engine + calibration + alpha scoring,
        and returns a replay brief alongside diff vs original.
        """
        from src.schemas.models import AnalysisRequest, AgentState, SECFiling, NewsItem
        from src.engines.deterministic_engine import DeterministicSignalEngine
        from src.engines.calibration import calibrate_all
        from src.engines.alpha_scorer import score_all_signals

        replay_id = str(uuid.uuid4())

        # Load historical data if warehouse available
        historical_filings: list[SECFiling] = []
        historical_news: list[NewsItem] = []

        if self._session and original_run_id:
            from src.engines.warehouse import FilingRecord, NewsRecord
            filing_rows = (
                self._session.query(FilingRecord)
                .filter(
                    FilingRecord.run_id == original_run_id,
                    FilingRecord.filing_date <= as_of_date,
                )
                .all()
            )
            news_rows = (
                self._session.query(NewsRecord)
                .filter(
                    NewsRecord.run_id == original_run_id,
                    NewsRecord.published_date <= as_of_date,
                )
                .all()
            )
            for r in filing_rows:
                try:
                    historical_filings.append(SECFiling(
                        accession_number=r.accession_number or "",
                        form_type=r.form_type or "",
                        filing_date=r.filing_date or "",
                        company_name=r.company_name or "",
                        cik=r.cik or "",
                        document_url=r.document_url or "",
                        description=r.description,
                        raw_excerpt=r.raw_excerpt,
                    ))
                except Exception:
                    pass
            for r in news_rows:
                try:
                    historical_news.append(NewsItem(
                        title=r.title or "", source=r.source or "",
                        published_date=r.published_date or "",
                        url=r.url or "", snippet=r.snippet or "",
                        relevance_score=r.relevance_score or 0.0,
                    ))
                except Exception:
                    pass

        # Build state with historical data
        request = AnalysisRequest(company_name=company_name)
        state = AgentState(request=request)
        state.filings    = historical_filings
        state.news_items = historical_news

        # Re-run deterministic engine
        state = DeterministicSignalEngine().run(state)

        # Re-run calibration
        calibrated = calibrate_all(state.signal_candidates)

        # Re-run alpha scoring (no LLM — pure deterministic replay)
        from src.engines.alpha_scorer import compute_alpha_score
        from src.schemas.models import DetectedSignal
        replay_signals = []
        for cand, sev, conf, _ in calibrated:
            sig = DetectedSignal(
                signal_type=cand.signal_type, severity=sev,
                headline=f"[REPLAY] {cand.signal_type.value.replace('_',' ').title()}",
                evidence=[cand.source_text[:200]],
                source_urls=[cand.source_url] if cand.source_url else [],
                confidence=conf, reasoning="[Deterministic replay — no LLM]",
                candidate_patterns=cand.matched_patterns,
                corroboration_count=cand.corroboration_count,
            )
            alpha = compute_alpha_score(sig, cand)
            replay_signals.append(sig.model_copy(update={"alpha_score": alpha}))

        result = {
            "replay_id": replay_id,
            "company_name": company_name,
            "as_of_date": as_of_date,
            "original_run_id": original_run_id,
            "config_snapshot": self.get_config_snapshot(),
            "filings_used": len(historical_filings),
            "news_used": len(historical_news),
            "candidates_produced": len(state.signal_candidates),
            "signals_produced": len(replay_signals),
            "signal_summary": [
                {
                    "type": s.signal_type.value,
                    "severity": s.severity.value,
                    "confidence": s.confidence,
                    "alpha": s.alpha_score.score if s.alpha_score else None,
                }
                for s in replay_signals
            ],
            "replayed_at": datetime.utcnow().isoformat(),
        }

        # Store replay record if warehouse available
        if self._session:
            try:
                from src.engines.warehouse import ReplayRunRecord
                self._session.add(ReplayRunRecord(
                    id=replay_id,
                    original_run_id=original_run_id or "",
                    company_name=company_name,
                    replay_date=as_of_date,
                    ruleset_version=RULESET_VERSION,
                    model_version=MODEL_VERSION,
                    prompt_version=PROMPT_VERSION,
                    scoring_version=SCORING_VERSION,
                    config_snapshot=json.dumps(self.get_config_snapshot()),
                    brief_json=json.dumps(result),
                ))
                self._session.commit()
            except Exception:
                self._session.rollback()

        return result


def compare_runs(original: dict, replay: dict) -> dict:
    """
    Diff two analysis runs. Returns signal-level differences.
    Useful for understanding how rule/scoring changes affect output.
    """
    orig_sigs = {s["type"]: s for s in original.get("signal_summary", [])}
    rep_sigs  = {s["type"]: s for s in replay.get("signal_summary",   [])}

    all_types = set(orig_sigs) | set(rep_sigs)
    diffs = []
    for sig_type in sorted(all_types):
        o = orig_sigs.get(sig_type)
        r = rep_sigs.get(sig_type)
        if o and not r:
            diffs.append({"type": sig_type, "change": "removed", "original": o})
        elif r and not o:
            diffs.append({"type": sig_type, "change": "added", "replay": r})
        elif o and r:
            severity_changed = o["severity"] != r["severity"]
            alpha_delta = (r.get("alpha") or 0) - (o.get("alpha") or 0)
            if severity_changed or abs(alpha_delta) > 5:
                diffs.append({
                    "type": sig_type, "change": "modified",
                    "severity_change": f"{o['severity']} → {r['severity']}" if severity_changed else "unchanged",
                    "alpha_delta": round(alpha_delta, 1),
                })

    return {
        "original_run_id": original.get("run_id"),
        "replay_id": replay.get("replay_id"),
        "signals_in_original": len(orig_sigs),
        "signals_in_replay": len(rep_sigs),
        "diffs": diffs,
        "diff_count": len(diffs),
    }
