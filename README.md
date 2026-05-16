# Deal Intelligence Agent

An autonomous multi-agent system that monitors regulatory filings and financial news across **US and African markets** to surface actionable deal intelligence signals — M&A activity, credit risk, distressed assets, regulatory actions, and more — delivered as structured analyst briefs with full reasoning traces, alpha scores, and compliance-grade audit logs.

Built for PE firms, credit analysts, hedge funds, and corporate finance teams who need a junior analyst that never sleeps.

---

## Architecture

```
AnalysisRequest
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│  DataCollectionAgent  (LangGraph Node 1)                 │
│                                                         │
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────┐ │
│  │  SEC EDGAR   │  │   Africa Tool    │  │   News    │ │
│  │  (US)        │  │  (African mkts)  │  │  (Global) │ │
│  │              │  │                  │  │           │ │
│  │ 8-K 10-K     │  │ NGX · JSE SENS   │  │ Reuters   │ │
│  │ 10-Q SC13D   │  │ NSE Kenya · GSE  │  │ Bloomberg │ │
│  │ Form 4       │  │ 37 news feeds    │  │ FT · CNBC │ │
│  │ Full-text    │  │ 29 PE/DFI/reg    │  │ Yahoo Fin │ │
│  │ keyword scan │  │ sources scraped  │  │           │ │
│  └──────────────┘  └──────────────────┘  └───────────┘ │
│                                                         │
│  → All three run concurrently. Each fails independently. │
│  → Merge + deduplicate filings and news across sources.  │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  DeterministicSignalEngine  (LangGraph Node 2)           │
│                                                         │
│  Zero LLM. Pure pattern matching + NER.                 │
│  70+ typed regex rules across 8 signal categories.      │
│  Named entity extraction (companies, amounts, %).       │
│  Source credibility weighting (SEC = 1.0, blogs = 0.4). │
│  Corroboration merging across independent sources.      │
│                                                         │
│  Output: SignalCandidate[]                              │
│  Rule: if zero candidates → zero signals. No exceptions. │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  LLMExplanationNode  (LangGraph Node 3)                  │
│                                                         │
│  Claude only sees confirmed candidates.                 │
│  Task: explain, contextualise, surface evidence.        │
│  Cannot invent signals. Cannot change signal_type.      │
│  Cannot override severity. Falls back gracefully        │
│  if API fails (deterministic output used directly).     │
│                                                         │
│  Output: DetectedSignal[] with headlines + reasoning    │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  AlphaScoringNode  (LangGraph Node 4)                    │
│                                                         │
│  Composite 0–100 alpha score per signal:                │
│    Severity weight      × 0.35                          │
│    Source credibility   × 0.25                          │
│    Corroboration count  × 0.20                          │
│    Recency decay        × 0.10                          │
│    Liquidity tier       × 0.10                          │
│                                                         │
│  Expected move estimates from historical comparables.   │
│  Compliance flags: human review above alpha 70          │
│  or CRITICAL severity.                                  │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  BriefSynthesisAgent  (LangGraph Node 5)                 │
│                                                         │
│  Claude writes narrative only. All signal data locked.  │
│  Executive summary, recommendation, key metrics,        │
│  risk factors, recent developments.                     │
│  Compliance mode: adds suppression counts + disclaimers.│
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
                    AnalystBrief
            (Terminal · JSON · Markdown)
```

---

## Signal Types

| Signal | Description | Key Patterns |
|--------|-------------|--------------|
| `m_and_a_activity` | M&A indicators from filings + news | Definitive agreement, LOI, tender offer, scheme of arrangement |
| `credit_risk` | Debt + covenant concerns | Going concern, covenant breach, Moody's/S&P/GCR downgrade |
| `distressed_asset` | Formal insolvency signals | Bankruptcy, business rescue (SA), provisional liquidation, judicial management |
| `earnings_surprise` | Revenue/profit misses | Profit warning, guidance cut, headline earnings miss, trading statement |
| `leadership_change` | Executive departures | CEO/CFO/MD resigned, interim appointment, board reconstitution |
| `regulatory_action` | Regulatory enforcement | SEC/FSCA/CMA/CBN probe, licence revoked, antitrust, fraud charge |
| `debt_restructuring` | Debt renegotiation | Forbearance, haircut, debt-for-equity swap, maturity extension |
| `insider_activity` | Insider + activist moves | Form 4, SC 13D/13G, director purchase, activist campaign |

---

## What's New vs a Basic RAG Chatbot

| Dimension | Typical AI finance tool | This system |
|-----------|------------------------|-------------|
| Signal detection | LLM decides | Deterministic rules engine — reproducible, auditable |
| Severity scoring | LLM opinion | Calibrated against historical materialisation rates |
| LLM role | Primary decision maker | Explanation layer only — cannot invent signals |
| Alpha score | None | 0–100 composite with component breakdown |
| Expected move | None | Historical comparables per signal type (14–91 events) |
| Feedback loop | None | False positive logging, source reliability EMA, precision/recall stats |
| Audit trail | None | SHA-256 hash-chained append-only log, tamper detection |
| Compliance mode | None | Signal suppression, human review flags, mandatory disclaimers |
| African markets | None | 37 news feeds, 4 exchanges, 29 PE/DFI/regulatory sources |

---

## Quickstart

### 1. Install

```bash
git clone https://github.com/HenryMorganDibie/deal-intelligence-agent
cd deal-intelligence-agent
pip install -r requirements.txt
```

### 2. Set API Key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Run

**US companies**
```bash
# Standard terminal output
python main.py analyse --company "Apple Inc" --ticker AAPL

# Deep scan, last 6 months, Markdown export
python main.py analyse --company "Revlon" --lookback 180 --depth deep --output markdown --out-file brief.md

# Focus signals, JSON export
python main.py analyse --company "SVB Financial" --signals credit_risk debt_restructuring --output json

# Compliance mode (suppresses low-confidence, adds human review flags)
python main.py analyse --company "WeWork" --compliance --output markdown
```

**African companies**
```bash
# Nigerian Exchange listed
python main.py analyse --company "Guaranty Trust Bank" --ticker GTCO

# JSE-listed South African
python main.py analyse --company "Shoprite" --signals m_and_a_activity distressed_asset

# East African
python main.py analyse --company "Safaricom" --depth deep --output markdown --out-file safaricom.md

# Pan-African fintech with compliance mode
python main.py analyse --company "Flutterwave" --signals regulatory_action credit_risk --compliance
```

**Feedback & audit**
```bash
# View recent analyst feedback
python main.py feedback --list

# View precision/recall stats per signal type
python main.py feedback --stats

# Submit a false positive correction
python main.py feedback --submit company=WeWork signal_type=m_and_a_activity feedback_type=false_positive original_severity=high note="Deal never materialised"

# Verify audit log chain integrity
python main.py audit --verify

# Tail last 20 audit entries
python main.py audit --tail 20
```

---

## Output Formats

### Terminal (Rich)
Colour-coded brief with severity indicators, alpha score component breakdown, expected move estimates, compliance banners, human review flags, pipeline trace, and sourcing table.

### JSON
Full `AnalystBrief` schema — ready for API integration, downstream ML pipelines, or database ingestion.

```json
{
  "company_name": "Guaranty Trust Bank",
  "ticker": "GTCO",
  "overall_severity": "high",
  "confidence_score": 0.88,
  "signal_candidates_count": 4,
  "top_alpha_score": 76.3,
  "liquidity_tier": "large_cap",
  "requires_human_review": false,
  "detected_signals": [
    {
      "signal_type": "m_and_a_activity",
      "severity": "high",
      "headline": "NGX announcement confirms acquisition talks",
      "evidence": ["NGX filing cites board approval", "BusinessDay confirms discussions"],
      "confidence": 0.84,
      "corroboration_count": 3,
      "candidate_patterns": ["\\bdefinitive\\s+merger", "\\bboard\\s+approved?\\b"],
      "alpha_score": {
        "score": 76.3,
        "severity_component": 0.78,
        "source_credibility": 1.0,
        "corroboration_weight": 0.80,
        "recency_weight": 0.97,
        "liquidity_tier": "large_cap",
        "expected_direction": "positive",
        "expected_magnitude_pct_low": 8.0,
        "expected_magnitude_pct_high": 20.0,
        "comparable_events_n": 62,
        "move_confidence": "medium",
        "requires_human_review": false
      }
    }
  ]
}
```

### Markdown
Publication-ready brief for client delivery, including alpha scores, expected moves, patterns fired, and pipeline trace.

---

## Data Sources

### US Markets
| Source | Coverage | Auth |
|--------|----------|------|
| SEC EDGAR Submissions API | All public US company filings | None |
| SEC EFTS Full-Text Search | 8-K, 10-K, 10-Q, SC 13D, Form 4 | None |
| Yahoo Finance RSS | Ticker-specific news | None |
| Google News RSS (US) | Financial press | None |

### African Exchanges
| Source | Coverage | Auth |
|--------|----------|------|
| NGX Group | Nigerian Exchange announcements | None |
| JSE SENS (senssearch.co.za) | Mandatory SA disclosures (auto-fallback to Google News ZA) | None |
| NSE Kenya | Nairobi Securities Exchange disclosures | None |
| Ghana Stock Exchange | GSE company announcements | None |

### African Financial News (37 RSS feeds)
Nigeria: BusinessDay, TechCabal, Stears, Nairametrics, Vanguard, ThisDay, Premium Times, The Guardian, Punch, Channels TV  
South Africa: Moneyweb, BusinessLive, Daily Maverick, Fin24, IOL Business, Mail & Guardian  
East Africa: Nation Africa, Daily Monitor Uganda, The East African, Standard Media Kenya, Business Daily Africa, Rwanda New Times, The Citizen Tanzania  
Pan-African: The Africa Report, African Business, Financial Afrik, Disrupt Africa, Ventureburn, WeeTracker, TechPoint Africa, Quartz Africa  
Ghana: Graphic Business, Citi Business, GhanaWeb  
Francophone: Jeune Afrique Economie  
North Africa: Daily News Egypt, Egypt Today  
Horn of Africa: Addis Fortune, The Reporter Ethiopia  

### Private Capital & Institutional Sources (29 scraped)
**PE/Deal Flow:** Global Private Capital, PSG Capital, Africa PE News (Deals/Exits/Debt/VC), AVCA  
**DFIs:** IFC, African Development Bank, Proparco, DBSA, BII (British International Investment), FMO  
**VC Funds:** Partech Africa, Novastar Ventures, Kepple Africa, TLcom Capital, Catalyst Fund  
**Credit/Debt:** Rand Merchant Bank, Standard Bank Research  
**Regulators:** SEC Nigeria, FSCA South Africa, CMA Kenya, CBN, SARB, Bayport Finance, Zawya, Afreximbank  

---

## Project Structure

```
deal-intelligence-agent/
├── main.py                              # CLI: analyse / feedback / audit
├── requirements.txt
├── ARCHITECTURE.md                      # Honest limitations + upgrade roadmap
├── src/
│   ├── schemas/
│   │   └── models.py                   # All Pydantic types
│   ├── engines/                        # Phase 2: deterministic + scoring layers
│   │   ├── deterministic_engine.py     # 70+ rules, NER, corroboration — zero LLM
│   │   ├── calibration.py             # Historical base rate tables → calibrated severity
│   │   ├── alpha_scorer.py            # 0–100 alpha score, expected move, compliance flags
│   │   ├── feedback.py                # False positive logging, analyst corrections, source EMA
│   │   └── audit_log.py               # SHA-256 hash-chained immutable audit trail
│   ├── tools/
│   │   ├── edgar_tool.py              # SEC EDGAR API (US)
│   │   ├── africa_tool.py             # NGX/JSE/NSE + 37 feeds + 29 PE/institutional sources
│   │   └── news_tool.py               # Global RSS + relevance scoring
│   ├── agents/
│   │   ├── collection_agent.py        # Node 1: 3-pipeline concurrent collection
│   │   ├── signal_agent.py            # Nodes 2–5: det. engine, LLM explain, alpha, synthesis
│   │   └── graph.py                   # LangGraph orchestration + run_analysis()
│   └── utils/
│       └── formatter.py               # Terminal (Rich), JSON, Markdown
├── data/
│   ├── feedback.json                  # Analyst corrections (auto-created)
│   └── audit_log.jsonl                # Immutable audit trail (auto-created)
└── tests/
    └── test_all.py                    # 111 tests across all layers
```

---

## Testing

```bash
pytest tests/test_all.py -v
```

**111 tests** across: schemas, deterministic engine (all 8 signal types, corroboration, NER, credibility), calibration (base rates, CRITICAL constraints), alpha scorer (ranking, recency decay, liquidity tier, expected moves, compliance flags), feedback loop (precision/recall, EMA, persistence), audit log (hash chain, tamper detection), Africa tool (37 feeds, 29 PE sources, RSS parsing, HTML scraping), EDGAR tool, signal parsing (LLM-cannot-invent constraint), collection agent (3-pipeline merge, deduplication, fault isolation), brief synthesis, formatter (JSON roundtrip, Markdown sections, alpha score output), graph integration (full pipeline, zero-candidate enforcement, compliance mode passthrough).

---

## Key Design Decisions

**Deterministic engine gates the LLM.** The LLM receives only pre-confirmed signal candidates from the rule engine. It explains — it does not decide. If the engine produces nothing, the brief has no signals, regardless of what the LLM might have found on its own.

**Severity is calibrated, not opined.** Every severity assignment maps to a historical materialisation rate table. `CRITICAL` on a `distressed_asset` signal means 91% of comparable cases led to a confirmed event within 90 days — not that the LLM used alarming language.

**CRITICAL requires 2+ independent sources.** A single source, however credible, cannot trigger CRITICAL severity. This is a hard compliance constraint in the calibration engine.

**Three concurrent data pipelines.** SEC EDGAR, African exchanges/news, and global news all run as concurrent asyncio tasks. Each fails independently — JSE SENS being down does not prevent EDGAR or news from completing.

**Hash-chained audit trail.** Every pipeline decision is written to an append-only JSONL file with a SHA-256 hash of the previous entry. `python main.py audit --verify` checks the full chain. Tampering with any entry breaks all subsequent hashes.

**Feedback closes the loop.** Analysts submit corrections via `python main.py feedback --submit`. Stats accumulate per signal type. Source reliability scores update via EMA. In a production deployment these drive recalibration of base rate tables.

---

## Roadmap (see ARCHITECTURE.md for full detail)

| Phase | What | Status |
|-------|------|--------|
| 1 — Backtested signal engine | Validate signals vs historical market moves | Next |
| 2 — Separation of concerns | ✅ Deterministic engine + LLM explanation layer | **Done** |
| 3 — Alpha score layer | ✅ Investable rankings with expected move estimates | **Done** |
| 4 — Institutional version | ✅ Audit logs, compliance mode, explainability constraints | **Done** |
| 5 — Multi-user / team mode | Watchlists, portfolio-level briefs, push alerts | Planned |
| 6 — ML severity model | Replace base rate tables with trained outcome model | Planned |

---

## Author

**Henry Dibie** — ML Systems Engineer & Data Scientist  
[github.com/HenryMorganDibie](https://github.com/HenryMorganDibie) · [linkedin.com/in/kinghenrymorgan](https://linkedin.com/in/kinghenrymorgan)
