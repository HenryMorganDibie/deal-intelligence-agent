"""
Comprehensive test suite for the Deal Intelligence Agent.
Covers: schemas, tools (mocked), agents (mocked), graph, formatter, edge cases.
Run with: pytest tests/test_all.py -v
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── Schemas ──────────────────────────────────────────────────────────────────

from src.schemas.models import (
    AnalysisRequest, AgentState, AnalystBrief, DetectedSignal,
    SECFiling, NewsItem, CompanyProfile, RiskFactor, KeyMetric,
    SignalType, Severity, FilingType
)


class TestAnalysisRequest:
    def test_basic_creation(self):
        req = AnalysisRequest(company_name="Apple Inc", ticker="AAPL")
        assert req.company_name == "Apple Inc"
        assert req.ticker == "AAPL"
        assert req.lookback_days == 90
        assert req.depth == "standard"

    def test_ticker_normalised_to_uppercase(self):
        req = AnalysisRequest(company_name="Test", ticker="aapl")
        assert req.ticker == "AAPL"

    def test_ticker_whitespace_stripped(self):
        req = AnalysisRequest(company_name="Test", ticker="  MSFT  ")
        assert req.ticker == "MSFT"

    def test_no_ticker(self):
        req = AnalysisRequest(company_name="Acme Corp")
        assert req.ticker is None

    def test_lookback_days_bounds(self):
        with pytest.raises(Exception):
            AnalysisRequest(company_name="Test", lookback_days=0)
        with pytest.raises(Exception):
            AnalysisRequest(company_name="Test", lookback_days=366)

    def test_depth_validation(self):
        for valid in ("quick", "standard", "deep"):
            req = AnalysisRequest(company_name="Test", depth=valid)
            assert req.depth == valid
        with pytest.raises(Exception):
            AnalysisRequest(company_name="Test", depth="extreme")

    def test_focus_signals(self):
        req = AnalysisRequest(
            company_name="Test",
            focus_signals=[SignalType.MA_ACTIVITY, SignalType.CREDIT_RISK]
        )
        assert len(req.focus_signals) == 2

    def test_empty_focus_signals_default(self):
        req = AnalysisRequest(company_name="Test")
        assert req.focus_signals == []


class TestDetectedSignal:
    def _make_signal(self, **kwargs) -> DetectedSignal:
        defaults = dict(
            signal_type=SignalType.MA_ACTIVITY,
            severity=Severity.HIGH,
            headline="Test acquisition signal",
            evidence=["Evidence A", "Evidence B"],
            confidence=0.85,
            reasoning="Because X happened and Y followed."
        )
        defaults.update(kwargs)
        return DetectedSignal(**defaults)

    def test_creation(self):
        sig = self._make_signal()
        assert sig.signal_type == SignalType.MA_ACTIVITY
        assert sig.severity == Severity.HIGH
        assert sig.confidence == 0.85

    def test_confidence_clamped(self):
        with pytest.raises(Exception):
            self._make_signal(confidence=1.5)
        with pytest.raises(Exception):
            self._make_signal(confidence=-0.1)

    def test_default_timestamps(self):
        sig = self._make_signal()
        assert isinstance(sig.detected_at, datetime)

    def test_empty_evidence_list(self):
        sig = self._make_signal(evidence=[])
        assert sig.evidence == []


class TestAnalystBrief:
    def _make_brief(self, signals=None) -> AnalystBrief:
        return AnalystBrief(
            company_name="Acme Corp",
            ticker="ACME",
            executive_summary="Acme shows M&A signals.",
            overall_severity=Severity.HIGH,
            recommendation="Flag for review.",
            confidence_score=0.78,
            detected_signals=signals or [],
        )

    def test_creation(self):
        brief = self._make_brief()
        assert brief.company_name == "Acme Corp"
        assert brief.ticker == "ACME"

    def test_signal_count_by_severity(self):
        signals = [
            DetectedSignal(signal_type=SignalType.MA_ACTIVITY, severity=Severity.HIGH,
                           headline="H1", evidence=[], confidence=0.9, reasoning="R"),
            DetectedSignal(signal_type=SignalType.CREDIT_RISK, severity=Severity.HIGH,
                           headline="H2", evidence=[], confidence=0.8, reasoning="R"),
            DetectedSignal(signal_type=SignalType.DISTRESSED_ASSET, severity=Severity.CRITICAL,
                           headline="H3", evidence=[], confidence=0.95, reasoning="R"),
        ]
        brief = self._make_brief(signals=signals)
        counts = brief.signal_count_by_severity()
        assert counts["high"] == 2
        assert counts["critical"] == 1
        assert counts["low"] == 0

    def test_top_signals_ordering(self):
        signals = [
            DetectedSignal(signal_type=SignalType.MA_ACTIVITY, severity=Severity.LOW,
                           headline="Low", evidence=[], confidence=0.5, reasoning="R"),
            DetectedSignal(signal_type=SignalType.CREDIT_RISK, severity=Severity.CRITICAL,
                           headline="Crit", evidence=[], confidence=0.95, reasoning="R"),
            DetectedSignal(signal_type=SignalType.REGULATORY_ACTION, severity=Severity.HIGH,
                           headline="High", evidence=[], confidence=0.75, reasoning="R"),
        ]
        brief = self._make_brief(signals=signals)
        top = brief.top_signals(n=2)
        assert top[0].severity == Severity.CRITICAL
        assert top[1].severity == Severity.HIGH

    def test_top_signals_capped(self):
        signals = [
            DetectedSignal(signal_type=SignalType.MA_ACTIVITY, severity=Severity.HIGH,
                           headline=f"S{i}", evidence=[], confidence=0.8, reasoning="R")
            for i in range(5)
        ]
        brief = self._make_brief(signals=signals)
        assert len(brief.top_signals(n=2)) == 2

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            self._make_brief()
            AnalystBrief(
                company_name="X", executive_summary="E", overall_severity=Severity.LOW,
                recommendation="R", confidence_score=1.5, detected_signals=[]
            )


class TestAgentState:
    def test_log_appends_trace(self):
        state = AgentState(request=AnalysisRequest(company_name="Test"))
        state.log("step_a", "Did something", {"key": "val"})
        assert len(state.reasoning_trace) == 1
        assert state.reasoning_trace[0]["step"] == "step_a"
        assert state.current_step == "step_a"

    def test_multiple_logs(self):
        state = AgentState(request=AnalysisRequest(company_name="Test"))
        state.log("step_a", "A")
        state.log("step_b", "B")
        assert len(state.reasoning_trace) == 2
        assert state.current_step == "step_b"

    def test_initial_state(self):
        req = AnalysisRequest(company_name="Test Co", ticker="TC")
        state = AgentState(request=req)
        assert state.filings == []
        assert state.news_items == []
        assert state.detected_signals == []
        assert state.brief is None
        assert state.errors == []
        assert state.retry_count == 0


# ─── Tools ────────────────────────────────────────────────────────────────────

class TestEdgarTool:
    @pytest.mark.asyncio
    async def test_score_relevance_import(self):
        from src.tools.news_tool import _score_relevance
        score = _score_relevance("Apple acquires startup", "merger deal announced", "Apple")
        assert score > 0.3  # company mention + M&A keyword

    @pytest.mark.asyncio
    async def test_score_relevance_no_match(self):
        from src.tools.news_tool import _score_relevance
        score = _score_relevance("Weather forecast sunny", "no relevant content", "Acme Corp")
        assert score < 0.2

    def test_extract_source_known_domain(self):
        from src.tools.news_tool import _extract_source
        assert _extract_source("https://www.reuters.com/article/test") == "Reuters"
        assert _extract_source("https://www.bloomberg.com/news/test") == "Bloomberg"
        assert _extract_source("https://www.wsj.com/articles/test") == "Wall Street Journal"

    def test_extract_source_unknown_domain(self):
        from src.tools.news_tool import _extract_source
        result = _extract_source("https://www.somesite.com/article")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_extract_source_invalid_url(self):
        from src.tools.news_tool import _extract_source
        result = _extract_source("not-a-url")
        assert result == "Unknown"

    def test_parse_rss_date_formats(self):
        from src.tools.news_tool import _parse_rss_date
        # Standard RSS format
        result = _parse_rss_date("Mon, 12 May 2025 14:30:00 GMT")
        assert result == "2025-05-12"

    def test_parse_rss_date_invalid_fallback(self):
        from src.tools.news_tool import _parse_rss_date
        result = _parse_rss_date("not a date at all")
        # Should return today's date as fallback
        assert result == datetime.utcnow().strftime("%Y-%m-%d")

    @pytest.mark.asyncio
    async def test_edgar_tool_context_manager(self):
        from src.tools.edgar_tool import EdgarTool
        async with EdgarTool() as edgar:
            assert edgar._client is not None
        assert edgar._client.is_closed

    @pytest.mark.asyncio
    async def test_edgar_tool_no_client_raises(self):
        from src.tools.edgar_tool import EdgarTool
        edgar = EdgarTool()
        with pytest.raises(RuntimeError, match="async context manager"):
            _ = edgar.client

    @pytest.mark.asyncio
    async def test_edgar_resolve_no_cik_returns_safe(self):
        """If EDGAR is unreachable, resolve_company returns safe fallback."""
        from src.tools.edgar_tool import EdgarTool
        async with EdgarTool() as edgar:
            with patch.object(edgar.client, "get", side_effect=Exception("network error")):
                result = await edgar.resolve_company("Nonexistent Corp XYZ123")
                assert isinstance(result, dict)
                assert "name" in result

    @pytest.mark.asyncio
    async def test_edgar_filings_empty_cik_returns_empty(self):
        from src.tools.edgar_tool import EdgarTool
        async with EdgarTool() as edgar:
            result = await edgar.get_recent_filings("")
            assert result == []

    @pytest.mark.asyncio
    async def test_edgar_extract_text_bad_url_returns_empty(self):
        from src.tools.edgar_tool import EdgarTool, SECFiling
        async with EdgarTool() as edgar:
            filing = SECFiling(
                accession_number="0001",
                form_type="8-K",
                filing_date="2024-01-01",
                company_name="Test",
                cik="0000001",
                document_url="https://httpbin.org/status/404"
            )
            result = await edgar.extract_filing_text(filing)
            assert result == ""


# ─── Agent Parsing Logic ───────────────────────────────────────────────────────

class TestSignalParser:
    def _make_state(self) -> AgentState:
        return AgentState(request=AnalysisRequest(company_name="Test"))

    def test_valid_signal_json(self):
        from src.agents.signal_agent import _parse_signals_from_response
        state = self._make_state()
        payload = json.dumps({"signals": [{
            "signal_type": "m_and_a_activity",
            "severity": "high",
            "headline": "Target acquired",
            "evidence": ["Filing shows acquisition", "CEO confirmed deal"],
            "source_urls": ["https://sec.gov/test"],
            "filing_references": ["0001234567-24-000001"],
            "confidence": 0.92,
            "reasoning": "SEC 8-K filed citing definitive merger agreement."
        }]})
        signals = _parse_signals_from_response(payload, state)
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.MA_ACTIVITY
        assert signals[0].severity == Severity.HIGH
        assert signals[0].confidence == 0.92

    def test_empty_signals_list(self):
        from src.agents.signal_agent import _parse_signals_from_response
        state = self._make_state()
        signals = _parse_signals_from_response('{"signals": []}', state)
        assert signals == []

    def test_markdown_fenced_json_stripped(self):
        from src.agents.signal_agent import _parse_signals_from_response
        state = self._make_state()
        payload = '```json\n{"signals": []}\n```'
        signals = _parse_signals_from_response(payload, state)
        assert signals == []

    def test_invalid_json_logs_error(self):
        from src.agents.signal_agent import _parse_signals_from_response
        state = self._make_state()
        signals = _parse_signals_from_response("not json at all {{{{", state)
        assert signals == []
        assert len(state.errors) >= 1

    def test_unknown_signal_type_mapped(self):
        from src.agents.signal_agent import _parse_signals_from_response
        state = self._make_state()
        payload = json.dumps({"signals": [{
            "signal_type": "merger_deal",  # non-standard
            "severity": "medium",
            "headline": "Deal spotted",
            "evidence": ["X"],
            "confidence": 0.6,
            "reasoning": "R"
        }]})
        signals = _parse_signals_from_response(payload, state)
        assert len(signals) == 1  # mapped to best-effort type

    def test_confidence_clamped_by_parser(self):
        from src.agents.signal_agent import _parse_signals_from_response
        state = self._make_state()
        payload = json.dumps({"signals": [{
            "signal_type": "credit_risk",
            "severity": "low",
            "headline": "Test",
            "evidence": [],
            "confidence": 99.9,  # out of range
            "reasoning": "R"
        }]})
        signals = _parse_signals_from_response(payload, state)
        assert len(signals) == 1
        assert signals[0].confidence <= 1.0

    def test_partial_signal_skipped(self):
        from src.agents.signal_agent import _parse_signals_from_response
        state = self._make_state()
        payload = json.dumps({"signals": [
            {  # valid
                "signal_type": "credit_risk",
                "severity": "high",
                "headline": "Valid signal",
                "evidence": ["E"],
                "confidence": 0.7,
                "reasoning": "R"
            },
            {  # missing required fields — should be skipped gracefully
                "signal_type": "credit_risk"
            }
        ]})
        signals = _parse_signals_from_response(payload, state)
        # At least the valid one should parse
        assert any(s.headline == "Valid signal" for s in signals)


# ─── Context Builders ─────────────────────────────────────────────────────────

class TestContextBuilders:
    def test_filing_context_truncates(self):
        from src.agents.signal_agent import _build_filing_context
        filings = [
            SECFiling(
                accession_number=f"acc-{i}",
                form_type="8-K",
                filing_date="2024-01-01",
                company_name="Test Corp",
                cik="0000001",
                document_url="https://sec.gov/test",
                description="Test filing",
                raw_excerpt="X" * 600
            )
            for i in range(50)
        ]
        result = _build_filing_context(filings, max_chars=5000)
        assert len(result) <= 5200  # small buffer for formatting

    def test_news_context_sorts_by_relevance(self):
        from src.agents.signal_agent import _build_news_context
        news = [
            NewsItem(title="Low relevance", source="S", published_date="2024-01-01",
                     url="http://x.com", snippet="nothing", relevance_score=0.1),
            NewsItem(title="High relevance", source="S", published_date="2024-01-01",
                     url="http://y.com", snippet="acquisition merger deal", relevance_score=0.9),
        ]
        result = _build_news_context(news)
        assert result.index("High relevance") < result.index("Low relevance")

    def test_empty_filings_returns_placeholder(self):
        from src.agents.signal_agent import _build_filing_context
        result = _build_filing_context([])
        assert "No filings" in result

    def test_empty_news_returns_placeholder(self):
        from src.agents.signal_agent import _build_news_context
        result = _build_news_context([])
        assert "No news" in result


# ─── Formatter ────────────────────────────────────────────────────────────────

class TestFormatter:
    def _make_full_brief(self) -> AnalystBrief:
        signal = DetectedSignal(
            signal_type=SignalType.MA_ACTIVITY,
            severity=Severity.HIGH,
            headline="Potential acquisition of Acme Corp",
            evidence=["8-K filed citing LOI", "CEO confirmed talks"],
            source_urls=["https://sec.gov/test"],
            filing_references=["0001234567-24-000001"],
            confidence=0.88,
            reasoning="Multiple corroborating sources indicate active deal process."
        )
        return AnalystBrief(
            company_name="Acme Corp",
            ticker="ACME",
            executive_summary="Acme Corp shows strong M&A signals following 8-K filings.",
            overall_severity=Severity.HIGH,
            recommendation="Recommend immediate position review and buy-side diligence.",
            confidence_score=0.85,
            detected_signals=[signal],
            key_metrics=[KeyMetric(name="Revenue", value="$2.1B", period="FY2023", interpretation="Stable growth")],
            risk_factors=[RiskFactor(factor="Regulatory hurdle", impact="Deal blocked", likelihood=Severity.MEDIUM)],
            recent_developments=["Activist investor filed 13D", "Board formed special committee"],
            total_sources=12,
            processing_time_seconds=18.4
        )

    def test_json_serialisation(self):
        from src.utils.formatter import brief_to_json
        brief = self._make_full_brief()
        result = brief_to_json(brief)
        parsed = json.loads(result)
        assert parsed["company_name"] == "Acme Corp"
        assert parsed["ticker"] == "ACME"
        assert len(parsed["detected_signals"]) == 1

    def test_markdown_contains_key_sections(self):
        from src.utils.formatter import brief_to_markdown
        brief = self._make_full_brief()
        md = brief_to_markdown(brief)
        assert "# Deal Intelligence Brief" in md
        assert "## Executive Summary" in md
        assert "## Detected Signals" in md
        assert "## Key Metrics" in md
        assert "## Risk Factors" in md
        assert "Acme Corp" in md
        assert "ACME" in md

    def test_markdown_includes_signals(self):
        from src.utils.formatter import brief_to_markdown
        brief = self._make_full_brief()
        md = brief_to_markdown(brief)
        assert "Potential acquisition of Acme Corp" in md

    def test_print_brief_no_crash(self, capsys):
        from src.utils.formatter import print_brief
        brief = self._make_full_brief()
        print_brief(brief)  # Should not raise

    def test_json_roundtrip(self):
        from src.utils.formatter import brief_to_json
        from src.schemas.models import AnalystBrief
        brief = self._make_full_brief()
        json_str = brief_to_json(brief)
        data = json.loads(json_str)
        # Re-validate the JSON is schema-compliant
        restored = AnalystBrief.model_validate(data)
        assert restored.company_name == brief.company_name
        assert len(restored.detected_signals) == len(brief.detected_signals)


# ─── Data Collection Agent ────────────────────────────────────────────────────

def _patch_collection(edgar_return=None, africa_return=None, news_return=None,
                      edgar_exc=None, africa_exc=None, news_exc=None):
    """Helper: patch all three collection sources cleanly."""
    edgar_mock  = AsyncMock(side_effect=edgar_exc)  if edgar_exc  else AsyncMock(return_value=edgar_return  or ({"name": "Test"}, []))
    africa_mock = AsyncMock(side_effect=africa_exc) if africa_exc else AsyncMock(return_value=africa_return or ([], []))
    news_mock   = AsyncMock(side_effect=news_exc)   if news_exc   else AsyncMock(return_value=news_return   or [])
    return edgar_mock, africa_mock, news_mock


class TestDataCollectionAgent:
    @pytest.mark.asyncio
    async def test_populates_state_on_success(self):
        from src.agents.collection_agent import DataCollectionAgent

        mock_profile  = {"name": "Apple Inc", "cik": "0000320193", "ticker": "AAPL"}
        mock_us_filings = [
            SECFiling(accession_number="acc1", form_type="8-K", filing_date="2024-01-15",
                      company_name="Apple Inc", cik="0000320193", document_url="https://sec.gov/x")
        ]
        mock_africa_filings = [
            SECFiling(accession_number="NGX-001", form_type="NGX Announcement",
                      filing_date="2024-01-10", company_name="Apple Inc",
                      cik="NGX", document_url="https://ngxgroup.com/x")
        ]
        mock_africa_news = [
            NewsItem(title="Apple expands to Nigeria", source="BusinessDay Nigeria",
                     published_date="2024-01-08", url="https://businessday.ng/x",
                     snippet="Expansion announced", relevance_score=0.75)
        ]
        mock_global_news = [
            NewsItem(title="Apple acquires startup", source="Reuters",
                     published_date="2024-01-10", url="https://reuters.com/x",
                     snippet="Deal announced", relevance_score=0.9)
        ]

        edgar_mock, africa_mock, news_mock = _patch_collection(
            edgar_return=(mock_profile, mock_us_filings),
            africa_return=(mock_africa_filings, mock_africa_news),
            news_return=mock_global_news,
        )
        with patch("src.agents.collection_agent.search_company_filings", new=edgar_mock), \
             patch("src.agents.collection_agent.fetch_african_intelligence", new=africa_mock), \
             patch("src.agents.collection_agent.fetch_market_news", new=news_mock):
            state = AgentState(request=AnalysisRequest(company_name="Apple Inc", ticker="AAPL"))
            result = await DataCollectionAgent().run(state)

        assert result.company_profile is not None
        assert result.company_profile.name == "Apple Inc"
        assert result.company_profile.cik == "0000320193"
        # US + African filings merged
        assert len(result.filings) == 2
        form_types = {f.form_type for f in result.filings}
        assert "8-K" in form_types
        assert "NGX Announcement" in form_types
        # Global + African news merged and sorted
        assert len(result.news_items) == 2
        assert result.news_items[0].relevance_score >= result.news_items[1].relevance_score

    @pytest.mark.asyncio
    async def test_handles_edgar_failure_gracefully(self):
        from src.agents.collection_agent import DataCollectionAgent

        edgar_mock, africa_mock, news_mock = _patch_collection(edgar_exc=Exception("EDGAR down"))
        with patch("src.agents.collection_agent.search_company_filings", new=edgar_mock), \
             patch("src.agents.collection_agent.fetch_african_intelligence", new=africa_mock), \
             patch("src.agents.collection_agent.fetch_market_news", new=news_mock):
            state = AgentState(request=AnalysisRequest(company_name="Test Corp"))
            result = await DataCollectionAgent().run(state)

        assert any("EDGAR" in e for e in result.errors)
        assert result.company_profile is not None  # Falls back to request data

    @pytest.mark.asyncio
    async def test_handles_africa_failure_gracefully(self):
        from src.agents.collection_agent import DataCollectionAgent

        edgar_mock, africa_mock, news_mock = _patch_collection(
            edgar_return=({"name": "GTBank"}, []),
            africa_exc=Exception("Africa tool down"),
        )
        with patch("src.agents.collection_agent.search_company_filings", new=edgar_mock), \
             patch("src.agents.collection_agent.fetch_african_intelligence", new=africa_mock), \
             patch("src.agents.collection_agent.fetch_market_news", new=news_mock):
            state = AgentState(request=AnalysisRequest(company_name="GTBank"))
            result = await DataCollectionAgent().run(state)

        assert any("Africa" in e for e in result.errors)
        assert result.filings == []      # no US or African filings
        assert result.news_items == []   # no news either (news_mock returns [])

    @pytest.mark.asyncio
    async def test_handles_news_failure_gracefully(self):
        from src.agents.collection_agent import DataCollectionAgent

        edgar_mock, africa_mock, news_mock = _patch_collection(
            edgar_return=({"name": "Test"}, []),
            news_exc=Exception("RSS down"),
        )
        with patch("src.agents.collection_agent.search_company_filings", new=edgar_mock), \
             patch("src.agents.collection_agent.fetch_african_intelligence", new=africa_mock), \
             patch("src.agents.collection_agent.fetch_market_news", new=news_mock):
            state = AgentState(request=AnalysisRequest(company_name="Test Corp"))
            result = await DataCollectionAgent().run(state)

        assert any("News" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_deduplicates_filings_across_sources(self):
        """Same accession number from both US and Africa shouldn't appear twice."""
        from src.agents.collection_agent import DataCollectionAgent

        duplicate_filing = SECFiling(
            accession_number="DUPE-001", form_type="8-K", filing_date="2024-01-15",
            company_name="Test", cik="0000001", document_url="https://sec.gov/x"
        )
        edgar_mock, africa_mock, news_mock = _patch_collection(
            edgar_return=({"name": "Test"}, [duplicate_filing]),
            africa_return=([duplicate_filing], []),
        )
        with patch("src.agents.collection_agent.search_company_filings", new=edgar_mock), \
             patch("src.agents.collection_agent.fetch_african_intelligence", new=africa_mock), \
             patch("src.agents.collection_agent.fetch_market_news", new=news_mock):
            state = AgentState(request=AnalysisRequest(company_name="Test"))
            result = await DataCollectionAgent().run(state)

        assert len(result.filings) == 1  # deduplicated

    @pytest.mark.asyncio
    async def test_deduplicates_news_across_sources(self):
        """Same headline from global + African feeds should appear only once."""
        from src.agents.collection_agent import DataCollectionAgent

        shared_news = NewsItem(
            title="Big merger announced", source="Reuters",
            published_date="2024-01-10", url="https://reuters.com/x",
            snippet="Deal confirmed", relevance_score=0.9
        )
        edgar_mock, africa_mock, news_mock = _patch_collection(
            edgar_return=({"name": "Test"}, []),
            africa_return=([], [shared_news]),
            news_return=[shared_news],
        )
        with patch("src.agents.collection_agent.search_company_filings", new=edgar_mock), \
             patch("src.agents.collection_agent.fetch_african_intelligence", new=africa_mock), \
             patch("src.agents.collection_agent.fetch_market_news", new=news_mock):
            state = AgentState(request=AnalysisRequest(company_name="Test"))
            result = await DataCollectionAgent().run(state)

        assert len(result.news_items) == 1  # deduplicated

    @pytest.mark.asyncio
    async def test_news_sorted_by_relevance_after_merge(self):
        from src.agents.collection_agent import DataCollectionAgent

        low  = NewsItem(title="Low item",  source="S", published_date="2024-01-01",
                        url="http://a.com", snippet="x", relevance_score=0.2)
        high = NewsItem(title="High item", source="S", published_date="2024-01-01",
                        url="http://b.com", snippet="x", relevance_score=0.9)
        edgar_mock, africa_mock, news_mock = _patch_collection(
            edgar_return=({"name": "Test"}, []),
            africa_return=([], [low]),
            news_return=[high],
        )
        with patch("src.agents.collection_agent.search_company_filings", new=edgar_mock), \
             patch("src.agents.collection_agent.fetch_african_intelligence", new=africa_mock), \
             patch("src.agents.collection_agent.fetch_market_news", new=news_mock):
            state = AgentState(request=AnalysisRequest(company_name="Test"))
            result = await DataCollectionAgent().run(state)

        assert result.news_items[0].relevance_score == 0.9
        assert result.news_items[1].relevance_score == 0.2

    @pytest.mark.asyncio
    async def test_logs_trace_entry(self):
        from src.agents.collection_agent import DataCollectionAgent

        edgar_mock, africa_mock, news_mock = _patch_collection()
        with patch("src.agents.collection_agent.search_company_filings", new=edgar_mock), \
             patch("src.agents.collection_agent.fetch_african_intelligence", new=africa_mock), \
             patch("src.agents.collection_agent.fetch_market_news", new=news_mock):
            state = AgentState(request=AnalysisRequest(company_name="Test"))
            result = await DataCollectionAgent().run(state)

        dc_logs = [t for t in result.reasoning_trace if t["step"] == "data_collection"]
        assert len(dc_logs) >= 1
        # The final data_collection log contains the collection summary with counts
        summary_log = dc_logs[-1]
        assert "US:" in summary_log["detail"]
        assert "Africa:" in summary_log["detail"]


# ─── Signal Detection Agent ───────────────────────────────────────────────────

class TestSignalDetectionAgent:
    def _make_populated_state(self) -> AgentState:
        state = AgentState(request=AnalysisRequest(company_name="Acme Corp", ticker="ACME"))
        state.company_profile = CompanyProfile(name="Acme Corp", ticker="ACME", cik="0000001")
        state.filings = [
            SECFiling(accession_number="acc1", form_type="8-K", filing_date="2024-01-01",
                      company_name="Acme Corp", cik="0000001",
                      document_url="https://sec.gov/x",
                      description="Material definitive agreement — merger")
        ]
        state.news_items = [
            NewsItem(title="Acme to be acquired", source="Reuters", published_date="2024-01-01",
                     url="https://reuters.com/x", snippet="Merger announced", relevance_score=0.95)
        ]
        return state

    @pytest.mark.asyncio
    async def test_calls_claude_and_parses_signals(self):
        from src.agents.signal_agent import SignalDetectionAgent

        mock_response_text = json.dumps({"signals": [{
            "signal_type": "m_and_a_activity",
            "severity": "critical",
            "headline": "Definitive merger agreement filed",
            "evidence": ["8-K cites definitive agreement", "Reuters confirms deal"],
            "source_urls": ["https://reuters.com/x"],
            "filing_references": ["acc1"],
            "confidence": 0.96,
            "reasoning": "Both the SEC filing and news corroborate active M&A."
        }]})

        mock_content = MagicMock()
        mock_content.text = mock_response_text
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        state = self._make_populated_state()
        agent = SignalDetectionAgent()

        with patch.object(agent.client.messages, "create", return_value=mock_response):
            result = await agent.run(state)

        assert len(result.detected_signals) == 1
        assert result.detected_signals[0].signal_type == SignalType.MA_ACTIVITY
        assert result.detected_signals[0].severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_handles_claude_api_failure(self):
        from src.agents.signal_agent import SignalDetectionAgent

        state = self._make_populated_state()
        agent = SignalDetectionAgent()

        with patch.object(agent.client.messages, "create", side_effect=Exception("API error")):
            result = await agent.run(state)

        assert result.detected_signals == []
        assert any("SignalDetectionAgent" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_no_signals_returns_empty_list(self):
        from src.agents.signal_agent import SignalDetectionAgent

        mock_content = MagicMock()
        mock_content.text = '{"signals": []}'
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        state = self._make_populated_state()
        agent = SignalDetectionAgent()

        with patch.object(agent.client.messages, "create", return_value=mock_response):
            result = await agent.run(state)

        assert result.detected_signals == []
        assert len(result.errors) == 0


# ─── Brief Synthesis Agent ────────────────────────────────────────────────────

class TestBriefSynthesisAgent:
    def _make_state_with_signals(self) -> AgentState:
        state = AgentState(request=AnalysisRequest(company_name="Acme Corp", ticker="ACME"))
        state.company_profile = CompanyProfile(name="Acme Corp", ticker="ACME", cik="0000001")
        state.filings = []
        state.news_items = []
        state.detected_signals = [
            DetectedSignal(
                signal_type=SignalType.MA_ACTIVITY,
                severity=Severity.HIGH,
                headline="Merger talks confirmed",
                evidence=["8-K filing", "Reuters article"],
                confidence=0.9,
                reasoning="Both sources corroborate."
            )
        ]
        return state

    @pytest.mark.asyncio
    async def test_produces_analyst_brief(self):
        from src.agents.signal_agent import BriefSynthesisAgent

        mock_response_text = json.dumps({
            "executive_summary": "Acme Corp shows high-probability acquisition signal.",
            "overall_severity": "high",
            "recommendation": "Initiate due diligence immediately.",
            "confidence_score": 0.88,
            "key_metrics": [{"name": "EV/EBITDA", "value": "12x", "period": "LTM", "interpretation": "Premium valuation"}],
            "risk_factors": [{"factor": "Antitrust", "impact": "Deal block", "likelihood": "medium", "mitigation": "Divestitures"}],
            "competitive_context": "Acquirer seeks market share in cloud infrastructure.",
            "recent_developments": ["LOI signed", "Board approved deal", "Shareholder vote scheduled"]
        })

        mock_content = MagicMock()
        mock_content.text = mock_response_text
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        state = self._make_state_with_signals()
        agent = BriefSynthesisAgent()

        with patch.object(agent.client.messages, "create", return_value=mock_response):
            result = await agent.run(state)

        assert result.brief is not None
        assert result.brief.company_name == "Acme Corp"
        assert result.brief.overall_severity == Severity.HIGH
        assert result.brief.confidence_score == 0.88
        assert len(result.brief.key_metrics) == 1
        assert len(result.brief.risk_factors) == 1
        assert len(result.brief.recent_developments) == 3

    @pytest.mark.asyncio
    async def test_handles_synthesis_failure(self):
        from src.agents.signal_agent import BriefSynthesisAgent

        state = self._make_state_with_signals()
        agent = BriefSynthesisAgent()

        with patch.object(agent.client.messages, "create", side_effect=Exception("Claude API down")):
            result = await agent.run(state)

        assert result.brief is None
        assert any("BriefSynthesisAgent" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_preserves_detected_signals_in_brief(self):
        from src.agents.signal_agent import BriefSynthesisAgent

        mock_response_text = json.dumps({
            "executive_summary": "Summary.",
            "overall_severity": "medium",
            "recommendation": "Watch.",
            "confidence_score": 0.6,
            "key_metrics": [],
            "risk_factors": [],
            "recent_developments": []
        })
        mock_content = MagicMock()
        mock_content.text = mock_response_text
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        state = self._make_state_with_signals()
        agent = BriefSynthesisAgent()

        with patch.object(agent.client.messages, "create", return_value=mock_response):
            result = await agent.run(state)

        assert result.brief is not None
        assert len(result.brief.detected_signals) == 1


# ─── Graph Integration ────────────────────────────────────────────────────────

class TestGraphIntegration:
    @pytest.mark.asyncio
    async def test_full_pipeline_produces_brief(self):
        """End-to-end graph test with all external calls mocked."""
        from src.agents.graph import run_analysis

        mock_profile = {"name": "Acme Corp", "cik": "0000001", "ticker": "ACME"}
        mock_filings = [
            SECFiling(accession_number="acc1", form_type="8-K", filing_date="2024-01-15",
                      company_name="Acme Corp", cik="0000001", document_url="https://sec.gov/x")
        ]
        mock_news = [
            NewsItem(title="Acme merger", source="Reuters", published_date="2024-01-15",
                     url="https://reuters.com/x", snippet="Deal confirmed", relevance_score=0.9)
        ]

        signal_json = json.dumps({"signals": [{
            "signal_type": "m_and_a_activity", "severity": "high",
            "headline": "Merger confirmed", "evidence": ["8-K", "Reuters"],
            "confidence": 0.92, "reasoning": "Corroborated by two sources."
        }]})
        brief_json = json.dumps({
            "executive_summary": "Acme is being acquired.",
            "overall_severity": "high",
            "recommendation": "Act now.",
            "confidence_score": 0.89,
            "key_metrics": [], "risk_factors": [], "recent_developments": []
        })

        def make_mock_response(text):
            mc = MagicMock(); mc.text = text
            mr = MagicMock(); mr.content = [mc]
            return mr

        with patch("src.agents.collection_agent.search_company_filings",
                   new=AsyncMock(return_value=(mock_profile, mock_filings))), \
             patch("src.agents.collection_agent.fetch_african_intelligence",
                   new=AsyncMock(return_value=([], []))), \
             patch("src.agents.collection_agent.fetch_market_news",
                   new=AsyncMock(return_value=mock_news)):
            with patch("anthropic.Anthropic") as MockAnthropic:
                instance = MockAnthropic.return_value
                instance.messages.create.side_effect = [
                    make_mock_response(signal_json),
                    make_mock_response(brief_json),
                ]
                from src.agents import signal_agent
                signal_agent.SignalDetectionAgent.__init__ = lambda self: setattr(self, "client", instance)
                signal_agent.BriefSynthesisAgent.__init__ = lambda self: setattr(self, "client", instance)

                req = AnalysisRequest(company_name="Acme Corp", ticker="ACME")
                brief = await run_analysis(req)

        assert brief is not None
        assert brief.company_name == "Acme Corp"

    @pytest.mark.asyncio
    async def test_graph_raises_on_no_brief(self):
        """Graph should raise RuntimeError if brief synthesis fails."""
        from src.agents.graph import run_analysis

        with patch("src.agents.collection_agent.search_company_filings",
                   new=AsyncMock(return_value=({"name": "Test"}, []))), \
             patch("src.agents.collection_agent.fetch_african_intelligence",
                   new=AsyncMock(return_value=([], []))), \
             patch("src.agents.collection_agent.fetch_market_news",
                   new=AsyncMock(return_value=[])):
            with patch("anthropic.Anthropic") as MockAnthropic:
                instance = MockAnthropic.return_value
                instance.messages.create.side_effect = Exception("Claude down")
                from src.agents import signal_agent
                signal_agent.SignalDetectionAgent.__init__ = lambda self: setattr(self, "client", instance)
                signal_agent.BriefSynthesisAgent.__init__ = lambda self: setattr(self, "client", instance)

                req = AnalysisRequest(company_name="Fail Corp")
                with pytest.raises(RuntimeError, match="Analysis failed"):
                    await run_analysis(req)


# ─── Africa Tool ──────────────────────────────────────────────────────────────

class TestAfricaTool:
    """Tests for African markets data tool."""

    def test_is_africa_focused_positive(self):
        from src.tools.africa_tool import _is_africa_focused
        assert _is_africa_focused("GTBank acquires fintech in Nigeria", "") is True
        assert _is_africa_focused("JSE-listed company announces merger", "") is True
        assert _is_africa_focused("Nairobi firm raises Series B", "") is True
        assert _is_africa_focused("", "deal confirmed in Johannesburg") is True
        assert _is_africa_focused("Expansion across Africa", "") is True

    def test_is_africa_focused_negative(self):
        from src.tools.africa_tool import _is_africa_focused
        assert _is_africa_focused("Apple acquires US startup", "deal in California") is False
        assert _is_africa_focused("Fed raises rates", "Wall Street reacts") is False

    def test_score_african_relevance_with_company_and_keyword(self):
        from src.tools.africa_tool import _score_african_relevance
        score = _score_african_relevance(
            "GTBank merger announced", "acquisition confirmed by board", "GTBank"
        )
        assert score > 0.3

    def test_score_african_relevance_no_match(self):
        from src.tools.africa_tool import _score_african_relevance
        score = _score_african_relevance("Weather today", "sunny skies", "Acme Corp")
        assert score < 0.2

    def test_score_african_relevance_african_distress_keywords(self):
        from src.tools.africa_tool import _score_african_relevance
        score = _score_african_relevance(
            "Firm placed under business rescue", "provisional liquidation filed", "Test Corp"
        )
        assert score > 0.1  # distressed keywords detected

    def test_extract_african_source_known(self):
        from src.tools.africa_tool import _extract_african_source
        assert _extract_african_source("https://businessday.ng/article/test") == "BusinessDay Nigeria"
        assert _extract_african_source("https://techcabal.com/post/test") == "TechCabal"
        assert _extract_african_source("https://moneyweb.co.za/news/test") == "Moneyweb"
        assert _extract_african_source("https://ngxgroup.com/data/test") == "NGX Group"
        assert _extract_african_source("https://stears.co/article/test") == "Stears"

    def test_extract_african_source_unknown(self):
        from src.tools.africa_tool import _extract_african_source
        result = _extract_african_source("https://somerandomblog.com/post")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_extract_african_source_invalid(self):
        from src.tools.africa_tool import _extract_african_source
        assert _extract_african_source("not-a-url") == "Unknown"

    def test_parse_rss_date_standard(self):
        from src.tools.africa_tool import _parse_rss_date
        result = _parse_rss_date("Mon, 12 May 2025 14:30:00 GMT")
        assert result == "2025-05-12"

    def test_parse_rss_date_iso_format(self):
        from src.tools.africa_tool import _parse_rss_date
        result = _parse_rss_date("2025-03-15T10:00:00Z")
        assert result == "2025-03-15"

    def test_parse_rss_date_fallback(self):
        from src.tools.africa_tool import _parse_rss_date
        result = _parse_rss_date("garbage date string")
        assert result == datetime.utcnow().strftime("%Y-%m-%d")

    @pytest.mark.asyncio
    async def test_context_manager(self):
        from src.tools.africa_tool import AfricaTool
        async with AfricaTool() as tool:
            assert tool._client is not None
        assert tool._client.is_closed

    @pytest.mark.asyncio
    async def test_no_client_raises(self):
        from src.tools.africa_tool import AfricaTool
        tool = AfricaTool()
        with pytest.raises(RuntimeError, match="async context manager"):
            _ = tool.client

    @pytest.mark.asyncio
    async def test_fetch_rss_network_error_returns_empty(self):
        from src.tools.africa_tool import AfricaTool
        async with AfricaTool() as tool:
            with patch.object(tool.client, "get", side_effect=Exception("network error")):
                result = await tool._fetch_rss("https://businessday.ng/feed/")
                assert result == []

    @pytest.mark.asyncio
    async def test_fetch_rss_invalid_xml_returns_empty(self):
        from src.tools.africa_tool import AfricaTool
        import httpx
        async with AfricaTool() as tool:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.content = b"not xml at all <<<"
            mock_resp.encoding = "utf-8"
            with patch.object(tool.client, "get", return_value=mock_resp):
                result = await tool._fetch_rss("https://businessday.ng/feed/")
                assert result == []

    @pytest.mark.asyncio
    async def test_fetch_rss_parses_valid_feed(self):
        from src.tools.africa_tool import AfricaTool
        valid_rss = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <item>
            <title>GTBank acquires fintech</title>
            <link>https://businessday.ng/article/1</link>
            <pubDate>Mon, 12 May 2025 10:00:00 GMT</pubDate>
            <description>Acquisition confirmed by board</description>
          </item>
        </channel></rss>"""
        async with AfricaTool() as tool:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.content = valid_rss
            mock_resp.encoding = "utf-8"
            with patch.object(tool.client, "get", return_value=mock_resp):
                items = await tool._fetch_rss("https://businessday.ng/feed/")
        assert len(items) == 1
        assert items[0]["title"] == "GTBank acquires fintech"
        assert items[0]["link"] == "https://businessday.ng/article/1"

    @pytest.mark.asyncio
    async def test_fetch_african_news_filters_by_lookback(self):
        """News items older than lookback_days should be excluded."""
        from src.tools.africa_tool import AfricaTool
        old_date = "Mon, 01 Jan 2020 10:00:00 GMT"
        old_rss = f"""<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <item>
            <title>Old GTBank news</title>
            <link>https://businessday.ng/old</link>
            <pubDate>{old_date}</pubDate>
            <description>Very old story</description>
          </item>
        </channel></rss>""".encode()

        async with AfricaTool() as tool:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.content = old_rss
            mock_resp.encoding = "utf-8"
            with patch.object(tool.client, "get", return_value=mock_resp):
                items = await tool.fetch_african_news("GTBank", lookback_days=90)
        assert len(items) == 0  # all filtered out as too old

    @pytest.mark.asyncio
    async def test_fetch_african_news_deduplicates_titles(self):
        """Same headline appearing in multiple feeds should only appear once."""
        from src.tools.africa_tool import AfricaTool
        today = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        dup_rss = f"""<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <item>
            <title>GTBank merger confirmed</title>
            <link>https://businessday.ng/1</link>
            <pubDate>{today}</pubDate>
            <description>GTBank acquisition deal confirmed merger</description>
          </item>
        </channel></rss>""".encode()

        async with AfricaTool() as tool:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.content = dup_rss
            mock_resp.encoding = "utf-8"
            # All requests return the same item — should deduplicate
            with patch.object(tool.client, "get", return_value=mock_resp):
                items = await tool.fetch_african_news("GTBank", lookback_days=90)
        # All feeds return the same title — should appear only once
        titles = [i.title for i in items]
        assert titles.count("GTBank merger confirmed") == 1

    @pytest.mark.asyncio
    async def test_fetch_african_intelligence_wrapper(self):
        """Convenience wrapper should return (filings, news) tuple."""
        from src.tools.africa_tool import fetch_african_intelligence, AfricaTool

        mock_filing = SECFiling(
            accession_number="NGX-001", form_type="NGX Announcement",
            filing_date="2024-01-10", company_name="GTBank",
            cik="NGX", document_url="https://ngxgroup.com/x"
        )
        mock_news_item = NewsItem(
            title="GTBank deal", source="BusinessDay Nigeria",
            published_date="2024-01-10", url="https://businessday.ng/x",
            snippet="Merger talks", relevance_score=0.8
        )

        with patch.object(AfricaTool, "fetch_ngx_announcements",
                          new=AsyncMock(return_value=[mock_filing])), \
             patch.object(AfricaTool, "fetch_jse_sens",
                          new=AsyncMock(return_value=[])), \
             patch.object(AfricaTool, "fetch_nse_kenya_disclosures",
                          new=AsyncMock(return_value=[])), \
             patch.object(AfricaTool, "fetch_african_news",
                          new=AsyncMock(return_value=[mock_news_item])):
            filings, news = await fetch_african_intelligence("GTBank", None, 90)

        assert len(filings) == 1
        assert filings[0].form_type == "NGX Announcement"
        assert len(news) == 1
        assert news[0].source == "BusinessDay Nigeria"

    @pytest.mark.asyncio
    async def test_fetch_african_intelligence_deduplicates_filings(self):
        """Same accession from multiple exchanges shouldn't be duplicated."""
        from src.tools.africa_tool import fetch_african_intelligence, AfricaTool

        dup = SECFiling(
            accession_number="DUPE-001", form_type="NGX Announcement",
            filing_date="2024-01-10", company_name="Test",
            cik="NGX", document_url="https://ngxgroup.com/x"
        )
        with patch.object(AfricaTool, "fetch_ngx_announcements", new=AsyncMock(return_value=[dup])), \
             patch.object(AfricaTool, "fetch_jse_sens",            new=AsyncMock(return_value=[dup])), \
             patch.object(AfricaTool, "fetch_nse_kenya_disclosures", new=AsyncMock(return_value=[])), \
             patch.object(AfricaTool, "fetch_african_news",         new=AsyncMock(return_value=[])):
            filings, _ = await fetch_african_intelligence("Test", None, 90)

        assert len(filings) == 1  # deduplicated

    @pytest.mark.asyncio
    async def test_jse_sens_falls_back_to_google_news(self):
        """When SENS RSS returns nothing, it should fall back to Google News SA."""
        from src.tools.africa_tool import AfricaTool
        today = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        fallback_rss = f"""<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <item>
            <title>Shoprite JSE SENS announcement merger</title>
            <link>https://businesslive.co.za/1</link>
            <pubDate>{today}</pubDate>
            <description>Shoprite files JSE SENS notice on merger agreement</description>
          </item>
        </channel></rss>""".encode()

        async with AfricaTool() as tool:
            empty_resp = MagicMock()
            empty_resp.raise_for_status = MagicMock()
            empty_resp.content = b"""<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>"""
            empty_resp.encoding = "utf-8"

            fallback_resp = MagicMock()
            fallback_resp.raise_for_status = MagicMock()
            fallback_resp.content = fallback_rss
            fallback_resp.encoding = "utf-8"

            call_count = {"n": 0}
            async def mock_get(url, **kwargs):
                call_count["n"] += 1
                # First call (SENS RSS) returns empty; subsequent (Google News) returns data
                return empty_resp if call_count["n"] == 1 else fallback_resp

            with patch.object(tool.client, "get", side_effect=mock_get):
                filings = await tool.fetch_jse_sens("Shoprite")

        assert len(filings) > 0
        assert any("Shoprite" in f.description for f in filings)

    def test_african_signal_keywords_coverage(self):
        """All six signal categories should have at least 3 keywords."""
        from src.tools.africa_tool import AFRICAN_SIGNAL_KEYWORDS
        for category, keywords in AFRICAN_SIGNAL_KEYWORDS.items():
            assert len(keywords) >= 3, f"Category {category} has too few keywords"

    def test_african_source_map_completeness(self):
        """Source map should cover major African financial media."""
        from src.tools.africa_tool import AFRICAN_SOURCE_MAP
        required = ["businessday.ng", "techcabal.com", "moneyweb.co.za",
                    "ngxgroup.com", "stears.co", "theafricareport.com"]
        for domain in required:
            assert domain in AFRICAN_SOURCE_MAP, f"{domain} missing from AFRICAN_SOURCE_MAP"

    def test_african_news_feeds_dict_has_urls(self):
        """All African news feed URLs should be valid https URLs."""
        from src.tools.africa_tool import AFRICAN_NEWS_FEEDS
        for name, url in AFRICAN_NEWS_FEEDS.items():
            assert url.startswith("https://"), f"{name} feed URL doesn't use HTTPS"


# ─── Edge Cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_brief_with_no_signals(self):
        brief = AnalystBrief(
            company_name="Quiet Corp",
            executive_summary="No signals detected.",
            overall_severity=Severity.LOW,
            recommendation="No action required.",
            confidence_score=0.95,
            detected_signals=[]
        )
        assert brief.signal_count_by_severity()["low"] == 0
        assert brief.top_signals() == []

    def test_brief_with_many_signals_top_n(self):
        signals = [
            DetectedSignal(
                signal_type=SignalType.CREDIT_RISK,
                severity=Severity.MEDIUM,
                headline=f"Signal {i}",
                evidence=[],
                confidence=0.5 + i * 0.05,
                reasoning="R"
            )
            for i in range(10)
        ]
        brief = AnalystBrief(
            company_name="Big Corp",
            executive_summary="Many signals.",
            overall_severity=Severity.HIGH,
            recommendation="Review all.",
            confidence_score=0.7,
            detected_signals=signals
        )
        assert len(brief.top_signals(n=3)) == 3

    def test_sec_filing_minimal_fields(self):
        filing = SECFiling(
            accession_number="",
            form_type="8-K",
            filing_date="2024-01-01",
            company_name="Test",
            cik="0001",
            document_url="https://sec.gov/x"
        )
        assert filing.raw_excerpt is None
        assert filing.description is None

    def test_company_profile_defaults(self):
        profile = CompanyProfile(name="Test Inc")
        assert profile.ticker is None
        assert profile.cik is None
        assert isinstance(profile.resolved_at, datetime)

    def test_news_item_relevance_bounds(self):
        with pytest.raises(Exception):
            NewsItem(title="T", source="S", published_date="2024-01-01",
                     url="http://x.com", snippet="S", relevance_score=1.5)
        with pytest.raises(Exception):
            NewsItem(title="T", source="S", published_date="2024-01-01",
                     url="http://x.com", snippet="S", relevance_score=-0.1)

    def test_african_filing_type_stored_correctly(self):
        """African exchange filings should be stored as SECFiling with exchange CIK markers."""
        for exchange_cik, form_type in [("NGX", "NGX Announcement"), ("JSE", "JSE SENS"), ("NSE-KE", "NSE Kenya Disclosure")]:
            f = SECFiling(
                accession_number=f"{exchange_cik}-001",
                form_type=form_type,
                filing_date="2024-01-01",
                company_name="Test Corp",
                cik=exchange_cik,
                document_url="https://example.com/x"
            )
            assert f.cik == exchange_cik
            assert f.form_type == form_type

    def test_mixed_us_african_filings_in_brief(self):
        """AnalystBrief should handle a mix of US SEC + African exchange filings."""
        us_filing = SECFiling(accession_number="SEC-001", form_type="8-K",
                              filing_date="2024-01-15", company_name="Test",
                              cik="0000001", document_url="https://sec.gov/x")
        ngx_filing = SECFiling(accession_number="NGX-001", form_type="NGX Announcement",
                               filing_date="2024-01-10", company_name="Test",
                               cik="NGX", document_url="https://ngxgroup.com/x")
        brief = AnalystBrief(
            company_name="Test Corp",
            executive_summary="Mixed sources.",
            overall_severity=Severity.MEDIUM,
            recommendation="Monitor.",
            confidence_score=0.7,
            detected_signals=[],
            filings_reviewed=[us_filing, ngx_filing],
            total_sources=2
        )
        assert len(brief.filings_reviewed) == 2
        form_types = {f.form_type for f in brief.filings_reviewed}
        assert "8-K" in form_types
        assert "NGX Announcement" in form_types
