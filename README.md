# Deal Intelligence Agent

An autonomous multi-agent system that monitors regulatory filings and financial news across **US and African markets** to surface actionable deal intelligence signals — M&A activity, credit risk, distressed assets, regulatory actions, and more — delivered as structured analyst briefs with full reasoning traces.

Built for PE firms, credit analysts, hedge funds, and corporate finance teams who need a junior analyst that never sleeps.

---

## Architecture

```
AnalysisRequest
      │
      ▼
┌──────────────────────────────────────────────┐
│           DataCollectionAgent                 │  ← Three concurrent pipelines
│           (LangGraph Node 1)                  │
│                                              │
│  ┌─────────────────┐  ┌────────────────────┐ │
│  │   SEC EDGAR      │  │   Africa Tool      │ │
│  │  (US Markets)    │  │ (African Markets)  │ │
│  │                  │  │                    │ │
│  │ • Company CIK    │  │ • NGX announcements│ │
│  │   resolution     │  │ • JSE SENS filings │ │
│  │ • 8-K, 10-K,     │  │ • NSE Kenya disc.  │ │
│  │   10-Q, SC 13D,  │  │ • 9 African news   │ │
│  │   Form 4 filings │  │   RSS feeds        │ │
│  │ • Full-text      │  │ • Google News      │ │
│  │   keyword search │  │   (NG / ZA / KE)   │ │
│  └─────────────────┘  └────────────────────┘ │
│                                              │
│  ┌──────────────────────────────────────────┐│
│  │         Global News (RSS)                ││
│  │  Reuters · Bloomberg · FT · Yahoo Finance││
│  │  BusinessDay · TechCabal · Moneyweb · ...││
│  └──────────────────────────────────────────┘│
│                                              │
│  → Merge + deduplicate all sources           │
└──────────────────┬───────────────────────────┘
                   │ AgentState (filings, news_items, company_profile)
                   ▼
┌──────────────────────────────────────────────┐
│          SignalDetectionAgent                 │  ← Claude Sonnet (reasoning pass)
│          (LangGraph Node 2)                   │
│  • Analyses all collected data in context     │
│  • Outputs typed DetectedSignal objects       │
│  • Each signal: type, severity, evidence,     │
│    confidence score, reasoning trace,         │
│    source URLs, filing references             │
└──────────────────┬───────────────────────────┘
                   │ AgentState (+ detected_signals)
                   ▼
┌──────────────────────────────────────────────┐
│          BriefSynthesisAgent                  │  ← Claude Sonnet (synthesis pass)
│          (LangGraph Node 3)                   │
│  • Executive summary + recommendation         │
│  • Key metrics, risk factors                  │
│  • Recent developments                        │
│  • Full reasoning trace (audit-ready)         │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
             AnalystBrief
       (JSON | Markdown | Terminal)
```

### Signal Types

| Signal | Description |
|--------|-------------|
| `m_and_a_activity` | Merger/acquisition indicators — SEC filings, NGX/JSE announcements, news |
| `credit_risk` | Debt covenant concerns, credit downgrades (Moody's, S&P, GCR Ratings), liquidity warnings |
| `distressed_asset` | Bankruptcy, business rescue (SA), receivership, going concern language |
| `earnings_surprise` | Revenue misses, profit warnings, trading statements, guidance cuts |
| `leadership_change` | CEO/CFO/MD departures, board resignations |
| `regulatory_action` | SEC/FSCA/CMA/CBN investigations, fines, licence revocations, antitrust |
| `debt_restructuring` | Debt renegotiation, write-downs, impairments |
| `insider_activity` | Form 4 filings, activist investor 13D/13G positions |

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
# Standard analysis
python main.py --company "Apple Inc" --ticker AAPL

# Deep scan, last 6 months, export Markdown brief
python main.py --company "Revlon" --lookback 180 --depth deep --output markdown --out-file brief.md

# Focus on specific signals, export JSON
python main.py --company "SVB Financial" --signals credit_risk debt_restructuring --output json
```

**African companies**
```bash
# Nigerian Exchange listed company
python main.py --company "Guaranty Trust Bank" --ticker GTCO

# JSE-listed South African company
python main.py --company "Shoprite" --signals m_and_a_activity distressed_asset

# East African company
python main.py --company "Safaricom" --depth deep --output markdown --out-file safaricom.md

# Pan-African fintech
python main.py --company "Flutterwave" --signals regulatory_action credit_risk --lookback 180
```

---

## Output

### Terminal (Rich)
Full colour-coded brief with signal severity indicators, metrics table, risk factors, and sourcing — including which exchange or media source each item came from.

### JSON
Complete `AnalystBrief` schema serialised to JSON — ready for API integration, downstream ML pipelines, or database ingestion.

```json
{
  "company_name": "Guaranty Trust Bank",
  "ticker": "GTCO",
  "brief_date": "2024-05-14T10:30:00",
  "overall_severity": "high",
  "confidence_score": 0.88,
  "executive_summary": "...",
  "recommendation": "...",
  "detected_signals": [
    {
      "signal_type": "m_and_a_activity",
      "severity": "high",
      "headline": "NGX announcement confirms acquisition talks",
      "evidence": ["NGX filing cites board approval...", "BusinessDay confirms..."],
      "confidence": 0.91,
      "reasoning": "Both the NGX disclosure and BusinessDay Nigeria coverage..."
    }
  ],
  "key_metrics": [...],
  "risk_factors": [...],
  "reasoning_trace": [...]
}
```

### Markdown
Publication-ready brief for client delivery or documentation.

---

## Data Sources

### US Markets
| Source | Coverage | Auth Required |
|--------|----------|---------------|
| SEC EDGAR Submissions API | All public US company filings | None |
| SEC EFTS Full-Text Search | 8-K, 10-K, 10-Q, SC 13D, Form 4 | None |
| Yahoo Finance RSS | Ticker-specific news | None |
| Google News RSS (US) | Financial news, press releases | None |

### African Markets
| Source | Coverage | Auth Required |
|--------|----------|---------------|
| NGX Group (Nigerian Exchange) | Company announcements, Nigeria | None |
| JSE SENS (senssearch.co.za) | Mandatory disclosures, South Africa | None |
| NSE Kenya Disclosures | Company announcements, Kenya | None |
| BusinessDay Nigeria RSS | Nigerian financial news | None |
| TechCabal RSS | African tech & startup news | None |
| The Africa Report RSS | Pan-African business news | None |
| African Business RSS | Pan-African market news | None |
| Moneyweb RSS | South African financial news | None |
| BusinessLive SA RSS | South African business news | None |
| Stears RSS | Nigerian data & analysis | None |
| Nation Africa RSS | East African business news | None |
| Google News (NG / ZA / KE) | Geo-scoped financial news | None |

No paid data subscriptions required. All sources are public.

---

## Project Structure

```
deal-intelligence-agent/
├── main.py                         # CLI entrypoint
├── requirements.txt
├── src/
│   ├── schemas/
│   │   └── models.py               # Pydantic types: Request, Signal, Brief, State
│   ├── tools/
│   │   ├── edgar_tool.py           # SEC EDGAR API integration (US)
│   │   ├── africa_tool.py          # NGX / JSE SENS / NSE Kenya + African news
│   │   └── news_tool.py            # Global RSS news + relevance scoring
│   ├── agents/
│   │   ├── collection_agent.py     # LangGraph Node 1: 3-pipeline concurrent collection
│   │   ├── signal_agent.py         # LangGraph Nodes 2+3: detection + synthesis
│   │   └── graph.py                # LangGraph graph construction + run_analysis()
│   └── utils/
│       └── formatter.py            # Terminal (Rich), JSON, Markdown renderers
└── tests/
    └── test_all.py                 # 95 tests across all layers
```

---

## Testing

```bash
pytest tests/test_all.py -v
```

**95 tests** covering:
- Schema validation and edge cases
- US tool parsing and error handling (EDGAR, news)
- African tool: RSS parsing, source mapping, relevance scoring, JSE SENS fallback logic, deduplication, lookback filtering
- Agent signal parsing (valid, malformed, edge cases)
- Collection agent: three-pipeline merging, deduplication across US + African sources, fault isolation per pipeline
- Context builder correctness
- Formatter correctness (JSON roundtrip, Markdown sections)
- Full graph integration (end-to-end mocked pipeline)

---

## Key Design Decisions

**Three concurrent pipelines.** SEC EDGAR, African exchanges, and global news all run as concurrent asyncio tasks. Each fails independently — if the JSE SENS feed is down, the EDGAR and news pipelines still complete and signal detection runs on whatever was collected.

**African market parity.** African exchange filings (NGX announcements, JSE SENS, NSE Kenya disclosures) are treated as first-class data — stored in the same `SECFiling` schema as SEC filings, passed through the same signal detection pipeline, and rendered in the same brief. The signal keyword set is extended with African-specific legal and regulatory terms: *business rescue, judicial management, provisional liquidation, FSCA action, CBN sanction, GCR Ratings.*

**JSE SENS fallback.** The JSE SENS RSS (senssearch.co.za) is tried first. If it returns nothing, the tool automatically retries with a Google News ZA query scoped to SENS language — so South African companies are covered even when the primary feed is unavailable.

**Structured outputs over free text.** Every object flowing through the graph is typed with Pydantic. The LLM returns JSON; the parser handles malformed responses gracefully without crashing the pipeline.

**Auditable reasoning traces.** Every `DetectedSignal` carries a `reasoning` field with the model's chain-of-thought. The `AnalystBrief` includes the full `reasoning_trace` across all pipeline steps — a compliance team can reconstruct every decision.

**Rate-limit awareness.** EDGAR's public API is rate-limited to 10 requests/second. The tool inserts `asyncio.sleep(0.12)` between keyword searches and uses retry-with-backoff via `tenacity` on all external calls.

---

## Author

**Henry Dibie** — ML Systems Engineer & Data Scientist  
[github.com/HenryMorganDibie](https://github.com/HenryMorganDibie) · [linkedin.com/in/kinghenrymorgan](https://linkedin.com/in/kinghenrymorgan)s