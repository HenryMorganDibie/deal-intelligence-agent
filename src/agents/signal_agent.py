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

import hashlib
import json
import re
from datetime import datetime
from typing import Any

import os
import anthropic
try:
    from groq import Groq as GroqClient
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False

from src.schemas.models import (
    AgentState, AnalystBrief, DetectedSignal, RiskFactor, KeyMetric,
    SignalType, Severity, SignalCandidate, LiquidityTier
)
from src.engines.deterministic_engine import DeterministicSignalEngine
from src.engines.signal_interaction import _get_systemic_risk
from src.engines.adaptive_calibration import adaptive_calibrate
from src.engines.alpha_scorer import score_all_signals, LOW_CONFIDENCE_SUPPRESS_THRESHOLD
from src.engines.confidence import decompose
from src.engines.semantic import extract_from_filing, extract_from_news, evidence_to_strings
from src.engines.audit_log import log_state
from src.utils.clock import utcnow
from src.utils.paths import DATA_DIR
from src.utils.storage import load_json, save_json

# ─── LLM Provider Selection ───────────────────────────────────────────────────
# Set DEAL_INTEL_PROVIDER=groq to use Groq/Llama (free, good for testing).
# Default is Anthropic Claude (production quality). DEAL_INTEL_ANTHROPIC_MODEL and
# DEAL_INTEL_EFFORT override the Claude model and its effort level.
PROVIDER = os.getenv("DEAL_INTEL_PROVIDER", "anthropic").lower()

ANTHROPIC_MODEL  = os.getenv("DEAL_INTEL_ANTHROPIC_MODEL", "claude-opus-5-5")
ANTHROPIC_EFFORT = os.getenv("DEAL_INTEL_EFFORT", "high")
GROQ_MODEL       = "llama-3.3-70b-versatile"
MODEL            = GROQ_MODEL if PROVIDER == "groq" else ANTHROPIC_MODEL

# Thinking is always on for current Claude models and counts toward max_tokens,
# so the Anthropic path reserves room for it on top of the caller's reply budget.
_THINKING_HEADROOM = 12000


def _get_llm_client():
    """Return (client, provider) tuple based on DEAL_INTEL_PROVIDER env var."""
    if PROVIDER == "groq":
        if not _GROQ_AVAILABLE:
            raise RuntimeError("groq package not installed. Run: pip install groq")
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY environment variable not set.")
        return GroqClient(api_key=api_key), "groq"
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        raise RuntimeError("no LLM API key is configured (ANTHROPIC_API_KEY is not set).")
    return anthropic.Anthropic(), "anthropic"


# Identical requests return the stored reply, so re-running or replaying an analysis
# over the same sources gives the same explanation text. LLM sampling is otherwise
# not reproducible. The key covers everything that shapes the reply. Disable with
# DEAL_INTEL_LLM_CACHE=0.
LLM_CACHE_PATH = DATA_DIR / "llm_cache.json"
_LLM_CACHE_MAX = 2000


def _llm_cache_key(provider: str, system: str, user: str, max_tokens: int) -> str:
    model = GROQ_MODEL if provider == "groq" else f"{ANTHROPIC_MODEL}|{ANTHROPIC_EFFORT}"
    payload = json.dumps([provider, model, system, user, max_tokens], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _call_llm(client, provider: str, system: str, user: str, max_tokens: int = 3000) -> str:
    """LLM call through the reproducibility cache (see LLM_CACHE_PATH)."""
    if os.getenv("DEAL_INTEL_LLM_CACHE", "1") == "0":
        return _call_llm_uncached(client, provider, system, user, max_tokens)
    key = _llm_cache_key(provider, system, user, max_tokens)
    cache: dict = load_json(LLM_CACHE_PATH, dict)
    if key in cache:
        return cache[key]["text"]
    text = _call_llm_uncached(client, provider, system, user, max_tokens)
    cache[key] = {"text": text, "at": utcnow().isoformat()}
    if len(cache) > _LLM_CACHE_MAX:   # drop the oldest entries
        for old in sorted(cache, key=lambda k: cache[k]["at"])[: len(cache) - _LLM_CACHE_MAX]:
            del cache[old]
    save_json(LLM_CACHE_PATH, cache)
    return text


def _call_llm_uncached(client, provider: str, system: str, user: str, max_tokens: int = 3000) -> str:
    """
    Unified LLM call that works with both Anthropic and Groq.
    Returns the response text string.
    Groq uses the OpenAI-compatible messages format; Anthropic uses its own.
    """
    if provider == "groq":
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        return response.choices[0].message.content or ""
    else:
        response = client.beta.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens + _THINKING_HEADROOM,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": ANTHROPIC_EFFORT},
            # On a safety-classifier decline, retry on the model Anthropic recommends.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            raise RuntimeError(f"Claude declined the request (category: {category})")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("Claude response hit max_tokens; output truncated")
        # The response can begin with thinking blocks; read text blocks by type.
        return "".join(b.text for b in response.content if b.type == "text")

_SEVERITY_RANK = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2, Severity.CRITICAL: 3}

EXPLANATION_SYSTEM = """You are a senior financial analyst writing explanations for pre-confirmed deal intelligence signals.

IMPORTANT: These signals were detected by a deterministic pattern-matching engine, not by you.
Your job is ONLY to:
1. Write a clear, professional headline for each signal
2. List the specific evidence from the source material
3. Explain the significance and context in plain analyst language
4. Note any ambiguities or caveats
5. Say whether the evidence is actually about the named company, or about another
   company that only mentions it in passing (e.g. a rival's results that refer to
   a deal involving it)

You MUST NOT invent new signals. You MUST NOT change the signal_type or severity.
You MUST reference only evidence present in the source material provided.

For each signal candidate, return a JSON object:
{
  "signal_type": "<same as input>",
  "headline": "<crisp one-line description>",
  "evidence": ["<specific fact from source>", "<specific fact>"],
  "reasoning": "<2-3 sentences of professional analyst context>",
  "about_company": true,
  "attribution_note": "<if about_company is false: which company the evidence is really about, and why>"
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
    seen: set[SignalType] = set()
    for item in data:
        try:
            if not isinstance(item, dict):
                continue
            raw_type = str(item.get("signal_type") or "").lower().replace(" ", "_").replace("-", "_")
            try:
                sig_type = SignalType(raw_type)
            except ValueError:
                continue

            cand = cand_map.get(sig_type)
            if cand is None or sig_type in seen:
                continue
            seen.add(sig_type)

            evidence = item.get("evidence") or []
            if isinstance(evidence, str):
                evidence = [evidence]
            evidence = [str(e) for e in evidence if e]

            sev, conf, _ = cal_map.get(sig_type, (Severity.LOW, 0.5, 0.1))

            signals.append(DetectedSignal(
                signal_type=sig_type,
                severity=sev,
                headline=str(item.get("headline") or f"{sig_type.value.replace('_',' ').title()} detected"),
                evidence=evidence or [cand.source_text[:200]],
                source_urls=[cand.source_url] if cand.source_url else [],
                filing_references=[cand.filing_reference] if cand.filing_reference else [],
                confidence=conf,
                reasoning=str(item.get("reasoning") or ""),
                attribution_doubt=(
                    str(item.get("attribution_note") or "evidence appears to concern another company")
                    if item.get("about_company") is False else None
                ),
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
        self.client_error = ""
        try:
            self.client, self.provider = _get_llm_client()
        except Exception as e:
            self.client, self.provider, self.client_error = None, PROVIDER, str(e)

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
            kept = [
                (c, sev, conf, mr) for c, sev, conf, mr in calibrated
                if conf >= LOW_CONFIDENCE_SUPPRESS_THRESHOLD
            ]
            state.low_confidence_signals_suppressed = len(calibrated) - len(kept)
            calibrated = kept

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
            if self.client is None:
                raise RuntimeError(self.client_error)
            raw = _call_llm(self.client, self.provider, EXPLANATION_SYSTEM, user_prompt, max_tokens=3000)
            signals = _parse_explanations(raw, candidates_for_llm, calibrated, state)
            # The LLM explains signals; it must not be able to drop one by omission.
            explained = {s.signal_type for s in signals}
            missing = [row for row in calibrated if row[0].signal_type not in explained]
            if missing:
                state.errors.append(
                    f"LLM omitted {len(missing)} confirmed signal(s); deterministic output used for those"
                )
                signals += _fallback_signals(missing)
            state.detected_signals = signals
            log_state(state, "llm_explanation", f"{len(signals)} signals explained")
        except Exception as e:
            state.errors.append(f"LLMExplanationNode error: {e}")
            state.detected_signals = _fallback_signals(calibrated)

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
        # Attach the evidence-quality breakdown for each signal's originating candidate.
        cand_map = {c.signal_type: c for c in state.signal_candidates}
        state.detected_signals = [
            s.model_copy(update={"confidence_decomposition": decompose(cand_map[s.signal_type])})
            if s.signal_type in cand_map else s
            for s in state.detected_signals
        ]
        log_state(state, "alpha_scoring", "Alpha scores attached")
        return state


class BriefSynthesisAgent:
    def __init__(self):
        self.client_error = ""
        try:
            self.client, self.provider = _get_llm_client()
        except Exception as e:
            self.client, self.provider, self.client_error = None, PROVIDER, str(e)

    async def run(self, state: AgentState) -> AgentState:
        state.log("brief_synthesis", "Synthesising analyst brief")
        # The requested name is the brief's identity: outcomes, portfolios and the
        # backtest are keyed on the name the analyst types, not on the SEC legal name.
        company = state.request.company_name
        legal   = state.company_profile.name if state.company_profile else None
        ticker  = state.request.ticker or (state.company_profile.ticker if state.company_profile else None)

        signals_json = json.dumps(
            [s.model_dump(mode="json", exclude={"alpha_score"}) for s in state.detected_signals],
            indent=2
        )

        review_reasons = [
            f"{sig.signal_type.value.replace('_', ' ').title()}: {sig.alpha_score.review_reason}"
            for sig in state.detected_signals
            if sig.alpha_score and sig.alpha_score.requires_human_review and sig.alpha_score.review_reason
        ] + [
            f"{sig.signal_type.value.replace('_', ' ').title()}: attribution doubt: {sig.attribution_doubt}"
            for sig in state.detected_signals if sig.attribution_doubt
        ]

        # Low-confidence signals are removed before explanation, so they are no
        # longer in detected_signals; the count is recorded at that point.
        suppressed = state.low_confidence_signals_suppressed if state.compliance_mode else 0

        compounds_json = json.dumps(
            [
                {
                    "signal_types": [t.value for t in c.component_signal_types],
                    "interaction": c.interaction_type.value,
                    "escalation_score": c.escalation_score,
                    "systemic_risk_level": c.systemic_risk_level.value,
                    "reasoning": c.reasoning_chain,
                }
                for c in state.compound_signals
            ],
            indent=2,
        )

        user_prompt = (
            f"Company: {company} ({ticker or 'private'})"
            + (f", legal name {legal}" if legal and legal.lower() != company.lower() else "") + "\n"
            f"Signals confirmed: {len(state.detected_signals)}\n"
            f"Sources reviewed: {len(state.filings)} filings, {len(state.news_items)} news items\n"
            f"Compliance mode: {'ON' if state.compliance_mode else 'OFF'}\n\n"
            f"CONFIRMED SIGNALS:\n{signals_json}\n\n"
            f"COMPOUND EVENTS (deterministic):\n{compounds_json}\n\nWrite the synthesis."
        )

        data: dict = {}
        narrative_error: str | None = None
        try:
            if self.client is None:
                raise RuntimeError(self.client_error)
            raw = _call_llm(self.client, self.provider, SYNTHESIS_SYSTEM, user_prompt, max_tokens=2500)
            raw = re.sub(r"```json|```", "", raw).strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                data = json.loads(match.group()) if match else {}
            if not isinstance(data, dict):
                data = {}
        except Exception as e:
            # The narrative is optional; the deterministic findings are not.
            narrative_error = str(e)
            state.errors.append(f"BriefSynthesisAgent error: {e}")
            review_reasons = review_reasons + [
                f"LLM narrative synthesis unavailable: {narrative_error[:200]}"
            ]


        def _text(key: str, default: str = "") -> str:
            v = data.get(key)
            return str(v).strip() if v not in (None, "") else default

        risk_factors = []
        for rf in data.get("risk_factors", []):
            try:
                risk_factors.append(RiskFactor(
                    factor=str(rf.get("factor") or ""), impact=str(rf.get("impact") or ""),
                    likelihood=Severity(str(rf.get("likelihood") or "medium").lower()),
                    mitigation=str(rf["mitigation"]) if rf.get("mitigation") else None,
                ))
            except Exception:
                pass

        key_metrics = []
        for km in data.get("key_metrics", []):
            try:
                key_metrics.append(KeyMetric(
                    name=str(km.get("name") or ""), value=str(km.get("value") or ""),
                    period=str(km.get("period") or ""),
                    interpretation=str(km.get("interpretation") or ""),
                ))
            except Exception:
                pass

        try:
            overall_sev = Severity(_text("overall_severity", "low" if narrative_error else "medium").lower())
        except ValueError:
            overall_sev = Severity.MEDIUM
        # Severity is calibrated deterministically; the narrative layer may
        # not rate the brief below its most severe confirmed signal.
        if state.detected_signals:
            floor = max((s.severity for s in state.detected_signals), key=_SEVERITY_RANK.get)
            if _SEVERITY_RANK[floor] > _SEVERITY_RANK[overall_sev]:
                overall_sev = floor

        try:
            confidence = max(0.0, min(1.0, float(data.get("confidence_score", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        if narrative_error:
            sigs = state.detected_signals
            confidence = round(sum(s.confidence for s in sigs) / len(sigs), 3) if sigs else 0.0

        recent = data.get("recent_developments") or []
        if isinstance(recent, str):
            recent = [recent]
        recent = [str(r) for r in recent if r]

        top_alpha = None
        top_liq   = None
        scored = [s for s in state.detected_signals if s.alpha_score]
        if scored:
            best = max(scored, key=lambda s: s.alpha_score.score)
            top_alpha = best.alpha_score.score
            top_liq   = best.alpha_score.liquidity_tier

        compliance_flags = []
        if state.compliance_mode:
            if suppressed:
                compliance_flags.append(f"{suppressed} low-confidence signal(s) suppressed")
            if review_reasons:
                compliance_flags.append(f"{len(review_reasons)} signal(s) require human review")
            compliance_flags.append("Output is AI-generated, unverified, not investment advice")

        state.brief = AnalystBrief(
            company_name=company, ticker=ticker,
            analyst_model=("deterministic engine only (LLM unavailable)" if narrative_error
                           else GROQ_MODEL if self.provider == "groq" else ANTHROPIC_MODEL),
            executive_summary=_text("executive_summary", (
                f"Narrative synthesis unavailable. {len(state.detected_signals)} signal(s) were "
                f"confirmed by the deterministic engine and are listed below."
                if narrative_error else "Analysis complete."
            )),
            overall_severity=overall_sev,
            recommendation=_text("recommendation", (
                "Review the confirmed signals and their sources directly before acting."
                if narrative_error else "Further review recommended."
            )),
            confidence_score=confidence,
            detected_signals=state.detected_signals,
            signal_candidates_count=len(state.signal_candidates),
            top_alpha_score=top_alpha, liquidity_tier=top_liq,
            requires_human_review=bool(review_reasons),
            human_review_reasons=review_reasons,
            key_metrics=key_metrics, risk_factors=risk_factors,
            competitive_context=_text("competitive_context") or None,
            recent_developments=recent,
            filings_reviewed=state.filings, news_reviewed=state.news_items,
            total_sources=len(state.filings) + len(state.news_items),
            compliance_mode=state.compliance_mode,
            compliance_flags=compliance_flags,
            low_confidence_signals_suppressed=suppressed,
            compound_signals=state.compound_signals,
            systemic_risk_level=_get_systemic_risk(state.compound_signals),
            reasoning_trace=state.reasoning_trace,
            audit_entries=state.audit_entries,
        )
        log_state(state, "brief_synthesis",
                  "Brief complete" + (" (deterministic fallback)" if narrative_error else ""))
        return state


# Compat alias
class SignalDetectionAgent(LLMExplanationNode):
    pass
