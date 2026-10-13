"""
Test isolation: every on-disk store the app uses is redirected to a fresh
temporary directory for each test, so tests never read or write the real
data/ directory (audit log, warehouse, memory, outcomes, ...) and never see
each other's state. Module attributes patched with monkeypatch are restored
after each test, which also undoes path overrides made inside test bodies.
"""
from __future__ import annotations

import pytest

# (module, attribute, file name) for every persistent store under data/.
_STORES = [
    ("src.engines.audit_log",          "AUDIT_PATH",           "audit_log.jsonl"),
    ("src.engines.backtest",           "BACKTEST_PATH",        "backtest_results.json"),
    ("src.engines.company_memory",     "MEMORY_PATH",          "company_memory.json"),
    ("src.engines.entity_resolver",    "ENTITY_REGISTRY_PATH", "entity_registry.json"),
    ("src.engines.feedback",           "FEEDBACK_PATH",        "feedback.json"),
    ("src.engines.graph_intelligence", "GRAPH_PATH",           "entity_graph.json"),
    ("src.engines.market_impact",      "OUTCOMES_PATH",        "market_outcomes.json"),
    ("src.engines.monitoring",         "WATCHLIST_PATH",       "watchlist.json"),
    ("src.engines.monitoring",         "ALERTS_PATH",          "alerts.json"),
    ("src.engines.portfolio",          "PORTFOLIO_PATH",       "portfolios.json"),
    ("src.engines.warehouse",          "DB_PATH",              "warehouse.db"),
]


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    import importlib
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for module_name, attr, filename in _STORES:
        module = importlib.import_module(module_name)
        monkeypatch.setattr(module, attr, data_dir / filename)
    # Cached singletons hold data loaded from the previous test's store.
    monkeypatch.setattr(importlib.import_module("src.engines.entity_resolver"), "_resolver", None)
    yield data_dir
