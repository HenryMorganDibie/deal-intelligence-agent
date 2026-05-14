"""
Deal Intelligence Agent Graph.
Orchestrates the full analysis pipeline using LangGraph:

  [START] → data_collection → signal_detection → brief_synthesis → [END]

Each node is an async agent that reads/writes AgentState.
Error handling and retry logic are built into each node.
"""
from __future__ import annotations

import time
from typing import Any

from langgraph.graph import StateGraph, START, END

from src.schemas.models import AgentState, AnalysisRequest, AnalystBrief
from src.agents.collection_agent import DataCollectionAgent
from src.agents.signal_agent import SignalDetectionAgent, BriefSynthesisAgent


# ─── Node wrappers (LangGraph requires dict in/dict out) ───────────────────────

def _state_to_dict(state: AgentState) -> dict[str, Any]:
    return state.model_dump(mode="python")


def _dict_to_state(d: dict[str, Any]) -> AgentState:
    return AgentState.model_validate(d)


async def _node_collect(state_dict: dict[str, Any]) -> dict[str, Any]:
    state = _dict_to_state(state_dict)
    agent = DataCollectionAgent()
    state = await agent.run(state)
    return _state_to_dict(state)


async def _node_detect(state_dict: dict[str, Any]) -> dict[str, Any]:
    state = _dict_to_state(state_dict)
    agent = SignalDetectionAgent()
    state = await agent.run(state)
    return _state_to_dict(state)


async def _node_synthesise(state_dict: dict[str, Any]) -> dict[str, Any]:
    state = _dict_to_state(state_dict)
    agent = BriefSynthesisAgent()
    state = await agent.run(state)
    return _state_to_dict(state)


# ─── Graph construction ────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Build and compile the LangGraph agent graph."""
    graph = StateGraph(dict)

    graph.add_node("data_collection",  _node_collect)
    graph.add_node("signal_detection", _node_detect)
    graph.add_node("brief_synthesis",  _node_synthesise)

    graph.add_edge(START,              "data_collection")
    graph.add_edge("data_collection",  "signal_detection")
    graph.add_edge("signal_detection", "brief_synthesis")
    graph.add_edge("brief_synthesis",  END)

    return graph.compile()


# ─── Public entry point ────────────────────────────────────────────────────────

async def run_analysis(request: AnalysisRequest) -> AnalystBrief:
    """
    Run the full deal intelligence analysis pipeline.

    Args:
        request: AnalysisRequest specifying the target company and parameters.

    Returns:
        AnalystBrief: structured, auditable analyst brief with all signals.

    Raises:
        RuntimeError: if the graph fails to produce a brief.
    """
    t0 = time.perf_counter()

    initial_state = AgentState(request=request)
    graph = build_graph()

    final_dict = await graph.ainvoke(_state_to_dict(initial_state))
    final_state = _dict_to_state(final_dict)

    elapsed = time.perf_counter() - t0

    if final_state.brief is None:
        errors = "; ".join(final_state.errors) if final_state.errors else "unknown error"
        raise RuntimeError(f"Analysis failed to produce a brief. Errors: {errors}")

    final_state.brief.processing_time_seconds = round(elapsed, 2)
    return final_state.brief
