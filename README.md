# Deal Intelligence Agent

An autonomous multi-agent system that monitors SEC EDGAR filings and financial news to surface actionable deal intelligence signals — M&A activity, credit risk, distressed assets, regulatory actions, and more — delivered as structured analyst briefs with full reasoning traces.

Built for PE firms, credit analysts, hedge funds, and corporate finance teams who need a junior analyst that never sleeps.

---

## Architecture

```
AnalysisRequest
      │
      ▼
┌─────────────────────┐
│  DataCollectionAgent │  ← SEC EDGAR API + RSS news (concurrent)
│  (LangGraph Node 1)  │    • Company resolution via EDGAR submissions
│                      │    • Filing retrieval (8-K, 10-K, 10-Q, SC 13D…)
│                      │    • Full-text keyword search across filings
│                      │    • Multi-source financial news with relevance scoring
└──────────┬──────────┘
           │ AgentState (filings, news_items, company_profile)
           ▼
┌─────────────────────┐
│  SignalDetectionAgent│  ← Claude Sonnet (reasoning pass)
│  (LangGraph Node 2)  │    • Analyses all collected data in structured context
│                      │    • Outputs typed DetectedSignal objects
│                      │    • Each signal has: type, severity, evidence, confidence,
│                      │      reasoning trace, source URLs, filing references
└──────────┬──────────┘
           │ AgentState (+ detected_signals)
           ▼
┌─────────────────────┐
│  BriefSynthesisAgent │  ← Claude Sonnet (synthesis pass)
│  (LangGraph Node 3)  │    • Produces structured AnalystBrief
│                      │    • Executive summary, recommendation, confidence score
│                      │    • Key metrics, risk factors, recent developments
│                      │    • Full reasoning trace (audit-ready)
└──────────┬──────────┘
           │
           ▼
      AnalystBrief
  (JSON | Markdown | Terminal)
```

### Signal Types

| Signal | Description |
|--------|-------------|
| `m_and_a_activity` | Merger/acquisition indicators from filings and news |
| `credit_risk` | Debt covenant concerns, downgrades, liquidity warnings |
| `distressed_asset` | Bankruptcy, receivership, going concern language |
| `earnings_surprise` | Revenue misses, profit warnings, guidance cuts |
| `leadership_change` | CEO/CFO departures, board resignations |
| `regulatory_action` | SEC investigations, antitrust, fines, subpoenas |
| `debt_restructuring` | Debt renegotiation, extension, write-downs |
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

```bash
# Standard analysis — terminal output
python main.py --company "Apple Inc" --ticker AAPL

# Deep scan, last 6 months, export Markdown brief
python main.py --company "Revlon" --lookback 180 --depth deep --output markdown --out-file brief.md

# Focus on specific signals, export JSON
python main.py --company "SVB Financial" --signals credit_risk debt_restructuring --output json

# Quick scan for M&A signals only
python main.py --company "Activision Blizzard" --ticker ATVI --signals m_and_a_activity --depth quick
```

---

## Output

### Terminal (Rich)
Full colour-coded brief with signal severity indicators, metrics table, risk factors, and sourcing.

### JSON
Complete `AnalystBrief` schema serialised to JSON — ready for API integration, downstream ML pipelines, or database ingestion.

```json
{
  "company_name": "Acme Corp",
  "ticker": "ACME",
  "brief_date": "2024-05-14T10:30:00",
  "overall_severity": "high",
  "confidence_score": 0.88,
  "executive_summary": "...",
  "recommendation": "...",
  "detected_signals": [
    {
      "signal_type": "m_and_a_activity",
      "severity": "high",
      "headline": "Definitive merger agreement filed with SEC",
      "evidence": ["8-K cites definitive agreement...", "Reuters confirms..."],
      "confidence": 0.96,
      "reasoning": "Both the SEC 8-K filing and Reuters coverage..."
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

| Source | Coverage | Auth Required |
|--------|----------|---------------|
| SEC EDGAR Submissions API | All public US company filings | None |
| SEC EFTS Full-Text Search | 8-K, 10-K, 10-Q, SC 13D, Form 4 | None |
| Google News RSS | Financial news, press releases | None |
| Yahoo Finance RSS | Ticker-specific news | None |

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
│   │   ├── edgar_tool.py           # SEC EDGAR API integration
│   │   └── news_tool.py            # RSS news collection + relevance scoring
│   ├── agents/
│   │   ├── collection_agent.py     # LangGraph Node 1: data collection
│   │   ├── signal_agent.py         # LangGraph Nodes 2+3: detection + synthesis
│   │   └── graph.py                # LangGraph graph construction + run_analysis()
│   └── utils/
│       └── formatter.py            # Terminal (Rich), JSON, Markdown renderers
└── tests/
    └── test_all.py                 # 65 tests across all layers
```

---

## Testing

```bash
pytest tests/test_all.py -v
```

**65 tests** covering:
- Schema validation and edge cases
- Tool parsing and error handling
- Agent signal parsing (valid, malformed, edge cases)
- Context builder correctness
- Formatter correctness (JSON roundtrip, Markdown sections)
- Agent fault isolation (EDGAR down, Claude down, news down)
- Full graph integration (end-to-end mocked pipeline)

---

## Key Design Decisions

**Structured outputs over free text.** Every piece of data flowing through the graph is typed with Pydantic. The LLM is instructed to return JSON; the parser handles malformed responses gracefully without crashing the pipeline.

**Fault isolation.** Each agent catches its own errors and appends to `state.errors`. A failed news fetch does not prevent signal detection from running on filing data alone.

**Auditable reasoning traces.** Every `DetectedSignal` carries a `reasoning` field containing the model's chain-of-thought. The `AnalystBrief` includes the full `reasoning_trace` across all pipeline steps — a compliance team can reconstruct every decision.

**Concurrent data collection.** EDGAR and news fetching run as concurrent asyncio tasks, cutting wall time roughly in half.

**Rate-limit awareness.** EDGAR's public API is rate-limited to 10 requests/second. The tool inserts `asyncio.sleep(0.12)` between keyword searches and uses retry-with-backoff via `tenacity`.

---

## Author

**Henry Dibie** — ML Systems Engineer & Data Scientist  
[github.com/HenryMorganDibie](https://github.com/HenryMorganDibie) · [linkedin.com/in/kinghenrymorgan](https://linkedin.com/in/kinghenrymorgan)
