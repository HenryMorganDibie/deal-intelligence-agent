# Deal Intelligence Agent

An autonomous multi-agent system that monitors regulatory filings and financial news across **US and African markets** to surface actionable deal intelligence signals — with compound event detection, alpha scoring, semantic evidence extraction, longitudinal company memory, real-time monitoring, and compliance-grade audit trails.

Built for PE firms, credit analysts, hedge funds, and corporate finance teams.

---

## What Makes This Different

| Dimension | Typical AI finance tool | This system |
|-----------|------------------------|-------------|
| Signal detection | LLM decides | Deterministic rule engine — reproducible, auditable |
| Severity scoring | LLM opinion | Calibrated against historical materialisation rates |
| Compound events | None | 14 typed interaction rules (cascading/reinforcing/contradictory) |
| LLM role | Primary decision maker | Explanation layer only — cannot invent signals |
| Confidence | Opaque single float | 7-component auditable decomposition |
| Evidence extraction | Keyword hits | Typed financial clause extraction (going concern, covenant breach, etc.) |
| Alpha score | None | 0–100 composite with component breakdown + expected move estimates |
| Adaptive calibration | None | Outcome-aware severity adjustment from analyst feedback |
| Company memory | None | Longitudinal EMA risk profiles, trend detection, event velocity |
| Feedback loop | None | False positive logging, source EMA, precision/recall per signal type |
| Audit trail | None | SHA-256 hash-chained append-only log, tamper detection |
| Compliance mode | None | Signal suppression, human review flags, mandatory disclaimers |
| Graph intelligence | None | Entity relationship graph, contagion risk, board overlap detection |
| Monitoring | None | Continuous watchlist with Slack/webhook alerts |
| Replay | None | Deterministic as-of-date historical reproduction |
| African markets | None | 37 news feeds, 4 exchanges, 29 PE/DFI/regulatory sources |

---

## 8-Node Pipeline

```
Request → DataCollection → DeterministicEngine → LLMExplanation
       → AlphaScoring → SignalInteraction → BriefSynthesis
       → PostProcessing → Brief
```

**Node 1 — DataCollection:** Three concurrent pipelines (SEC EDGAR, Africa Tool, Global News). Each fails independently.

**Node 2 — DeterministicSignalEngine:** 70+ typed regex rules, NER, source credibility weighting, corroboration merging. Zero LLM. If zero candidates → zero signals. No exceptions.

**Node 3 — LLMExplanationNode:** Receives only confirmed candidates. Semantic evidence extraction enriches context first. Adaptive calibration derives severity. LLM writes headlines and reasoning only.

**Node 4 — AlphaScoringNode:** 0–100 composite score. Expected move estimates from 14–91 historical comparables per signal type. Compliance flags at alpha ≥70 or CRITICAL severity.

**Node 5 — SignalInteractionEngine:** 14 interaction rules detect compound events (cascading distress, elevated M&A probability, contradictory signals). Alpha multipliers up to 2.5× applied to participating signals.

**Node 6 — BriefSynthesisAgent:** LLM writes narrative only. All signal data locked before this node runs.

**Node 7 — PostProcessingNode:** Warehouse storage, company memory EMA update, entity graph update. All failures non-fatal.

---

## Quickstart

```bash
git clone https://github.com/HenryMorganDibie/deal-intelligence-agent
cd deal-intelligence-agent
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

### Analyse

```bash
# Terminal output
python main.py analyse --company "Guaranty Trust Bank" --ticker GTCO

# Compliance mode, Markdown export
python main.py analyse --company "WeWork" --compliance --output markdown --out-file brief.md

# Focus signals, JSON
python main.py analyse --company "SVB Financial" --signals credit_risk debt_restructuring --output json

# Deep scan, African company
python main.py analyse --company "Shoprite" --depth deep --lookback 180
```

### Monitor

```bash
# Add to watchlist
python main.py monitor --add "GTBank" "Safaricom" "Shoprite"

# Run one check cycle
python main.py monitor --run-once

# Continuous monitoring (1hr interval)
python main.py monitor --run --interval 3600

# View alerts
python main.py monitor --alerts

# Add with Slack webhook
python main.py monitor --add "Flutterwave" --webhook https://hooks.slack.com/...
```

### Company Memory

```bash
# View longitudinal risk profile
python main.py memory --company "GTBank"

# List all tracked companies (sorted by risk)
python main.py memory --list

# Companies above risk threshold
python main.py memory --watchlist-alerts
```

### Feedback & Calibration

```bash
# Submit false positive correction
python main.py feedback --submit company=WeWork signal_type=m_and_a_activity \
  feedback_type=false_positive original_severity=high note="Deal never materialised"

# View precision/recall stats
python main.py feedback --stats

# View adaptive calibration report
python main.py calibration --report
```

### Audit & Replay

```bash
# Verify audit chain integrity
python main.py audit --verify

# Tail audit log
python main.py audit --tail 20

# Replay analysis as-of historical date
python main.py replay --company "Credit Suisse" --date "2023-02-01"
```

### Graph Intelligence

```bash
# Entity graph summary
python main.py graph --summary

# Contagion risk for a distressed company
python main.py graph --contagion "Bed Bath Beyond"

# Add lender relationship
python main.py graph --add-lender "Standard Bank" "Acme Corp"
```

### Market Outcomes

```bash
# Record actual market reaction
python main.py outcomes --record company=Acme signal_type=m_and_a_activity \
  severity=high detection_date=2024-01-15 price_10d=18.5 confirmed=true \
  expected_direction=positive

# View accuracy metrics
python main.py outcomes --stats
```

### Signal Registry

```bash
# List all signal types
python main.py registry --list

# Show full spec for one signal type
python main.py registry --show credit_risk
```

---

## Data Sources

### US Markets
SEC EDGAR (8-K, 10-K, 10-Q, SC 13D, Form 4), Yahoo Finance RSS, Google News US

### African Exchanges
NGX Group (Nigeria), JSE SENS (South Africa, with Google News ZA fallback), NSE Kenya, Ghana Stock Exchange

### African Financial News (37 RSS feeds)
**Nigeria:** BusinessDay, TechCabal, Stears, Nairametrics, Vanguard, ThisDay, Premium Times, The Guardian, Punch, Channels TV  
**South Africa:** Moneyweb, BusinessLive, Daily Maverick, Fin24, IOL Business, Mail & Guardian  
**East Africa:** Nation Africa, Daily Monitor Uganda, The East African, Standard Media Kenya, Business Daily Africa, Rwanda New Times, The Citizen Tanzania  
**Pan-African:** The Africa Report, African Business, Financial Afrik, Disrupt Africa, Ventureburn, WeeTracker, TechPoint Africa, Quartz Africa  
**Ghana:** Graphic Business, Citi Business, GhanaWeb  
**Francophone:** Jeune Afrique Economie  
**North Africa:** Daily News Egypt, Egypt Today  
**Horn of Africa:** Addis Fortune, The Reporter Ethiopia  

### Private Capital & Institutional Sources (29 scraped)
**PE/Deal Flow:** Global Private Capital, PSG Capital, Africa PE News (Deals/Exits/Debt/VC), AVCA  
**DFIs:** IFC, African Development Bank, Proparco, DBSA, British International Investment, FMO  
**VC Funds:** Partech Africa, Novastar Ventures, Kepple Africa, TLcom Capital, Catalyst Fund  
**Credit/Debt:** Rand Merchant Bank, Standard Bank Research  
**Regulators:** SEC Nigeria, FSCA South Africa, CMA Kenya, CBN, SARB, Bayport Finance, Zawya, Afreximbank  

---

## Project Structure

```
deal-intelligence-agent/
├── main.py                              # CLI: 10 command groups
├── requirements.txt
├── README.md
├── ARCHITECTURE.md                      # Full technical reference + honest limitations
├── src/
│   ├── schemas/models.py               # All Pydantic types (20+ models)
│   ├── engines/                        # Deterministic intelligence layer
│   │   ├── deterministic_engine.py     # 70+ rules, NER, corroboration — zero LLM
│   │   ├── signal_interaction.py       # 14 compound event rules, alpha multipliers
│   │   ├── calibration.py             # Historical base rate tables
│   │   ├── adaptive_calibration.py    # Outcome-aware severity adjustment
│   │   ├── confidence.py              # 7-component confidence decomposition
│   │   ├── semantic.py                # Typed financial clause extraction
│   │   ├── alpha_scorer.py            # 0–100 alpha score + expected moves
│   │   ├── feedback.py                # Analyst corrections + source EMA
│   │   ├── audit_log.py               # SHA-256 hash-chained audit trail
│   │   ├── warehouse.py               # SQLite event warehouse (7 tables)
│   │   ├── replay.py                  # Deterministic historical replay
│   │   ├── company_memory.py          # Longitudinal EMA risk profiles
│   │   ├── market_impact.py           # Market outcome tracking
│   │   ├── signal_registry.py         # Modular signal specifications
│   │   ├── graph_intelligence.py      # NetworkX entity relationship graph
│   │   └── monitoring.py              # Watchlist + Slack/webhook alerts
│   ├── tools/
│   │   ├── edgar_tool.py              # SEC EDGAR API
│   │   ├── africa_tool.py             # 37 feeds + 29 PE/institutional sources
│   │   └── news_tool.py               # Global RSS + relevance scoring
│   ├── agents/
│   │   ├── collection_agent.py        # Node 1: 3-pipeline concurrent collection
│   │   ├── signal_agent.py            # Nodes 2–4: det. engine, LLM explain, alpha, synthesis
│   │   └── graph.py                   # 8-node LangGraph orchestration
│   └── utils/
│       └── formatter.py               # Terminal (Rich), JSON, Markdown
├── data/                               # Auto-created on first run
│   ├── warehouse.db                   # SQLite event warehouse
│   ├── feedback.json                  # Analyst corrections
│   ├── audit_log.jsonl                # Immutable audit trail
│   ├── company_memory.json            # Longitudinal risk profiles
│   ├── market_outcomes.json           # Outcome tracking
│   ├── entity_graph.json              # Entity relationship graph
│   ├── watchlist.json                 # Monitoring watchlist
│   └── alerts.json                    # Alert history
└── tests/
    └── test_all.py                    # 190 tests across all layers
```

---

## Testing

```bash
pytest tests/test_all.py -v
```

**190 tests** covering every layer: schemas (all new types), deterministic engine (all 8 signal types, corroboration, NER), signal interaction (all compound rules, alpha multipliers, contradictory detection), warehouse (table creation, store/retrieve, signal history, scoring trend), replay (config snapshot, deterministic replay, run comparison diffs), company memory (EMA updates, trend detection, signal density, leadership tracking), confidence decomposition (all 7 components, source ranking, calibration adjustment), semantic extraction (all 9 clause types, financial amounts, max_per_type), adaptive calibration (static fallback, report structure), market impact (direction accuracy, magnitude error, per-signal metrics), signal registry (all types registered, pattern counts, escalation validity), graph intelligence (company/executive/lender nodes, contagion risk, save/reload, shared executives), monitoring (watchlist CRUD, alert persistence, threshold logic), collection agent (3-pipeline merge, deduplication, fault isolation), brief synthesis, formatter, graph integration.

---

## Author

**Henry Dibie** — ML Systems Engineer & Data Scientist  
[github.com/HenryMorganDibie](https://github.com/HenryMorganDibie) · [linkedin.com/in/kinghenrymorgan](https://linkedin.com/in/kinghenrymorgan)
