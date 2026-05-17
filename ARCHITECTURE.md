# Architecture & Roadmap

This document is the authoritative technical reference for the Deal Intelligence Agent system — written from the perspective of a fund technology reviewer. It covers current capabilities, honest limitations, the engineering decisions behind each layer, and the path forward.

---

## Core Architectural Principle

**Deterministic system = truth layer. LLM system = explanation layer.**

The LLM never originates a signal. It never escalates severity. It never fires a compound event. Every decision that could affect an investment recommendation is made by a deterministic, reproducible, auditable rule engine. The LLM's only job is to write clear analyst-readable explanations of what the deterministic engine already confirmed.

This principle is enforced structurally in the graph — the LLM node receives only pre-confirmed `SignalCandidate` objects. If the deterministic engine produces zero candidates, the LLM node receives nothing and produces nothing.

---

## Pipeline Architecture (8 Nodes)

```
AnalysisRequest
      │
      ▼
Node 1 — DataCollectionAgent
  Three concurrent async pipelines:
    ├── SEC EDGAR (US): company CIK resolution, filings (8-K/10-K/10-Q/SC13D/Form4), full-text keyword search
    ├── Africa Tool: NGX/JSE SENS/NSE Kenya/GSE disclosures, 37 RSS feeds, 29 PE/DFI/regulatory sources (HTML scraped)
    └── Global News: Reuters/Bloomberg/FT/Yahoo Finance/Moneyweb/BusinessDay/TechCabal...
  Each pipeline fails independently. Merge + deduplicate all sources.
  Output: state.filings, state.news_items, state.company_profile
      │
      ▼
Node 2 — DeterministicSignalEngine                     ← ZERO LLM
  70+ typed regex rules across 8 signal categories.
  Named entity extraction (companies, amounts, percentages).
  Source credibility weighting (SEC filing = 1.0, unknown blog = 0.40).
  Corroboration merging: same signal type from multiple sources → merged candidate.
  Hard rule: if zero candidates produced → zero signals in final brief. No exceptions.
  Output: state.signal_candidates (SignalCandidate[])
      │
      ▼
Node 3 — LLMExplanationNode                            ← LLM (explanation only)
  Receives only confirmed SignalCandidates.
  Semantic evidence extraction runs first (extract typed clauses from source text).
  Adaptive calibration derives severity from outcome-adjusted base rates.
  Confidence decomposition: 7-component breakdown replaces opaque float.
  LLM writes: headline, evidence list, reasoning. Cannot change signal_type or severity.
  Fallback: if LLM API fails, deterministic output used directly.
  Output: state.detected_signals (DetectedSignal[])
      │
      ▼
Node 4 — AlphaScoringNode                              ← ZERO LLM
  Composite 0–100 alpha score per signal:
    severity_weight × 0.35 + source_credibility × 0.25 +
    corroboration × 0.20 + recency_decay × 0.10 + liquidity_tier × 0.10
  Expected move estimates from historical comparable events (14–91 cases per signal type).
  Compliance flags: human review triggered above alpha 70 or CRITICAL severity.
  Output: state.detected_signals with alpha_score attached
      │
      ▼
Node 5 — SignalInteractionEngine                       ← ZERO LLM
  14 typed interaction rules across compound event categories.
  Matches combinations of detected signals against rule library.
  Produces CompoundSignal objects: interaction_type, escalation_score, alpha_multiplier.
  Applies alpha multipliers back to participating signals.
  Example rules:
    CEO departure + covenant breach + insider selling → CASCADING distress (2.5× alpha)
    Activist 13D + M&A language → REINFORCING deal probability (1.8× alpha)
    M&A language + formal distress → CONTRADICTORY, reduce confidence
  Output: state.compound_signals, updated state.detected_signals
      │
      ▼
Node 6 — BriefSynthesisAgent                          ← LLM (narrative only)
  All signal data is locked before LLM runs. LLM writes narrative only.
  Compliance mode: suppresses signals below 0.40 confidence, adds disclaimers.
  Human review flags propagated from alpha scorer to brief.
  Output: state.brief (AnalystBrief)
      │
      ▼
Node 7 — PostProcessingNode                            ← ZERO LLM
  Warehouse storage (SQLite): filings, news, candidates, signals, compounds, brief.
  Company memory update: EMA rolling risk scores, trend detection, signal density.
  Entity graph update: company node added/updated in NetworkX relationship graph.
  All post-processing failures are non-fatal (errors logged, pipeline continues).
  Output: state.brief (unchanged), warehouse/memory/graph updated
      │
      ▼
AnalystBrief → Terminal (Rich) | JSON | Markdown
```

---

## Engine Layer Reference

### 1. Signal Interaction Engine (`engines/signal_interaction.py`)
Reasons over combinations of 2+ detected signals using 14 typed interaction rules. Produces `CompoundSignal` objects with `InteractionType` (reinforcing/cascading/escalating/converging/contradictory), `escalation_score`, `alpha_multiplier`, and `systemic_risk_level`. Alpha multipliers are applied back to individual signal scores — a signal involved in a compound escalation can see up to 2.5× alpha boost.

### 2. Historical Event Warehouse (`engines/warehouse.py`)
SQLite database (7 tables) storing every pipeline artifact: filings, news, signal candidates, detected signals, compound events, analyst briefs, market outcomes, replay runs, scoring history. Enables retrospective analysis, backtesting, longitudinal trend tracking, and calibration. `EventWarehouse` class provides typed read/write API.

### 3. Deterministic Replay Engine (`engines/replay.py`)
Loads historical data from the warehouse filtered to a specific as-of date. Re-runs the full deterministic pipeline (engine + calibration + alpha) without any LLM, using locked rule/scoring/prompt versions from a `CONFIG_SNAPSHOT`. Stores replay results alongside originals for diff comparison. `compare_runs()` produces signal-level diffs.

### 4. Company Memory (`engines/company_memory.py`)
Persistent longitudinal risk profiles (`CompanyRiskProfile`) updated on every analysis run via EMA. Tracks: rolling risk score, governance/liquidity/credit/regulatory dimension scores, event velocity (signals/30d), risk trend (improving/stable/deteriorating), 30d delta, leadership change count, debt restructure count, regulatory action count, alpha score history (last 20), repeated signal patterns, analyst attention score.

### 5. Confidence Decomposition (`engines/confidence.py`)
Replaces opaque single confidence floats with a 7-component auditable breakdown: source_reliability (70% static + 30% learned EMA), corroboration (sigmoid-shaped), filing_strength (by filing type), historical_precision (from feedback stats), entity_match (by NER count), temporal_relevance (exponential decay, 21-day half-life), extraction_confidence (by pattern count). Weighted sum → `final_confidence`. Includes `reasoning` string explaining any deficiencies.

### 6. Semantic Evidence Extraction (`engines/semantic.py`)
Extracts typed financial evidence clauses from source text using 9 clause template categories: going_concern, covenant_breach, merger_language, restructuring_clause, insolvency_formal, impairment_statement, litigation_language, liquidity_stress, governance_deterioration. Each extraction includes: clause_text, context window, confidence score, entity subject, financial amount, temporal marker. Runs before LLM explanation to enrich candidate context.

### 7. Adaptive Calibration (`engines/adaptive_calibration.py`)
Wraps static calibration tables with outcome-aware adjustments. When ≥10 feedback samples exist for a signal type, derives a precision_adjustment (0.5 + precision) and false_positive_penalty (1.0 − fp_rate × 0.5) and compounds them with the static score. Sector-specific precision maps applied where available. Net effect: signal types with proven track records get higher effective scores; chronic false positives get penalised automatically.

### 8. Market Impact & Outcome Modeling (`engines/market_impact.py`)
Records actual market reactions after signals are raised: 5d/10d/30d price moves, event confirmation, direction accuracy, magnitude error vs expected move. Aggregates accuracy metrics across all recorded outcomes and per signal type. Feeds into adaptive calibration. `get_accuracy_metrics()` returns system-level intelligence quality report.

### 9. Deterministic Engine (`engines/deterministic_engine.py`)
70+ typed regex rules in 3 specificity tiers per signal type (high/medium/low base scores: 0.88–0.95 / 0.72–0.80 / 0.50–0.60). Named entity extraction for companies (suffix patterns), amounts (multi-currency), percentages. Source credibility lookup table (31 sources, 0.40–1.00). Corroboration merging: multiple sources for same signal type merged into single candidate with boosted corroboration_count.

### 10. Signal Registry (`engines/signal_registry.py`)
Centralised `SignalSpec` dataclass for each signal type: display name, description, version, pattern tiers, semantic evidence types, corroboration rules, escalation relationships, historical precision. Single source of truth for all signal metadata. Enables modular testing, calibration, and expansion without touching detection logic.

### 11. Cross-Signal Graph Intelligence (`engines/graph_intelligence.py`)
NetworkX-based entity relationship graph. Nodes: companies, executives, lenders, regulators. Edges: employed_by, lends_to, board_overlap, acquired, regulates. Operations: `detect_contagion_risk()` (lenders at risk, board-connected companies, regulatory watchers), `get_connected_companies()` (N-hop traversal), `get_shared_executives()`, `get_acquisition_chain()`. Graph persisted to `data/entity_graph.json`. Auto-updated from every brief.

### 12. Feedback Loop (`engines/feedback.py`)
Analyst corrections stored in `data/feedback.json`. Tracks false positives, confirmations, missed events, severity corrections. Computes rolling precision/recall per signal type. Updates source reliability via EMA (α=0.15). `false_positive_rate()` consumed by adaptive calibration. `get_signal_stats()` drives confidence decomposition's `historical_precision_score`.

### 13. Monitoring Engine (`engines/monitoring.py`)
Watchlist-driven continuous monitoring. `MonitoringEngine.run_once()` runs full pipeline for all watched companies and returns triggered alerts. `run_continuous()` loops on configurable interval. Alert delivery: terminal, webhook (generic), Slack (formatted blocks via incoming webhook). Alert thresholds configurable per company (severity + alpha). Alerts persisted to `data/alerts.json`.

### 14. Audit Log (`engines/audit_log.py`)
Append-only JSONL file with SHA-256 hash chain. Every pipeline decision: step name, company, action, detail, data snapshot. Each entry's `data_hash` is SHA-256 of its own content. `prev_hash` chains to the previous entry. `verify_chain()` validates full chain integrity — tampering with any entry breaks all subsequent hashes. Compliance-grade: cannot be silently modified.

---

## Honest Limitations

### 1. Signal Taxonomy Is Empirically Seeded, Not Backtested
Base rate tables in `calibration.py` are grounded in published research (Ince & Porter 2006, Mitchell & Mulherin 1996, Bhana JSE 2010, AVCA Annual Reports 2018–2023) but have not been backtested against a proprietary outcome dataset. They represent informed priors, not statistically validated precision/recall curves. Adaptive calibration begins correcting this as feedback accumulates, but the system needs 10+ analyst-confirmed outcomes per signal type before adaptive mode activates.

### 2. African Market Calibration Is Thinner
The base rate tables were developed primarily from US/global research. African market dynamics — thinner liquidity, fewer public disclosures, different regulatory timelines — may produce systematically different materialisation rates. The adaptive calibration layer will correct for this over time, but early deployments on African companies should treat severity scores with additional caution.

### 3. LLM Non-Determinism in Explanation Layer
Even with the deterministic engine gating signals, the LLM explanation text is non-deterministic. Two runs with identical candidates may produce slightly different headlines or evidence lists. This does not affect signal type, severity, confidence, or alpha score (all deterministic) — but it means the explanation text cannot be reproduced exactly. The `reasoning_trace` records what the LLM was shown, enabling post-hoc review.

### 4. No Real-Time Market Data Integration
Alpha scores include expected move estimates from historical comparables, but the system does not connect to live price feeds, bond spreads, or options markets. The `market_impact.py` module records outcomes after the fact via analyst input — it does not auto-fetch prices. Production integration would require a market data provider (Bloomberg, Refinitiv, or free alternatives like yfinance).

### 5. Graph Intelligence Is Bootstrap-Phase
The entity relationship graph (`graph_intelligence.py`) is populated from briefs and manual additions. Without a pre-loaded dataset of known relationships (board memberships, lender networks, acquisition histories), the graph starts empty and builds incrementally. Network effects — second-order contagion, board overlap detection — only become meaningful after sustained operation.

---

## Upgrade Roadmap

| Phase | What | Status |
|-------|------|--------|
| Separation of concerns | Deterministic engine + LLM explanation layer | ✅ Done |
| Alpha score layer | 0–100 investable rankings + expected move estimates | ✅ Done |
| Compound event engine | Signal interaction rules + escalation multipliers | ✅ Done |
| Institutional audit | Hash-chained audit log + compliance mode | ✅ Done |
| Feedback loop | False positive tracking + source EMA + precision/recall | ✅ Done |
| Confidence decomposition | 7-component auditable breakdown | ✅ Done |
| Semantic extraction | Typed financial clause extraction | ✅ Done |
| Adaptive calibration | Outcome-aware severity adjustment | ✅ Done |
| Market outcome modeling | Direction accuracy + magnitude error tracking | ✅ Done |
| Signal registry | Modular, versioned signal specifications | ✅ Done |
| Graph intelligence | Entity relationship graph + contagion detection | ✅ Done |
| Historical warehouse | SQLite event store across all pipeline artifacts | ✅ Done |
| Replay engine | Deterministic as-of-date historical reproduction | ✅ Done |
| Company memory | Longitudinal EMA risk profiles + trend detection | ✅ Done |
| Real-time monitoring | Watchlist + Slack/webhook alerting | ✅ Done |
| Backtested signal engine | Validate rules vs historical market moves at scale | Next |
| ML severity model | Replace base rate tables with trained outcome model | Next |
| Live market data | Real-time price/spread feeds for outcome auto-tracking | Next |
| Multi-user team mode | Shared watchlists, portfolio briefs, role-based access | Planned |
| Research dashboard | React frontend: risk timelines, signal heatmaps, replay UI | Planned |
| Graph pre-population | Bulk load known entity relationships from public data | Planned |

---

*Last updated: May 2026. Maintained alongside codebase.*
