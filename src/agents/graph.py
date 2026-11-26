"""
Deal Intelligence Agent Graph — the 7-step pipeline.

[START]
  → data_collection          (concurrent EDGAR + Africa + news)
  → deterministic_detection  (rule engine, zero LLM)
  → llm_explanation          (LLM explains confirmed candidates only)
  → alpha_scoring            (investable ranking + compliance flags)
  → signal_interaction       (compound event detection)
  → brief_synthesis          (narrative synthesis)
  → post_processing          (local SQLite warehouse, company memory, graph intelligence)
[END]
"""
from __future__ import annotations

import inspect
import time
import uuid
from typing import Any, Awaitable, Callable, Union

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

    # Warehouse storage
    try:
        from src.engines.warehouse import store_analysis_run
        store_analysis_run(run_id, state.brief)
    except ImportError:
        pass                                           # local store; the hosted API does not install it
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
        update_graph_from_brief(state.brief, state.company_profile.insiders if state.company_profile else None)
    except ImportError:
        pass                                           # local graph; the hosted API does not install networkx
    except Exception as e:
        state.errors.append(f"Graph update failed (non-fatal): {e}")

    log_state(state, "post_processing", f"Run {run_id} stored")
    return _to_dict(state)


Node = Callable[[dict[str, Any]], Union[dict[str, Any], Awaitable[dict[str, Any]]]]

# The pipeline is a straight line, so it runs as an ordered list of steps. A graph library added about 30 MB of
# packages to every cold start of the hosted API for no branching it used.
PIPELINE: tuple[tuple[str, Node], ...] = (
    ("data_collection",         _node_collect),
    ("deterministic_detection", _node_deterministic),
    ("llm_explanation",         _node_explain),
    ("alpha_scoring",           _node_alpha),
    ("signal_interaction",      _node_interaction),
    ("brief_synthesis",         _node_synthesise),
    ("post_processing",         _node_post_process),
)


class _Pipeline:
    def __init__(self, steps: tuple[tuple[str, Node], ...]):
        self.steps = steps

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        for _name, step in self.steps:
            result = step(state)
            if inspect.isawaitable(result):
                result = await result
            state = {**state, **(result or {})}
        return state


def build_graph() -> _Pipeline:
    return _Pipeline(PIPELINE)


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
