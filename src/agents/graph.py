"""
Deal Intelligence Agent Graph — Full 8-Node Pipeline.

[START]
  → data_collection          (concurrent EDGAR + Africa + news)
  → deterministic_detection  (rule engine, zero LLM)
  → llm_explanation          (LLM explains confirmed candidates only)
  → alpha_scoring            (investable ranking + compliance flags)
  → signal_interaction       (compound event detection)
  → brief_synthesis          (narrative synthesis)
  → post_processing          (warehouse, company memory, graph intelligence)
[END]
"""
from __future__ import annotations

import time
import uuid
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
from src.engines.signal_interaction import SignalInteractionEngine
from src.engines.audit_log import log_state


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


def _node_interaction(d: dict[str, Any]) -> dict[str, Any]:
    state = _to_state(d)
    state = SignalInteractionEngine().run(state)
    return _to_dict(state)


async def _node_synthesise(d: dict[str, Any]) -> dict[str, Any]:
    state = _to_state(d)
    state = await BriefSynthesisAgent().run(state)
    return _to_dict(state)


async def _node_post_process(d: dict[str, Any]) -> dict[str, Any]:
    """
    Post-processing node: warehouse storage, company memory update,
    entity graph update. All failures are non-fatal.
    """
    state = _to_state(d)
    if state.brief is None:
        return _to_dict(state)

    run_id = str(uuid.uuid4())

    # Attach compound signals to brief
    if state.compound_signals and hasattr(state.brief, 'compound_signals'):
        state.brief = state.brief.model_copy(update={
            "compound_signals": state.compound_signals
        })

    # Warehouse storage
    try:
        from src.engines.warehouse import store_analysis_run
        store_analysis_run(run_id, state.brief)
    except Exception as e:
        state.errors.append(f"Warehouse storage failed (non-fatal): {e}")

    # Company memory update
    try:
        from src.engines.company_memory import update_profile
        update_profile(state.brief)
    except Exception as e:
        state.errors.append(f"Company memory update failed (non-fatal): {e}")

    # Entity graph update
    try:
        from src.engines.graph_intelligence import update_graph_from_brief
        update_graph_from_brief(state.brief)
    except Exception as e:
        state.errors.append(f"Graph update failed (non-fatal): {e}")

    log_state(state, "post_processing", f"Run {run_id} stored")
    return _to_dict(state)


def build_graph() -> Any:
    g = StateGraph(dict)
    g.add_node("data_collection",         _node_collect)
    g.add_node("deterministic_detection", _node_deterministic)
    g.add_node("llm_explanation",         _node_explain)
    g.add_node("alpha_scoring",           _node_alpha)
    g.add_node("signal_interaction",      _node_interaction)
    g.add_node("brief_synthesis",         _node_synthesise)
    g.add_node("post_processing",         _node_post_process)

    g.add_edge(START,                     "data_collection")
    g.add_edge("data_collection",         "deterministic_detection")
    g.add_edge("deterministic_detection", "llm_explanation")
    g.add_edge("llm_explanation",         "alpha_scoring")
    g.add_edge("alpha_scoring",           "signal_interaction")
    g.add_edge("signal_interaction",      "brief_synthesis")
    g.add_edge("brief_synthesis",         "post_processing")
    g.add_edge("post_processing",         END)
    return g.compile()


async def run_analysis(request: AnalysisRequest, compliance_mode: bool = False) -> AnalystBrief:
    t0      = time.perf_counter()
    initial = AgentState(request=request, compliance_mode=compliance_mode)
    graph   = build_graph()
    final   = _to_state(await graph.ainvoke(_to_dict(initial)))

    if final.brief is None:
        errors = "; ".join(final.errors) if final.errors else "unknown error"
        raise RuntimeError(f"Analysis failed to produce a brief. Errors: {errors}")

    final.brief.processing_time_seconds = round(time.perf_counter() - t0, 2)
    return final.brief
