# Deal Intelligence Agent

An autonomous multi-agent deal intelligence system for **US and African markets**. Deterministic signal engine + LLM explanation layer + compound event detection + alpha scoring + backtesting + portfolio intelligence + real-time monitoring + entity resolution + institutional audit trail.

Built for PE firms, credit analysts, hedge funds, and corporate finance teams.

---

## What Makes This Different

| Dimension | Typical AI finance tool | This system |
|-----------|------------------------|-------------|
| Signal detection | LLM decides | Deterministic rule engine — reproducible, auditable |
| Severity | LLM opinion | Calibrated against historical materialisation rates |
| Compound events | None | 14 typed interaction rules (cascading/reinforcing/contradictory) |
| LLM role | Primary decision maker | Explanation only — cannot invent signals |
| Confidence | Opaque float | 7-component auditable decomposition |
| Evidence | Keyword hits | 9 typed financial clause categories (going concern, covenant breach, etc.) |
| Alpha score | None | 0–100 composite + SHAP-style breakdown + expected move estimates |
| Backtesting | None | Precision/recall/F1/hit rate/excess return/drawdown per signal type |
| Adaptive calibration | None | Outcome-aware severity from analyst feedback |
| Portfolio intelligence | None | Portfolio risk aggregation + contagion cluster detection |
| Company memory | None | Longitudinal EMA risk profiles + trend detection |
| Entity resolution | None | Canonical registry + LEI/CIK/ticker deduplication |
| Market data | None | yfinance auto-outcome fetching (US + African listed) |
| Audit trail | None | SHA-256 hash-chained append-only log, tamper detection |
| Compliance mode | None | Signal suppression, human review flags, disclaimers |
| Graph intelligence | None | NetworkX entity graph + contagion risk detection |
| Monitoring | None | Continuous watchlist + Slack/webhook alerting |
| Replay | None | Deterministic as-of-date historical reproduction |
| African markets | None | 49 RSS feeds, 7 exchanges, 48 PE/DFI/regulatory sources |

---

## 8-Node Pipeline

```
Request
  → DataCollection    (SEC EDGAR + 49 African feeds + 48 PE sources + global news, concurrent)
  → DeterministicEngine  (70+ rules, NER, semantic extraction, corroboration — zero LLM)
  → LLMExplanation    (explains confirmed candidates only — cannot invent signals)
  → AlphaScoring      (0–100 composite + SHAP breakdown + expected moves)
  → SignalInteraction  (14 compound event rules, up to 2.5× alpha multipliers)
  → BriefSynthesis    (narrative only — all signal data locked)
  → PostProcessing    (warehouse + company memory + entity graph)
  → AnalystBrief
```

---

## Quickstart

```bash
git clone https://github.com/HenryMorganDibie/deal-intelligence-agent
cd deal-intelligence-agent
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

### Core Analysis

```bash
python main.py analyse --company "GTBank" --ticker GTCO
python main.py analyse --company "WeWork" --compliance --output markdown --out-file brief.md
python main.py analyse --company "SVB Financial" --signals credit_risk debt_restructuring --output json
```

### Backtesting

```bash
python main.py backtest --synthetic    # framework demo with seeded data
python main.py backtest --run          # against real warehouse outcomes
python main.py backtest --report       # show latest results
```

### Portfolio Intelligence

```bash
python main.py portfolio --name africa_fund --add "GTBank" --ticker GTCO --weight 0.2 --market Africa
python main.py portfolio --name africa_fund --add "Safaricom" --ticker SCOM --weight 0.15 --market Africa
python main.py portfolio --name africa_fund --risk
```

### Market Data (Automated Outcomes)

```bash
python main.py marketdata --price AAPL
python main.py marketdata --volatility GTCO.LG
python main.py marketdata --auto-outcome --company "Apple" --ticker AAPL \
  --signal m_and_a_activity --severity high --date 2024-01-15
```

### Entity Resolution

```bash
python main.py entities --register "GTBank" --ticker GTCO \
  --aliases "Guaranty Trust Bank" "GTBank Plc" --cik "" --lei ""
python main.py entities --resolve "GTBank Plc"
python main.py entities --merge "Guaranty Trust Bank" "GTBank Plc"
python main.py entities --stats
```

### Alpha Explanation

```bash
# After running an analysis, get SHAP-style breakdown via JSON output:
python main.py analyse --company "WeWork" --output json | python3 -c \
  "import json,sys; d=json.load(sys.stdin); [print(json.dumps(s['alpha_score'],indent=2)) for s in d['detected_signals'] if s.get('alpha_score')]"
```

### Monitoring

```bash
python main.py monitor --add "GTBank" "Shoprite" "Safaricom"
python main.py monitor --run-once
python main.py monitor --run --interval 3600
python main.py monitor --alerts
```

### Feedback & Calibration

```bash
python main.py feedback --submit company=WeWork signal_type=m_and_a_activity \
  feedback_type=false_positive original_severity=high
python main.py feedback --stats
python main.py calibration --report
```

### Replay

```bash
python main.py replay --company "Credit Suisse" --date "2023-02-01"
```

### Audit & Graph

```bash
python main.py audit --verify
python main.py graph --contagion "Bed Bath Beyond"
python main.py graph --summary
```

---

## Data Sources

**US:** SEC EDGAR (8-K/10-K/10-Q/SC13D/Form4), Yahoo Finance RSS, Google News US

**African Exchanges (7):** NGX Nigeria, JSE South Africa (SENS), NSE Kenya, GSE Ghana, Egyptian Exchange (EGX), Casablanca Stock Exchange, BRVM West Africa

**African News (49 RSS feeds):** Nigeria (10), South Africa (6), East Africa (7), Pan-African (8), Ghana (3), North Africa/Maghreb (3), West Africa/Francophone (4), Southern Africa (3), Horn of Africa (2), Ethiopia (2)

**Private Capital & Institutional (48 scraped sources):**
- PE/Deal Flow: GPCA, PSG Capital, Africa PE News × 4 categories, AVCA
- DFIs: IFC, AfDB, Proparco, DBSA, BII, FMO
- VC: Partech Africa, Novastar, Kepple Africa, TLcom, Catalyst Fund
- Credit: Rand Merchant Bank, Standard Bank Research
- Exchanges: EGX, Casablanca, BRVM, DSE Tanzania, USE Uganda, RSE Rwanda
- Regulators: SEC Nigeria, FSCA SA, CMA Kenya, CBN, SARB
- Ratings/Macro: GCR Ratings, IMF Africa, World Bank Africa, Moody's Africa, Afreximbank

---

## Project Structure

```
deal-intelligence-agent/
├── main.py                              # CLI: 16 command groups
├── requirements.txt
├── README.md
├── ARCHITECTURE.md                      # Full technical reference + honest limitations
├── src/
│   ├── schemas/models.py               # All Pydantic types (25+ models)
│   ├── engines/                        # 21 deterministic intelligence engines
│   │   ├── deterministic_engine.py     # 70+ rules, NER, credibility
│   │   ├── signal_interaction.py       # 14 compound event rules
│   │   ├── calibration.py             # Historical base rate tables
│   │   ├── adaptive_calibration.py    # Outcome-aware severity adjustment
│   │   ├── confidence.py              # 7-component confidence decomposition
│   │   ├── semantic.py                # 9 typed financial clause categories
│   │   ├── alpha_scorer.py            # 0–100 composite + expected moves
│   │   ├── alpha_explainer.py         # SHAP-style attribution breakdown
│   │   ├── signal_registry.py         # Modular signal specifications
│   │   ├── feedback.py                # Analyst corrections + source EMA
│   │   ├── audit_log.py               # SHA-256 hash-chained audit trail
│   │   ├── warehouse.py               # SQLite event warehouse (8 tables)
│   │   ├── replay.py                  # Deterministic historical replay
│   │   ├── backtest.py                # Precision/recall/F1/hit rate/drawdown
│   │   ├── company_memory.py          # Longitudinal EMA risk profiles
│   │   ├── market_data.py             # yfinance auto-outcome fetching
│   │   ├── market_impact.py           # Outcome tracking + accuracy metrics
│   │   ├── portfolio.py               # Portfolio risk aggregation
│   │   ├── entity_resolver.py         # Canonical registry + LEI/CIK/alias
│   │   ├── graph_intelligence.py      # NetworkX entity graph + contagion
│   │   └── monitoring.py              # Watchlist + Slack/webhook alerts
│   ├── tools/
│   │   ├── edgar_tool.py              # SEC EDGAR API
│   │   ├── africa_tool.py             # 49 feeds + 48 PE/institutional sources
│   │   └── news_tool.py               # Global RSS + relevance scoring
│   ├── agents/
│   │   ├── collection_agent.py        # Node 1: 3-pipeline concurrent
│   │   ├── signal_agent.py            # Nodes 2–6: det. engine → LLM → alpha → synthesis
│   │   └── graph.py                   # 8-node LangGraph orchestration
│   └── utils/
│       └── formatter.py               # Terminal (Rich), JSON, Markdown
├── data/                               # Auto-created on first run
│   ├── warehouse.db                   # SQLite (8 tables)
│   ├── feedback.json                  # Analyst corrections
│   ├── audit_log.jsonl                # Immutable hash-chained trail
│   ├── company_memory.json            # Risk profiles
│   ├── market_outcomes.json           # Outcome tracking
│   ├── backtest_results.json          # Backtest history
│   ├── entity_registry.json           # Canonical entity registry
│   ├── entity_graph.json              # NetworkX graph
│   ├── watchlist.json                 # Monitoring watchlist
│   ├── portfolios.json                # Portfolio definitions
│   └── alerts.json                    # Alert history
└── tests/
    └── test_all.py                    # 248 tests across all layers
```

---

## Testing

```bash
pytest tests/test_all.py -v
```

**248 tests** across every layer: schemas, deterministic engine (all 8 signal types), signal interaction (all compound rules + alpha multipliers), warehouse (7 tables, store/retrieve, history), replay (config snapshot, deterministic run, diff comparison), backtesting (all signal types, metrics structure, F1 formula, max drawdown), company memory (EMA updates, trend detection, signal density), confidence decomposition (all 7 components), semantic extraction (all 9 clause types), adaptive calibration, market data (ticker resolution, invalid ticker handling, African exchange suffixes), portfolio intelligence (CRUD, risk aggregation, contagion detection, risk levels), entity resolver (register/resolve/aliases/CIK/ticker/merge/normalisation/stats), alpha explainer (all components, SHAP attribution, compound boost, compliance notes), African sources expansion (BRVM/EGX/Casablanca/IMF/World Bank/GCR/Ecofin/Morocco present), collection agent (3-pipeline merge, deduplication, fault isolation), graph integration.

---

## Author

**Henry Dibie** — ML Systems Engineer & Data Scientist
[github.com/HenryMorganDibie](https://github.com/HenryMorganDibie) · [linkedin.com/in/kinghenrymorgan](https://linkedin.com/in/kinghenrymorgan)
