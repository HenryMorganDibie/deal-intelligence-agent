# Architecture & Roadmap

Authoritative technical reference for the Deal Intelligence Agent. Written from the perspective of a fund technology reviewer.

---

## Core Architectural Principle

**Deterministic system = truth layer. LLM system = explanation layer.**

The LLM never originates a signal. It never escalates severity. It never fires a compound event. Every decision that affects an investment recommendation is made by a deterministic, reproducible, auditable rule engine. The LLM's only job is to write clear analyst-readable explanations of what the deterministic engine already confirmed. This is enforced structurally — the LLM node receives only pre-confirmed `SignalCandidate` objects. Zero candidates → zero signals. No exceptions.

---

## Pipeline Architecture (8 Nodes)

```
AnalysisRequest
      │
      ▼
Node 1 — DataCollectionAgent
  Three concurrent async pipelines (each fails independently):
    ├── SEC EDGAR: CIK resolution, 8-K/10-K/10-Q/SC13D/Form4, full-text keyword search
    ├── Africa Tool: NGX/JSE SENS/NSE Kenya/GSE + EGX/Casablanca/BRVM + 49 RSS feeds + 48 PE/DFI/regulatory sources
    └── Global News: Reuters/Bloomberg/FT/Yahoo Finance + all African media
  Merge + deduplicate across all sources.
      │
      ▼
Node 2 — DeterministicSignalEngine                     ← ZERO LLM
  70+ typed regex rules (3 specificity tiers) × 8 signal types.
  Named entity extraction: companies, multi-currency amounts, percentages.
  Source credibility registry: 35+ sources rated 0.40–1.00.
  Corroboration merging: same signal type from multiple sources → merged candidate.
  Semantic evidence extraction: 9 typed financial clause categories enriching candidates.
  Hard rule: zero candidates → zero signals → no LLM call.
      │
      ▼
Node 3 — LLMExplanationNode                            ← LLM (explanation only)
  Adaptive calibration derives severity from outcome-adjusted base rates.
  7-component confidence decomposition replaces opaque float.
  LLM writes: headline, evidence list, 2-3 sentence reasoning. Cannot change signal_type or severity.
  Fallback: if LLM API fails, deterministic output used directly (no crash).
      │
      ▼
Node 4 — AlphaScoringNode                              ← ZERO LLM
  0–100 composite score: severity×0.35 + credibility×0.25 + corroboration×0.20 + recency×0.10 + liquidity×0.10
  Expected move estimates from 14–91 historical comparables per signal type.
  SHAP-style explainer: every point attributed to a specific component.
  Compliance flags: human review at alpha ≥70 or CRITICAL severity.
      │
      ▼
Node 5 — SignalInteractionEngine                       ← ZERO LLM
  14 typed interaction rules across 5 categories (reinforcing/cascading/escalating/converging/contradictory).
  Alpha multipliers up to 2.5× applied to participating signals.
  Example: CEO departure + covenant breach + insider selling → CASCADING distress (2.5×).
      │
      ▼
Node 6 — BriefSynthesisAgent                          ← LLM (narrative only)
  All signal data locked before LLM runs.
  Compliance mode: suppression + disclaimers.
      │
      ▼
Node 7 — PostProcessingNode                            ← ZERO LLM
  Warehouse storage (SQLite, 8 tables).
  Company memory EMA update.
  Entity graph update.
  All failures non-fatal.
      │
      ▼
AnalystBrief → Terminal | JSON | Markdown
```

---

## Full Engine Reference

| Engine | File | Purpose |
|--------|------|---------|
| Deterministic Signal Engine | `engines/deterministic_engine.py` | 70+ rules, NER, corroboration, zero LLM |
| Signal Interaction Engine | `engines/signal_interaction.py` | 14 compound event rules, alpha multipliers |
| Calibration | `engines/calibration.py` | Historical base rate tables per signal type |
| Adaptive Calibration | `engines/adaptive_calibration.py` | Outcome-aware severity adjustment from feedback |
| Confidence Decomposition | `engines/confidence.py` | 7-component auditable confidence breakdown |
| Semantic Extraction | `engines/semantic.py` | 9 typed financial clause categories |
| Alpha Scorer | `engines/alpha_scorer.py` | 0–100 composite + expected moves |
| Alpha Explainer | `engines/alpha_explainer.py` | SHAP-style deterministic score attribution |
| Signal Registry | `engines/signal_registry.py` | Modular, versioned signal specifications |
| Signal Interaction | `engines/signal_interaction.py` | Compound event detection, escalation |
| Feedback Loop | `engines/feedback.py` | False positive logging, source EMA, precision/recall |
| Audit Log | `engines/audit_log.py` | SHA-256 hash-chained immutable trail |
| Historical Warehouse | `engines/warehouse.py` | SQLite, 8 tables, full artifact storage |
| Replay Engine | `engines/replay.py` | Deterministic as-of-date historical reproduction |
| Backtesting Engine | `engines/backtest.py` | Precision/recall/F1/hit rate/excess return/drawdown |
| Company Memory | `engines/company_memory.py` | Longitudinal EMA risk profiles, trend detection |
| Market Data | `engines/market_data.py` | yfinance price/volatility/auto-outcome fetching |
| Market Impact | `engines/market_impact.py` | Outcome tracking, direction accuracy, magnitude error |
| Portfolio Intelligence | `engines/portfolio.py` | Portfolio-level risk aggregation, contagion clusters |
| Entity Resolver | `engines/entity_resolver.py` | Canonical registry, LEI/CIK/ticker deduplication |
| Graph Intelligence | `engines/graph_intelligence.py` | NetworkX entity graph, contagion risk |
| Monitoring Engine | `engines/monitoring.py` | Watchlist, continuous polling, Slack/webhook alerts |

---

## Data Sources

### US Markets
SEC EDGAR (8-K, 10-K, 10-Q, SC 13D/13G, Form 4, DEF 14A), Yahoo Finance RSS, Google News US

### African Exchanges (6)
NGX (Nigeria), JSE SENS (South Africa), NSE Kenya, Ghana Stock Exchange (GSE), Egyptian Exchange (EGX), Casablanca Stock Exchange, BRVM (West Africa/Francophone)

### African Financial News (49 RSS feeds)
Nigeria (10): BusinessDay, TechCabal, Stears, Nairametrics, Vanguard, ThisDay, Premium Times, The Guardian, Punch, Channels TV
South Africa (6): Moneyweb, BusinessLive, Daily Maverick, Fin24, IOL Business, Mail & Guardian
East Africa (7): Nation Africa, Daily Monitor Uganda, The East African, Standard Media Kenya, Business Daily Africa, Rwanda New Times, The Citizen Tanzania
Pan-African (8): The Africa Report, African Business, Financial Afrik, Disrupt Africa, Ventureburn, WeeTracker, TechPoint Africa, Quartz Africa
Ghana (3): Graphic Business, Citi Business, GhanaWeb
North Africa/Maghreb (3): Morocco World News, Egypt Independent, Al-Ahram Weekly
West Africa/Francophone (4): Agence Ecofin, Financial Afrik FR, SenePlus, BRVM Actualites
Southern/Central Africa (3): Zimbabwe Independent, Zambia Daily Mail, BusinessReport SA
Horn of Africa (2): Addis Fortune, The Reporter Ethiopia

### Private Capital & Institutional Sources (48 scraped)
PE/Deal Flow: GPCA, PSG Capital, Africa PE News (Deals/Exits/Debt/VC), AVCA
DFIs: IFC, AfDB, Proparco, DBSA, BII, FMO
VC Funds: Partech Africa, Novastar Ventures, Kepple Africa, TLcom Capital, Catalyst Fund
Credit/Debt: Rand Merchant Bank, Standard Bank Research
Exchanges: EGX, Casablanca, BRVM, DSE Tanzania, USE Uganda, RSE Rwanda
Regulators: SEC Nigeria, FSCA SA, CMA Kenya, CBN, SARB
Ratings/Macro: GCR Ratings, IMF Africa, World Bank Africa Blog, Moody's Africa, Afreximbank

---

## Honest Limitations

### 1. Backtesting Is Still Bootstrap Phase
`backtest.py` has the full framework (precision/recall/F1/hit rate/excess return/max drawdown/time-to-materialization) but requires accumulated analyst-confirmed outcomes to produce statistically valid results. The synthetic mode demonstrates the framework. Real validation needs 50+ confirmed outcomes per signal type. Use `python main.py backtest --synthetic` for framework demonstration; `--run` for real results as outcomes accumulate.

### 2. African Market Calibration Is Thinner
Base rate tables were developed primarily from US/global research. African market dynamics (thinner liquidity, fewer public disclosures, different regulatory timelines) may produce different materialisation rates. Adaptive calibration corrects this over time, but early deployments on African companies should treat severity scores with additional caution.

### 3. LLM Non-Determinism in Explanation Layer
Deterministic engine gates signals; LLM explanation text is non-deterministic. Two runs with identical candidates may produce slightly different headlines. This does not affect signal type, severity, confidence, or alpha score (all deterministic).

### 4. Market Data Integration Is Automated for Listed Companies Only
`market_data.py` (yfinance) covers US and major African listed companies. Private companies, OTC instruments, and thinly traded African stocks may return no data. Manual outcome recording via `python main.py outcomes --record` remains the fallback.

### 5. Entity Graph Is Bootstrap-Phase
The entity relationship graph builds incrementally from briefs and manual additions. Network effects (contagion, board overlap detection) become meaningful after sustained operation against a consistent company universe.

### 6. Semantic Extraction Is Regex-Based
The semantic extraction engine uses typed regex clause patterns — not embeddings or neural NLP. It handles standard disclosure language reliably but may miss novel phrasings or non-English African disclosures. The hybrid NLP upgrade (FinBERT/sentence-transformers) is the next major detection improvement.

---

## CLI Command Reference

```bash
# Analysis
python main.py analyse --company "GTBank" --ticker GTCO [--compliance] [--output json|markdown]

# Backtesting
python main.py backtest --synthetic          # framework demo
python main.py backtest --run                # against warehouse data
python main.py backtest --report             # latest results

# Portfolio
python main.py portfolio --name myportfolio --add "GTBank" --ticker GTCO --weight 0.2 --market Africa
python main.py portfolio --name myportfolio --risk

# Market Data (automated outcomes)
python main.py marketdata --price AAPL
python main.py marketdata --volatility GTCO.LG
python main.py marketdata --auto-outcome --company "Apple" --ticker AAPL --signal m_and_a_activity --date 2024-01-15

# Entity Resolution
python main.py entities --register "GTBank" --ticker GTCO --aliases "Guaranty Trust Bank" "GTBank Plc"
python main.py entities --resolve "GTBank Plc"
python main.py entities --merge "Guaranty Trust Bank" "GTBank Plc"

# Alpha Explanation
python main.py explain --company "GTBank"

# Monitoring
python main.py monitor --add "GTBank" "Safaricom" --webhook https://hooks.slack.com/...
python main.py monitor --run --interval 3600

# Memory & Profiles
python main.py memory --company "GTBank"
python main.py memory --list

# Replay
python main.py replay --company "Credit Suisse" --date "2023-02-01"

# Feedback & Calibration
python main.py feedback --submit company=WeWork signal_type=m_and_a_activity feedback_type=false_positive original_severity=high
python main.py feedback --stats
python main.py calibration --report

# Audit
python main.py audit --verify
python main.py audit --tail 20

# Outcomes
python main.py outcomes --stats
python main.py outcomes --record company=Apple signal_type=m_and_a_activity severity=high detection_date=2024-01-15 price_10d=18.5 confirmed=true

# Graph & Registry
python main.py graph --contagion "Bed Bath Beyond"
python main.py registry --show credit_risk
```

---

## Upgrade Roadmap

| Phase | What | Status |
|-------|------|--------|
| Separation of concerns | Deterministic engine + LLM explanation layer | ✅ Done |
| Alpha score layer | 0–100 composite + expected moves + SHAP explainer | ✅ Done |
| Compound event engine | 14 interaction rules + escalation multipliers | ✅ Done |
| Institutional audit | Hash-chained audit log + compliance mode | ✅ Done |
| Feedback loop | False positive tracking + source EMA + precision/recall | ✅ Done |
| Confidence decomposition | 7-component auditable breakdown | ✅ Done |
| Semantic extraction | 9 typed financial clause categories | ✅ Done |
| Adaptive calibration | Outcome-aware severity adjustment | ✅ Done |
| Market outcome modeling | Direction accuracy + magnitude error tracking | ✅ Done |
| Signal registry | Modular, versioned signal specifications | ✅ Done |
| Graph intelligence | NetworkX entity graph + contagion detection | ✅ Done |
| Historical warehouse | SQLite, 8 tables, full artifact storage | ✅ Done |
| Replay engine | Deterministic as-of-date reproduction | ✅ Done |
| Company memory | Longitudinal EMA risk profiles + trend detection | ✅ Done |
| Real-time monitoring | Watchlist + Slack/webhook alerting | ✅ Done |
| Backtesting framework | Precision/recall/F1/hit rate/excess return | ✅ Done |
| Market data integration | yfinance auto-outcome fetching | ✅ Done |
| Portfolio intelligence | Portfolio risk aggregation + contagion clusters | ✅ Done |
| Entity resolution | Canonical registry + LEI/CIK/alias deduplication | ✅ Done |
| African market depth | 49 feeds + 48 PE/DFI sources + 7 exchanges | ✅ Done |
| Hybrid NLP detection | FinBERT/sentence-transformers alongside deterministic | Next |
| ML severity model | Trained outcome model replacing base rate tables | Next |
| Live market data (pro) | Bloomberg/Refinitiv for full coverage | Next |
| Research dashboard | React frontend: risk timelines, heatmaps, replay UI | Next |
| Multi-user team mode | Shared watchlists, portfolio briefs, role-based access | Planned |
| Proprietary dataset | Structured event intelligence dataset for model training | Long-term |

---

*Last updated: May 2026. Maintained alongside codebase.*
