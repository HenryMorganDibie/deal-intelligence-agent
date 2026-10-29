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
    ("src.engines.sens_log",           "LOG_PATH",             "sens_announcements.jsonl"),
    ("src.engines.audit_log",          "AUDIT_PATH",           "audit_log.jsonl"),
    ("src.agents.signal_agent",        "LLM_CACHE_PATH",       "llm_cache.json"),
    ("src.engines.backtest",           "BACKTEST_PATH",        "backtest_results.json"),
    ("src.engines.backtest",           "GROUND_TRUTH_PATH",    "ground_truth_events.json"),
    ("src.engines.company_memory",     "MEMORY_PATH",          "company_memory.json"),
    ("src.engines.entity_resolver",    "ENTITY_REGISTRY_PATH", "entity_registry.json"),
    ("src.engines.feedback",           "FEEDBACK_PATH",        "feedback.json"),
    ("src.engines.graph_intelligence", "GRAPH_PATH",           "entity_graph.json"),
    ("src.engines.market_impact",      "OUTCOMES_PATH",        "market_outcomes.json"),
    ("src.engines.monitoring",         "WATCHLIST_PATH",       "watchlist.json"),
    ("src.engines.monitoring",         "ALERTS_PATH",          "alerts.json"),
    ("src.engines.portfolio",          "PORTFOLIO_PATH",       "portfolios.json"),
    ("src.engines.warehouse",          "DB_PATH",              "warehouse.db"),
    ("src.tools.african_prices",       "SNAPSHOT_PATH",        "african_prices.json"),
    ("src.engines.historical_backtest", "RESULTS_PATH",        "historical_backtest.json"),
    ("src.engines.historical_backtest", "REPORT_PATH",         "BACKTEST.md"),
    ("src.engines.historical_backtest", "SUMMARY_PATH",        "backtest_summary.json"),
    ("src.engines.historical_backtest", "CACHE_DIR",           "hist_cache"),
    ("src.engines.historical_backtest", "RUNS_DIR",            "backtest_runs"),
    ("src.engines.backtest_universe",   "UNIVERSE_PATH",       "backtest_universe.csv"),
    ("src.engines.backtest_universe",   "LISTED_NAMES_PATH",   "african_listed_companies.json"),
    ("src.engines.deals",              "DEALS_PATH",           "deals.json"),
    ("src.engines.markets",            "SNAPSHOT_PATH",        "market_snapshot.json"),
    ("src.engines.instruments",        "LOCAL_PATH",           "market_instruments.json"),
    ("src.engines.alpha_scorer",       "_RANKER_PATH",         "learned_ranker.json"),
]


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    import importlib
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for module_name, attr, filename in _STORES:
        module = importlib.import_module(module_name)
        monkeypatch.setattr(module, attr, data_dir / filename)
    # No real LLM keys from the environment: tests set the ones they need.
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GROQ_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    # Keep tests offline and deterministic: no live market-cap lookups.
    alpha_scorer = importlib.import_module("src.engines.alpha_scorer")
    monkeypatch.setattr(alpha_scorer, "_market_cap_usd", lambda ticker: None)
    alpha_scorer._load_learned_ranker.cache_clear()
    # Cached singletons hold data loaded from the previous test's store.
    monkeypatch.setattr(importlib.import_module("src.engines.entity_resolver"), "_resolver", None)
    yield data_dir
    alpha_scorer._load_learned_ranker.cache_clear()
