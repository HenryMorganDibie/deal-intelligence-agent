"""
Signal Detection & Brief Synthesis Agents.

Architecture (Phase 2 — Separation of Concerns):

  Node 1 — DeterministicDetectionNode
    Runs DeterministicSignalEngine (zero LLM).
    Produces SignalCandidate[] from pure pattern matching + NER.
    If zero candidates -> zero signals. LLM cannot override this.

  Node 2 — LLMExplanationNode
    Only runs if deterministic engine produced >= 1 candidate.
    LLM receives confirmed candidates and explains each one.
    LLM never invents signals -- it only contextualises them.

  Node 3 — AlphaScoringNode
    Attaches AlphaScore to every explained signal.
    Applies compliance flags (human review triggers).

  Node 4 — BriefSynthesisAgent
    Synthesises all scored signals into a final AnalystBrief.
    Applies compliance mode suppressions if enabled.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import anthropic

from src.schemas.models import (
    AgentState, AnalystBrief, DetectedSignal, RiskFactor, KeyMetric,
    SignalType, Severity, SignalCandidate, LiquidityTier
)
from src.engines.deterministic_engine import DeterministicSignalEngine
from src.engines.calibration import calibrate_all
from src.engines.adaptive_calibration import adaptive_calibrate
from src.engines.alpha_scorer import score_all_signals, LOW_CONFIDENCE_SUPPRESS_THRESHOLD
from src.engines.confidence import decompose_all
from src.engines.semantic import extract_from_filing, extract_from_news, evidence_to_strings
from src.engines.audit_log import log_state

MODEL = "claude-sonnet-4-20250514"

EXPLANATION_SYSTEM = """You are a senior financial analyst writing explanations for pre-confirmed deal intelligence signals.

IMPORTANT: These signals were detected by a deterministic pattern-matching engine, not by you.
Your job is ONLY to:
1. Write a clear, professional headline for each signal
2. List the specific evidence from the source material
3. Explain the significance and context in plain analyst language
4. Note any ambiguities or caveats

You MUST NOT invent new signals. You MUST NOT change the signal_type or severity.
You MUST reference only evidence present in the source material provided.

For each signal candidate, return a JSON object:
{
  "signal_type": "<same as input>",
  "headline": "<crisp one-line description>",
  "evidence": ["<specific fact from source>", "<specific fact>"],
  "reasoning": "<2-3 sentences of professional analyst context>"
}

Return ONLY a JSON array of these objects. No markdown. No preamble."""

SYNTHESIS_SYSTEM = """You are a senior analyst writing a deal intelligence brief synthesis.

Given pre-scored signals, write only the narrative synthesis.
Do NOT re-detect or re-evaluate signals -- they are already confirmed and scored.

Return ONLY a JSON object:
{
  "executive_summary": "2-3 sentence sharp executive summary",
  "overall_severity": "low|medium|high|critical",
  "recommendation": "One clear actionable recommendation",
  "confidence_score": 0.0-1.0,
  "key_metrics": [{"name":"","value":"","period":"","interpretation":""}],
  "risk_factors": [{"factor":"","impact":"","likelihood":"low|medium|high|critical","mitigation":""}],
  "competitive_context": "optional paragraph",
  "recent_developments": ["bullet 1", "bullet 2"]
}"""


def _enrich_with_semantic_evidence(candidates: list[SignalCandidate], state: AgentState) -> None:
    """Augment candidate source_text with semantic evidence extracted from filings/news."""
    for cand in candidates:
        all_evidence = []
        # Extract from filings matching this candidate's source
        for filing in state.filings[:5]:
            text = " ".join(filter(None, [filing.description, filing.raw_excerpt]))
            if text:
                ev = extract_from_filing(text)
                all_evidence.extend(evidence_to_strings(ev[:2]))
        # Extract from top news items
        for news in state.news_items[:3]:
            ev = extract_from_news(news.title, news.snippet)
            all_evidence.extend(evidence_to_strings(ev[:1]))
        if all_evidence:
            cand.entity_mentions = list(set(cand.entity_mentions + all_evidence[:3]))


def _candidates_to_prompt(candidates: list[SignalCandidate]) -> str:
    lines = []
    for i, c in enumerate(candidates, 1):
        lines.append(
            f"CANDIDATE {i}:\n"
            f"  signal_type: {c.signal_type.value}\n"
            f"  patterns_fired: {', '.join(c.matched_patterns[:4])}\n"
            f"  source_type: {c.source_type} ({c.source_name})\n"
            f"  corroboration: {c.corroboration_count} independent source(s)\n"
            f"  source_text: {c.source_text[:600]}\n"
            f"  entities_found: {', '.join(c.entity_mentions[:5]) or 'none'}\n"
        )
    return "\n".join(lines)


def _parse_explanations(
    raw: str,
    candidates: list[SignalCandidate],
    calibrated: list[tuple],
    state: AgentState,
) -> list[DetectedSignal]:
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            data = [data]
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except Exception:
                state.errors.append("LLM explanation parser: invalid JSON")
                return []
        else:
            state.errors.append("LLM explanation parser: no JSON array found")
            return []

    cal_map: dict[SignalType, tuple] = {}
    for cand, sev, conf, mat_rate in calibrated:
        cal_map[cand.signal_type] = (sev, conf, mat_rate)

    cand_map: dict[SignalType, SignalCandidate] = {c.signal_type: c for c in candidates}

    signals: list[DetectedSignal] = []
    for item in data:
        try:
            raw_type = item.get("signal_type", "").lower().replace(" ", "_").replace("-", "_")
            try:
                sig_type = SignalType(raw_type)
            except ValueError:
                continue

            cand = cand_map.get(sig_type)
            if cand is None:
                continue

            sev, conf, _ = cal_map.get(sig_type, (Severity.LOW, 0.5, 0.1))

            signals.append(DetectedSignal(
                signal_type=sig_type,
                severity=sev,
                headline=item.get("headline", f"{sig_type.value.replace('_',' ').title()} detected"),
                evidence=item.get("evidence", []),
                source_urls=[cand.source_url] if cand.source_url else [],
                filing_references=[cand.filing_reference] if cand.filing_reference else [],
                confidence=conf,
                reasoning=item.get("reasoning", ""),
                candidate_patterns=cand.matched_patterns,
                corroboration_count=cand.corroboration_count,
            ))
        except Exception as e:
            state.errors.append(f"Signal parse error: {e}")
            continue

    return signals


def _fallback_signals(calibrated: list[tuple]) -> list[DetectedSignal]:
    signals = []
    for cand, sev, conf, _ in calibrated:
        signals.append(DetectedSignal(
            signal_type=cand.signal_type,
            severity=sev,
            headline=f"{cand.signal_type.value.replace('_', ' ').title()} -- deterministic detection",
            evidence=[cand.source_text[:200]],
            source_urls=[cand.source_url] if cand.source_url else [],
            filing_references=[cand.filing_reference] if cand.filing_reference else [],
            confidence=conf,
            reasoning="LLM explanation unavailable -- deterministic engine output used directly.",
            candidate_patterns=cand.matched_patterns,
            corroboration_count=cand.corroboration_count,
        ))
    return signals


class DeterministicDetectionNode:
    def run(self, state: AgentState) -> AgentState:
        engine = DeterministicSignalEngine()
        state = engine.run(state)
        log_state(state, "deterministic_detection",
                  f"{len(state.signal_candidates)} candidates produced")
        return state


class LLMExplanationNode:
    def __init__(self):
        self.client = anthropic.Anthropic()

    async def run(self, state: AgentState) -> AgentState:
        state.log("llm_explanation", f"Explaining {len(state.signal_candidates)} candidates")

        if not state.signal_candidates:
            state.log("llm_explanation", "No candidates -- skipping LLM pass")
            return state

        # Use adaptive calibration (falls back to static when insufficient data)
        calibrated = []
        for cand in state.signal_candidates:
            try:
                sector = state.company_profile.sector if state.company_profile else None
                sev, conf, mat = adaptive_calibrate(cand, sector=sector)
                calibrated.append((cand, sev, conf, mat))
            except Exception:
                from src.engines.calibration import calibrate
                sev, conf, mat = calibrate(cand)
                calibrated.append((cand, sev, conf, mat))

        if state.compliance_mode:
            calibrated = [
                (c, sev, conf, mr) for c, sev, conf, mr in calibrated
                if conf >= LOW_CONFIDENCE_SUPPRESS_THRESHOLD
            ]

        if not calibrated:
            state.log("llm_explanation", "All candidates suppressed by compliance filter")
            return state

        candidates_for_llm = [c for c, _, _, _ in calibrated]
        company = state.company_profile.name if state.company_profile else state.request.company_name

        # Enrich candidates with semantic evidence before LLM sees them
        _enrich_with_semantic_evidence(candidates_for_llm, state)

        user_prompt = (
            f"Company: {company}\n"
            f"Lookback: {state.request.lookback_days} days\n\n"
            f"The deterministic engine confirmed these {len(candidates_for_llm)} signal candidates:\n\n"
            f"{_candidates_to_prompt(candidates_for_llm)}\n\n"
            f"Write explanations for each. Do not invent signals."
        )

        try:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=3000,
                system=EXPLANATION_SYSTEM,
                messages=[{"role": "user", "content": user_prompt}]
            )
            raw = response.content[0].text
            signals = _parse_explanations(raw, candidates_for_llm, calibrated, state)
            state.detected_signals = signals
            log_state(state, "llm_explanation", f"{len(signals)} signals explained")
        except Exception as e:
            state.errors.append(f"LLMExplanationNode error: {e}")
            state.detected_signals = _fallback_signals(calibrated_all := calibrate_all(state.signal_candidates))

        return state


class AlphaScoringNode:
    def run(self, state: AgentState) -> AgentState:
        state.log("alpha_scoring", f"Scoring {len(state.detected_signals)} signals")
        if not state.detected_signals:
            return state
        profile  = state.company_profile
        ticker   = profile.ticker   if profile else state.request.ticker
        exchange = profile.exchange  if profile else None
        sector   = profile.sector   if profile else None
        state.detected_signals = score_all_signals(
            state.detected_signals,
            state.signal_candidates,
            ticker=ticker, exchange=exchange, sector=sector,
            compliance_mode=state.compliance_mode,
        )
        log_state(state, "alpha_scoring", "Alpha scores attached")
        return state


class BriefSynthesisAgent:
    def __init__(self):
        self.client = anthropic.Anthropic()

    async def run(self, state: AgentState) -> AgentState:
        state.log("brief_synthesis", "Synthesising analyst brief")
        company = state.company_profile.name if state.company_profile else state.request.company_name
        ticker  = state.request.ticker or (state.company_profile.ticker if state.company_profile else None)

        signals_json = json.dumps(
            [s.model_dump(mode="json", exclude={"alpha_score"}) for s in state.detected_signals],
            indent=2
        )

        review_reasons = [
            sig.alpha_score.review_reason
            for sig in state.detected_signals
            if sig.alpha_score and sig.alpha_score.requires_human_review and sig.alpha_score.review_reason
        ]

        suppressed = sum(
            1 for s in state.detected_signals
            if state.compliance_mode and s.confidence < LOW_CONFIDENCE_SUPPRESS_THRESHOLD
        )

        user_prompt = (
            f"Company: {company} ({ticker or 'private'})\n"
            f"Signals confirmed: {len(state.detected_signals)}\n"
            f"Sources reviewed: {len(state.filings)} filings, {len(state.news_items)} news items\n"
            f"Compliance mode: {'ON' if state.compliance_mode else 'OFF'}\n\n"
            f"CONFIRMED SIGNALS:\n{signals_json}\n\nWrite the synthesis."
        )

        try:
            response = self.client.messages.create(
                model=MODEL, max_tokens=2500,
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

            risk_factors = []
            for rf in data.get("risk_factors", []):
                try:
                    risk_factors.append(RiskFactor(
                        factor=rf.get("factor", ""), impact=rf.get("impact", ""),
                        likelihood=Severity(rf.get("likelihood", "medium").lower()),
                        mitigation=rf.get("mitigation"),
                    ))
                except Exception:
                    pass

            key_metrics = []
            for km in data.get("key_metrics", []):
                try:
                    key_metrics.append(KeyMetric(
                        name=km.get("name", ""), value=km.get("value", ""),
                        period=km.get("period", ""), interpretation=km.get("interpretation", ""),
                    ))
                except Exception:
                    pass

            try:
                overall_sev = Severity(data.get("overall_severity", "medium").lower())
            except ValueError:
                overall_sev = Severity.MEDIUM

            confidence = max(0.0, min(1.0, float(data.get("confidence_score", 0.5))))
            top_alpha  = None
            top_liq    = None
            if state.detected_signals and state.detected_signals[0].alpha_score:
                top_alpha = state.detected_signals[0].alpha_score.score
                top_liq   = state.detected_signals[0].alpha_score.liquidity_tier

            compliance_flags = []
            if state.compliance_mode:
                if suppressed:
                    compliance_flags.append(f"{suppressed} low-confidence signal(s) suppressed")
                if review_reasons:
                    compliance_flags.append(f"{len(review_reasons)} signal(s) require human review")
                compliance_flags.append("Output is AI-generated, unverified, not investment advice")

            state.brief = AnalystBrief(
                company_name=company, ticker=ticker,
                executive_summary=data.get("executive_summary", "Analysis complete."),
                overall_severity=overall_sev,
                recommendation=data.get("recommendation", "Further review recommended."),
                confidence_score=confidence,
                detected_signals=state.detected_signals,
                signal_candidates_count=len(state.signal_candidates),
                top_alpha_score=top_alpha, liquidity_tier=top_liq,
                requires_human_review=bool(review_reasons),
                human_review_reasons=review_reasons,
                key_metrics=key_metrics, risk_factors=risk_factors,
                competitive_context=data.get("competitive_context"),
                recent_developments=data.get("recent_developments", []),
                filings_reviewed=state.filings, news_reviewed=state.news_items,
                total_sources=len(state.filings) + len(state.news_items),
                compliance_mode=state.compliance_mode,
                compliance_flags=compliance_flags,
                low_confidence_signals_suppressed=suppressed,
                reasoning_trace=state.reasoning_trace,
                audit_entries=state.audit_entries,
            )
            log_state(state, "brief_synthesis", "Brief complete")
        except Exception as e:
            state.errors.append(f"BriefSynthesisAgent error: {e}")

        return state


# Compat alias
class SignalDetectionAgent(LLMExplanationNode):
    pass
