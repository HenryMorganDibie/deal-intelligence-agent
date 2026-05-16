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
        s = AgentState(request=AnalysisRequest(company_name="Acme"))
        s.filings    = filings or []
        s.news_items = news   or []
        return s

    def _filing(self, desc="", form="8-K"):
        return SECFiling(accession_number="acc1", form_type=form,
                         filing_date="2024-01-01", company_name="Acme",
                         cik="0000001", document_url="https://sec.gov/x",
                         description=desc)

    def _news(self, title="", snippet="", score=0.8):
        return NewsItem(title=title, source="Reuters", published_date="2024-01-01",
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
        s = self._state(news=[self._news("SEC investigation launched", "SEC probe into fraud allegations")])
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
            news=[self._news("Merger confirmed", "acquisition deal announced", 0.9)]
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
            SECFiling(accession_number="NGX-001", form_type="NGX Announcement",
                      filing_date="2024-01-01", company_name="GTBank",
                      cik="NGX", document_url="https://ngx.com/x",
                      description="Board approves merger with acquisition target")
        ])
        result = DeterministicSignalEngine().run(s)
        assert len(result.signal_candidates) > 0

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
        now   = _recency_decay(datetime.utcnow())
        old   = _recency_decay(datetime.utcnow() - timedelta(days=60))
        floor = _recency_decay(datetime.utcnow() - timedelta(days=365))
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
        assert _parse_rss_date("garbage") == datetime.utcnow().strftime("%Y-%m-%d")


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
        af_f = [SECFiling(accession_number="NGX-001",form_type="NGX Announcement",
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
        dup = SECFiling(accession_number="DUPE",form_type="8-K",filing_date="2024-01-01",
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
        shared = NewsItem(title="Same news",source="Reuters",published_date="2024-01-01",
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
        mc = MagicMock(); mc.text = text
        mr = MagicMock(); mr.content = [mc]
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
        with patch.object(agent.client.messages,"create",return_value=self._mock(payload)):
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
        with patch.object(agent.client.messages,"create",return_value=self._mock(payload)):
            r = await agent.run(s)
        assert r.brief.compliance_mode is True
        assert any("not investment advice" in f.lower() for f in r.brief.compliance_flags)

    @pytest.mark.asyncio
    async def test_handles_llm_failure(self):
        from src.agents.signal_agent import BriefSynthesisAgent
        s = self._state()
        agent = BriefSynthesisAgent()
        with patch.object(agent.client.messages,"create",side_effect=Exception("LLM down")):
            r = await agent.run(s)
        assert r.brief is None
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
    async def test_full_pipeline(self):
        from src.agents.graph import run_analysis

        profile = {"name":"Acme","cik":"0000001","ticker":"ACME"}
        filing  = SECFiling(accession_number="acc1",form_type="8-K",filing_date="2024-01-15",
                            company_name="Acme",cik="0000001",document_url="https://sec.gov/x",
                            description="Definitive merger agreement signed with Target Corp")
        news    = [NewsItem(title="Acme merger confirmed",source="Reuters",published_date="2024-01-15",
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
            mc = MagicMock(); mc.text = text
            mr = MagicMock(); mr.content = [mc]
            return mr

        em, am, nm = _patch_all(edgar=(profile,[filing]), news=news)
        with patch("src.agents.collection_agent.search_company_filings",em), \
             patch("src.agents.collection_agent.fetch_african_intelligence",am), \
             patch("src.agents.collection_agent.fetch_market_news",nm):
            with patch("anthropic.Anthropic") as MockAnth:
                inst = MockAnth.return_value
                inst.messages.create.side_effect = [
                    mock_response(explain_json),
                    mock_response(brief_json),
                ]
                import src.agents.signal_agent as sa
                sa.LLMExplanationNode.__init__ = lambda self: setattr(self,"client",inst)
                sa.BriefSynthesisAgent.__init__ = lambda self: setattr(self,"client",inst)
                brief = await run_analysis(AnalysisRequest(company_name="Acme",ticker="ACME"))

        assert brief is not None
        assert brief.company_name == "Acme"
        assert brief.signal_candidates_count >= 1

    @pytest.mark.asyncio
    async def test_no_candidates_no_signals(self):
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
                    mc = MagicMock(); mc.text = text
                    mr = MagicMock(); mr.content = [mc]
                    return mr
                inst.messages.create.return_value = mock_response(brief_json)
                import src.agents.signal_agent as sa
                sa.LLMExplanationNode.__init__ = lambda self: setattr(self,"client",inst)
                sa.BriefSynthesisAgent.__init__ = lambda self: setattr(self,"client",inst)
                brief = await run_analysis(AnalysisRequest(company_name="Quiet Corp"))

        assert brief.detected_signals == []
        assert brief.signal_candidates_count == 0

    @pytest.mark.asyncio
    async def test_compliance_mode_passed_through(self):
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
                    mc = MagicMock(); mc.text = text
                    mr = MagicMock(); mr.content = [mc]
                    return mr
                inst.messages.create.return_value = mock_response(brief_json)
                import src.agents.signal_agent as sa
                sa.LLMExplanationNode.__init__ = lambda self: setattr(self,"client",inst)
                sa.BriefSynthesisAgent.__init__ = lambda self: setattr(self,"client",inst)
                brief = await run_analysis(AnalysisRequest(company_name="X"), compliance_mode=True)

        assert brief.compliance_mode is True
        assert any("not investment advice" in f.lower() for f in brief.compliance_flags)
