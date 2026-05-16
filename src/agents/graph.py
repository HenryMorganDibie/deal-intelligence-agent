"""
Deal Intelligence Agent Graph — Full Pipeline.

[START]
  → data_collection        (concurrent EDGAR + Africa + news)
  → deterministic_detection (rule engine, zero LLM)
  → llm_explanation         (LLM explains confirmed candidates only)
  → alpha_scoring           (investable ranking, compliance flags)
  → brief_synthesis         (narrative synthesis)
[END]
"""
from __future__ import annotations

import time
from typing import Any

from langgraph.graph import StateGraph, START, END

from src.schemas.models import AgentState, AnalysisRequest, AnalystBrief
from src.agents.collection_agent import DataCollectionAgent
from src.agents.signal_agent import (
    DeterministicDetectionNode,
    LLMExplanationNode,
    AlphaScoringNode,
    BriefSynthesisAgent,
)


def _to_dict(state: AgentState) -> dict[str, Any]:
    return state.model_dump(mode="python")


def _to_state(d: dict[str, Any]) -> AgentState:
    return AgentState.model_validate(d)


async def _node_collect(d: dict[str, Any]) -> dict[str, Any]:
    state = _to_state(d)
    state = await DataCollectionAgent().run(state)
    return _to_dict(state)


def _node_deterministic(d: dict[str, Any]) -> dict[str, Any]:
    state = _to_state(d)
    state = DeterministicDetectionNode().run(state)
    return _to_dict(state)


async def _node_explain(d: dict[str, Any]) -> dict[str, Any]:
    state = _to_state(d)
    state = await LLMExplanationNode().run(state)
    return _to_dict(state)


def _node_alpha(d: dict[str, Any]) -> dict[str, Any]:
    state = _to_state(d)
    state = AlphaScoringNode().run(state)
    return _to_dict(state)


async def _node_synthesise(d: dict[str, Any]) -> dict[str, Any]:
    state = _to_state(d)
    state = await BriefSynthesisAgent().run(state)
    return _to_dict(state)


def build_graph() -> Any:
    g = StateGraph(dict)
    g.add_node("data_collection",          _node_collect)
    g.add_node("deterministic_detection",  _node_deterministic)
    g.add_node("llm_explanation",          _node_explain)
    g.add_node("alpha_scoring",            _node_alpha)
    g.add_node("brief_synthesis",          _node_synthesise)

    g.add_edge(START,                     "data_collection")
    g.add_edge("data_collection",         "deterministic_detection")
    g.add_edge("deterministic_detection", "llm_explanation")
    g.add_edge("llm_explanation",         "alpha_scoring")
    g.add_edge("alpha_scoring",           "brief_synthesis")
    g.add_edge("brief_synthesis",          END)
    return g.compile()


async def run_analysis(request: AnalysisRequest, compliance_mode: bool = False) -> AnalystBrief:
    t0 = time.perf_counter()
    initial = AgentState(request=request, compliance_mode=compliance_mode)
    graph   = build_graph()
    final   = _to_state(await graph.ainvoke(_to_dict(initial)))

    if final.brief is None:
        errors = "; ".join(final.errors) if final.errors else "unknown error"
        raise RuntimeError(f"Analysis failed to produce a brief. Errors: {errors}")

    final.brief.processing_time_seconds = round(time.perf_counter() - t0, 2)
    return final.brief
