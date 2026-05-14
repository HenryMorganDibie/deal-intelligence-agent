"""
Signal Detection Agent.
Uses Claude to reason over collected filings + news and surface
structured DetectedSignal objects with full reasoning traces.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import anthropic

from src.schemas.models import (
    AgentState, DetectedSignal, SECFiling, NewsItem,
    SignalType, Severity, CompanyProfile
)

MODEL = "claude-sonnet-4-20250514"

SIGNAL_DETECTION_SYSTEM = """You are a senior financial intelligence analyst specialising in M&A, credit risk, and distressed asset identification.

Your task: analyse SEC filings and news items for a company and identify actionable deal intelligence signals.

For each signal you detect, you MUST provide:
1. signal_type (one of: m_and_a_activity, credit_risk, distressed_asset, earnings_surprise, leadership_change, regulatory_action, debt_restructuring, insider_activity)
2. severity (low, medium, high, critical)
3. headline: crisp one-line description
4. evidence: list of 2-5 specific supporting facts/quotes from the source material
5. source_urls: relevant URLs from the material
6. filing_references: accession numbers from SEC filings
7. confidence: float 0.0-1.0 (your certainty this signal is real and material)
8. reasoning: your full chain-of-thought explaining WHY this is a signal

Return ONLY a JSON object with key "signals" containing an array of signal objects.
No markdown, no explanation outside the JSON.
Be precise. Prefer fewer high-confidence signals over many low-confidence ones.
If no meaningful signals exist, return {"signals": []}."""


SYNTHESIS_SYSTEM = """You are a senior analyst at a top-tier investment bank writing a deal intelligence brief.

Given detected signals, company profile, and source material, write a structured analyst brief.

Return ONLY a JSON object with these exact keys:
{
  "executive_summary": "2-3 sentence sharp executive summary of the situation",
  "overall_severity": "low|medium|high|critical",
  "recommendation": "One clear actionable recommendation for the analyst/investor",
  "confidence_score": 0.0-1.0,
  "key_metrics": [
    {"name": "metric name", "value": "value", "period": "period", "interpretation": "what this means"}
  ],
  "risk_factors": [
    {"factor": "risk name", "impact": "description of impact", "likelihood": "low|medium|high|critical", "mitigation": "optional mitigation"}
  ],
  "competitive_context": "Optional paragraph on competitive dynamics",
  "recent_developments": ["bullet 1", "bullet 2", "bullet 3"]
}

Be precise, professional, and data-driven. Reference specific numbers where available.
Return ONLY valid JSON."""


def _build_filing_context(filings: list[SECFiling], max_chars: int = 6000) -> str:
    """Format filings into LLM-consumable context."""
    lines = []
    total = 0
    for f in filings:
        entry = (
            f"[{f.form_type} | {f.filing_date} | {f.company_name}]\n"
            f"Accession: {f.accession_number}\n"
            f"URL: {f.document_url}\n"
        )
        if f.description:
            entry += f"Description: {f.description}\n"
        if f.raw_excerpt:
            entry += f"Excerpt: {f.raw_excerpt[:500]}\n"
        entry += "---\n"
        if total + len(entry) > max_chars:
            break
        lines.append(entry)
        total += len(entry)
    return "\n".join(lines) if lines else "No filings available."


def _build_news_context(news_items: list[NewsItem], max_chars: int = 5000) -> str:
    """Format news into LLM-consumable context."""
    lines = []
    total = 0
    for n in sorted(news_items, key=lambda x: x.relevance_score, reverse=True):
        entry = (
            f"[{n.source} | {n.published_date} | Relevance: {n.relevance_score:.2f}]\n"
            f"Title: {n.title}\n"
            f"Snippet: {n.snippet}\n"
            f"URL: {n.url}\n---\n"
        )
        if total + len(entry) > max_chars:
            break
        lines.append(entry)
        total += len(entry)
    return "\n".join(lines) if lines else "No news available."


def _parse_signals_from_response(raw: str, state: AgentState) -> list[DetectedSignal]:
    """Safely parse LLM JSON response into DetectedSignal objects."""
    # Strip markdown fences if present
    raw = re.sub(r"```json|```", "", raw).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON block
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except Exception:
                state.errors.append("Signal parser: invalid JSON from LLM")
                return []
        else:
            state.errors.append("Signal parser: no JSON found in LLM response")
            return []

    raw_signals = data.get("signals", [])
    signals: list[DetectedSignal] = []

    for rs in raw_signals:
        try:
            # Normalise signal_type
            raw_type = rs.get("signal_type", "").lower().replace(" ", "_").replace("-", "_")
            try:
                sig_type = SignalType(raw_type)
            except ValueError:
                # Best-effort mapping
                mapping = {
                    "ma": SignalType.MA_ACTIVITY, "merger": SignalType.MA_ACTIVITY,
                    "credit": SignalType.CREDIT_RISK, "debt": SignalType.CREDIT_RISK,
                    "distress": SignalType.DISTRESSED_ASSET,
                    "leadership": SignalType.LEADERSHIP_CHANGE,
                    "regulatory": SignalType.REGULATORY_ACTION,
                    "insider": SignalType.INSIDER_ACTIVITY,
                    "earnings": SignalType.EARNINGS_SURPRISE,
                    "restructur": SignalType.DEBT_RESTRUCTURE,
                }
                sig_type = next(
                    (v for k, v in mapping.items() if k in raw_type),
                    SignalType.CREDIT_RISK
                )

            severity = Severity(rs.get("severity", "medium").lower())
            confidence = float(rs.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            signal = DetectedSignal(
                signal_type=sig_type,
                severity=severity,
                headline=rs.get("headline", "Unspecified signal"),
                evidence=rs.get("evidence", []),
                source_urls=rs.get("source_urls", []),
                filing_references=rs.get("filing_references", []),
                confidence=confidence,
                reasoning=rs.get("reasoning", ""),
                detected_at=datetime.utcnow()
            )
            signals.append(signal)
        except Exception as e:
            state.errors.append(f"Signal parse error: {e}")
            continue

    return signals


class SignalDetectionAgent:
    """
    LangGraph node: analyses collected data and produces DetectedSignal objects.
    """

    def __init__(self):
        self.client = anthropic.Anthropic()

    async def run(self, state: AgentState) -> AgentState:
        state.log("signal_detection", "Starting signal detection pass")

        filing_ctx = _build_filing_context(state.filings)
        news_ctx   = _build_news_context(state.news_items)
        company    = state.company_profile.name if state.company_profile else state.request.company_name

        focus = ""
        if state.request.focus_signals:
            focus = f"\nPrioritise these signal types: {', '.join(s.value for s in state.request.focus_signals)}"

        user_prompt = f"""Analyse the following data for {company} and detect deal intelligence signals.{focus}

=== SEC FILINGS ({len(state.filings)} retrieved) ===
{filing_ctx}

=== NEWS ITEMS ({len(state.news_items)} retrieved) ===
{news_ctx}

Identify all material signals. Be specific, reference exact evidence from the material above."""

        try:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SIGNAL_DETECTION_SYSTEM,
                messages=[{"role": "user", "content": user_prompt}]
            )
            raw = response.content[0].text
            signals = _parse_signals_from_response(raw, state)
            state.detected_signals = signals
            state.log(
                "signal_detection",
                f"Detected {len(signals)} signals",
                {"signal_types": [s.signal_type.value for s in signals]}
            )
        except Exception as e:
            state.errors.append(f"SignalDetectionAgent error: {e}")
            state.log("signal_detection", f"Error: {e}")

        return state


class BriefSynthesisAgent:
    """
    LangGraph node: synthesises detected signals into a structured AnalystBrief.
    """

    def __init__(self):
        self.client = anthropic.Anthropic()

    async def run(self, state: AgentState) -> AgentState:
        from src.schemas.models import AnalystBrief, RiskFactor, KeyMetric

        state.log("brief_synthesis", "Synthesising analyst brief")

        company  = state.company_profile.name if state.company_profile else state.request.company_name
        ticker   = state.request.ticker or (state.company_profile.ticker if state.company_profile else None)
        signals_json = json.dumps(
            [s.model_dump(mode="json") for s in state.detected_signals], indent=2
        )
        profile_ctx = ""
        if state.company_profile:
            p = state.company_profile
            profile_ctx = (
                f"Sector: {p.sector or 'Unknown'}\n"
                f"Exchange: {p.exchange or 'Unknown'}\n"
                f"CIK: {p.cik or 'Unknown'}\n"
            )

        user_prompt = f"""Write a structured analyst brief for {company} ({ticker or 'private'}).

{profile_ctx}
Lookback: {state.request.lookback_days} days
Total filings reviewed: {len(state.filings)}
Total news items reviewed: {len(state.news_items)}

DETECTED SIGNALS:
{signals_json}

Write a professional, actionable analyst brief based on this intelligence."""

        try:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=3000,
                system=SYNTHESIS_SYSTEM,
                messages=[{"role": "user", "content": user_prompt}]
            )
            raw = response.content[0].text
            raw = re.sub(r"```json|```", "", raw).strip()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                data = json.loads(match.group()) if match else {}

            # Parse risk factors
            risk_factors = []
            for rf in data.get("risk_factors", []):
                try:
                    risk_factors.append(RiskFactor(
                        factor=rf.get("factor", ""),
                        impact=rf.get("impact", ""),
                        likelihood=Severity(rf.get("likelihood", "medium").lower()),
                        mitigation=rf.get("mitigation")
                    ))
                except Exception:
                    pass

            # Parse key metrics
            key_metrics = []
            for km in data.get("key_metrics", []):
                try:
                    key_metrics.append(KeyMetric(
                        name=km.get("name", ""),
                        value=km.get("value", ""),
                        period=km.get("period", ""),
                        interpretation=km.get("interpretation", "")
                    ))
                except Exception:
                    pass

            severity_raw = data.get("overall_severity", "medium").lower()
            try:
                overall_severity = Severity(severity_raw)
            except ValueError:
                overall_severity = Severity.MEDIUM

            confidence = float(data.get("confidence_score", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            brief = AnalystBrief(
                company_name=company,
                ticker=ticker,
                executive_summary=data.get("executive_summary", "Analysis complete."),
                overall_severity=overall_severity,
                recommendation=data.get("recommendation", "Further review recommended."),
                confidence_score=confidence,
                detected_signals=state.detected_signals,
                key_metrics=key_metrics,
                risk_factors=risk_factors,
                competitive_context=data.get("competitive_context"),
                recent_developments=data.get("recent_developments", []),
                filings_reviewed=state.filings,
                news_reviewed=state.news_items,
                total_sources=len(state.filings) + len(state.news_items),
                reasoning_trace=state.reasoning_trace
            )

            state.brief = brief
            state.log("brief_synthesis", "Brief synthesised successfully")

        except Exception as e:
            state.errors.append(f"BriefSynthesisAgent error: {e}")
            state.log("brief_synthesis", f"Error: {e}")

        return state
