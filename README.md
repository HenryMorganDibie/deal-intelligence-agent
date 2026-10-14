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
| Confidence | Opaque float | Calibrated base-rate probability, plus a 7-component evidence-quality breakdown per signal |
| Evidence | Keyword hits | 9 typed financial clause categories (going concern, covenant breach, etc.) |
| Alpha score | None | 0–100 composite + SHAP-style breakdown + expected move estimates |
| Backtesting | None | Precision, recall, F1, hit rate, benchmark-adjusted return and drawdown per signal type, against automatically labelled outcomes |
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
  → SignalInteraction  (17 direction-aware compound event rules, up to 2.5× alpha multipliers)
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

Optional configuration:

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEAL_INTEL_PROVIDER` | `auto` | `auto` uses every provider with a key, Claude first then Groq, falling through on any failure; `anthropic` or `groq` to pin one |
| `DEAL_INTEL_GROQ_MODEL` | `openai/gpt-oss-120b` | Groq model (falls back to `qwen/qwen3.8-27b`) |
| `DEAL_INTEL_ANTHROPIC_MODEL` | `claude-opus-5-5` | Claude model for explanation and synthesis |
| `DEAL_INTEL_EFFORT` | `high` | Claude effort level (`low`, `medium`, `high`, `xhigh`, `max`) |
| `DEAL_INTEL_WEBHOOK_URL` | unset | Default webhook for monitoring alerts |

If the LLM is unavailable (no key, outage, or a declined request), the brief is still
produced from the deterministic engine's findings, labelled as such and flagged for
human review.

### Core Analysis

```bash
python main.py analyse --company "GTBank" --ticker GTCO
python main.py analyse --company "WeWork" --compliance --output markdown --out-file brief.md
python main.py analyse --company "SVB Financial" --signals credit_risk debt_restructuring --output json
```

### Backtesting

```bash
python main.py backtest --synthetic    # framework demo with seeded data
python main.py outcomes --auto-label   # label past predictions (price vs benchmark, SEC filings)
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
# African listings whose symbol is also a US ticker need the exchange suffix:
# SLM is Sallie Mae; use SLM.JO for Sanlam (likewise MTN.JO, UBA.LG, ...)
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

## Hosted App

**Live:** [deal-intelligence-app.vercel.app](https://deal-intelligence-app.vercel.app) (API: `deal-intelligence-api.vercel.app`)

The web app in `web/` (Next.js 14, Tailwind) is the landing page plus the app. There are no
accounts: anyone can run an analysis, each brief gets a shareable link, and a visitor's list
of briefs is kept in their own browser. The pipeline runs in `api/index.py`, a FastAPI
function that reuses this repository's code unchanged.

| Piece | Where | Notes |
|---|---|---|
| Web | Vercel project, root directory `web/` | `NEXT_PUBLIC_API_URL`, optional `NEXT_PUBLIC_SITE_URL` |
| API | Vercel project, repository root (`vercel.json`) | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `DEAL_INTEL_API_SECRET`, `ALLOWED_ORIGINS`, optional `ANTHROPIC_API_KEY`, `DEAL_INTEL_PER_VISITOR_DAILY` (10), `DEAL_INTEL_GLOBAL_DAILY` (300) |
| Storage | Supabase | `briefs` and `runs` tables behind functions (`supabase/migrations/`) |

Writes go through database functions that require `DEAL_INTEL_API_SECRET`, which only the
API holds, so the public key can read a brief by its id and nothing else. Visitors are
counted by a salted hash of their IP (never the IP itself) for the daily limits. To see
usage, run `select * from private.daily_usage;` in the Supabase SQL editor (runs, distinct
visitors, completed and failed per day); page views are in Vercel Web Analytics. Without
`ANTHROPIC_API_KEY` briefs come from the deterministic engine only and say so.

Local development:

```bash
pip install -r requirements.txt && uvicorn api.index:app --port 8787   # API
cd web && npm install && npm run dev                                    # http://localhost:3000
```

with `web/.env.local` pointing `NEXT_PUBLIC_API_URL` at `http://localhost:8787`.

---

## Data Sources

**US:** SEC EDGAR (8-K with item codes, 10-K, 10-Q, SC 13D/13G, Form 4 open-market trades, DEF 14A), Yahoo Finance RSS, Google News US

**African Exchanges:** official disclosures from NGX Nigeria (exchange document library), NSE Kenya (exchange document library) and JSE South Africa (SENS, current day); GSE Ghana, Egyptian Exchange (EGX), Casablanca and BRVM via news search and scraped sources

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
├── requirements.txt                     # runtime (also used by the Vercel API)
├── requirements-dev.txt                 # + pytest
├── api/index.py                         # hosted API (FastAPI on Vercel)
├── web/                                 # landing page + signed-in app (Next.js)
├── README.md
├── ARCHITECTURE.md                      # Full technical reference + honest limitations
├── supabase/migrations/                 # hosted app schema (briefs, runs, outcomes)
├── src/
│   ├── schemas/models.py               # All Pydantic types (25+ models)
│   ├── engines/                        # 21 deterministic intelligence engines
│   │   ├── deterministic_engine.py     # 70+ rules, NER, credibility
│   │   ├── signal_interaction.py       # 17 direction-aware compound event rules
│   │   ├── calibration.py             # Historical base rate tables
│   │   ├── adaptive_calibration.py    # Outcome-aware severity adjustment
│   │   ├── confidence.py              # 7-component evidence-quality breakdown per signal
│   │   ├── semantic.py                # 9 typed financial clause categories
│   │   ├── alpha_scorer.py            # 0–100 composite + expected moves
│   │   ├── alpha_explainer.py         # SHAP-style attribution breakdown
│   │   ├── signal_registry.py         # Signal metadata; patterns derived from the engine rules
│   │   ├── feedback.py                # Analyst corrections + source EMA
│   │   ├── audit_log.py               # SHA-256 hash-chained audit trail
│   │   ├── warehouse.py               # SQLite event warehouse (8 tables)
│   │   ├── replay.py                  # Deterministic historical replay
│   │   ├── backtest.py                # Precision/recall/F1/hit rate/abnormal return/drawdown
│   │   ├── outcome_labeller.py        # Automatic outcomes: benchmark-adjusted moves, SEC ground truth
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
    ├── conftest.py                    # Redirects every data store to a per-test temp dir
    └── test_all.py                    # 373 tests across all layers
```

---

## Testing

```bash
pip install -r requirements-dev.txt
pytest tests/test_all.py -v
```

**373 tests** (`pytest`; they never touch the real `data/` directory) across every layer: schemas, deterministic engine (all 8 signal types), signal interaction (all compound rules + alpha multipliers), warehouse (7 tables, store/retrieve, history), replay (config snapshot, deterministic run, diff comparison), backtesting (all signal types, metrics structure, F1 formula, max drawdown), company memory (EMA updates, trend detection, signal density), confidence decomposition (all 7 components), semantic extraction (all 9 clause types), adaptive calibration, market data (ticker resolution, invalid ticker handling, African exchange suffixes), portfolio intelligence (CRUD, risk aggregation, contagion detection, risk levels), entity resolver (register/resolve/aliases/CIK/ticker/merge/normalisation/stats), alpha explainer (all components, SHAP attribution, compound boost, compliance notes), African sources expansion (BRVM/EGX/Casablanca/IMF/World Bank/GCR/Ecofin/Morocco present), collection agent (3-pipeline merge, deduplication, fault isolation), graph integration, automatic outcome labelling (benchmark-adjusted returns, SEC ground truth, recall), French-language detection, the hosted API.

---

## Author

**Henry Dibie** — ML Systems Engineer & Data Scientist
[github.com/HenryMorganDibie](https://github.com/HenryMorganDibie) · [linkedin.com/in/kinghenrymorgan](https://linkedin.com/in/kinghenrymorgan)
