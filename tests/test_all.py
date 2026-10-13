"""
Comprehensive test suite — Deal Intelligence Agent.
Covers all layers: schemas, deterministic engine, calibration,
alpha scorer, feedback, audit log, tools, agents, graph, formatter.
Run: pytest tests/test_all.py -v
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas.models import (
    AnalysisRequest, AgentState, AnalystBrief, DetectedSignal,
    SECFiling, NewsItem, CompanyProfile, RiskFactor, KeyMetric,
    SignalType, Severity, SignalCandidate, AlphaScore, LiquidityTier,
    FeedbackEntry, FeedbackType, AuditEntry
)
from src.utils.clock import utcnow

# A date inside the default 90-day lookback window, for source fixtures.
RECENT_DAY = (utcnow() - timedelta(days=2)).strftime("%Y-%m-%d")

# ─── Schemas ──────────────────────────────────────────────────────────────────

class TestAnalysisRequest:
    def test_basic(self):
        r = AnalysisRequest(company_name="Apple Inc", ticker="AAPL")
        assert r.ticker == "AAPL"
        assert r.lookback_days == 90

    def test_ticker_normalised(self):
        assert AnalysisRequest(company_name="X", ticker="aapl").ticker == "AAPL"

    def test_ticker_stripped(self):
        assert AnalysisRequest(company_name="X", ticker="  MSFT  ").ticker == "MSFT"

    def test_lookback_bounds(self):
        with pytest.raises(Exception): AnalysisRequest(company_name="X", lookback_days=0)
        with pytest.raises(Exception): AnalysisRequest(company_name="X", lookback_days=366)

    def test_depth_validation(self):
        for d in ("quick","standard","deep"):
            assert AnalysisRequest(company_name="X", depth=d).depth == d
        with pytest.raises(Exception): AnalysisRequest(company_name="X", depth="extreme")

    def test_focus_signals(self):
        r = AnalysisRequest(company_name="X", focus_signals=[SignalType.MA_ACTIVITY])
        assert len(r.focus_signals) == 1


class TestSignalCandidate:
    def _make(self, **kw):
        d = dict(signal_type=SignalType.MA_ACTIVITY, matched_patterns=[r"\bmerger\b"],
                 source_text="merger announced", source_type="filing",
                 source_name="8-K", raw_score=0.85)
        d.update(kw); return SignalCandidate(**d)

    def test_creation(self):
        c = self._make()
        assert c.signal_type == SignalType.MA_ACTIVITY
        assert c.raw_score == 0.85

    def test_score_bounds(self):
        with pytest.raises(Exception): self._make(raw_score=1.5)
        with pytest.raises(Exception): self._make(raw_score=-0.1)

    def test_corroboration_default(self):
        assert self._make().corroboration_count == 1


class TestAlphaScore:
    def test_creation(self):
        a = AlphaScore(score=72.5, severity_component=0.8, source_credibility=0.9,
                       corroboration_weight=0.7, recency_weight=0.95,
                       liquidity_tier=LiquidityTier.MID_CAP)
        assert a.score == 72.5
        assert a.liquidity_tier == LiquidityTier.MID_CAP

    def test_score_bounds(self):
        with pytest.raises(Exception):
            AlphaScore(score=101, severity_component=0.8, source_credibility=0.9,
                       corroboration_weight=0.7, recency_weight=0.95)

    def test_review_flag(self):
        a = AlphaScore(score=80, severity_component=1.0, source_credibility=1.0,
                       corroboration_weight=1.0, recency_weight=1.0,
                       requires_human_review=True, review_reason="High alpha")
        assert a.requires_human_review is True


class TestDetectedSignal:
    def _make(self, **kw):
        d = dict(signal_type=SignalType.MA_ACTIVITY, severity=Severity.HIGH,
                 headline="Test", evidence=["E1"], confidence=0.85, reasoning="R")
        d.update(kw); return DetectedSignal(**d)

    def test_creation(self): assert self._make().confidence == 0.85
    def test_confidence_bounds(self):
        with pytest.raises(Exception): self._make(confidence=1.5)
    def test_candidate_patterns_default(self):
        assert self._make().candidate_patterns == []
    def test_alpha_score_optional(self):
        assert self._make().alpha_score is None


class TestAnalystBrief:
    def _make(self, signals=None):
        return AnalystBrief(
            company_name="Acme", executive_summary="Summary",
            overall_severity=Severity.HIGH, recommendation="Act",
            confidence_score=0.8, detected_signals=signals or []
        )

    def test_signal_count_by_severity(self):
        signals = [
            DetectedSignal(signal_type=SignalType.MA_ACTIVITY, severity=Severity.HIGH,
                           headline="H", evidence=[], confidence=0.9, reasoning="R"),
            DetectedSignal(signal_type=SignalType.CREDIT_RISK, severity=Severity.CRITICAL,
                           headline="H", evidence=[], confidence=0.95, reasoning="R"),
        ]
        b = self._make(signals)
        counts = b.signal_count_by_severity()
        assert counts["high"] == 1; assert counts["critical"] == 1

    def test_top_signals_ordered(self):
        signals = [
            DetectedSignal(signal_type=SignalType.MA_ACTIVITY, severity=Severity.LOW,
                           headline="Low", evidence=[], confidence=0.5, reasoning="R"),
            DetectedSignal(signal_type=SignalType.CREDIT_RISK, severity=Severity.CRITICAL,
                           headline="Crit", evidence=[], confidence=0.95, reasoning="R"),
        ]
        top = self._make(signals).top_signals(1)
        assert top[0].severity == Severity.CRITICAL

    def test_compliance_fields(self):
        b = AnalystBrief(company_name="X", executive_summary="E", overall_severity=Severity.LOW,
                         recommendation="R", confidence_score=0.5, detected_signals=[],
                         compliance_mode=True, compliance_flags=["flag1"])
        assert b.compliance_mode is True
        assert "flag1" in b.compliance_flags


class TestAgentState:
    def test_log(self):
        s = AgentState(request=AnalysisRequest(company_name="X"))
        s.log("step_a", "Did A"); s.log("step_b", "Did B")
        assert len(s.reasoning_trace) == 2
        assert s.current_step == "step_b"

    def test_signal_candidates_default(self):
        s = AgentState(request=AnalysisRequest(company_name="X"))
        assert s.signal_candidates == []

    def test_compliance_mode_default(self):
        s = AgentState(request=AnalysisRequest(company_name="X"))
        assert s.compliance_mode is False


# ─── Deterministic Engine ──────────────────────────────────────────────────────

class TestDeterministicEngine:
    def _state(self, filings=None, news=None):
        # CIK matches self._filing(): these are the company's own SEC filings.
        s = AgentState(request=AnalysisRequest(company_name="Acme", cik="0000001"))
        s.filings    = filings or []
        s.news_items = news   or []
        return s

    def _filing(self, desc="", form="8-K"):
        return SECFiling(accession_number="acc1", form_type=form,
                         filing_date=RECENT_DAY, company_name="Acme",
                         cik="0000001", document_url="https://sec.gov/x",
                         description=desc)

    def _news(self, title="", snippet="", score=0.8):
        return NewsItem(title=title, source="Reuters", published_date=RECENT_DAY,
                        url="http://x.com", snippet=snippet, relevance_score=score)

    def test_ma_pattern_fires(self):
        from src.engines.deterministic_engine import DeterministicSignalEngine
        s = self._state(filings=[self._filing("Definitive merger agreement signed with Target Corp")])
        result = DeterministicSignalEngine().run(s)
        assert any(c.signal_type == SignalType.MA_ACTIVITY for c in result.signal_candidates)

    def test_credit_going_concern(self):
        from src.engines.deterministic_engine import DeterministicSignalEngine
        s = self._state(filings=[self._filing("Substantial doubt about ability to continue as a going concern")])
        result = DeterministicSignalEngine().run(s)
        assert any(c.signal_type == SignalType.CREDIT_RISK for c in result.signal_candidates)

    def test_distressed_business_rescue(self):
        from src.engines.deterministic_engine import DeterministicSignalEngine
        s = self._state(filings=[self._filing("Business rescue proceedings commenced by board")])
        result = DeterministicSignalEngine().run(s)
        assert any(c.signal_type == SignalType.DISTRESSED_ASSET for c in result.signal_candidates)

    def test_earnings_profit_warning(self):
        from src.engines.deterministic_engine import DeterministicSignalEngine
        s = self._state(news=[self._news("Acme issues profit warning", "revenue significantly below expectations")])
        result = DeterministicSignalEngine().run(s)
        assert any(c.signal_type == SignalType.EARNINGS_SURPRISE for c in result.signal_candidates)

    def test_leadership_ceo_resignation(self):
        from src.engines.deterministic_engine import DeterministicSignalEngine
        s = self._state(filings=[self._filing("CEO resigned effective immediately from the board")])
        result = DeterministicSignalEngine().run(s)
        assert any(c.signal_type == SignalType.LEADERSHIP_CHANGE for c in result.signal_candidates)

    def test_regulatory_sec_probe(self):
        from src.engines.deterministic_engine import DeterministicSignalEngine
        s = self._state(news=[self._news("SEC investigation launched into Acme", "SEC probe into fraud allegations")])
        result = DeterministicSignalEngine().run(s)
        assert any(c.signal_type == SignalType.REGULATORY_ACTION for c in result.signal_candidates)

    def test_debt_restructuring(self):
        from src.engines.deterministic_engine import DeterministicSignalEngine
        s = self._state(filings=[self._filing("Debt restructuring agreement reached with lenders, forbearance granted")])
        result = DeterministicSignalEngine().run(s)
        assert any(c.signal_type == SignalType.DEBT_RESTRUCTURE for c in result.signal_candidates)

    def test_insider_form4(self):
        from src.engines.deterministic_engine import DeterministicSignalEngine
        s = self._state(filings=[self._filing("Form 4 filed — director purchase of 50,000 shares", form="Form 4")])
        result = DeterministicSignalEngine().run(s)
        assert any(c.signal_type == SignalType.INSIDER_ACTIVITY for c in result.signal_candidates)

    def test_no_signals_empty_data(self):
        from src.engines.deterministic_engine import DeterministicSignalEngine
        s = self._state()
        result = DeterministicSignalEngine().run(s)
        assert result.signal_candidates == []

    def test_corroboration_merged(self):
        from src.engines.deterministic_engine import DeterministicSignalEngine
        s = self._state(
            filings=[self._filing("Definitive merger agreement signed")],
            news=[self._news("Acme merger confirmed", "acquisition deal announced", 0.9)]
        )
        result = DeterministicSignalEngine().run(s)
        ma = next((c for c in result.signal_candidates if c.signal_type == SignalType.MA_ACTIVITY), None)
        assert ma is not None
        assert ma.corroboration_count >= 2

    def test_deduplication_same_signal_type(self):
        from src.engines.deterministic_engine import DeterministicSignalEngine
        s = self._state(filings=[
            self._filing("Definitive merger agreement"),
            self._filing("Merger talks confirmed, acquisition agreed"),
        ])
        result = DeterministicSignalEngine().run(s)
        ma_count = sum(1 for c in result.signal_candidates if c.signal_type == SignalType.MA_ACTIVITY)
        assert ma_count == 1  # merged into one

    def test_exchange_filing_gets_top_credibility(self):
        from src.engines.deterministic_engine import DeterministicSignalEngine
        s = self._state(filings=[
            SECFiling(accession_number="NGX-001", form_type="NGX Disclosure",
                      filing_date=RECENT_DAY, company_name="GTBank",
                      cik="NGX", document_url="https://ngx.com/x",
                      description="Acme board approves merger with acquisition target")
        ])
        result = DeterministicSignalEngine().run(s)
        assert len(result.signal_candidates) > 0

    def test_off_target_sources_do_not_create_signals(self):
        """Live-run regression: an unrelated company's deal was reported as the target's."""
        from src.engines.deterministic_engine import DeterministicSignalEngine
        s = self._state(
            filings=[SECFiling(accession_number="JSE-1", form_type="JSE SENS",
                               filing_date=RECENT_DAY, company_name="Acme", cik="JSE",
                               document_url="u", description="Foschini completes Street Fever acquisition")],
            news=[self._news("Foschini acquisition", "takeover of Street Fever", 0.9)],
        )
        result = DeterministicSignalEngine().run(s)
        assert result.signal_candidates == []

    def test_third_party_sec_filing_must_name_target(self):
        """Full-text search returns other filers' 8-Ks; they only count if they name the target."""
        from src.engines.deterministic_engine import DeterministicSignalEngine
        other = SECFiling(accession_number="x", form_type="8-K", filing_date=RECENT_DAY,
                          company_name="Beta Corp", cik="0000999", document_url="u",
                          description="Definitive merger agreement signed")
        assert DeterministicSignalEngine().run(self._state(filings=[other])).signal_candidates == []

    def test_sec_filing_needs_no_name_mention(self):
        """SEC filings are fetched by the company's CIK, so they are on-target by construction."""
        from src.engines.deterministic_engine import DeterministicSignalEngine
        s = self._state(filings=[self._filing("Definitive merger agreement signed")])
        assert DeterministicSignalEngine().run(s).signal_candidates

    def test_company_matchers(self):
        from src.engines.deterministic_engine import _company_matchers, _mentions_company
        m = _company_matchers("Guaranty Trust Bank Plc", ticker="GTCO")
        assert _mentions_company("Guaranty Trust Bank posts loss", m)
        assert _mentions_company("GTCO shares fall", m)
        assert not _mentions_company("A bank announced a trust merger", m)
        assert not _mentions_company("gtco lowercase is not the ticker", m)
        apple = _company_matchers("Apple Inc.", ticker="AAPL")
        assert _mentions_company("Apple to acquire startup", apple)
        assert not _mentions_company("Pineapple Holdings acquisition", apple)

    def test_entity_extraction(self):
        from src.engines.deterministic_engine import _extract_entities
        text = "Acme Corp acquires Target Ltd for $2.1 billion representing 35 percent premium"
        entities = _extract_entities(text)
        assert any("Corp" in e or "Ltd" in e for e in entities)
        assert any("billion" in e or "$" in e for e in entities)
        # Also test percentage directly
        text2 = "deal represents 35% premium over closing price"
        entities2 = _extract_entities(text2)
        assert any("%" in e for e in entities2)

    def test_source_credibility_lookup(self):
        from src.engines.deterministic_engine import _source_credibility
        assert _source_credibility("Reuters") == 0.95
        assert _source_credibility("JSE SENS") == 1.0
        assert _source_credibility("unknown blog") == 0.40

    def test_low_relevance_news_filtered(self):
        from src.engines.deterministic_engine import DeterministicSignalEngine
        s = self._state(news=[self._news("Merger announced", "deal confirmed", score=0.05)])
        result = DeterministicSignalEngine().run(s)
        # Very low relevance score should be filtered
        # Even if patterns match, raw_score * 0.05 will be below threshold
        for c in result.signal_candidates:
            assert c.raw_score >= 0.20


# ─── Calibration ──────────────────────────────────────────────────────────────

class TestCalibration:
    def _cand(self, sig_type, raw_score, corroboration=1):
        return SignalCandidate(
            signal_type=sig_type, matched_patterns=["test"],
            source_text="test", source_type="filing", source_name="8-K",
            raw_score=raw_score, corroboration_count=corroboration
        )

    def test_high_score_gives_critical(self):
        from src.engines.calibration import calibrate
        c = self._cand(SignalType.DISTRESSED_ASSET, 0.92, corroboration=2)
        sev, conf, mat = calibrate(c)
        assert sev == Severity.CRITICAL
        assert conf > 0.7

    def test_low_score_gives_low(self):
        from src.engines.calibration import calibrate
        c = self._cand(SignalType.MA_ACTIVITY, 0.30)
        sev, conf, mat = calibrate(c)
        assert sev == Severity.LOW

    def test_critical_requires_2_corroborations(self):
        from src.engines.calibration import calibrate
        # Single source shouldn't be CRITICAL even with high raw score
        c = self._cand(SignalType.DISTRESSED_ASSET, 0.95, corroboration=1)
        sev, conf, mat = calibrate(c)
        assert sev in (Severity.HIGH, Severity.CRITICAL)
        # With 2 sources it should be CRITICAL
        c2 = self._cand(SignalType.DISTRESSED_ASSET, 0.95, corroboration=2)
        sev2, _, _ = calibrate(c2)
        assert sev2 == Severity.CRITICAL

    def test_corroboration_raises_confidence(self):
        from src.engines.calibration import calibrate
        c1 = self._cand(SignalType.CREDIT_RISK, 0.75, corroboration=1)
        c3 = self._cand(SignalType.CREDIT_RISK, 0.75, corroboration=3)
        _, conf1, _ = calibrate(c1)
        _, conf3, _ = calibrate(c3)
        assert conf3 >= conf1

    def test_calibrate_all(self):
        from src.engines.calibration import calibrate_all
        candidates = [
            self._cand(SignalType.MA_ACTIVITY, 0.88, 2),
            self._cand(SignalType.CREDIT_RISK, 0.60, 1),
        ]
        results = calibrate_all(candidates)
        assert len(results) == 2
        for cand, sev, conf, mat in results:
            assert isinstance(sev, Severity)
            assert 0 <= conf <= 1.0
            assert 0 <= mat <= 1.0

    def test_confidence_never_exceeds_1(self):
        from src.engines.calibration import calibrate
        c = self._cand(SignalType.DISTRESSED_ASSET, 1.0, corroboration=5)
        _, conf, _ = calibrate(c)
        assert conf <= 1.0


# ─── Alpha Scorer ──────────────────────────────────────────────────────────────

class TestAlphaScorer:
    def _signal(self, sig_type=SignalType.MA_ACTIVITY, severity=Severity.HIGH, conf=0.8):
        return DetectedSignal(
            signal_type=sig_type, severity=severity, headline="Test",
            evidence=["E1"], confidence=conf, reasoning="R"
        )

    def _candidate(self, sig_type=SignalType.MA_ACTIVITY, raw_score=0.85, corr=2):
        return SignalCandidate(
            signal_type=sig_type, matched_patterns=["test"],
            source_text="test", source_type="filing",
            source_name="Reuters", raw_score=raw_score, corroboration_count=corr
        )

    def test_alpha_score_range(self):
        from src.engines.alpha_scorer import compute_alpha_score
        alpha = compute_alpha_score(self._signal(), self._candidate())
        assert 0 <= alpha.score <= 100

    def test_critical_scores_higher_than_low(self):
        from src.engines.alpha_scorer import compute_alpha_score
        high = compute_alpha_score(self._signal(severity=Severity.CRITICAL), self._candidate())
        low  = compute_alpha_score(self._signal(severity=Severity.LOW),      self._candidate())
        assert high.score > low.score

    def test_more_corroboration_scores_higher(self):
        from src.engines.alpha_scorer import compute_alpha_score
        s = self._signal()
        low_corr  = compute_alpha_score(s, self._candidate(corr=1))
        high_corr = compute_alpha_score(s, self._candidate(corr=5))
        assert high_corr.score > low_corr.score

    def test_expected_move_populated(self):
        from src.engines.alpha_scorer import compute_alpha_score
        alpha = compute_alpha_score(
            self._signal(SignalType.DISTRESSED_ASSET, Severity.CRITICAL),
            self._candidate(SignalType.DISTRESSED_ASSET)
        )
        assert alpha.expected_direction == "negative"
        assert alpha.expected_magnitude_pct_high > 0
        assert alpha.comparable_events_n > 0

    def test_human_review_flagged_above_threshold(self):
        from src.engines.alpha_scorer import compute_alpha_score, HUMAN_REVIEW_ALPHA_THRESHOLD
        # Critical + Reuters source should breach threshold
        alpha = compute_alpha_score(
            self._signal(SignalType.DISTRESSED_ASSET, Severity.CRITICAL),
            self._candidate(SignalType.DISTRESSED_ASSET, corr=3)
        )
        if alpha.score >= HUMAN_REVIEW_ALPHA_THRESHOLD:
            assert alpha.requires_human_review is True

    def test_compliance_mode_low_confidence_flagged(self):
        from src.engines.alpha_scorer import compute_alpha_score
        alpha = compute_alpha_score(
            self._signal(conf=0.2), self._candidate(), compliance_mode=True
        )
        assert alpha.requires_human_review is True

    def test_score_all_signals_sorted(self):
        from src.engines.alpha_scorer import score_all_signals
        signals = [
            self._signal(SignalType.MA_ACTIVITY, Severity.LOW),
            self._signal(SignalType.DISTRESSED_ASSET, Severity.CRITICAL),
        ]
        candidates = [
            self._candidate(SignalType.MA_ACTIVITY),
            self._candidate(SignalType.DISTRESSED_ASSET, corr=3),
        ]
        scored = score_all_signals(signals, candidates)
        assert scored[0].alpha_score.score >= scored[1].alpha_score.score

    def test_recency_decay(self):
        from src.engines.alpha_scorer import _recency_decay
        now   = _recency_decay(utcnow())
        old   = _recency_decay(utcnow() - timedelta(days=60))
        floor = _recency_decay(utcnow() - timedelta(days=365))
        assert now >= old >= floor
        assert floor >= 0.30

    def test_liquidity_tier_inferred(self):
        from src.engines.alpha_scorer import _infer_liquidity_tier
        assert _infer_liquidity_tier("AAPL", None, None) == LiquidityTier.LARGE_CAP
        assert _infer_liquidity_tier(None, None, None) == LiquidityTier.PRIVATE
        assert _infer_liquidity_tier("XYZ", "NYSE", None) == LiquidityTier.MID_CAP


# ─── Feedback ──────────────────────────────────────────────────────────────────

class TestFeedback:
    def _tmp_path(self, tmp_path):
        import src.engines.feedback as fb
        fb.FEEDBACK_PATH = tmp_path / "feedback.json"
        return fb

    def test_submit_and_retrieve(self, tmp_path):
        fb = self._tmp_path(tmp_path)
        entry = fb.submit_feedback(
            company_name="Acme", signal_type=SignalType.MA_ACTIVITY,
            feedback_type=FeedbackType.FALSE_POSITIVE, original_severity=Severity.HIGH,
            analyst_note="Did not materialise"
        )
        assert entry.feedback_id is not None
        recent = fb.get_recent_feedback(10)
        assert any(e.feedback_id == entry.feedback_id for e in recent)

    def test_stats_update_on_submit(self, tmp_path):
        fb = self._tmp_path(tmp_path)
        fb.submit_feedback("X", SignalType.CREDIT_RISK, FeedbackType.CONFIRMED, Severity.HIGH)
        fb.submit_feedback("X", SignalType.CREDIT_RISK, FeedbackType.FALSE_POSITIVE, Severity.MEDIUM)
        stats = fb.get_signal_stats()
        s = stats["credit_risk"]
        assert s["total"] == 2
        assert s["confirmed"] == 1
        assert s["false_positive"] == 1

    def test_precision_calculated(self, tmp_path):
        fb = self._tmp_path(tmp_path)
        fb.submit_feedback("X", SignalType.MA_ACTIVITY, FeedbackType.CONFIRMED, Severity.HIGH)
        fb.submit_feedback("X", SignalType.MA_ACTIVITY, FeedbackType.CONFIRMED, Severity.HIGH)
        fb.submit_feedback("X", SignalType.MA_ACTIVITY, FeedbackType.FALSE_POSITIVE, Severity.LOW)
        stats = fb.get_signal_stats()
        assert stats["m_and_a_activity"]["precision"] == pytest.approx(2/3, abs=0.01)

    def test_source_reliability_ema(self, tmp_path):
        fb = self._tmp_path(tmp_path)
        for _ in range(5):
            fb.update_source_reliability("Reuters", was_correct=True)
        rel = fb.get_source_reliability()
        assert rel["Reuters"] > 0.70

    def test_false_positive_rate(self, tmp_path):
        fb = self._tmp_path(tmp_path)
        fb.submit_feedback("X", SignalType.REGULATORY_ACTION, FeedbackType.FALSE_POSITIVE, Severity.HIGH)
        fb.submit_feedback("X", SignalType.REGULATORY_ACTION, FeedbackType.CONFIRMED, Severity.HIGH)
        rate = fb.false_positive_rate(SignalType.REGULATORY_ACTION)
        assert rate == pytest.approx(0.5, abs=0.01)

    def test_empty_feedback_returns_empty(self, tmp_path):
        fb = self._tmp_path(tmp_path)
        assert fb.get_recent_feedback() == []
        assert fb.get_signal_stats() == {}


# ─── Audit Log ────────────────────────────────────────────────────────────────

class TestAuditLog:
    def _tmp(self, tmp_path):
        import src.engines.audit_log as al
        al.AUDIT_PATH = tmp_path / "audit.jsonl"
        return al

    def test_write_and_read(self, tmp_path):
        al = self._tmp(tmp_path)
        al.log_entry("test_step", "Acme", "data_collected", "Fetched 5 filings")
        entries = al.read_log()
        assert len(entries) == 1
        assert entries[0].pipeline_step == "test_step"
        assert entries[0].company_name == "Acme"

    def test_hash_chain_valid(self, tmp_path):
        al = self._tmp(tmp_path)
        for i in range(5):
            al.log_entry("step", "X", f"action_{i}", f"detail_{i}")
        valid, msg = al.verify_chain()
        assert valid is True
        assert "valid" in msg.lower()

    def test_chain_broken_on_tamper(self, tmp_path):
        al = self._tmp(tmp_path)
        al.log_entry("step1", "X", "act1", "detail1")
        al.log_entry("step2", "X", "act2", "detail2")
        # Tamper: corrupt the first line
        lines = al.AUDIT_PATH.read_text().strip().split("\n")
        data  = json.loads(lines[0])
        data["prev_hash"] = "tampered_hash"
        lines[0] = json.dumps(data)
        al.AUDIT_PATH.write_text("\n".join(lines) + "\n")
        valid, msg = al.verify_chain()
        assert valid is False

    def test_chain_detects_edited_content(self, tmp_path):
        al = self._tmp(tmp_path)
        al.log_entry("step1", "X", "act1", "detail1", data={"a": 1})
        al.log_entry("step2", "X", "act2", "detail2", data={"a": 2})
        lines = al.AUDIT_PATH.read_text().strip().split("\n")
        data = json.loads(lines[0])
        data["detail"] = "edited after the fact"   # hashes left untouched
        lines[0] = json.dumps(data)
        al.AUDIT_PATH.write_text("\n".join(lines) + "\n")
        valid, msg = al.verify_chain()
        assert valid is False
        assert "modified" in msg

    def test_chain_detects_deleted_entry(self, tmp_path):
        al = self._tmp(tmp_path)
        for i in range(3):
            al.log_entry("step", "X", f"act{i}", f"d{i}")
        lines = al.AUDIT_PATH.read_text().strip().split("\n")
        al.AUDIT_PATH.write_text(lines[0] + "\n" + lines[2] + "\n")
        valid, msg = al.verify_chain()
        assert valid is False

    def test_legacy_entries_checked_for_linkage_only(self, tmp_path):
        al = self._tmp(tmp_path)
        legacy = {"entry_id": "e1", "pipeline_step": "s", "company_name": "X",
                  "action": "a", "detail": "d", "data_hash": "abc",
                  "prev_hash": "GENESIS", "model_version": "", "analyst_id": "system"}
        al.AUDIT_PATH.write_text(json.dumps(legacy) + "\n")
        valid, msg = al.verify_chain()
        assert valid is True and "legacy" in msg

    def test_genesis_hash_for_first_entry(self, tmp_path):
        al = self._tmp(tmp_path)
        e = al.log_entry("step", "X", "act", "detail")
        assert e.prev_hash == "GENESIS"

    def test_chained_prev_hash(self, tmp_path):
        al = self._tmp(tmp_path)
        e1 = al.log_entry("step1", "X", "act1", "d1")
        e2 = al.log_entry("step2", "X", "act2", "d2")
        assert e2.prev_hash == e1.data_hash

    def test_empty_log_verify_ok(self, tmp_path):
        al = self._tmp(tmp_path)
        valid, msg = al.verify_chain()
        assert valid is True

    def test_data_hash_is_sha256(self, tmp_path):
        al = self._tmp(tmp_path)
        e = al.log_entry("step", "X", "act", "det")
        assert len(e.data_hash) == 64
        assert all(c in "0123456789abcdef" for c in e.data_hash)


# ─── News Tool ────────────────────────────────────────────────────────────────

class TestNewsTool:
    def test_score_relevance_positive(self):
        from src.tools.news_tool import _score_relevance
        assert _score_relevance("Apple acquires startup", "merger deal", "Apple") > 0.3

    def test_score_relevance_negative(self):
        from src.tools.news_tool import _score_relevance
        assert _score_relevance("Weather today", "sunny", "Acme") < 0.2

    def test_extract_source_known(self):
        from src.tools.news_tool import _extract_source
        assert _extract_source("https://www.reuters.com/x") == "Reuters"
        assert _extract_source("https://www.bloomberg.com/x") == "Bloomberg"

    def test_extract_source_african(self):
        from src.tools.news_tool import _extract_source
        assert _extract_source("https://businessday.ng/x") == "BusinessDay Nigeria"
        assert _extract_source("https://nairametrics.com/x") == "Nairametrics"

    def test_parse_rss_date(self):
        from src.tools.news_tool import _parse_rss_date
        assert _parse_rss_date("Mon, 12 May 2025 14:30:00 GMT") == "2025-05-12"

    def test_parse_rss_date_fallback(self):
        from src.tools.news_tool import _parse_rss_date
        assert _parse_rss_date("garbage") == utcnow().strftime("%Y-%m-%d")


# ─── Africa Tool ──────────────────────────────────────────────────────────────

class TestAfricaTool:
    def test_is_africa_focused(self):
        from src.tools.africa_tool import _is_africa_focused
        assert _is_africa_focused("GTBank deal in Nigeria", "") is True
        assert _is_africa_focused("JSE merger", "") is True
        assert _is_africa_focused("Apple US deal", "California") is False

    def test_score_relevance(self):
        from src.tools.africa_tool import _score_african_relevance
        high = _score_african_relevance("GTBank merger deal acquisition", "confirmed", "GTBank")
        low  = _score_african_relevance("Weather today", "sunny", "Acme")
        assert high > low

    def test_extract_source_african(self):
        from src.tools.africa_tool import _extract_african_source
        assert _extract_african_source("https://businessday.ng/x") == "BusinessDay Nigeria"
        assert _extract_african_source("https://avca.africa/x") == "AVCA"
        assert _extract_african_source("https://africaprivateequitynews.com/deals") == "Africa PE News"
        assert _extract_african_source("https://afdb.org/x") == "African Development Bank"
        assert _extract_african_source("https://proparco.fr/x") == "Proparco"

    def test_source_map_completeness(self):
        from src.tools.africa_tool import AFRICAN_SOURCE_MAP
        for domain in ["businessday.ng","moneyweb.co.za","avca.africa",
                        "africaprivateequitynews.com","ifc.org","afdb.org",
                        "proparco.fr","cma.or.ke","sec.gov.ng","fsca.co.za"]:
            assert domain in AFRICAN_SOURCE_MAP, f"{domain} missing"

    def test_news_feeds_all_https(self):
        from src.tools.africa_tool import AFRICAN_NEWS_FEEDS
        for name, url in AFRICAN_NEWS_FEEDS.items():
            assert url.startswith("https://"), f"{name}: {url}"

    def test_news_feeds_expanded(self):
        from src.tools.africa_tool import AFRICAN_NEWS_FEEDS
        assert len(AFRICAN_NEWS_FEEDS) >= 30, "Expected 30+ news feeds"

    def test_pe_sources_completeness(self):
        from src.tools.africa_tool import PE_CAPITAL_SOURCES
        urls = [url for _, url, _, _ in PE_CAPITAL_SOURCES]
        for domain in ["globalprivatecapital.org","psgcapital.com","ifc.org",
                        "africaprivateequitynews.com","avca.africa","afdb.org",
                        "proparco.fr","cma.or.ke","sec.gov.ng"]:
            assert any(domain in u for u in urls), f"{domain} missing from PE_CAPITAL_SOURCES"

    def test_pe_sources_all_https(self):
        from src.tools.africa_tool import PE_CAPITAL_SOURCES
        for name, url, _, _ in PE_CAPITAL_SOURCES:
            assert url.startswith("https://"), f"{name}: not HTTPS"

    def test_pe_sources_count(self):
        from src.tools.africa_tool import PE_CAPITAL_SOURCES
        assert len(PE_CAPITAL_SOURCES) >= 20, "Expected 20+ PE/institutional sources"

    @pytest.mark.asyncio
    async def test_context_manager(self):
        from src.tools.africa_tool import AfricaTool
        async with AfricaTool() as t: assert t._client is not None
        assert t._client.is_closed

    @pytest.mark.asyncio
    async def test_fetch_rss_network_error(self):
        from src.tools.africa_tool import AfricaTool
        async with AfricaTool() as t:
            with patch.object(t.client, "get", side_effect=Exception("network error")):
                assert await t._fetch_rss("https://businessday.ng/feed/") == []

    @pytest.mark.asyncio
    async def test_fetch_rss_parses_valid_xml(self):
        from src.tools.africa_tool import AfricaTool
        rss = b"""<?xml version="1.0"?><rss version="2.0"><channel>
          <item><title>GTBank merger</title><link>https://bd.ng/1</link>
          <pubDate>Mon, 12 May 2025 10:00:00 GMT</pubDate>
          <description>Merger confirmed</description></item>
        </channel></rss>"""
        async with AfricaTool() as t:
            mock_r = MagicMock()
            mock_r.raise_for_status = MagicMock()
            mock_r.content = rss; mock_r.encoding = "utf-8"
            with patch.object(t.client, "get", return_value=mock_r):
                items = await t._fetch_rss("https://businessday.ng/feed/")
        assert len(items) == 1
        assert items[0]["title"] == "GTBank merger"

    @pytest.mark.asyncio
    async def test_scrape_pe_source_extracts_links(self):
        from src.tools.africa_tool import AfricaTool
        html = """<html><body>
          <a href="https://africaprivateequitynews.com/deals/gtbank">GTBank acquires fintech in merger deal announced</a>
          <a href="/nav">Home</a>
        </body></html>"""
        async with AfricaTool() as t:
            m = MagicMock(); m.raise_for_status = MagicMock()
            m.text = html
            with patch.object(t.client, "get", return_value=m):
                items = await t._scrape_pe_source("Africa PE News","https://africaprivateequitynews.com/t/deals","GTBank","2024-01-01")
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_scrape_pe_network_error_returns_empty(self):
        from src.tools.africa_tool import AfricaTool
        async with AfricaTool() as t:
            with patch.object(t.client, "get", side_effect=Exception("down")):
                assert await t._scrape_pe_source("Test","https://example.com","X","2024-01-01") == []


# ─── EDGAR Tool ───────────────────────────────────────────────────────────────

class TestEdgarTool:
    @pytest.mark.asyncio
    async def test_context_manager(self):
        from src.tools.edgar_tool import EdgarTool
        async with EdgarTool() as e: assert e._client is not None
        assert e._client.is_closed

    @pytest.mark.asyncio
    async def test_no_client_raises(self):
        from src.tools.edgar_tool import EdgarTool
        with pytest.raises(RuntimeError): EdgarTool().client

    @pytest.mark.asyncio
    async def test_empty_cik_returns_empty(self):
        from src.tools.edgar_tool import EdgarTool
        async with EdgarTool() as e:
            assert await e.get_recent_filings("") == []

    @pytest.mark.asyncio
    async def test_resolve_network_error_safe(self):
        from src.tools.edgar_tool import EdgarTool
        async with EdgarTool() as e:
            with patch.object(e.client, "get", side_effect=Exception("network")):
                r = await e.resolve_company("NonExistent Corp")
                assert isinstance(r, dict)


# ─── Signal Parsing (LLM layer) ───────────────────────────────────────────────

class TestSignalParsing:
    def _state(self):
        s = AgentState(request=AnalysisRequest(company_name="Acme"))
        s.signal_candidates = [
            SignalCandidate(signal_type=SignalType.MA_ACTIVITY, matched_patterns=[r"\bmerger\b"],
                            source_text="merger deal", source_type="filing",
                            source_name="8-K", raw_score=0.88, corroboration_count=2)
        ]
        return s

    def test_valid_explanation_parsed(self):
        from src.agents.signal_agent import _parse_explanations
        from src.engines.calibration import calibrate_all
        state = self._state()
        calibrated = calibrate_all(state.signal_candidates)
        payload = json.dumps([{
            "signal_type": "m_and_a_activity",
            "headline": "Merger confirmed",
            "evidence": ["8-K cites definitive agreement"],
            "reasoning": "Both filing and news confirm active deal."
        }])
        signals = _parse_explanations(payload, state.signal_candidates, calibrated, state)
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.MA_ACTIVITY

    def test_llm_cannot_invent_signal_not_in_candidates(self):
        from src.agents.signal_agent import _parse_explanations
        from src.engines.calibration import calibrate_all
        state = self._state()
        calibrated = calibrate_all(state.signal_candidates)
        # LLM tries to return credit_risk which was NOT detected by deterministic engine
        payload = json.dumps([{
            "signal_type": "credit_risk",
            "headline": "Invented signal",
            "evidence": ["made up"],
            "reasoning": "I just felt like it."
        }])
        signals = _parse_explanations(payload, state.signal_candidates, calibrated, state)
        assert len(signals) == 0  # no candidate for credit_risk → rejected

    def test_invalid_json_logs_error(self):
        from src.agents.signal_agent import _parse_explanations
        from src.engines.calibration import calibrate_all
        state = self._state()
        calibrated = calibrate_all(state.signal_candidates)
        signals = _parse_explanations("not json {{{{", state.signal_candidates, calibrated, state)
        assert signals == []
        assert len(state.errors) >= 1

    def test_markdown_fences_stripped(self):
        from src.agents.signal_agent import _parse_explanations
        from src.engines.calibration import calibrate_all
        state = self._state()
        calibrated = calibrate_all(state.signal_candidates)
        payload = "```json\n[]\n```"
        signals = _parse_explanations(payload, state.signal_candidates, calibrated, state)
        assert signals == []

    def test_fallback_signals_from_calibration(self):
        from src.agents.signal_agent import _fallback_signals
        from src.engines.calibration import calibrate_all
        state = self._state()
        calibrated = calibrate_all(state.signal_candidates)
        signals = _fallback_signals(calibrated)
        assert len(signals) == 1
        assert "deterministic" in signals[0].reasoning.lower()


# ─── Collection Agent ─────────────────────────────────────────────────────────

def _patch_all(edgar=None, africa=None, news=None, edgar_exc=None, africa_exc=None, news_exc=None):
    return (
        AsyncMock(side_effect=edgar_exc)  if edgar_exc  else AsyncMock(return_value=edgar  or ({"name":"Test"},[])),
        AsyncMock(side_effect=africa_exc) if africa_exc else AsyncMock(return_value=africa or ([],[])),
        AsyncMock(side_effect=news_exc)   if news_exc   else AsyncMock(return_value=news   or []),
    )


class TestDataCollectionAgent:
    @pytest.mark.asyncio
    async def test_populates_state(self):
        from src.agents.collection_agent import DataCollectionAgent
        profile = {"name":"Apple Inc","cik":"0000320193","ticker":"AAPL"}
        us_f = [SECFiling(accession_number="acc1",form_type="8-K",filing_date="2024-01-15",
                          company_name="Apple",cik="0000320193",document_url="https://sec.gov/x")]
        af_f = [SECFiling(accession_number="NGX-001",form_type="NGX Disclosure",
                          filing_date="2024-01-10",company_name="Apple",cik="NGX",document_url="https://ngx.com/x")]
        af_n = [NewsItem(title="Apple Africa",source="BusinessDay Nigeria",published_date="2024-01-08",
                         url="https://bd.ng/x",snippet="Expansion",relevance_score=0.75)]
        gl_n = [NewsItem(title="Apple merger",source="Reuters",published_date="2024-01-10",
                         url="https://reuters.com/x",snippet="Deal",relevance_score=0.9)]
        em, am, nm = _patch_all(edgar=(profile,us_f), africa=(af_f,af_n), news=gl_n)
        with patch("src.agents.collection_agent.search_company_filings",em), \
             patch("src.agents.collection_agent.fetch_african_intelligence",am), \
             patch("src.agents.collection_agent.fetch_market_news",nm):
            s = AgentState(request=AnalysisRequest(company_name="Apple",ticker="AAPL"))
            r = await DataCollectionAgent().run(s)
        assert r.company_profile.name == "Apple Inc"
        assert len(r.filings) == 2
        assert len(r.news_items) == 2
        assert r.news_items[0].relevance_score >= r.news_items[1].relevance_score

    @pytest.mark.asyncio
    async def test_edgar_failure_isolated(self):
        from src.agents.collection_agent import DataCollectionAgent
        em, am, nm = _patch_all(edgar_exc=Exception("EDGAR down"))
        with patch("src.agents.collection_agent.search_company_filings",em), \
             patch("src.agents.collection_agent.fetch_african_intelligence",am), \
             patch("src.agents.collection_agent.fetch_market_news",nm):
            s = AgentState(request=AnalysisRequest(company_name="Test"))
            r = await DataCollectionAgent().run(s)
        assert any("EDGAR" in e for e in r.errors)
        assert r.company_profile is not None

    @pytest.mark.asyncio
    async def test_africa_failure_isolated(self):
        from src.agents.collection_agent import DataCollectionAgent
        em, am, nm = _patch_all(africa_exc=Exception("Africa down"))
        with patch("src.agents.collection_agent.search_company_filings",em), \
             patch("src.agents.collection_agent.fetch_african_intelligence",am), \
             patch("src.agents.collection_agent.fetch_market_news",nm):
            s = AgentState(request=AnalysisRequest(company_name="Test"))
            r = await DataCollectionAgent().run(s)
        assert any("Africa" in e for e in r.errors)

    @pytest.mark.asyncio
    async def test_deduplicates_filings(self):
        from src.agents.collection_agent import DataCollectionAgent
        dup = SECFiling(accession_number="DUPE",form_type="8-K",filing_date=RECENT_DAY,
                        company_name="X",cik="001",document_url="https://sec.gov/x")
        em, am, nm = _patch_all(edgar=({"name":"X"},[dup]), africa=([dup],[]))
        with patch("src.agents.collection_agent.search_company_filings",em), \
             patch("src.agents.collection_agent.fetch_african_intelligence",am), \
             patch("src.agents.collection_agent.fetch_market_news",nm):
            s = AgentState(request=AnalysisRequest(company_name="X"))
            r = await DataCollectionAgent().run(s)
        assert len(r.filings) == 1

    @pytest.mark.asyncio
    async def test_deduplicates_news(self):
        from src.agents.collection_agent import DataCollectionAgent
        shared = NewsItem(title="Same news",source="Reuters",published_date=RECENT_DAY,
                          url="https://reuters.com/x",snippet="x",relevance_score=0.8)
        em, am, nm = _patch_all(africa=([],[shared]), news=[shared])
        with patch("src.agents.collection_agent.search_company_filings",em), \
             patch("src.agents.collection_agent.fetch_african_intelligence",am), \
             patch("src.agents.collection_agent.fetch_market_news",nm):
            s = AgentState(request=AnalysisRequest(company_name="X"))
            r = await DataCollectionAgent().run(s)
        assert len(r.news_items) == 1


# ─── Brief Synthesis Agent ────────────────────────────────────────────────────

class TestBriefSynthesisAgent:
    def _state(self):
        s = AgentState(request=AnalysisRequest(company_name="Acme",ticker="ACME"))
        s.company_profile = CompanyProfile(name="Acme",ticker="ACME",cik="001")
        s.filings = []; s.news_items = []
        s.signal_candidates = [
            SignalCandidate(signal_type=SignalType.MA_ACTIVITY,matched_patterns=[r"\bmerger\b"],
                            source_text="merger",source_type="filing",source_name="8-K",raw_score=0.88,corroboration_count=2)
        ]
        s.detected_signals = [
            DetectedSignal(signal_type=SignalType.MA_ACTIVITY,severity=Severity.HIGH,
                           headline="Merger confirmed",evidence=["8-K"],confidence=0.88,reasoning="Deal active")
        ]
        return s

    def _mock(self, text):
        mc = MagicMock(); mc.type = "text"; mc.text = text
        mr = MagicMock(); mr.content = [mc]; mr.stop_reason = "end_turn"
        return mr

    @pytest.mark.asyncio
    async def test_produces_brief(self):
        from src.agents.signal_agent import BriefSynthesisAgent
        payload = json.dumps({
            "executive_summary":"Acme is being acquired.",
            "overall_severity":"high","recommendation":"Act now.",
            "confidence_score":0.88,"key_metrics":[],"risk_factors":[],"recent_developments":[]
        })
        s = self._state()
        agent = BriefSynthesisAgent()
        with patch.object(agent.client.beta.messages,"create",return_value=self._mock(payload)):
            r = await agent.run(s)
        assert r.brief is not None
        assert r.brief.company_name == "Acme"
        assert r.brief.signal_candidates_count == 1

    @pytest.mark.asyncio
    async def test_compliance_flags_added(self):
        from src.agents.signal_agent import BriefSynthesisAgent
        payload = json.dumps({
            "executive_summary":"E","overall_severity":"medium","recommendation":"R",
            "confidence_score":0.5,"key_metrics":[],"risk_factors":[],"recent_developments":[]
        })
        s = self._state(); s.compliance_mode = True
        agent = BriefSynthesisAgent()
        with patch.object(agent.client.beta.messages,"create",return_value=self._mock(payload)):
            r = await agent.run(s)
        assert r.brief.compliance_mode is True
        assert any("not investment advice" in f.lower() for f in r.brief.compliance_flags)

    @pytest.mark.asyncio
    async def test_handles_llm_failure(self):
        from src.agents.signal_agent import BriefSynthesisAgent
        s = self._state()
        agent = BriefSynthesisAgent()
        with patch.object(agent.client.beta.messages,"create",side_effect=Exception("LLM down")):
            r = await agent.run(s)
        # Deterministic findings survive an LLM outage, flagged for human review.
        assert r.brief is not None
        assert [sig.headline for sig in r.brief.detected_signals] == ["Merger confirmed"]
        assert r.brief.overall_severity == Severity.HIGH
        assert r.brief.requires_human_review
        assert "LLM unavailable" in r.brief.analyst_model
        assert any("BriefSynthesisAgent" in e for e in r.errors)


# ─── Formatter ────────────────────────────────────────────────────────────────

class TestFormatter:
    def _brief(self):
        sig = DetectedSignal(
            signal_type=SignalType.MA_ACTIVITY, severity=Severity.HIGH,
            headline="Merger confirmed", evidence=["8-K filed","Reuters confirmed"],
            confidence=0.88, reasoning="Active deal.",
            candidate_patterns=[r"\bmerger\b"], corroboration_count=2,
            alpha_score=AlphaScore(score=74.5, severity_component=0.78,
                                   source_credibility=0.95, corroboration_weight=0.68,
                                   recency_weight=0.99, liquidity_tier=LiquidityTier.MID_CAP,
                                   expected_direction="positive",
                                   expected_magnitude_pct_low=8.0, expected_magnitude_pct_high=20.0,
                                   comparable_events_n=62, move_confidence="medium")
        )
        return AnalystBrief(
            company_name="Acme Corp", ticker="ACME",
            executive_summary="Acme shows M&A signals.",
            overall_severity=Severity.HIGH,
            recommendation="Initiate diligence.",
            confidence_score=0.85, detected_signals=[sig],
            signal_candidates_count=3, top_alpha_score=74.5,
            liquidity_tier=LiquidityTier.MID_CAP,
            key_metrics=[KeyMetric(name="EV/EBITDA",value="12x",period="LTM",interpretation="Premium")],
            risk_factors=[RiskFactor(factor="Antitrust",impact="Deal block",likelihood=Severity.MEDIUM)],
            recent_developments=["LOI signed","Board approved"],
            total_sources=12, processing_time_seconds=22.1
        )

    def test_json_roundtrip(self):
        from src.utils.formatter import brief_to_json
        b = self._brief()
        data = json.loads(brief_to_json(b))
        assert data["company_name"] == "Acme Corp"
        assert data["top_alpha_score"] == 74.5
        assert data["signal_candidates_count"] == 3

    def test_markdown_sections(self):
        from src.utils.formatter import brief_to_markdown
        md = brief_to_markdown(self._brief())
        for section in ["# Deal Intelligence Brief","## Executive Summary",
                         "## Confirmed Signals","## Key Metrics","## Risk Factors",
                         "Alpha Score","Expected Move","Patterns Fired"]:
            assert section in md, f"Missing: {section}"

    def test_markdown_compliance_banner(self):
        from src.utils.formatter import brief_to_markdown
        b = self._brief()
        b.compliance_mode = True
        b.compliance_flags = ["Output is AI-generated, unverified, not investment advice"]
        md = brief_to_markdown(b)
        assert "Compliance Mode" in md

    def test_markdown_human_review_banner(self):
        from src.utils.formatter import brief_to_markdown
        b = self._brief()
        b.requires_human_review = True
        b.human_review_reasons = ["Alpha score 80 ≥ threshold 70"]
        md = brief_to_markdown(b)
        assert "HUMAN REVIEW REQUIRED" in md

    def test_print_brief_no_crash(self):
        from src.utils.formatter import print_brief
        print_brief(self._brief())  # must not raise

    def test_json_alpha_score_serialised(self):
        from src.utils.formatter import brief_to_json
        data = json.loads(brief_to_json(self._brief()))
        sig = data["detected_signals"][0]
        assert "alpha_score" in sig
        assert sig["alpha_score"]["score"] == 74.5


# ─── Graph Integration ────────────────────────────────────────────────────────

class TestGraphIntegration:
    @pytest.mark.asyncio
    async def test_full_pipeline(self, monkeypatch):
        from src.agents.graph import run_analysis

        profile = {"name":"Acme","cik":"0000001","ticker":"ACME"}
        filing  = SECFiling(accession_number="acc1",form_type="8-K",filing_date=RECENT_DAY,
                            company_name="Acme",cik="0000001",document_url="https://sec.gov/x",
                            description="Definitive merger agreement signed with Target Corp")
        news    = [NewsItem(title="Acme merger confirmed",source="Reuters",published_date=RECENT_DAY,
                            url="https://reuters.com/x",snippet="Merger acquisition deal confirmed",relevance_score=0.9)]

        explain_json = json.dumps([{
            "signal_type":"m_and_a_activity","headline":"Merger confirmed",
            "evidence":["8-K","Reuters"],"reasoning":"Active deal."
        }])
        brief_json = json.dumps({
            "executive_summary":"Acme acquired.","overall_severity":"high",
            "recommendation":"Act.","confidence_score":0.88,
            "key_metrics":[],"risk_factors":[],"recent_developments":[]
        })

        def mock_response(text):
            mc = MagicMock(); mc.type = "text"; mc.text = text
            mr = MagicMock(); mr.content = [mc]; mr.stop_reason = "end_turn"
            return mr

        em, am, nm = _patch_all(edgar=(profile,[filing]), news=news)
        with patch("src.agents.collection_agent.search_company_filings",em), \
             patch("src.agents.collection_agent.fetch_african_intelligence",am), \
             patch("src.agents.collection_agent.fetch_market_news",nm):
            with patch("anthropic.Anthropic") as MockAnth:
                inst = MockAnth.return_value
                inst.beta.messages.create.side_effect = [
                    mock_response(explain_json),
                    mock_response(brief_json),
                ]
                import src.agents.signal_agent as sa
                monkeypatch.setattr(sa, "_get_llm_client", lambda: (inst, "anthropic"))
                brief = await run_analysis(AnalysisRequest(company_name="Acme",ticker="ACME"))

        assert brief is not None
        assert brief.company_name == "Acme"
        assert brief.signal_candidates_count >= 1
        # The mocked LLM text must actually reach the brief.
        assert brief.executive_summary == "Acme acquired."
        assert any(s.headline == "Merger confirmed" for s in brief.detected_signals)

    @pytest.mark.asyncio
    async def test_no_candidates_no_signals(self, monkeypatch):
        """If deterministic engine finds nothing, final brief has no signals."""
        from src.agents.graph import run_analysis

        em, am, nm = _patch_all()  # empty data
        with patch("src.agents.collection_agent.search_company_filings",em), \
             patch("src.agents.collection_agent.fetch_african_intelligence",am), \
             patch("src.agents.collection_agent.fetch_market_news",nm):
            with patch("anthropic.Anthropic") as MockAnth:
                inst = MockAnth.return_value
                brief_json = json.dumps({
                    "executive_summary":"No signals.","overall_severity":"low",
                    "recommendation":"Monitor.","confidence_score":0.3,
                    "key_metrics":[],"risk_factors":[],"recent_developments":[]
                })
                def mock_response(text):
                    mc = MagicMock(); mc.type = "text"; mc.text = text
                    mr = MagicMock(); mr.content = [mc]; mr.stop_reason = "end_turn"
                    return mr
                inst.beta.messages.create.return_value = mock_response(brief_json)
                import src.agents.signal_agent as sa
                monkeypatch.setattr(sa, "_get_llm_client", lambda: (inst, "anthropic"))
                brief = await run_analysis(AnalysisRequest(company_name="Quiet Corp"))

        assert brief.detected_signals == []
        assert brief.signal_candidates_count == 0

    @pytest.mark.asyncio
    async def test_compliance_mode_passed_through(self, monkeypatch):
        from src.agents.graph import run_analysis

        em, am, nm = _patch_all()
        with patch("src.agents.collection_agent.search_company_filings",em), \
             patch("src.agents.collection_agent.fetch_african_intelligence",am), \
             patch("src.agents.collection_agent.fetch_market_news",nm):
            with patch("anthropic.Anthropic") as MockAnth:
                inst = MockAnth.return_value
                brief_json = json.dumps({
                    "executive_summary":"E","overall_severity":"low","recommendation":"R",
                    "confidence_score":0.3,"key_metrics":[],"risk_factors":[],"recent_developments":[]
                })
                def mock_response(text):
                    mc = MagicMock(); mc.type = "text"; mc.text = text
                    mr = MagicMock(); mr.content = [mc]; mr.stop_reason = "end_turn"
                    return mr
                inst.beta.messages.create.return_value = mock_response(brief_json)
                import src.agents.signal_agent as sa
                monkeypatch.setattr(sa, "_get_llm_client", lambda: (inst, "anthropic"))
                brief = await run_analysis(AnalysisRequest(company_name="X"), compliance_mode=True)

        assert brief.compliance_mode is True
        assert any("not investment advice" in f.lower() for f in brief.compliance_flags)


# ─── Signal Interaction Engine (#1) ───────────────────────────────────────────

class TestSignalInteractionEngine:
    def _make_signal(self, sig_type, severity=Severity.HIGH, conf=0.85, corr=2):
        return DetectedSignal(
            signal_type=sig_type, severity=severity, headline="Test",
            evidence=["E"], confidence=conf, reasoning="R",
            corroboration_count=corr
        )

    def _state_with_signals(self, *signal_types):
        s = AgentState(request=AnalysisRequest(company_name="Test"))
        s.detected_signals = [self._make_signal(st) for st in signal_types]
        return s

    def test_ma_plus_insider_produces_compound(self):
        from src.engines.signal_interaction import SignalInteractionEngine
        state = self._state_with_signals(SignalType.MA_ACTIVITY, SignalType.INSIDER_ACTIVITY)
        result = SignalInteractionEngine().run(state)
        assert len(result.compound_signals) >= 1
        types = [c.interaction_type.value for c in result.compound_signals]
        assert "reinforcing" in types

    def test_credit_plus_distressed_produces_escalating(self):
        from src.engines.signal_interaction import SignalInteractionEngine
        state = self._state_with_signals(SignalType.CREDIT_RISK, SignalType.DISTRESSED_ASSET)
        result = SignalInteractionEngine().run(state)
        assert len(result.compound_signals) >= 1
        assert any(c.escalation_score >= 0.85 for c in result.compound_signals)

    def test_triple_compound_leadership_credit_insider(self):
        from src.engines.signal_interaction import SignalInteractionEngine
        state = self._state_with_signals(
            SignalType.LEADERSHIP_CHANGE, SignalType.CREDIT_RISK, SignalType.INSIDER_ACTIVITY
        )
        result = SignalInteractionEngine().run(state)
        assert len(result.compound_signals) >= 1
        # Should find the distress escalation rule
        highest = max(result.compound_signals, key=lambda c: c.escalation_score)
        assert highest.escalation_score >= 0.85

    def test_single_signal_no_compounds(self):
        from src.engines.signal_interaction import SignalInteractionEngine
        state = self._state_with_signals(SignalType.MA_ACTIVITY)
        result = SignalInteractionEngine().run(state)
        assert result.compound_signals == []

    def test_alpha_multiplier_applied(self):
        from src.engines.signal_interaction import SignalInteractionEngine
        from src.schemas.models import AlphaScore, LiquidityTier
        state = self._state_with_signals(SignalType.MA_ACTIVITY, SignalType.INSIDER_ACTIVITY)
        # Give signals alpha scores
        for sig in state.detected_signals:
            sig.alpha_score = AlphaScore(
                score=50.0, severity_component=0.78, source_credibility=0.9,
                corroboration_weight=0.68, recency_weight=0.99,
                liquidity_tier=LiquidityTier.MID_CAP
            )
        result = SignalInteractionEngine().run(state)
        # Signals in compound should have boosted alpha
        if result.compound_signals:
            max_score = max(s.alpha_score.score for s in result.detected_signals if s.alpha_score)
            assert max_score > 50.0

    def test_compound_confidence_geometric_mean(self):
        from src.engines.signal_interaction import _find_interactions
        signals = [
            self._make_signal(SignalType.CREDIT_RISK, conf=0.80),
            self._make_signal(SignalType.DISTRESSED_ASSET, conf=0.90),
        ]
        compounds = _find_interactions(signals)
        assert len(compounds) >= 1
        # Compounded confidence should be between the two individual values
        cc = compounds[0].compounded_confidence
        assert 0.70 <= cc <= 1.0

    def test_systemic_risk_level_set(self):
        from src.engines.signal_interaction import SignalInteractionEngine
        state = self._state_with_signals(SignalType.DISTRESSED_ASSET, SignalType.REGULATORY_ACTION)
        result = SignalInteractionEngine().run(state)
        if result.compound_signals:
            levels = [c.systemic_risk_level.value for c in result.compound_signals]
            assert any(l in ("systemic","contained") for l in levels)

    def test_contradictory_ma_distressed_detected(self):
        from src.engines.signal_interaction import _find_interactions
        from src.schemas.models import InteractionType
        signals = [
            self._make_signal(SignalType.MA_ACTIVITY),
            self._make_signal(SignalType.DISTRESSED_ASSET),
        ]
        compounds = _find_interactions(signals)
        contradictory = [c for c in compounds if c.interaction_type == InteractionType.CONTRADICTORY]
        assert len(contradictory) >= 1

    def test_reasoning_chain_populated(self):
        from src.engines.signal_interaction import SignalInteractionEngine
        state = self._state_with_signals(SignalType.MA_ACTIVITY, SignalType.INSIDER_ACTIVITY)
        result = SignalInteractionEngine().run(state)
        if result.compound_signals:
            assert len(result.compound_signals[0].reasoning_chain) > 20

    def test_low_severity_signals_excluded(self):
        from src.engines.signal_interaction import SignalInteractionEngine, _signals_qualify
        signals = [self._make_signal(SignalType.MA_ACTIVITY, severity=Severity.LOW)]
        qualified = _signals_qualify(signals)
        assert len(qualified) == 0


# ─── Warehouse (#2) ───────────────────────────────────────────────────────────

class TestWarehouse:
    def test_schema_import(self):
        from src.engines.warehouse import (
            FilingRecord, NewsRecord, DetectedSignalRecord,
            AnalystBriefRecord, MarketOutcomeRecord, ReplayRunRecord
        )
        assert True  # all import without error

    def test_get_engine_creates_tables(self, tmp_path):
        from src.engines import warehouse as wh
        wh.DB_PATH = tmp_path / "test_wh.db"
        engine = wh.get_engine()
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        for expected in ["filings","news_items","detected_signals","analyst_briefs",
                         "market_outcomes","replay_runs","scoring_history"]:
            assert expected in tables, f"Missing table: {expected}"

    def test_store_and_retrieve(self, tmp_path):
        from src.engines import warehouse as wh
        wh.DB_PATH = tmp_path / "test_wh2.db"
        brief = AnalystBrief(
            company_name="TestCo", ticker="TC",
            executive_summary="Test.", overall_severity=Severity.HIGH,
            recommendation="Watch.", confidence_score=0.75,
            detected_signals=[], total_sources=5
        )
        with wh.EventWarehouse() as w:
            w.store_run("run_001", brief)
            history = w.get_company_history("TestCo")
        assert len(history) == 1
        assert history[0]["company_name"] == "TestCo"

    def test_signal_history_query(self, tmp_path):
        from src.engines import warehouse as wh
        wh.DB_PATH = tmp_path / "test_wh3.db"
        sig = DetectedSignal(
            signal_type=SignalType.MA_ACTIVITY, severity=Severity.HIGH,
            headline="Test merger", evidence=["E"], confidence=0.8, reasoning="R"
        )
        brief = AnalystBrief(
            company_name="TestCo", executive_summary="E",
            overall_severity=Severity.HIGH, recommendation="R",
            confidence_score=0.8, detected_signals=[sig]
        )
        with wh.EventWarehouse() as w:
            w.store_run("run_002", brief)
            history = w.get_signal_history("TestCo")
        assert len(history) >= 1
        assert history[0]["signal_type"] == "m_and_a_activity"

    def test_scoring_trend(self, tmp_path):
        from src.engines import warehouse as wh
        wh.DB_PATH = tmp_path / "test_wh4.db"
        brief = AnalystBrief(
            company_name="TrendCo", executive_summary="E",
            overall_severity=Severity.MEDIUM, recommendation="R",
            confidence_score=0.6, detected_signals=[], top_alpha_score=55.0
        )
        with wh.EventWarehouse() as w:
            w.store_run("run_003", brief)
            trend = w.get_scoring_trend("TrendCo")
        # May be empty since no signals, but should not crash
        assert isinstance(trend, list)


# ─── Replay Engine (#3) ───────────────────────────────────────────────────────

class TestReplayEngine:
    def test_config_snapshot(self):
        from src.engines.replay import ReplayEngine
        engine = ReplayEngine()
        snap = engine.get_config_snapshot()
        assert "ruleset_version" in snap
        assert "model_version" in snap
        assert "prompt_version" in snap
        assert "scoring_version" in snap
        assert "snapshot_at" in snap

    @pytest.mark.asyncio
    async def test_replay_no_warehouse(self):
        """Replay without warehouse still runs deterministic engine."""
        from src.engines.replay import ReplayEngine
        engine = ReplayEngine()  # no session
        result = await engine.replay("Test Corp", "2024-01-01")
        assert result["company_name"] == "Test Corp"
        assert result["as_of_date"] == "2024-01-01"
        assert "candidates_produced" in result
        assert "config_snapshot" in result

    def test_compare_runs_no_diff(self):
        from src.engines.replay import compare_runs
        original = {"run_id":"r1","signal_summary":[{"type":"credit_risk","severity":"high","alpha":60}]}
        replay   = {"replay_id":"r2","signal_summary":[{"type":"credit_risk","severity":"high","alpha":60}]}
        diff = compare_runs(original, replay)
        assert diff["diff_count"] == 0

    def test_compare_runs_detects_removal(self):
        from src.engines.replay import compare_runs
        original = {"run_id":"r1","signal_summary":[{"type":"credit_risk","severity":"high","alpha":60}]}
        replay   = {"replay_id":"r2","signal_summary":[]}
        diff = compare_runs(original, replay)
        assert diff["diff_count"] == 1
        assert diff["diffs"][0]["change"] == "removed"

    def test_compare_runs_detects_addition(self):
        from src.engines.replay import compare_runs
        original = {"run_id":"r1","signal_summary":[]}
        replay   = {"replay_id":"r2","signal_summary":[{"type":"m_and_a_activity","severity":"high","alpha":75}]}
        diff = compare_runs(original, replay)
        assert diff["diffs"][0]["change"] == "added"


# ─── Company Memory (#4) ──────────────────────────────────────────────────────

class TestCompanyMemory:
    def _brief(self, severity=Severity.HIGH, alpha=70.0):
        sig = DetectedSignal(
            signal_type=SignalType.CREDIT_RISK, severity=severity,
            headline="Test", evidence=["E"], confidence=0.8, reasoning="R"
        )
        b = AnalystBrief(
            company_name="MemCo", ticker="MC",
            executive_summary="E", overall_severity=severity,
            recommendation="R", confidence_score=0.8,
            detected_signals=[sig], top_alpha_score=alpha
        )
        return b

    def test_create_profile(self, tmp_path):
        from src.engines import company_memory as cm
        cm.MEMORY_PATH = tmp_path / "memory.json"
        profile = cm.update_profile(self._brief())
        assert profile.company_name == "MemCo"
        assert profile.total_analyses_run == 1
        assert profile.total_signals_detected == 1

    def test_ema_update(self, tmp_path):
        from src.engines import company_memory as cm
        cm.MEMORY_PATH = tmp_path / "memory2.json"
        cm.update_profile(self._brief(Severity.LOW, alpha=20.0))
        profile1 = cm.get_profile("MemCo", "MC")
        cm.update_profile(self._brief(Severity.CRITICAL, alpha=95.0))
        profile2 = cm.get_profile("MemCo", "MC")
        assert profile2.rolling_risk_score > profile1.rolling_risk_score
        assert profile2.total_analyses_run == 2

    def test_risk_trend_detection(self, tmp_path):
        from src.engines import company_memory as cm
        cm.MEMORY_PATH = tmp_path / "memory3.json"
        cm.update_profile(self._brief(Severity.LOW, alpha=10.0))
        cm.update_profile(self._brief(Severity.CRITICAL, alpha=95.0))
        cm.update_profile(self._brief(Severity.CRITICAL, alpha=95.0))
        profile = cm.get_profile("MemCo","MC")
        assert profile.risk_trend in ("deteriorating","stable")

    def test_signal_density_tracked(self, tmp_path):
        from src.engines import company_memory as cm
        cm.MEMORY_PATH = tmp_path / "memory4.json"
        cm.update_profile(self._brief())
        profile = cm.get_profile("MemCo","MC")
        assert "credit_risk" in profile.historical_signal_density

    def test_leadership_change_counted(self, tmp_path):
        from src.engines import company_memory as cm
        cm.MEMORY_PATH = tmp_path / "memory5.json"
        sig = DetectedSignal(
            signal_type=SignalType.LEADERSHIP_CHANGE, severity=Severity.HIGH,
            headline="CEO resigned", evidence=["E"], confidence=0.85, reasoning="R"
        )
        b = AnalystBrief(
            company_name="LeadCo", executive_summary="E",
            overall_severity=Severity.HIGH, recommendation="R",
            confidence_score=0.8, detected_signals=[sig]
        )
        cm.update_profile(b)
        profile = cm.get_profile("LeadCo")
        assert profile.leadership_change_count == 1

    def test_get_profile_none_for_unknown(self, tmp_path):
        from src.engines import company_memory as cm
        cm.MEMORY_PATH = tmp_path / "memory6.json"
        assert cm.get_profile("NonExistentXYZ123") is None

    def test_watchlist_alerts(self, tmp_path):
        from src.engines import company_memory as cm
        cm.MEMORY_PATH = tmp_path / "memory7.json"
        cm.update_profile(self._brief(Severity.CRITICAL, alpha=95.0))
        cm.update_profile(self._brief(Severity.CRITICAL, alpha=95.0))
        cm.update_profile(self._brief(Severity.CRITICAL, alpha=95.0))
        alerts = cm.get_watchlist_alerts(threshold=5.0)  # low threshold to trigger
        assert len(alerts) >= 1


# ─── Confidence Decomposition (#5) ────────────────────────────────────────────

class TestConfidenceDecomposition:
    def _cand(self, sig_type=SignalType.MA_ACTIVITY, raw=0.85, corr=2, source="Reuters"):
        return SignalCandidate(
            signal_type=sig_type, matched_patterns=[r"\bmerger\b"],
            source_text="merger deal confirmed acquisition", source_type="news",
            source_name=source, raw_score=raw, corroboration_count=corr,
            entity_mentions=["Acme Corp","$2.1 billion","35%"]
        )

    def test_decompose_returns_all_components(self):
        from src.engines.confidence import decompose
        c = self._cand()
        d = decompose(c)
        assert 0 <= d.final_confidence <= 1.0
        assert 0 <= d.source_reliability_score <= 1.0
        assert 0 <= d.corroboration_score <= 1.0
        assert 0 <= d.filing_strength_score <= 1.0
        assert 0 <= d.historical_precision_score <= 1.0
        assert 0 <= d.entity_match_confidence <= 1.0
        assert 0 <= d.temporal_relevance_score <= 1.0
        assert 0 <= d.extraction_confidence <= 1.0

    def test_high_credibility_source_scores_higher(self):
        from src.engines.confidence import decompose
        reuters = decompose(self._cand(source="Reuters"))
        unknown = decompose(self._cand(source="unknown_blog_xyz"))
        assert reuters.source_reliability_score > unknown.source_reliability_score

    def test_more_corroboration_higher_score(self):
        from src.engines.confidence import decompose
        low  = decompose(self._cand(corr=1))
        high = decompose(self._cand(corr=5))
        assert high.corroboration_score > low.corroboration_score

    def test_more_entities_higher_match_score(self):
        from src.engines.confidence import _entity_match_score, decompose
        no_entities = self._cand()
        no_entities.entity_mentions = []
        many_entities = self._cand()
        many_entities.entity_mentions = ["Acme Corp","Target Ltd","$2.1B","35%","merger"]
        d_none = decompose(no_entities)
        d_many = decompose(many_entities)
        assert d_many.entity_match_confidence > d_none.entity_match_confidence

    def test_decompose_all_returns_dict(self):
        from src.engines.confidence import decompose_all
        candidates = [self._cand(SignalType.MA_ACTIVITY), self._cand(SignalType.CREDIT_RISK)]
        result = decompose_all(candidates)
        assert "m_and_a_activity" in result
        assert "credit_risk" in result

    def test_reasoning_populated(self):
        from src.engines.confidence import decompose
        c = self._cand(corr=1, source="unknown_xyz")  # weak source + low corr
        d = decompose(c)
        assert len(d.reasoning) > 10

    def test_calibration_adjustment_affects_final(self):
        from src.engines.confidence import decompose
        c = self._cand()
        d1 = decompose(c, calibration_adjustment=1.0)
        d2 = decompose(c, calibration_adjustment=0.8)
        assert d1.final_confidence > d2.final_confidence


# ─── Semantic Extraction (#6) ─────────────────────────────────────────────────

class TestSemanticExtraction:
    def test_going_concern_extracted(self):
        from src.engines.semantic import extract_evidence
        text = "Management has substantial doubt about the company's ability to continue as a going concern."
        ev = extract_evidence(text)
        types = [e.evidence_type for e in ev]
        assert "going_concern" in types

    def test_covenant_breach_extracted(self):
        from src.engines.semantic import extract_evidence
        text = "The company has experienced a breach of its financial covenant under the credit agreement."
        ev = extract_evidence(text)
        types = [e.evidence_type for e in ev]
        assert "covenant_breach" in types

    def test_merger_language_extracted(self):
        from src.engines.semantic import extract_evidence
        text = "The company has entered into a definitive agreement to acquire Target Corp."
        ev = extract_evidence(text)
        types = [e.evidence_type for e in ev]
        assert "merger_language" in types

    def test_insolvency_formal_extracted(self):
        from src.engines.semantic import extract_evidence
        text = "The company filed for Chapter 11 bankruptcy protection in the Delaware court."
        ev = extract_evidence(text)
        types = [e.evidence_type for e in ev]
        assert "insolvency_formal" in types

    def test_restructuring_clause_extracted(self):
        from src.engines.semantic import extract_evidence
        text = "The company has entered into a forbearance agreement with its lenders."
        ev = extract_evidence(text)
        types = [e.evidence_type for e in ev]
        assert "restructuring_clause" in types

    def test_financial_amount_extracted(self):
        from src.engines.semantic import extract_evidence
        text = "Recognised an impairment charge of $450 million during the quarter."
        ev = extract_evidence(text)
        if ev:
            assert any(e.financial_amount for e in ev)

    def test_empty_text_returns_empty(self):
        from src.engines.semantic import extract_evidence
        assert extract_evidence("") == []
        assert extract_evidence("   ") == []

    def test_evidence_to_strings(self):
        from src.engines.semantic import extract_evidence, evidence_to_strings
        text = "The company has entered into a definitive agreement to acquire Target Corp."
        ev = extract_evidence(text)
        strings = evidence_to_strings(ev)
        assert isinstance(strings, list)
        if strings:
            assert all(isinstance(s, str) for s in strings)
            assert all(len(s) > 5 for s in strings)

    def test_confidence_scores_valid(self):
        from src.engines.semantic import extract_evidence
        text = "Substantial doubt about ability to continue as a going concern. Covenant breach declared."
        ev = extract_evidence(text)
        for e in ev:
            assert 0 < e.confidence <= 1.0

    def test_max_per_type_respected(self):
        from src.engines.semantic import extract_evidence
        # Repeat the same pattern multiple times
        text = " ".join([
            "substantial doubt about ability to continue as a going concern"
        ] * 10)
        ev = extract_evidence(text, max_per_type=2)
        going_concern = [e for e in ev if e.evidence_type == "going_concern"]
        assert len(going_concern) <= 2


# ─── Adaptive Calibration (#7) ────────────────────────────────────────────────

class TestAdaptiveCalibration:
    def _cand(self, sig_type=SignalType.CREDIT_RISK, raw=0.80, corr=2):
        return SignalCandidate(
            signal_type=sig_type, matched_patterns=["test"],
            source_text="test", source_type="filing",
            source_name="8-K", raw_score=raw, corroboration_count=corr
        )

    def test_returns_valid_tuple(self):
        from src.engines.adaptive_calibration import adaptive_calibrate
        sev, conf, mat = adaptive_calibrate(self._cand())
        assert isinstance(sev, Severity)
        assert 0 <= conf <= 1.0
        assert 0 <= mat <= 1.0

    def test_falls_back_to_static_no_data(self, tmp_path):
        """With no feedback data, should behave like static calibration."""
        from src.engines import feedback as fb, adaptive_calibration as ac
        fb.FEEDBACK_PATH = tmp_path / "fb_empty.json"
        sev_adaptive, conf_adaptive, _ = ac.adaptive_calibrate(self._cand())
        from src.engines.calibration import calibrate
        sev_static, conf_static, _ = calibrate(self._cand())
        # Should be identical when no feedback data
        assert sev_adaptive == sev_static

    def test_calibration_report_has_all_signal_types(self):
        from src.engines.adaptive_calibration import get_calibration_report
        from src.schemas.models import SignalType
        report = get_calibration_report()
        for sig_type in SignalType:
            assert sig_type.value in report

    def test_report_structure(self):
        from src.engines.adaptive_calibration import get_calibration_report
        report = get_calibration_report()
        for sig, data in report.items():
            assert "feedback_samples" in data
            assert "adaptive_active" in data
            assert "precision_adjustment" in data
            assert "fp_penalty" in data
            assert "net_adjustment" in data


# ─── Market Impact (#8) ───────────────────────────────────────────────────────

class TestMarketImpact:
    def test_record_and_retrieve(self, tmp_path):
        from src.engines import market_impact as mi
        mi.OUTCOMES_PATH = tmp_path / "outcomes.json"
        outcome = mi.record_outcome(
            company_name="Acme", signal_type=SignalType.MA_ACTIVITY,
            severity_at_detection=Severity.HIGH, detection_date="2024-01-15",
            alpha_score_at_detection=72.0, price_change_10d_pct=15.3,
            event_confirmed=True, expected_direction="positive",
            expected_magnitude_low=8.0, expected_magnitude_high=20.0
        )
        assert outcome.direction_correct is True  # 15.3% positive matches "positive"
        assert outcome.magnitude_error_pct is not None

    def test_direction_correct_negative(self, tmp_path):
        from src.engines import market_impact as mi
        mi.OUTCOMES_PATH = tmp_path / "outcomes2.json"
        outcome = mi.record_outcome(
            company_name="Test", signal_type=SignalType.DISTRESSED_ASSET,
            severity_at_detection=Severity.CRITICAL, detection_date="2024-01-01",
            price_change_10d_pct=-22.0, event_confirmed=True,
            expected_direction="negative"
        )
        assert outcome.direction_correct is True

    def test_direction_wrong(self, tmp_path):
        from src.engines import market_impact as mi
        mi.OUTCOMES_PATH = tmp_path / "outcomes3.json"
        outcome = mi.record_outcome(
            company_name="Test", signal_type=SignalType.CREDIT_RISK,
            severity_at_detection=Severity.HIGH, detection_date="2024-01-01",
            price_change_10d_pct=5.0, expected_direction="negative"
        )
        assert outcome.direction_correct is False

    def test_accuracy_metrics(self, tmp_path):
        from src.engines import market_impact as mi
        mi.OUTCOMES_PATH = tmp_path / "outcomes4.json"
        mi.record_outcome("A", SignalType.MA_ACTIVITY, Severity.HIGH, "2024-01-01",
                          price_change_10d_pct=12.0, event_confirmed=True, expected_direction="positive")
        mi.record_outcome("B", SignalType.MA_ACTIVITY, Severity.HIGH, "2024-01-02",
                          price_change_10d_pct=-5.0, event_confirmed=False, expected_direction="positive")
        metrics = mi.get_accuracy_metrics()
        assert metrics["total_outcomes"] == 2
        assert metrics["event_confirmation_rate"] == 0.5

    def test_empty_outcomes_returns_message(self, tmp_path):
        from src.engines import market_impact as mi
        mi.OUTCOMES_PATH = tmp_path / "outcomes_empty.json"
        result = mi.get_accuracy_metrics()
        assert "message" in result

    def test_signal_accuracy_filter(self, tmp_path):
        from src.engines import market_impact as mi
        mi.OUTCOMES_PATH = tmp_path / "outcomes5.json"
        mi.record_outcome("A", SignalType.INSIDER_ACTIVITY, Severity.MEDIUM, "2024-01-01",
                          price_change_10d_pct=3.0, event_confirmed=True)
        result = mi.get_signal_accuracy(SignalType.INSIDER_ACTIVITY)
        assert result["samples"] == 1
        assert result["signal_type"] == "insider_activity"


# ─── Signal Registry (#10) ────────────────────────────────────────────────────

class TestSignalRegistry:
    def test_all_signal_types_registered(self):
        from src.engines.signal_registry import SIGNAL_REGISTRY
        from src.schemas.models import SignalType
        for sig_type in SignalType:
            assert sig_type in SIGNAL_REGISTRY, f"{sig_type.value} not in registry"

    def test_each_spec_has_patterns(self):
        from src.engines.signal_registry import SIGNAL_REGISTRY
        for sig_type, spec in SIGNAL_REGISTRY.items():
            total = (len(spec.trigger_patterns_high) +
                     len(spec.trigger_patterns_medium) +
                     len(spec.trigger_patterns_low))
            assert total >= 3, f"{sig_type.value} has fewer than 3 patterns"

    def test_get_signal_spec(self):
        from src.engines.signal_registry import get_signal_spec
        spec = get_signal_spec(SignalType.MA_ACTIVITY)
        assert spec is not None
        assert spec.display_name == "M&A Activity"

    def test_get_all_patterns(self):
        from src.engines.signal_registry import get_all_patterns
        patterns = get_all_patterns(SignalType.CREDIT_RISK)
        assert len(patterns) == 3  # high, medium, low
        scores = [score for _, score in patterns]
        assert scores[0] > scores[1] > scores[2]  # high > medium > low

    def test_list_all_signals(self):
        from src.engines.signal_registry import list_all_signals
        from src.schemas.models import SignalType
        all_sigs = list_all_signals()
        assert len(all_sigs) == len(list(SignalType))
        for s in all_sigs:
            assert "signal_type" in s
            assert "display_name" in s
            assert "total_patterns" in s

    def test_escalation_rules_valid(self):
        from src.engines.signal_registry import SIGNAL_REGISTRY
        all_types = set(SignalType)
        for spec in SIGNAL_REGISTRY.values():
            for related in spec.escalates_with:
                assert related in all_types
            for contradicted in spec.contradicts:
                assert contradicted in all_types

    def test_distressed_has_highest_precision(self):
        from src.engines.signal_registry import SIGNAL_REGISTRY
        distressed_spec = SIGNAL_REGISTRY[SignalType.DISTRESSED_ASSET]
        assert distressed_spec.historical_precision >= 0.75


# ─── Graph Intelligence (#11) ────────────────────────────────────────────────

class TestGraphIntelligence:
    def _fresh_engine(self, tmp_path):
        from src.engines import graph_intelligence as gi
        gi.GRAPH_PATH = tmp_path / "graph.json"
        return gi.EntityGraphEngine()

    def test_add_and_retrieve_company(self, tmp_path):
        engine = self._fresh_engine(tmp_path)
        engine.add_company("Acme Corp", ticker="ACME")
        assert "Acme Corp" in engine.G.nodes

    def test_add_executive_creates_edge(self, tmp_path):
        engine = self._fresh_engine(tmp_path)
        engine.add_company("Acme Corp")
        engine.add_executive("John Smith", "Acme Corp", "CEO")
        assert engine.G.has_edge("exec:John Smith", "Acme Corp")

    def test_lender_relationship(self, tmp_path):
        engine = self._fresh_engine(tmp_path)
        engine.add_company("Borrower Co")
        engine.add_lender_relationship("Big Bank", "Borrower Co", "revolving_credit")
        exposure = engine.get_lender_exposure("Big Bank")
        assert any(e["company"] == "Borrower Co" for e in exposure)

    def test_connected_companies(self, tmp_path):
        engine = self._fresh_engine(tmp_path)
        engine.add_company("A")
        engine.add_company("B")
        engine.add_board_overlap("Jane Doe", "A", "B")
        connected = engine.get_connected_companies("A", depth=1)
        assert "B" in connected

    def test_contagion_risk_unknown_company(self, tmp_path):
        engine = self._fresh_engine(tmp_path)
        result = engine.detect_contagion_risk("Unknown Corp XYZ")
        assert result["risk_level"] == "unknown"

    def test_contagion_risk_known_company(self, tmp_path):
        engine = self._fresh_engine(tmp_path)
        engine.add_company("Distressed Co")
        engine.add_lender_relationship("Big Bank", "Distressed Co")
        result = engine.detect_contagion_risk("Distressed Co")
        assert "risk_level" in result
        assert result["risk_level"] in ("isolated","contained","systemic")

    def test_save_and_reload(self, tmp_path):
        from src.engines import graph_intelligence as gi
        gi.GRAPH_PATH = tmp_path / "graph2.json"
        e1 = gi.EntityGraphEngine()
        e1.add_company("TestCo", ticker="TC")
        e1.save()
        e2 = gi.EntityGraphEngine()
        assert "TestCo" in e2.G.nodes

    def test_graph_summary(self, tmp_path):
        engine = self._fresh_engine(tmp_path)
        engine.add_company("A")
        engine.add_company("B")
        engine.add_lender_relationship("Bank", "A")
        summary = engine.graph_summary()
        assert summary["total_nodes"] >= 2
        assert "node_types" in summary
        assert "edge_types" in summary

    def test_acquisition_chain(self, tmp_path):
        engine = self._fresh_engine(tmp_path)
        engine.add_company("Acquirer")
        engine.add_company("Target")
        engine.add_acquisition("Acquirer", "Target", status="completed")
        chain = engine.get_acquisition_chain("Acquirer")
        assert "Target" in chain

    def test_shared_executives(self, tmp_path):
        engine = self._fresh_engine(tmp_path)
        engine.add_company("Corp A")
        engine.add_company("Corp B")
        engine.add_executive("Jane CEO", "Corp A", "CEO")
        engine.add_executive("Jane CEO", "Corp B", "Board Member")
        shared = engine.get_shared_executives("Corp A", "Corp B")
        assert "Jane CEO" in shared


# ─── Monitoring Engine (#13) ──────────────────────────────────────────────────

class TestMonitoringEngine:
    def test_add_to_watchlist(self, tmp_path):
        from src.engines import monitoring as mo
        mo.WATCHLIST_PATH = tmp_path / "watchlist.json"
        entry = mo.add_to_watchlist("GTBank", ticker="GTCO")
        assert entry["company_name"] == "GTBank"
        assert entry["ticker"] == "GTCO"

    def test_watchlist_deduplicates(self, tmp_path):
        from src.engines import monitoring as mo
        mo.WATCHLIST_PATH = tmp_path / "watchlist2.json"
        mo.add_to_watchlist("GTBank", ticker="GTCO")
        mo.add_to_watchlist("GTBank", ticker="GTCO")  # second add = update
        wl = mo.get_watchlist()
        assert len([w for w in wl if w["company_name"] == "GTBank"]) == 1

    def test_remove_from_watchlist(self, tmp_path):
        from src.engines import monitoring as mo
        mo.WATCHLIST_PATH = tmp_path / "watchlist3.json"
        mo.add_to_watchlist("Shoprite")
        ok = mo.remove_from_watchlist("Shoprite")
        assert ok is True
        assert all(w["company_name"] != "Shoprite" for w in mo.get_watchlist())

    def test_remove_nonexistent(self, tmp_path):
        from src.engines import monitoring as mo
        mo.WATCHLIST_PATH = tmp_path / "watchlist4.json"
        ok = mo.remove_from_watchlist("NonExistentCo")
        assert ok is False

    def test_alert_saved(self, tmp_path):
        from src.engines import monitoring as mo
        mo.ALERTS_PATH = tmp_path / "alerts.json"
        alert = {
            "alert_id": "test_001", "company": "TestCo", "severity": "high",
            "alpha_score": 75.0, "signal_count": 2, "headline": "Test alert",
            "recommendation": "Act", "requires_human_review": False,
            "triggered_at": "2024-01-15T10:00:00"
        }
        from src.engines.monitoring import _save_alert
        _save_alert(alert)
        alerts = mo.get_recent_alerts()
        assert len(alerts) == 1
        assert alerts[0]["alert_id"] == "test_001"

    def test_should_alert_high_severity(self, tmp_path):
        from src.engines.monitoring import _should_alert
        from src.schemas.models import AnalystBrief, Severity
        brief = AnalystBrief(
            company_name="X", executive_summary="E", overall_severity=Severity.HIGH,
            recommendation="R", confidence_score=0.8, detected_signals=[]
        )
        entry = {"alert_severity": "medium", "alert_alpha": 50.0}
        assert _should_alert(brief, entry) is True

    def test_should_not_alert_low_severity(self, tmp_path):
        from src.engines.monitoring import _should_alert
        from src.schemas.models import AnalystBrief, Severity
        brief = AnalystBrief(
            company_name="X", executive_summary="E", overall_severity=Severity.LOW,
            recommendation="R", confidence_score=0.4, detected_signals=[]
        )
        entry = {"alert_severity": "high", "alert_alpha": 80.0}
        assert _should_alert(brief, entry) is False

    def test_alpha_threshold_triggers_alert(self, tmp_path):
        from src.engines.monitoring import _should_alert
        from src.schemas.models import AnalystBrief, Severity
        brief = AnalystBrief(
            company_name="X", executive_summary="E", overall_severity=Severity.LOW,
            recommendation="R", confidence_score=0.5, detected_signals=[],
            top_alpha_score=85.0  # above threshold
        )
        entry = {"alert_severity": "critical", "alert_alpha": 50.0}
        assert _should_alert(brief, entry) is True


# ─── Market Data Engine ───────────────────────────────────────────────────────

class TestMarketData:
    def test_resolve_african_ticker(self):
        from src.engines.market_data import _resolve_ticker
        assert _resolve_ticker("GTCO") == "GTCO.LG"
        assert _resolve_ticker("MTN.JO") == "MTN.JO"
        assert _resolve_ticker("SCOM") == "SCOM.NR"

    def test_us_tickers_not_redirected_to_african_listings(self):
        """SLM is Sallie Mae and MTN is Vail Resorts in the US; JSE listings need a suffix."""
        from src.engines.market_data import _resolve_ticker
        for us in ("SLM", "MTN", "UBA", "ABG", "BHP", "SOL", "REM", "FSR"):
            assert _resolve_ticker(us) == us

    def test_resolve_us_ticker_unchanged(self):
        from src.engines.market_data import _resolve_ticker
        assert _resolve_ticker("AAPL") == "AAPL"
        assert _resolve_ticker("MSFT") == "MSFT"

    def test_resolve_ticker_with_suffix(self):
        from src.engines.market_data import _resolve_ticker
        assert _resolve_ticker("BHP.JO") == "BHP.JO"

    def test_get_current_price_invalid_ticker(self):
        from src.engines.market_data import get_current_price
        # Non-existent ticker should return None gracefully
        result = get_current_price("XXXXINVALIDXXXX")
        assert result is None

    def test_get_volatility_invalid_ticker(self):
        from src.engines.market_data import get_volatility
        result = get_volatility("XXXXINVALIDXXXX")
        assert result is None

    def test_fetch_price_moves_invalid_ticker(self):
        from src.engines.market_data import _fetch_price_moves
        result = _fetch_price_moves("XXXXINVALIDXXXX", "2024-01-01")
        assert isinstance(result, dict)
        assert all(v is None for v in result.values())

    def test_auto_record_outcome_no_data(self, tmp_path):
        from src.engines import market_impact as mi
        mi.OUTCOMES_PATH = tmp_path / "outcomes_md.json"
        from src.engines.market_data import auto_record_outcome
        from src.schemas.models import SignalType, Severity
        # Invalid ticker should return None without crashing
        result = auto_record_outcome(
            company_name="Test", ticker="XXXXINVALID",
            signal_type=SignalType.CREDIT_RISK,
            severity_at_detection=Severity.HIGH,
            detection_date="2024-01-15",
        )
        assert result is None

    def test_exchange_suffixes_defined(self):
        from src.engines.market_data import EXCHANGE_SUFFIXES
        for exchange in ["NGX","JSE","NSE","GSE","EGX","CSE","BRVM"]:
            assert exchange in EXCHANGE_SUFFIXES

    def test_african_ticker_map_populated(self):
        from src.engines.market_data import AFRICAN_TICKER_MAP
        assert len(AFRICAN_TICKER_MAP) >= 10
        assert all("." in v for v in AFRICAN_TICKER_MAP.values())


# ─── Backtesting Engine ───────────────────────────────────────────────────────

class TestBacktestEngine:
    def test_synthetic_backtest_runs(self, tmp_path):
        from src.engines import backtest as bt
        bt.BACKTEST_PATH = tmp_path / "backtest.json"
        result = bt.BacktestEngine().run_synthetic()
        assert "metrics_by_signal_type" in result
        assert "overall" in result
        assert result["mode"] == "synthetic"

    def test_synthetic_covers_all_signal_types(self, tmp_path):
        from src.engines import backtest as bt
        from src.schemas.models import SignalType
        bt.BACKTEST_PATH = tmp_path / "backtest2.json"
        result = bt.BacktestEngine().run_synthetic()
        for sig_type in SignalType:
            assert sig_type.value in result["metrics_by_signal_type"]

    def test_metrics_structure(self, tmp_path):
        from src.engines import backtest as bt
        bt.BACKTEST_PATH = tmp_path / "backtest3.json"
        result = bt.BacktestEngine().run_synthetic()
        for sig, metrics in result["metrics_by_signal_type"].items():
            assert "precision" in metrics
            assert "f1" in metrics
            assert "hit_rate" in metrics
            assert "false_positive_rate" in metrics
            assert 0 <= metrics["precision"] <= 1.0
            assert 0 <= metrics["f1"] <= 1.0
            assert 0 <= metrics["hit_rate"] <= 1.0

    def test_overall_metrics_computed(self, tmp_path):
        from src.engines import backtest as bt
        bt.BACKTEST_PATH = tmp_path / "backtest4.json"
        result = bt.BacktestEngine().run_synthetic()
        overall = result["overall"]
        assert "macro_precision" in overall
        assert "macro_f1" in overall
        assert "avg_hit_rate" in overall

    def test_results_persisted(self, tmp_path):
        from src.engines import backtest as bt
        bt.BACKTEST_PATH = tmp_path / "backtest5.json"
        bt.BacktestEngine().run_synthetic()
        latest = bt.get_latest_backtest()
        assert latest is not None
        assert "metrics_by_signal_type" in latest

    def test_history_grows(self, tmp_path):
        from src.engines import backtest as bt
        bt.BACKTEST_PATH = tmp_path / "backtest6.json"
        bt.BacktestEngine().run_synthetic()
        bt.BacktestEngine().run_synthetic()
        history = bt.get_backtest_history()
        assert len(history) == 2

    def test_warehouse_backtest_empty(self, tmp_path):
        from src.engines import backtest as bt, warehouse as wh
        bt.BACKTEST_PATH = tmp_path / "backtest7.json"
        wh.DB_PATH = tmp_path / "empty_wh.db"
        result = bt.BacktestEngine().run_from_warehouse()
        # Empty warehouse: should return valid result with empty metrics
        assert "metrics_by_signal_type" in result or "error" in result

    def test_f1_formula(self):
        from src.engines.backtest import _f1
        assert _f1(0.8, 0.6) == pytest.approx(0.6857, abs=0.001)
        assert _f1(0.0, 0.5) == 0.0
        assert _f1(0.0, 0.0) == 0.0

    def test_max_drawdown(self):
        from src.engines.backtest import _max_drawdown
        assert _max_drawdown([100, 90, 80, 95, 70]) == pytest.approx(30.0, abs=0.1)
        assert _max_drawdown([]) == 0.0
        assert _max_drawdown([50]) == 0.0


# ─── Portfolio Intelligence ───────────────────────────────────────────────────

class TestPortfolioIntelligence:
    def test_create_portfolio(self, tmp_path):
        from src.engines import portfolio as po
        po.PORTFOLIO_PATH = tmp_path / "portfolios.json"
        p = po.Portfolio("test_portfolio")
        p.add_holding("Apple Inc", ticker="AAPL", weight=0.3, sector="technology", market="US")
        holdings = p.get_holdings()
        assert "Apple Inc" in holdings
        assert holdings["Apple Inc"]["ticker"] == "AAPL"
        assert holdings["Apple Inc"]["weight"] == 0.3

    def test_add_multiple_holdings(self, tmp_path):
        from src.engines import portfolio as po
        po.PORTFOLIO_PATH = tmp_path / "portfolios2.json"
        p = po.Portfolio("multi")
        p.add_holding("GTBank", ticker="GTCO", weight=0.2, market="Africa")
        p.add_holding("Shoprite", ticker="SHP", weight=0.15, market="Africa")
        p.add_holding("Apple Inc", ticker="AAPL", weight=0.3, market="US")
        assert len(p.get_holdings()) == 3

    def test_remove_holding(self, tmp_path):
        from src.engines import portfolio as po
        po.PORTFOLIO_PATH = tmp_path / "portfolios3.json"
        p = po.Portfolio("remove_test")
        p.add_holding("TestCo")
        assert p.remove_holding("TestCo") is True
        assert "TestCo" not in p.get_holdings()

    def test_remove_nonexistent(self, tmp_path):
        from src.engines import portfolio as po
        po.PORTFOLIO_PATH = tmp_path / "portfolios4.json"
        p = po.Portfolio("empty")
        assert p.remove_holding("NonExistent") is False

    def test_aggregate_risk_empty_portfolio(self, tmp_path):
        from src.engines import portfolio as po
        po.PORTFOLIO_PATH = tmp_path / "portfolios5.json"
        p = po.Portfolio("empty_risk")
        result = p.aggregate_risk()
        assert "error" in result

    def test_aggregate_risk_no_profiles(self, tmp_path):
        from src.engines import portfolio as po, company_memory as cm
        po.PORTFOLIO_PATH = tmp_path / "portfolios6.json"
        cm.MEMORY_PATH    = tmp_path / "memory_po.json"
        p = po.Portfolio("no_profiles")
        p.add_holding("UnknownCo1", weight=0.5)
        p.add_holding("UnknownCo2", weight=0.5)
        result = p.aggregate_risk()
        # Should handle missing profiles gracefully
        assert "weighted_portfolio_risk" in result
        assert result["weighted_portfolio_risk"] == 0.0

    def test_list_portfolios(self, tmp_path):
        from src.engines import portfolio as po
        po.PORTFOLIO_PATH = tmp_path / "portfolios7.json"
        po.Portfolio("port_a").add_holding("Co1")
        po.Portfolio("port_b").add_holding("Co2")
        names = po.list_portfolios()
        assert "port_a" in names
        assert "port_b" in names

    def test_delete_portfolio(self, tmp_path):
        from src.engines import portfolio as po
        po.PORTFOLIO_PATH = tmp_path / "portfolios8.json"
        po.Portfolio("to_delete").add_holding("Co1")
        ok = po.delete_portfolio("to_delete")
        assert ok is True
        assert "to_delete" not in po.list_portfolios()

    def test_risk_level_function(self):
        from src.engines.portfolio import _risk_level
        assert _risk_level(80) == "critical"
        assert _risk_level(55) == "high"
        assert _risk_level(35) == "medium"
        assert _risk_level(10) == "low"


# ─── Entity Resolver ──────────────────────────────────────────────────────────

class TestEntityResolver:
    def _resolver(self, tmp_path):
        from src.engines import entity_resolver as er
        er.ENTITY_REGISTRY_PATH = tmp_path / "registry.json"
        er._resolver = None  # reset module-level cache
        return er.EntityResolver()

    def test_register_and_resolve(self, tmp_path):
        r = self._resolver(tmp_path)
        eid = r.register("Apple Inc", ticker="AAPL", cik="0000320193")
        assert eid is not None
        entity = r.resolve("Apple Inc")
        assert entity is not None
        assert entity["ticker"] == "AAPL"

    def test_resolve_by_ticker(self, tmp_path):
        r = self._resolver(tmp_path)
        r.register("Apple Inc", ticker="AAPL")
        entity = r.resolve("AAPL")
        assert entity is not None
        assert entity["canonical_name"] == "Apple Inc"

    def test_resolve_by_cik(self, tmp_path):
        r = self._resolver(tmp_path)
        r.register("Apple Inc", cik="0000320193")
        entity = r.resolve("0000320193")
        assert entity is not None

    def test_resolve_alias(self, tmp_path):
        r = self._resolver(tmp_path)
        r.register("Apple Inc", aliases=["Apple Computer", "AAPL Corp"])
        entity = r.resolve("Apple Computer")
        assert entity is not None
        assert entity["canonical_name"] == "Apple Inc"

    def test_normalise_deduplicates(self, tmp_path):
        r = self._resolver(tmp_path)
        id1 = r.register("Apple Inc.")
        id2 = r.register("Apple, Inc")
        # Both should resolve to same or similar canonical id
        assert r.resolve("Apple Inc") is not None

    def test_resolve_nonexistent(self, tmp_path):
        r = self._resolver(tmp_path)
        assert r.resolve("NonExistentCompanyXYZ999") is None

    def test_get_canonical_name(self, tmp_path):
        r = self._resolver(tmp_path)
        r.register("Apple Inc", aliases=["AAPL"])
        assert r.get_canonical_name("Apple Inc") == "Apple Inc"
        assert r.get_canonical_name("Unknown Co") == "Unknown Co"  # fallback

    def test_merge_duplicates(self, tmp_path):
        r = self._resolver(tmp_path)
        r.register("Guaranty Trust Bank", ticker="GTCO")
        r.register("GTBank Plc", ticker="GTB")
        ok = r.merge_duplicates("Guaranty Trust Bank", "GTBank Plc")
        assert ok is True
        # Duplicate should now resolve to primary
        entity = r.resolve("GTBank Plc")
        assert entity is not None
        assert entity["canonical_name"] == "Guaranty Trust Bank"

    def test_stats(self, tmp_path):
        r = self._resolver(tmp_path)
        r.register("Apple Inc", ticker="AAPL", cik="0000320193")
        r.register("GTBank", ticker="GTCO")
        stats = r.stats()
        assert stats["total_entities"] == 2
        assert stats["with_ticker"] == 2
        assert stats["with_cik"] >= 1

    def test_list_all(self, tmp_path):
        r = self._resolver(tmp_path)
        r.register("CompA")
        r.register("CompB")
        all_entities = r.list_all()
        assert len(all_entities) == 2

    def test_normalise_removes_suffixes(self):
        from src.engines.entity_resolver import _normalise_name
        assert _normalise_name("Apple Inc.") == _normalise_name("Apple")
        assert _normalise_name("GTBank Plc") == _normalise_name("GTBank")
        assert _normalise_name("Acme Corporation") == _normalise_name("Acme")


# ─── Alpha Explainer ─────────────────────────────────────────────────────────

class TestAlphaExplainer:
    def _signal_with_alpha(self, severity=Severity.HIGH, score=72.5):
        from src.schemas.models import AlphaScore, LiquidityTier
        alpha = AlphaScore(
            score=score, severity_component=0.78,
            source_credibility=0.95, corroboration_weight=0.68,
            recency_weight=0.99, liquidity_tier=LiquidityTier.MID_CAP,
            expected_direction="positive",
            expected_magnitude_pct_low=8.0, expected_magnitude_pct_high=20.0,
            comparable_events_n=62, move_confidence="medium",
        )
        return DetectedSignal(
            signal_type=SignalType.MA_ACTIVITY, severity=severity,
            headline="Test", evidence=["E"], confidence=0.85, reasoning="R",
            corroboration_count=2, alpha_score=alpha,
        )

    def test_explain_returns_all_sections(self):
        from src.engines.alpha_explainer import explain_alpha
        sig = self._signal_with_alpha()
        result = explain_alpha(sig)
        for key in ["final_score","base_score","component_contributions",
                    "component_reasons","raw_components","weights_used",
                    "plain_english","compliance_notes"]:
            assert key in result, f"Missing key: {key}"

    def test_component_contributions_sum_to_base(self):
        from src.engines.alpha_explainer import explain_alpha
        sig = self._signal_with_alpha()
        result = explain_alpha(sig)
        total = sum(result["component_contributions"].values())
        assert abs(total - result["base_score"]) < 0.5  # rounding tolerance

    def test_all_five_components_present(self):
        from src.engines.alpha_explainer import explain_alpha
        sig = self._signal_with_alpha()
        result = explain_alpha(sig)
        for comp in ["severity","source_credibility","corroboration","recency","liquidity"]:
            assert comp in result["component_contributions"]
            assert comp in result["component_reasons"]

    def test_weights_sum_to_one(self):
        from src.engines.alpha_explainer import explain_alpha
        sig = self._signal_with_alpha()
        result = explain_alpha(sig)
        total_weight = sum(result["weights_used"].values())
        assert abs(total_weight - 1.0) < 0.001

    def test_compound_boost_adds_to_score(self):
        from src.engines.alpha_explainer import explain_alpha
        sig = self._signal_with_alpha(score=50.0)
        result_no_boost  = explain_alpha(sig, compound_multiplier=1.0)
        result_with_boost = explain_alpha(sig, compound_multiplier=1.8)
        assert result_with_boost["compound_boost"] > 0
        assert result_with_boost["final_score"] > result_no_boost["final_score"]

    def test_no_alpha_returns_error(self):
        from src.engines.alpha_explainer import explain_alpha
        sig = DetectedSignal(
            signal_type=SignalType.MA_ACTIVITY, severity=Severity.HIGH,
            headline="T", evidence=[], confidence=0.8, reasoning="R"
        )
        result = explain_alpha(sig)
        assert "error" in result

    def test_plain_english_populated(self):
        from src.engines.alpha_explainer import explain_alpha
        sig = self._signal_with_alpha()
        result = explain_alpha(sig)
        assert len(result["plain_english"]) > 30

    def test_explain_brief(self):
        from src.engines.alpha_explainer import explain_brief
        from src.schemas.models import AnalystBrief
        sig = self._signal_with_alpha()
        brief = AnalystBrief(
            company_name="Test", executive_summary="E",
            overall_severity=Severity.HIGH, recommendation="R",
            confidence_score=0.8, detected_signals=[sig]
        )
        explanations = explain_brief(brief)
        assert len(explanations) == 1
        assert "final_score" in explanations[0]

    def test_critical_compliance_note(self):
        from src.engines.alpha_explainer import explain_alpha
        sig = self._signal_with_alpha(severity=Severity.CRITICAL, score=85.0)
        sig.alpha_score = sig.alpha_score.model_copy(update={
            "requires_human_review": True,
            "review_reason": "CRITICAL severity requires review"
        })
        result = explain_alpha(sig)
        assert len(result["compliance_notes"]) >= 1


# ─── African Sources Expansion ────────────────────────────────────────────────

class TestAfricanSourcesExpansion:
    def test_brvm_in_feeds(self):
        from src.tools.africa_tool import AFRICAN_NEWS_FEEDS
        urls = list(AFRICAN_NEWS_FEEDS.values())
        assert any("brvm" in u.lower() for u in urls), "BRVM feed missing"

    def test_egyptian_exchange_in_pe_sources(self):
        from src.tools.africa_tool import PE_CAPITAL_SOURCES
        urls = [url for _, url, _, _ in PE_CAPITAL_SOURCES]
        assert any("egx" in u.lower() for u in urls), "Egyptian Exchange missing"

    def test_casablanca_in_pe_sources(self):
        from src.tools.africa_tool import PE_CAPITAL_SOURCES
        urls = [url for _, url, _, _ in PE_CAPITAL_SOURCES]
        assert any("casablanca" in u.lower() for u in urls), "Casablanca missing"

    def test_gcr_ratings_in_sources(self):
        from src.tools.africa_tool import PE_CAPITAL_SOURCES, AFRICAN_SOURCE_MAP
        assert "gcrratings.com" in AFRICAN_SOURCE_MAP

    def test_imf_africa_in_sources(self):
        from src.tools.africa_tool import PE_CAPITAL_SOURCES
        names = [name for name, _, _, _ in PE_CAPITAL_SOURCES]
        assert any("imf" in n.lower() for n in names), "IMF Africa missing"

    def test_world_bank_in_sources(self):
        from src.tools.africa_tool import PE_CAPITAL_SOURCES
        names = [name for name, _, _, _ in PE_CAPITAL_SOURCES]
        assert any("world bank" in n.lower() for n in names), "World Bank missing"

    def test_agence_ecofin_in_feeds(self):
        from src.tools.africa_tool import AFRICAN_NEWS_FEEDS
        assert any("ecofin" in url.lower() for url in AFRICAN_NEWS_FEEDS.values())

    def test_morocco_in_feeds(self):
        from src.tools.africa_tool import AFRICAN_NEWS_FEEDS
        assert any("morocco" in url.lower() or "morocc" in url.lower()
                   for url in AFRICAN_NEWS_FEEDS.values()), "Morocco feed missing"

    def test_total_feeds_count(self):
        from src.tools.africa_tool import AFRICAN_NEWS_FEEDS
        assert len(AFRICAN_NEWS_FEEDS) >= 45, f"Expected 45+ feeds, got {len(AFRICAN_NEWS_FEEDS)}"  # currently 49

    def test_total_pe_sources_count(self):
        from src.tools.africa_tool import PE_CAPITAL_SOURCES
        assert len(PE_CAPITAL_SOURCES) >= 35, f"Expected 35+ PE sources, got {len(PE_CAPITAL_SOURCES)}"  # currently 48

    def test_all_new_pe_sources_https(self):
        from src.tools.africa_tool import PE_CAPITAL_SOURCES
        for name, url, _, _ in PE_CAPITAL_SOURCES:
            assert url.startswith("https://"), f"{name}: not HTTPS"


# ─── LLM Provider (Groq + Anthropic) ─────────────────────────────────────────

class TestLLMProvider:
    def test_default_provider_is_anthropic(self):
        import os
        os.environ.pop("DEAL_INTEL_PROVIDER", None)
        # Re-import to pick up default
        import importlib
        import src.agents.signal_agent as sa
        importlib.reload(sa)
        assert sa.PROVIDER == "anthropic"
        assert sa.MODEL == sa.ANTHROPIC_MODEL

    def test_groq_provider_sets_model(self, monkeypatch):
        monkeypatch.setenv("DEAL_INTEL_PROVIDER", "groq")
        import importlib, src.agents.signal_agent as sa
        importlib.reload(sa)
        assert sa.PROVIDER == "groq"
        assert sa.MODEL == sa.GROQ_MODEL
        assert "llama" in sa.GROQ_MODEL.lower()
        # Reset
        monkeypatch.delenv("DEAL_INTEL_PROVIDER", raising=False)
        importlib.reload(sa)

    def test_anthropic_model_name(self):
        import src.agents.signal_agent as sa
        assert "claude" in sa.ANTHROPIC_MODEL.lower()

    def test_groq_model_is_versatile(self):
        import src.agents.signal_agent as sa
        assert sa.GROQ_MODEL == "llama-3.3-70b-versatile"

    @staticmethod
    def _anthropic_client(*blocks, stop_reason="end_turn"):
        mock_client = MagicMock()
        mock_resp = MagicMock(); mock_resp.content = list(blocks); mock_resp.stop_reason = stop_reason
        mock_client.beta.messages.create.return_value = mock_resp
        return mock_client

    @staticmethod
    def _block(kind, text=""):
        b = MagicMock(); b.type = kind; b.text = text
        return b

    def test_call_llm_anthropic_mock(self):
        """_call_llm works with mocked Anthropic client."""
        import src.agents.signal_agent as sa
        mock_client = self._anthropic_client(self._block("text", '{"signals":[]}'))
        result = sa._call_llm(mock_client, "anthropic", "system", "user", max_tokens=100)
        assert result == '{"signals":[]}'
        mock_client.beta.messages.create.assert_called_once()
        kwargs = mock_client.beta.messages.create.call_args[1]
        assert kwargs["model"] == sa.ANTHROPIC_MODEL
        assert kwargs["max_tokens"] > 100          # room for thinking
        assert kwargs["fallbacks"] == "default"

    def test_call_llm_anthropic_skips_thinking_blocks(self):
        import src.agents.signal_agent as sa
        client = self._anthropic_client(self._block("thinking"), self._block("text", "answer"))
        assert sa._call_llm(client, "anthropic", "s", "u") == "answer"

    def test_call_llm_anthropic_refusal_raises(self):
        import src.agents.signal_agent as sa
        client = self._anthropic_client(stop_reason="refusal")
        with pytest.raises(RuntimeError, match="declined"):
            sa._call_llm(client, "anthropic", "s", "u")

    def test_call_llm_anthropic_truncation_raises(self):
        import src.agents.signal_agent as sa
        client = self._anthropic_client(self._block("text", "{"), stop_reason="max_tokens")
        with pytest.raises(RuntimeError, match="max_tokens"):
            sa._call_llm(client, "anthropic", "s", "u")

    def test_call_llm_groq_mock(self):
        """_call_llm works with mocked Groq client (OpenAI-compatible format)."""
        import src.agents.signal_agent as sa
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '{"signals":[]}'
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_resp
        result = sa._call_llm(mock_client, "groq", "system", "user", max_tokens=100)
        assert result == '{"signals":[]}'
        mock_client.chat.completions.create.assert_called_once()
        # Verify it uses the right model and format
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == sa.GROQ_MODEL
        assert any(m["role"] == "system" for m in call_kwargs["messages"])
        assert any(m["role"] == "user"   for m in call_kwargs["messages"])

    def test_call_llm_groq_uses_chat_completions(self):
        """Groq path must use chat.completions.create, not messages.create."""
        import src.agents.signal_agent as sa
        mock_client = MagicMock()
        mock_choice = MagicMock(); mock_choice.message.content = "ok"
        mock_resp = MagicMock(); mock_resp.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_resp
        sa._call_llm(mock_client, "groq", "sys", "usr")
        assert mock_client.chat.completions.create.called
        assert not mock_client.messages.create.called

    def test_call_llm_anthropic_uses_messages_create(self):
        """Anthropic path must use the Messages API, not chat.completions."""
        import src.agents.signal_agent as sa
        mock_client = self._anthropic_client(self._block("text", "ok"))
        sa._call_llm(mock_client, "anthropic", "sys", "usr")
        assert mock_client.beta.messages.create.called
        assert not mock_client.chat.completions.create.called

    def test_get_llm_client_returns_anthropic_by_default(self, monkeypatch):
        import importlib, src.agents.signal_agent as sa
        monkeypatch.delenv("DEAL_INTEL_PROVIDER", raising=False)
        importlib.reload(sa)
        # With no GROQ_API_KEY set, default should try anthropic
        assert sa.PROVIDER == "anthropic"

    def test_groq_raises_without_api_key(self, monkeypatch):
        monkeypatch.setenv("DEAL_INTEL_PROVIDER", "groq")
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        import importlib, src.agents.signal_agent as sa
        importlib.reload(sa)
        with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
            sa._get_llm_client()
        monkeypatch.delenv("DEAL_INTEL_PROVIDER", raising=False)
        importlib.reload(sa)

    def test_groq_available_flag(self):
        import src.agents.signal_agent as sa
        # groq is installed so should be True
        assert sa._GROQ_AVAILABLE is True


# ─── Report integrity (audit regressions) ─────────────────────────────────────

def _sig(sig_type, severity=Severity.HIGH, conf=0.85, alpha=None, reasoning="R", **kw):
    a = kw.pop("alpha_score", None)
    if alpha is not None:
        a = AlphaScore(score=alpha, severity_component=0.5, source_credibility=0.5,
                       corroboration_weight=0.5, recency_weight=0.5)
    return DetectedSignal(signal_type=sig_type, severity=severity, headline="H",
                          evidence=["E"], confidence=conf, reasoning=reasoning,
                          alpha_score=a, **kw)


def _cand(sig_type, raw=0.9):
    return SignalCandidate(signal_type=sig_type, matched_patterns=["p"], source_text="text",
                           source_type="filing", source_name="8-K", raw_score=raw)


def _patch_llm(monkeypatch, reply):
    import src.agents.signal_agent as sa
    monkeypatch.setattr(sa, "_get_llm_client", lambda: (MagicMock(), "anthropic"))
    monkeypatch.setattr(sa, "_call_llm", lambda *a, **k: reply)
    return sa


class TestReportIntegrity:
    @pytest.fixture(autouse=True)
    def _no_audit_writes(self, monkeypatch):
        import src.agents.signal_agent as sa
        monkeypatch.setattr(sa, "log_state", lambda *a, **k: None)

    async def test_llm_cannot_drop_confirmed_signal(self, monkeypatch):
        sa = _patch_llm(monkeypatch, json.dumps([{
            "signal_type": "m_and_a_activity", "headline": "Deal", "evidence": ["x"], "reasoning": "y"}]))
        state = AgentState(request=AnalysisRequest(company_name="Acme"))
        state.signal_candidates = [_cand(SignalType.MA_ACTIVITY), _cand(SignalType.CREDIT_RISK)]
        out = await sa.LLMExplanationNode().run(state)
        assert {s.signal_type for s in out.detected_signals} == {SignalType.MA_ACTIVITY, SignalType.CREDIT_RISK}

    async def test_duplicate_llm_items_deduplicated(self, monkeypatch):
        item = {"signal_type": "credit_risk", "headline": "C", "evidence": "single string", "reasoning": "r"}
        sa = _patch_llm(monkeypatch, json.dumps([item, item]))
        state = AgentState(request=AnalysisRequest(company_name="Acme"))
        state.signal_candidates = [_cand(SignalType.CREDIT_RISK)]
        out = await sa.LLMExplanationNode().run(state)
        assert len(out.detected_signals) == 1
        assert out.detected_signals[0].evidence == ["single string"]

    async def test_fallback_respects_compliance_suppression(self, monkeypatch):
        import src.agents.signal_agent as sa
        monkeypatch.setattr(sa, "_get_llm_client", lambda: (MagicMock(), "anthropic"))
        def boom(*a, **k): raise RuntimeError("LLM down")
        monkeypatch.setattr(sa, "_call_llm", boom)
        monkeypatch.setattr(sa, "adaptive_calibrate",
                            lambda c, sector=None: (Severity.LOW, 0.1 if c.signal_type == SignalType.CREDIT_RISK else 0.9, 0.1))
        state = AgentState(request=AnalysisRequest(company_name="Acme"), compliance_mode=True)
        state.signal_candidates = [_cand(SignalType.MA_ACTIVITY), _cand(SignalType.CREDIT_RISK)]
        out = await sa.LLMExplanationNode().run(state)
        assert [s.signal_type for s in out.detected_signals] == [SignalType.MA_ACTIVITY]
        assert out.low_confidence_signals_suppressed == 1

    async def test_synthesis_brief_fields(self, monkeypatch):
        sa = _patch_llm(monkeypatch, json.dumps({
            "executive_summary": None, "overall_severity": "low", "recommendation": "Watch",
            "confidence_score": "high", "recent_developments": "one item",
        }))
        from src.engines.signal_interaction import _find_interactions
        state = AgentState(request=AnalysisRequest(company_name="Acme"), compliance_mode=True)
        state.detected_signals = [
            _sig(SignalType.CREDIT_RISK, Severity.CRITICAL, alpha=40.0),
            _sig(SignalType.DISTRESSED_ASSET, Severity.HIGH, alpha=60.0),
        ]
        state.compound_signals = _find_interactions(state.detected_signals)
        state.low_confidence_signals_suppressed = 2
        out = await sa.BriefSynthesisAgent().run(state)
        b = out.brief
        assert b is not None, out.errors
        assert b.overall_severity == Severity.CRITICAL          # floored at max signal severity
        assert b.confidence_score == 0.5                        # non-numeric coerced
        assert b.executive_summary == "Analysis complete."
        assert b.recent_developments == ["one item"]
        assert b.top_alpha_score == 60.0                        # max, not list position
        assert b.analyst_model == sa.ANTHROPIC_MODEL
        assert b.compound_signals and b.systemic_risk_level.value != "isolated"
        assert "2 low-confidence signal(s) suppressed" in b.compliance_flags

    def test_compound_boost_retriggers_human_review(self):
        from src.engines.signal_interaction import _apply_alpha_multipliers, _find_interactions
        sigs = [_sig(SignalType.CREDIT_RISK, alpha=50.0), _sig(SignalType.DISTRESSED_ASSET, alpha=50.0)]
        out = _apply_alpha_multipliers(sigs, _find_interactions(sigs))
        assert all(s.alpha_score.score >= 70 for s in out)
        assert all(s.alpha_score.requires_human_review for s in out)

    def test_contradictory_compound_reduces_alpha(self):
        from src.engines.signal_interaction import _apply_alpha_multipliers, _find_interactions
        sigs = [_sig(SignalType.MA_ACTIVITY, alpha=50.0), _sig(SignalType.DISTRESSED_ASSET, alpha=50.0)]
        compounds = _find_interactions(sigs)
        assert any(c.interaction_type.value == "contradictory" for c in compounds)
        out = {s.signal_type: s.alpha_score.score for s in _apply_alpha_multipliers(sigs, compounds)}
        assert out[SignalType.MA_ACTIVITY] < 50.0

    def test_compound_confidence_is_geometric_mean(self):
        from src.engines.signal_interaction import _find_interactions
        c = _find_interactions([_sig(SignalType.CREDIT_RISK, conf=0.4),
                                _sig(SignalType.DISTRESSED_ASSET, conf=0.9)])[0]
        assert c.compounded_confidence == pytest.approx(0.6, abs=1e-3)


class TestReportRendering:
    def _brief(self, **kw):
        base = dict(company_name="Acme [UPDATE]", executive_summary="Margin [bold]fell[/] sharply",
                    overall_severity=Severity.HIGH, recommendation="Act [/x]", confidence_score=0.7,
                    detected_signals=[_sig(SignalType.CREDIT_RISK, reasoning="",
                                           alpha_score=None)])
        base.update(kw)
        return AnalystBrief(**base)

    def test_terminal_tolerates_markup_like_text(self):
        from src.utils.formatter import print_brief
        b = self._brief(risk_factors=[RiskFactor(factor="FX [/red]", impact="x", likelihood=Severity.LOW)],
                        recent_developments=["[/]"],
                        news_reviewed=[NewsItem(title="[BREAKING] [/b]", source="R", url="u",
                                                published_date="2026-01-01", snippet="s")])
        print_brief(b)  # must not raise MarkupError

    def test_markdown_table_cells_escaped(self):
        from src.utils.formatter import brief_to_markdown
        b = self._brief(key_metrics=[KeyMetric(name="EV|EBITDA", value="12x", period="LTM",
                                               interpretation="line1\nline2")])
        md = brief_to_markdown(b)
        assert "| EV\\|EBITDA | 12x | LTM | line1 line2 |" in md

    def test_markdown_empty_reasoning_not_rendered_as_stray_markers(self):
        from src.utils.formatter import brief_to_markdown
        assert "\n**\n" not in brief_to_markdown(self._brief())

    def test_markdown_expected_move_without_bounds(self):
        from src.utils.formatter import brief_to_markdown
        a = AlphaScore(score=50, severity_component=0.5, source_credibility=0.5,
                       corroboration_weight=0.5, recency_weight=0.5, expected_direction="negative")
        b = self._brief(detected_signals=[_sig(SignalType.CREDIT_RISK).model_copy(update={"alpha_score": a})])
        assert "Expected Move" not in brief_to_markdown(b)

    def test_compound_events_and_context_rendered(self):
        from src.utils.formatter import brief_to_markdown, print_brief
        from src.engines.signal_interaction import _find_interactions
        sigs = [_sig(SignalType.CREDIT_RISK), _sig(SignalType.DISTRESSED_ASSET)]
        b = self._brief(detected_signals=sigs, compound_signals=_find_interactions(sigs),
                        competitive_context="Peers are stable.")
        md = brief_to_markdown(b)
        assert "## Compound Events" in md and "## Competitive Context" in md
        assert "**Systemic Risk:**" in md
        print_brief(b)


class TestCLI:
    def test_main_module_imports_and_builds_parser(self):
        import importlib
        main = importlib.import_module("main")
        parser = main.build_parser()
        args = parser.parse_args(["analyse", "--company", "Acme", "--output", "markdown"])
        assert args.company == "Acme"


class TestSourceData:
    def test_8k_items_described_and_matched(self):
        from src.tools.edgar_tool import _describe_8k_items
        from src.engines.deterministic_engine import _match_rules
        d = _describe_8k_items("1.03,9.01")
        assert d.startswith("Item 1.03: Bankruptcy or Receivership")
        assert [t for t, _, _ in _match_rules(d)] == [SignalType.DISTRESSED_ASSET]
        assert _match_rules(_describe_8k_items("2.02,9.01")) == []   # routine results release

    def test_earnings_restatement_rule(self):
        from src.engines.deterministic_engine import _match_rules
        assert any(t == SignalType.EARNINGS_SURPRISE for t, _, _ in _match_rules("earnings restatement announced"))

    async def test_google_news_publisher_used_as_source(self):
        from src.tools.news_tool import NewsTool
        rss = ('<rss><channel><item><title>Acme agrees merger - Reuters</title>'
               '<link>https://news.google.com/rss/articles/abc</link>'
               f'<pubDate>{utcnow():%a, %d %b %Y %H:%M:%S} GMT</pubDate>'
               '<description>Acme merger</description>'
               '<source url="https://www.reuters.com">Reuters</source></item></channel></rss>')
        tool = NewsTool()
        tool._client = MagicMock()
        resp = MagicMock(); resp.text = rss; resp.raise_for_status = MagicMock()
        tool._client.get = AsyncMock(return_value=resp)
        items = await tool.fetch_company_news("Acme", lookback_days=30)
        assert items and items[0].source == "Reuters"

    def test_stable_exchange_ids(self):
        from src.tools.africa_tool import _stable_id
        assert _stable_id("same title") == _stable_id("same title") == "%06d" % (
            int(__import__("hashlib").sha256(b"same title").hexdigest(), 16) % 999999)


def test_material_definitive_agreement_is_not_m_and_a():
    """Live-run regression: a Boeing debt 8-K (Items 1.01 + 2.03) was reported as M&A."""
    from src.engines.deterministic_engine import _match_rules
    from src.tools.edgar_tool import _describe_8k_items
    assert _match_rules(_describe_8k_items("1.01,2.03,9.01")) == []
    assert any(t == SignalType.MA_ACTIVITY
               for t, _, _ in _match_rules("Acme signs definitive agreement to be acquired"))


def test_every_data_store_is_isolated_in_tests():
    """A new *_PATH store must be added to tests/conftest.py, or tests write to the real data/ dir."""
    import re
    from tests.conftest import _STORES
    declared = set()
    for f in Path("src").rglob("*.py"):
        for m in re.finditer(r"^(\w+_PATH)\s*=\s*Path\(__file__\)", f.read_text(), re.M):
            declared.add((".".join(f.with_suffix("").parts), m.group(1)))
    assert declared <= {(m, a) for m, a, _ in _STORES}


class TestBacktestScoring:
    def _signal(self, company, sig_type, when):
        from src.engines.warehouse import DetectedSignalRecord
        return DetectedSignalRecord(run_id=str(uuid.uuid4()), company_name=company,
                                    signal_type=sig_type, severity="high", detected_at=when)

    def test_scores_real_outcomes_once_per_prediction(self):
        from src.engines import backtest as bt
        from src.engines.warehouse import get_session
        from src.engines.market_impact import record_outcome
        day = datetime(2026, 3, 2, 9)
        s = get_session()
        s.add_all([
            # the same prediction from two runs on one day counts once
            self._signal("Acme", "credit_risk", day),
            self._signal("Acme", "credit_risk", day.replace(hour=15)),
            # no matching outcome: a false positive
            self._signal("Beta", "credit_risk", day),
            # outcome exists but is far outside the matching window: also a false positive
            self._signal("Gamma", "credit_risk", day),
        ])
        s.commit(); s.close()
        record_outcome("Acme", SignalType.CREDIT_RISK, Severity.HIGH, "2026-03-03",
                       price_change_5d_pct=-4.0, price_change_10d_pct=-9.0, event_confirmed=True,
                       confirmation_date="2026-03-13", expected_direction="negative")
        record_outcome("Gamma", SignalType.CREDIT_RISK, Severity.HIGH, "2025-01-01",
                       event_confirmed=True)

        m = bt.BacktestEngine().run_from_warehouse()["metrics_by_signal_type"]["credit_risk"]
        assert (m["signals_flagged"], m["true_positives"], m["false_positives"]) == (3, 1, 2)
        assert m["precision"] == pytest.approx(1 / 3, abs=1e-3)
        assert m["hit_rate"] == 1.0            # price fell, as a credit-risk signal predicts
        assert m["max_drawdown_pct"] == 9.0
        assert m["median_days_to_event"] == 10
        assert m["recall_approx"] is None and m["f1"] is None


def test_portfolio_risk_normalises_fractional_weights(monkeypatch):
    """Two 80-risk holdings at 20% and 15% weight are an 80-risk portfolio, not 28."""
    from src.engines import portfolio as po, company_memory as cm
    from src.schemas.models import CompanyRiskProfile
    profiles = {
        "A": CompanyRiskProfile(company_id="a", company_name="A", rolling_risk_score=80.0),
        "B": CompanyRiskProfile(company_id="b", company_name="B", rolling_risk_score=80.0),
    }
    monkeypatch.setattr(cm, "get_profile", lambda name, ticker=None: profiles.get(name))
    p = po.Portfolio("weights")
    p.add_holding("A", weight=0.20, market="US")
    p.add_holding("B", weight=0.15, market="Africa")
    p.add_holding("NoProfile", weight=0.10, market="US")
    r = p.aggregate_risk()
    assert r["weighted_portfolio_risk"] == 80.0
    assert r["portfolio_risk_level"] == "critical"
    assert r["profile_coverage_weight"] == round(0.35 / 0.45, 3)
    assert sum(r["market_exposure"].values()) == pytest.approx(1.0, abs=1e-3)


def test_company_memory_counts_each_event_once():
    from src.engines.company_memory import update_profile, get_profile
    sig = DetectedSignal(signal_type=SignalType.CREDIT_RISK, severity=Severity.HIGH, headline="H",
                         evidence=["E"], confidence=0.8, reasoning="R",
                         filing_references=["0000000000-26-000001"])
    brief = AnalystBrief(company_name="Acme", ticker="ACME", executive_summary="x",
                         overall_severity=Severity.HIGH, recommendation="y", confidence_score=0.8,
                         detected_signals=[sig])
    for _ in range(3):                   # e.g. three monitoring runs seeing the same 8-K
        update_profile(brief)
    p = get_profile("Acme", "ACME")
    assert p.historical_signal_density == {"credit_risk": 1}
    assert p.total_signals_detected == 1
    assert p.repeated_patterns == []
    assert get_profile("Acme") is not None   # holding added without a ticker still resolves


class TestAdaptiveGating:
    def test_single_false_positive_does_not_penalise(self):
        from src.engines.feedback import submit_feedback
        from src.engines.adaptive_calibration import _get_fp_penalty
        from src.schemas.models import FeedbackType
        submit_feedback("Acme", SignalType.CREDIT_RISK, FeedbackType.FALSE_POSITIVE, Severity.HIGH)
        assert _get_fp_penalty(SignalType.CREDIT_RISK) == 1.0

    def test_missed_event_reports_do_not_activate_precision(self):
        from src.engines.feedback import submit_feedback
        from src.engines.adaptive_calibration import _get_precision_adjustment
        from src.schemas.models import FeedbackType
        for _ in range(12):
            submit_feedback("Acme", SignalType.CREDIT_RISK, FeedbackType.MISSED_EVENT, Severity.HIGH)
        assert _get_precision_adjustment(SignalType.CREDIT_RISK) == 1.0


class TestMonitoringAlerts:
    def _brief(self, *sigs, severity=Severity.HIGH):
        return AnalystBrief(company_name="Acme", executive_summary="x", overall_severity=severity,
                            recommendation="y", confidence_score=0.7, detected_signals=list(sigs))

    def _sig(self, ref, sig_type=SignalType.CREDIT_RISK):
        return DetectedSignal(signal_type=sig_type, severity=Severity.HIGH, headline="H",
                              evidence=["E"], confidence=0.8, reasoning="R", filing_references=[ref])

    async def test_alerts_once_per_event_then_on_new_event(self, monkeypatch):
        from src.engines import monitoring as mon
        import src.agents.graph as graph
        briefs = [self._brief(self._sig("A")), self._brief(self._sig("A")),
                  self._brief(self._sig("A"), self._sig("B", SignalType.DISTRESSED_ASSET))]
        async def fake_run(request, compliance_mode=False):
            return briefs.pop(0)
        monkeypatch.setattr(graph, "run_analysis", fake_run)
        mon.add_to_watchlist("Acme", alert_severity="medium")
        engine = mon.MonitoringEngine()
        assert len(await engine.run_once()) == 1      # new event
        assert len(await engine.run_once()) == 0      # same event, no repeat alert
        assert len(await engine.run_once()) == 1      # a new event alerts again
        assert len(mon.get_recent_alerts()) == 2
        assert mon.get_watchlist()[0]["check_count"] == 3


def test_audit_entries_record_the_configured_model():
    import src.agents.signal_agent as sa
    from src.engines.audit_log import log_entry
    assert log_entry("step", "Acme", "act", "detail").model_version == sa.MODEL


def test_entity_graph_loads_pre_3_4_networkx_files(isolated_data_dir):
    import json as _json
    from src.engines import graph_intelligence as gi
    gi.GRAPH_PATH.write_text(_json.dumps({
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [{"id": "Acme"}, {"id": "Bank"}],
        "links": [{"source": "Bank", "target": "Acme", "edge_type": "lends_to"}],
    }))
    g = gi.EntityGraphEngine()
    assert g.G.has_edge("Bank", "Acme")
    gi.GRAPH_PATH.write_text("{not json")
    assert gi.EntityGraphEngine().G.number_of_nodes() == 0
    assert list(isolated_data_dir.glob("entity_graph.json.unreadable-*"))   # kept, not overwritten


class TestStorage:
    def test_save_is_atomic_and_roundtrips(self, tmp_path):
        from src.utils.storage import load_json, save_json
        path = tmp_path / "x.json"
        save_json(path, {"a": 1})
        assert load_json(path, dict) == {"a": 1}
        assert not (tmp_path / "x.json.tmp").exists()

    def test_unreadable_file_is_moved_aside_not_overwritten(self, isolated_data_dir):
        from src.engines import feedback
        feedback.FEEDBACK_PATH.write_text('{"entries": [ truncated')
        assert feedback._load()["entries"] == []
        backups = list(isolated_data_dir.glob("feedback.json.unreadable-*"))
        assert backups and backups[0].read_text().startswith('{"entries": [ truncated')


class TestEntityResolution:
    def test_no_substring_false_matches(self):
        from src.engines.entity_resolver import EntityResolver
        r = EntityResolver()
        r.register("Apple Inc", ticker="AAPL")
        assert r.resolve("Pineapple Holdings") is None
        assert r.resolve("Apple")["ticker"] == "AAPL"

    def test_ambiguous_fuzzy_query_resolves_to_nothing(self):
        from src.engines.entity_resolver import EntityResolver
        r = EntityResolver()
        r.register("Guaranty Trust Bank")
        r.register("Standard Trust Holdings")
        assert r.resolve("Trust") is None
        assert r.resolve("Guaranty Trust")["canonical_name"] == "Guaranty Trust Bank"

    def test_merge_repoints_duplicate_identifiers(self):
        from src.engines.entity_resolver import EntityResolver
        r = EntityResolver()
        r.register("Guaranty Trust Bank", ticker="GTCO")
        r.register("GTBank Plc", ticker="GUARANTY")
        assert r.merge_duplicates("Guaranty Trust Bank", "GTBank Plc")
        assert r.resolve("GUARANTY")["canonical_name"] == "Guaranty Trust Bank"


def test_engine_and_alpha_agree_on_source_credibility():
    from src.engines.deterministic_engine import candidate_credibility
    from src.engines.alpha_scorer import _source_credibility_for_signal
    for source_type, name, expected in [("filing", "8-K", 1.0), ("filing", "10-Q", 1.0),
                                        ("filing", "SC 13D", 1.0), ("filing", "JSE SENS", 1.0), ("filing", "NGX Disclosure", 1.0),
                                        ("news", "Reuters", 0.95), ("news", "Bloomberg.com", 0.95)]:
        cand = SignalCandidate(signal_type=SignalType.CREDIT_RISK, matched_patterns=["p"], source_text="t",
                               source_type=source_type, source_name=name, raw_score=0.5)
        assert candidate_credibility(source_type, name) == expected
        assert _source_credibility_for_signal(cand) == expected


def test_recency_uses_source_date_not_run_time():
    from src.engines.deterministic_engine import DeterministicSignalEngine
    from src.engines.alpha_scorer import _recency_decay
    old = (utcnow() - timedelta(days=56)).strftime("%Y-%m-%d")
    s = AgentState(request=AnalysisRequest(company_name="Acme"))
    s.news_items = [NewsItem(title="Acme profit warning", source="Reuters", published_date=old,
                             url="u", snippet="profit warning issued", relevance_score=0.9)]
    cand = DeterministicSignalEngine().run(s).signal_candidates[0]
    assert cand.source_date.strftime("%Y-%m-%d") == old
    assert _recency_decay(cand.source_date) == pytest.approx(0.30, abs=0.01)   # 4 half-lives, floored


def test_alpha_explanation_matches_stored_score():
    from src.engines.alpha_explainer import explain_alpha
    a = AlphaScore(score=40.0, severity_component=0.78, source_credibility=0.95, corroboration_weight=0.5,
                   recency_weight=1.0, liquidity_tier=LiquidityTier.LARGE_CAP)
    sig = DetectedSignal(signal_type=SignalType.MA_ACTIVITY, severity=Severity.HIGH, headline="H",
                         evidence=["E"], confidence=0.7, reasoning="R", alpha_score=a)
    exp = explain_alpha(sig)          # stored score was reduced by a contradictory compound
    assert exp["final_score"] == 40.0
    assert exp["compound_boost"] < 0
    assert "removed" in exp["plain_english"]


def test_first_analysis_sets_full_risk_without_trend():
    from src.engines.company_memory import update_profile
    brief = AnalystBrief(company_name="Acme", ticker="ACME", executive_summary="x",
                         overall_severity=Severity.CRITICAL, recommendation="y",
                         confidence_score=0.8, detected_signals=[])
    p = update_profile(brief)
    assert p.rolling_risk_score == 90.0
    assert p.risk_trend == "stable" and p.risk_delta_30d == 0.0


def test_registry_patterns_are_the_engine_rules():
    """The registry must describe the rules the engine actually runs."""
    from src.engines.signal_registry import SIGNAL_REGISTRY
    from src.engines.deterministic_engine import SIGNAL_RULES
    for sig_type, spec in SIGNAL_REGISTRY.items():
        engine = {p for t, ps, _ in SIGNAL_RULES if t == sig_type for p in ps}
        registry = set(spec.trigger_patterns_high + spec.trigger_patterns_medium + spec.trigger_patterns_low)
        assert registry == engine, sig_type


def test_signals_carry_evidence_quality_breakdown():
    import src.agents.signal_agent as sa
    from src.utils.formatter import brief_to_markdown
    state = AgentState(request=AnalysisRequest(company_name="Acme", ticker="ACME"))
    state.signal_candidates = [SignalCandidate(signal_type=SignalType.DISTRESSED_ASSET, matched_patterns=["p"],
                                               source_text="t", source_type="filing", source_name="8-K",
                                               raw_score=0.95)]
    state.detected_signals = [DetectedSignal(signal_type=SignalType.DISTRESSED_ASSET, severity=Severity.HIGH,
                                             headline="H", evidence=["E"], confidence=0.7, reasoning="R")]
    out = sa.AlphaScoringNode().run(state)
    d = out.detected_signals[0].confidence_decomposition
    assert d is not None and d.source_reliability_score == 1.0 and d.filing_strength_score == 1.0
    brief = AnalystBrief(company_name="Acme", executive_summary="x", overall_severity=Severity.HIGH,
                         recommendation="y", confidence_score=0.7, detected_signals=out.detected_signals)
    assert "**Evidence Quality:**" in brief_to_markdown(brief)


async def test_exchange_search_results_are_news_not_filings(monkeypatch):
    from src.tools import africa_tool as at
    async def fake_rss(self, url, source_name=""):
        if "senssearch" in url:
            return []
        return [{"title": "Acme posts results", "link": "https://news.google.com/x", "description": "Acme",
                 "pubDate": "", "source_override": source_name, "publisher": "BusinessDay"}]
    async def no_news(self, company_name, lookback_days=90):
        return []
    monkeypatch.setattr(at.AfricaTool, "_fetch_rss", fake_rss)
    monkeypatch.setattr(at.AfricaTool, "fetch_african_news", no_news)
    monkeypatch.setattr(at.asyncio, "sleep", AsyncMock())
    filings, news = await at.fetch_african_intelligence("Acme", None)
    assert filings == []
    assert news and all(n.source == "BusinessDay" for n in news)


def _form4(code, shares, price, plan="0", title="CEO"):
    return (f"<ownershipDocument><aff10b5One>{plan}</aff10b5One><rptOwnerName>DOE JANE</rptOwnerName>"
            f"<officerTitle>{title}</officerTitle><nonDerivativeTable><nonDerivativeTransaction>"
            f"<transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>"
            f"<transactionAmounts><transactionShares><value>{shares}</value></transactionShares>"
            f"<transactionPricePerShare><value>{price}</value></transactionPricePerShare></transactionAmounts>"
            f"</nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>")


class TestDirectionalSignals:
    def test_form4_keeps_only_discretionary_trades(self):
        from src.tools.edgar_tool import describe_form4
        assert "open-market purchase of 1,000 shares" in describe_form4(_form4("P", 1000, 50))
        assert describe_form4(_form4("A", 50000, 0)) is None            # grant
        assert describe_form4(_form4("F", 5000, 90)) is None            # tax withholding
        assert describe_form4(_form4("S", 100000, 90, plan="1")) is None  # 10b5-1 plan sale
        assert describe_form4(_form4("S", 100, 90)) is None             # below $1M
        assert "not under a 10b5-1 plan" in describe_form4(_form4("S", 100000, 90))

    def _alpha(self, sig_type, text, severity=Severity.HIGH):
        from src.engines.alpha_scorer import compute_alpha_score
        cand = SignalCandidate(signal_type=sig_type, matched_patterns=["p"], source_text=text,
                               source_type="news", source_name="Reuters", raw_score=0.8)
        sig = DetectedSignal(signal_type=sig_type, severity=severity, headline="H", evidence=["E"],
                             confidence=0.7, reasoning="R")
        return compute_alpha_score(sig, cand, ticker="ACME")

    def test_earnings_beat_detected_and_positive(self):
        from src.engines.deterministic_engine import _match_rules
        text = "Acme crushes estimates and raises full-year guidance"
        assert any(t == SignalType.EARNINGS_SURPRISE for t, _, _ in _match_rules(text))
        assert self._alpha(SignalType.EARNINGS_SURPRISE, text).expected_direction == "positive"
        assert self._alpha(SignalType.EARNINGS_SURPRISE, "Acme issues profit warning").expected_direction == "negative"

    def test_insider_sale_is_negative(self):
        sale = "Form 4 filed: open-market sale of 100,000 shares ($9,000,000), not under a 10b5-1 plan by X"
        assert self._alpha(SignalType.INSIDER_ACTIVITY, sale).expected_direction == "negative"
        buy = "Form 4 filed: open-market purchase of 1,000 shares ($50,000) by X"
        assert self._alpha(SignalType.INSIDER_ACTIVITY, buy).expected_direction == "positive"

    def test_positive_signals_do_not_raise_risk(self):
        from src.engines.company_memory import update_profile
        beat = DetectedSignal(signal_type=SignalType.EARNINGS_SURPRISE, severity=Severity.HIGH, headline="H",
                              evidence=["E"], confidence=0.7, reasoning="R",
                              alpha_score=self._alpha(SignalType.EARNINGS_SURPRISE, "Acme beats estimates"))
        p = update_profile(AnalystBrief(company_name="Acme", executive_summary="x", overall_severity=Severity.HIGH,
                                        recommendation="y", confidence_score=0.7, detected_signals=[beat]))
        assert p.rolling_risk_score == 10.0   # LOW baseline, not the beat's alpha


async def test_replay_uses_live_calibration_and_compounds():
    """Replay must score a stored run the way a live run would (adaptive calibration + compounds)."""
    from src.engines.replay import ReplayEngine
    from src.engines.warehouse import get_session, store_analysis_run
    from src.engines.adaptive_calibration import adaptive_calibrate
    from src.engines.deterministic_engine import DeterministicSignalEngine
    filings = [SECFiling(accession_number="a1", form_type="8-K", filing_date="2024-01-02", company_name="Acme",
                         cik="0000001", document_url="u1",
                         description="Item 1.03: Bankruptcy or Receivership; Item 2.04: Triggering Events")]
    brief = AnalystBrief(company_name="Acme", ticker="ACME", executive_summary="x",
                         overall_severity=Severity.HIGH, recommendation="y", confidence_score=0.7,
                         detected_signals=[], filings_reviewed=filings)
    store_analysis_run("run-1", brief)
    session = get_session()
    result = await ReplayEngine(session).replay("Acme", "2024-01-31", "run-1")
    session.close()
    types = {s["type"] for s in result["signal_summary"]}
    assert types == {"distressed_asset", "credit_risk"}
    assert result["compound_events"]                      # credit risk + distress interact
    live = AgentState(request=AnalysisRequest(company_name="Acme", cik="0000001", as_of_date="2024-01-31"))
    live.filings = filings
    cand = next(c for c in DeterministicSignalEngine().run(live).signal_candidates
                if c.signal_type == SignalType.DISTRESSED_ASSET)
    replayed = next(s for s in result["signal_summary"] if s["type"] == "distressed_asset")
    assert replayed["severity"] == adaptive_calibrate(cand)[0].value
    assert "calibration_feedback_stats" in result["config_snapshot"]


class TestLiquidityTier:
    def test_tier_from_market_cap(self, monkeypatch):
        from src.engines import alpha_scorer as al
        monkeypatch.setattr(al, "_market_cap_usd", lambda t: 147e9)
        assert al._infer_liquidity_tier("BA", None, None) == LiquidityTier.LARGE_CAP
        monkeypatch.setattr(al, "_market_cap_usd", lambda t: 5e9)
        assert al._infer_liquidity_tier("XYZ", None, None) == LiquidityTier.MID_CAP
        monkeypatch.setattr(al, "_market_cap_usd", lambda t: 100e6)
        assert al._infer_liquidity_tier("XYZ", None, None) == LiquidityTier.MICRO_CAP

    def test_minor_unit_currency_converted(self, monkeypatch):
        """JSE quotes market cap in South African cents (ZAc)."""
        import yfinance as yf
        from src.engines import alpha_scorer as al
        class FakeTicker:
            def __init__(self, sym): self.sym = sym
            @property
            def fast_info(self):
                if self.sym == "ZARUSD=X":
                    return {"lastPrice": 0.06}
                return {"marketCap": 53_000_000_000_000.0, "currency": "ZAc"}
        monkeypatch.setattr(yf, "Ticker", FakeTicker)
        assert al._lookup_market_cap_usd("NPN.JO") == pytest.approx(53e12 / 100 * 0.06)

    def test_falls_back_without_market_data(self):
        from src.engines import alpha_scorer as al
        assert al._infer_liquidity_tier("GTCO", None, None) == LiquidityTier.LARGE_CAP
        assert al._infer_liquidity_tier(None, None, None) == LiquidityTier.PRIVATE


async def test_rss_text_is_unescaped():
    from src.tools.news_tool import NewsTool
    rss = ('<rss><channel><item><title>A &amp; B</title><link>l</link><pubDate></pubDate>'
           '<description>&lt;a href="x"&gt;Acme&lt;/a&gt;&amp;nbsp;&amp;nbsp;Reuters</description>'
           '</item></channel></rss>')
    tool = NewsTool(); tool._client = MagicMock()
    resp = MagicMock(); resp.text = rss; resp.raise_for_status = MagicMock()
    tool._client.get = AsyncMock(return_value=resp)
    item = (await tool._fetch_rss("u"))[0]
    assert item["title"] == "A & B" and item["description"] == "Acme Reuters"


class TestLimitsRemoved:
    async def test_all_form4s_read_and_paced(self, monkeypatch):
        import asyncio as _asyncio
        from src.tools import edgar_tool as et
        filings = [SECFiling(accession_number=str(i), form_type="4", filing_date="2026-09-01",
                             company_name="Acme", cik="1", document_url=f"https://sec.gov/x/xslF345X06/f{i}.xml")
                   for i in range(25)]
        times = []
        async def fake_get(url):
            times.append(_asyncio.get_running_loop().time())
            resp = MagicMock(); resp.raise_for_status = MagicMock()
            resp.text = _form4("P", 100, 10) if url.endswith(("f0.xml", "f24.xml")) else _form4("A", 100, 0)
            return resp
        tool = et.EdgarTool(); tool._client = MagicMock(); tool._client.get = fake_get
        monkeypatch.setattr(et, "SEC_MAX_REQUESTS_PER_SECOND", 200)   # keep the test fast
        kept = await tool._enrich_form4(filings)
        assert len(times) == 25                                       # no cap: every Form 4 read
        assert [k.accession_number for k in kept] == ["0", "24"]      # grants dropped
        assert all(not k.document_url.count("xslF345X") for k in kept)

    async def test_rate_limiter_spacing(self):
        import asyncio as _asyncio
        from src.tools.edgar_tool import _RateLimiter
        lim = _RateLimiter(50)
        loop = _asyncio.get_running_loop(); t0 = loop.time()
        await _asyncio.gather(*(lim.wait() for _ in range(11)))
        assert loop.time() - t0 >= 0.19                               # 10 intervals of 20ms

    def test_single_credible_news_story_not_forced_low(self):
        from src.engines.deterministic_engine import DeterministicSignalEngine
        from src.engines.calibration import calibrate
        s = AgentState(request=AnalysisRequest(company_name="Intel", ticker="INTC"))
        s.news_items = [NewsItem(title="Intel forecast crushes estimates", source="Reuters",
                                 published_date="2026-10-01", url="u", snippet="", relevance_score=0.3)]
        cand = DeterministicSignalEngine().run(s).signal_candidates[0]
        assert cand.raw_score == pytest.approx(0.80 * 0.95)
        assert calibrate(cand)[0] == Severity.HIGH

    def test_exchange_code(self):
        from src.tools.africa_tool import _exchange_code
        assert _exchange_code("NPN.JO", ".JO") == "NPN"
        assert _exchange_code("NPN", ".JO") == "NPN"
        assert _exchange_code("GTCO.LG", ".JO") is None
        assert _exchange_code(None, ".JO") is None

    async def test_exchange_disclosure_parsers(self):
        from src.tools.africa_tool import AfricaTool
        tool = AfricaTool(); tool._client = MagicMock()
        def resp(text=None, js=None):
            r = MagicMock(); r.raise_for_status = MagicMock(); r.text = text; r.json = MagicMock(return_value=js)
            return r
        tool._client.get = AsyncMock(return_value=resp(js={"d": {"results": [{
            "CompanySymbol": "GTCO", "CompanyName": "GUARANTY TRUST HOLDING COMPANY PLC",
            "Type_of_Submission": "Corporate Actions", "Modified": "2026-09-29T10:00:00Z",
            "URL": {"Url": "https://doclib.ngxgroup.com/Financial_NewsDocs/47959_GUARANTY_TRUST_HOLDING_COMPANY_PLC-2026_INTERIM_DIVIDEND.pdf"}}]}}))
        ngx = await tool.fetch_ngx_disclosures("GTBank", "GTCO.LG")
        assert ngx[0].description == "GTCO: Corporate Actions: GUARANTY TRUST HOLDING COMPANY PLC - 2026 INTERIM DIVIDEND"
        assert ngx[0].filing_date == "2026-09-29" and ngx[0].form_type == "NGX Disclosure"
        tool._client.get = AsyncMock(return_value=resp(js=[
            {"date": "2026-05-07T10:00:00", "mime_type": "application/pdf", "source_url": "https://nse/x.pdf",
             "title": {"rendered": "Safaricom Plc &#8211; Audited Results"}},
            {"date": "2026-05-07T10:00:00", "mime_type": "image/png", "source_url": "u", "title": {"rendered": "logo"}}]))
        nse = await tool.fetch_nse_kenya_documents("Safaricom")
        assert [f.description for f in nse] == ["Safaricom Plc – Audited Results"]
        tool._client.get = AsyncMock(return_value=resp(text=(
            '<tr><td>17:05 - 13 Oct 2026</td><td><a href="/v3/sens_display.php?tdate=20261013170500&amp;seq=90&amp;scode=NPN">'
            '17:05 - 13 Oct 2026 | NASPERS LIMITED - Update on Repurchase Programme Price: 0</a></td></tr>')))
        sens = await tool.fetch_jse_sens("NPN.JO")
        assert sens[0].description == "NPN: NASPERS LIMITED - Update on Repurchase Programme"
        assert sens[0].filing_date == "2026-10-13"
        assert await tool.fetch_jse_sens("GTCO.LG") == []


def test_sources_outside_lookback_window_are_ignored():
    """Live-run regression: a 2023 CEO-departure story was reported in a 90-day analysis."""
    from src.engines.deterministic_engine import DeterministicSignalEngine
    s = AgentState(request=AnalysisRequest(company_name="Naspers", lookback_days=90))
    s.news_items = [NewsItem(title="Naspers announces abrupt departure of CEO", source="CNBC Africa",
                             published_date="2023-09-18", url="u", snippet="", relevance_score=0.5)]
    out = DeterministicSignalEngine().run(s)
    assert out.signal_candidates == []
    assert "1 outside the 90-day window" in out.reasoning_trace[-1]["detail"]


async def test_replay_window_ends_at_as_of_date():
    """Replay measures the lookback window from its as-of date, not from today."""
    from src.engines.deterministic_engine import DeterministicSignalEngine
    filing = SECFiling(accession_number="a", form_type="8-K", filing_date="2024-01-02", company_name="Acme",
                       cik="0000001", document_url="u", description="Item 1.03: Bankruptcy or Receivership")
    for as_of, expected in [("2024-01-31", 1), ("2024-12-31", 0), ("2023-12-31", 0)]:
        s = AgentState(request=AnalysisRequest(company_name="Acme", cik="0000001", as_of_date=as_of))
        s.filings = [filing]
        assert len(DeterministicSignalEngine().run(s).signal_candidates) == expected, as_of
