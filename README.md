# Deal Intelligence Agent

An autonomous multi-agent deal intelligence system for **US and African markets**, covering all 54 African countries. Deterministic signal engine + LLM explanation layer (Claude and Groq) + compound event detection + alpha scoring + backtesting + deals database + investors and funds + company financials + country, currency and sector risk + source-grounded research + monitoring and alerts + institutional audit trail.

Built for PE firms, credit analysts, research houses, hedge funds, and corporate finance teams.

---

## What It Covers

| Capability | What it does | Where |
|---|---|---|
| **Company profiles and financial statements** | NGX and NSE Kenya audited statements parsed from the filed PDFs (Group current and prior year) and checked with accounting identities, each figure marked verified, inconsistent or unchecked; Yahoo Finance statements and multiples for JSE, EGX, Casablanca, US and European listings, cross-checked against SEC XBRL for SEC filers; exchange profile (board, auditor, sector) | `financials.py`, `company_profile.py` |
| **PE, VC, debt and M&A transactions** | 1,700+ deals over two years across 48 countries, extracted daily from African business and private-capital publications in English, French and Portuguese: type, parties, amount in USD (at the year's official rate), stake, round, stage, sector, country, every source linked | `deals.py`, `market_feed.py` |
| **Investors, funds, LPs and GP activity** | Every party gets a role (investor, lender, acquirer, seller, LP, GP); a registry of Africa-focused DFIs, multilaterals, PE, VC, sovereign and pension investors resolves name variants (BII = CDC Group, BAD = AfDB); profiles, leaderboards, fund closes with their LPs | `investors.py` |
| **Valuations and comparable deals** | Reported and stake-implied valuations, comparables scored on sector, type, country and size with size and valuation quartiles, listed multiples | `deals.py`, `market_risk.py` |
| **Country, currency and sector risk** | All 54 countries: a 0 to 100 score from World Bank governance and macro indicators with every component and formula shown; 42 currencies: regime, spot vs official, depreciation, volatility; sector risk from the balance of adverse events and deal flow | `country_risk.py`, `market_risk.py` |
| **Research reports and source-grounded AI search** | Questions answered only from numbered evidence (deals, events, risk, investors, live news); citations checked, invalid ones removed, uncited sentences reported; country and sector reports | `research.py` |
| **Corporate event monitoring and alerts** | Daily feed of corporate events and deals across all 54 countries; watchlists by company, country and event type with an RSS feed and webhooks | `market_feed.py`, `watch.py` |
| **Historical outcomes and signal evaluation** | Walk-forward backtest (46 companies, 18 months), precision vs base rate (lift), recall, price hit rates, severity breakdown; live briefs labelled daily | `historical_backtest.py`, [docs/BACKTEST.md](docs/BACKTEST.md) |
| **Data coverage and verification by country** | For each country: prices, statements, filings, news edition and languages, regulators, risk-data coverage, deals and events, and a verification tier (A, B, C) | `coverage.py` |

Data is what public sources carry: undisclosed private deals that no one reports cannot appear, and most African exchanges outside NGX and NSE Kenya publish no machine-readable filings (they are tier C). The coverage page states this per country.

---

## What Makes This Different

| Dimension | Typical AI finance tool | This system |
|-----------|------------------------|-------------|
| Signal detection | LLM decides | Deterministic rule engine — reproducible, auditable |
| Severity | LLM opinion | Rule-strength bands (stated thresholds); CRITICAL needs two independent sources |
| Compound events | None | 14 typed interaction rules (cascading/reinforcing/contradictory) |
| LLM role | Primary decision maker | Explanation only — cannot invent signals |
| Confidence | Opaque float | Measured hit rate of past flags of the same type and severity (walk-forward backtest, then live outcomes), with its sample size, plus a 7-component evidence-quality rubric |
| Evidence | Keyword hits | 9 typed financial clause categories (going concern, covenant breach, etc.) |
| Alpha score | None | 0–100 composite with stated design weights, validated in the backtest (confirmation rate 13% / 25% / 40% across alpha thirds), SHAP-style breakdown, measured moves after similar flags |
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
| African markets | None | All 54 countries: national news editions in their languages, every regulator and central bank, 49 RSS feeds, 48 PE/DFI/regulatory sources |

---

## 8-Node Pipeline

```
Request
  → DataCollection    (SEC EDGAR + 49 African feeds + 48 PE sources + global news, concurrent)
  → DeterministicEngine  (70+ rules, NER, semantic extraction, corroboration — zero LLM)
  → LLMExplanation    (explains confirmed candidates only — cannot invent signals)
  → AlphaScoring      (0–100 composite + SHAP breakdown + measured moves after similar flags)
  → SignalInteraction  (17 direction-aware compound event rules; compound-adjusted score shown beside alpha, untested)
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

### Deals, Countries, Research, Companies

```bash
python main.py deals --ingest                       # read every feed now (54 countries)
python main.py deals --backfill 24                  # two years of history (date-restricted searches)
python main.py deals --search Moniepoint --country NG
python main.py deals --reextract                    # re-apply the extractor to the kept headlines
python main.py deals --upload                       # push to the hosted database
python main.py countries                            # risk ranking for the 54 countries
python main.py countries --country SN               # risk components and currency for one country
python main.py countries --refresh                  # re-download World Bank indicators (slow)
python main.py research "Which Kenyan fintechs raised money this year, and from whom?"
python main.py profile --company "Dangote Cement" --ticker DANGCEM.LG
python main.py analyse --company Sonatel --country SN
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
| API | Vercel project, repository root (`vercel.json`) | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `DEAL_INTEL_API_SECRET`, `ALLOWED_ORIGINS`, `CRON_SECRET`, `DEAL_INTEL_APP_URL`, `ANTHROPIC_API_KEY` and/or `GROQ_API_KEY`, `DEAL_INTEL_PER_VISITOR_DAILY` (10), `DEAL_INTEL_GLOBAL_DAILY` (300) |
| Storage | Supabase | briefs, runs, outcomes, prices, LLM cache, deals, events and watchlists behind functions (`supabase/migrations/`) |
| Crons | Vercel (daily) | `/api/cron/ingest` reads every feed into deals and events and delivers webhooks; `/api/cron/label` labels brief outcomes and snapshots NGX/NSE prices; `/api/cron/showcase` runs the pipeline on a fixed list of US and African companies (`engines/showcase.py`) for the landing page, stored apart from visitors' briefs |

App pages: Briefs, Research, Deals, Investors, Companies, Countries, Alerts, Coverage, Evaluation. The API routes are listed at the top of `src/hosted_market.py`.

Writes go through database functions that require `DEAL_INTEL_API_SECRET`, which only the
API holds, so the public key can read a brief by its id and nothing else. Visitors are
counted by a salted hash of their IP (never the IP itself) for the daily limits. To see
usage, run `select * from private.daily_usage;` in the Supabase SQL editor (runs, distinct
visitors, completed and failed per day); page views are in Vercel Web Analytics. Without
an LLM key (Claude or Groq) briefs and research answers come from the deterministic engine only and say so.

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
├── docs/BACKTEST.md                     # historical backtest report (+ backtest_summary.json)
├── src/
│   ├── hosted_market.py                # API routes: countries, deals, investors, companies, research, alerts
│   ├── data/
│   │   ├── africa_countries.py         # the 54 countries: codes, languages, currency, exchange, regulators
│   │   ├── country_indicators.json     # World Bank governance and macro snapshot (committed)
│   │   └── measured_outcomes.json      # backtest observations, hit rates and moves; pooled hourly with live outcomes
│   ├── schemas/models.py               # All Pydantic types (25+ models)
│   ├── engines/                        # 21 deterministic intelligence engines
│   │   ├── deterministic_engine.py     # 70+ rules, NER, credibility
│   │   ├── signal_interaction.py       # 17 direction-aware compound event rules
│   │   ├── calibration.py             # Severity bands + measured hit rates
│   │   ├── measured.py                # measured outcome tables (from the backtest)
│   │   ├── adaptive_calibration.py    # Outcome-aware severity adjustment
│   │   ├── confidence.py              # 7-component evidence-quality breakdown per signal
│   │   ├── semantic.py                # 9 typed financial clause categories
│   │   ├── alpha_scorer.py            # 0–100 composite + measured moves
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
│   │   ├── monitoring.py              # Watchlist + Slack/webhook alerts (CLI)
│   │   ├── deals.py                   # deal extraction, merging, search, comparables
│   │   ├── market_feed.py             # daily feed: 54-country searches + RSS -> deals and events
│   │   ├── investors.py               # investor registry, roles, profiles, funds and LPs
│   │   ├── financials.py              # statement parsing (NGX, NSE Kenya PDFs), Yahoo, SEC XBRL, checks
│   │   ├── company_profile.py         # company profiles: identity, market, statements, private markets
│   │   ├── country_risk.py            # 54-country risk scores from World Bank indicators
│   │   ├── market_risk.py             # currency risk, sector risk, valuation view
│   │   ├── research.py                # source-grounded research and reports
│   │   ├── watch.py                   # watchlist matching, RSS, webhooks
│   │   ├── coverage.py                # coverage and verification tier per country
│   │   └── historical_backtest.py     # walk-forward historical backtest
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
    ├── test_all.py                    # pipeline, engines, API
    └── test_africa_data.py            # countries, risk, deals, investors, financials, research, alerts
```

---

## Testing

```bash
pip install -r requirements-dev.txt
pytest -q
```

**526 tests** (`pytest`; they never touch the real `data/` directory) across every layer: schemas, deterministic engine (all 8 signal types), signal interaction (all compound rules + alpha multipliers), warehouse (7 tables, store/retrieve, history), replay (config snapshot, deterministic run, diff comparison), backtesting (all signal types, metrics structure, F1 formula, max drawdown), company memory (EMA updates, trend detection, signal density), confidence decomposition (all 7 components), semantic extraction (all 9 clause types), adaptive calibration, market data (ticker resolution, invalid ticker handling, African exchange suffixes), portfolio intelligence (CRUD, risk aggregation, contagion detection, risk levels), entity resolver (register/resolve/aliases/CIK/ticker/merge/normalisation/stats), alpha explainer (all components, SHAP attribution, compound boost, compliance notes), African sources expansion (BRVM/EGX/Casablanca/IMF/World Bank/GCR/Ecofin/Morocco present), collection agent (3-pipeline merge, deduplication, fault isolation), graph integration, automatic outcome labelling (benchmark-adjusted returns, SEC ground truth, recall), French-language detection, the hosted API, the 54-country registry, country and currency risk formulas, deal extraction (amounts, roles, stages, rejection of non-deals) in three languages, investor roles, statement parsing and accounting checks, citation validation, watchlist matching and webhook safety, coverage tiers.

---

## Author

**Henry Dibie** — ML Systems Engineer & Data Scientist
[github.com/HenryMorganDibie](https://github.com/HenryMorganDibie) · [linkedin.com/in/kinghenrymorgan](https://linkedin.com/in/kinghenrymorgan)
