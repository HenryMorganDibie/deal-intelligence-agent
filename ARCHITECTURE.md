# Architecture & Roadmap

This document provides an honest technical assessment of the current system — written from the perspective of a fund technology reviewer — its known limitations, and the engineering roadmap toward an institutional-grade deal intelligence platform.

---

## Current State: Early Production

The system is **production-ready for research and analyst augmentation** — it reliably collects data from US and African markets, surfaces signals across 8 signal types, and produces structured briefs with reasoning traces. It is **not yet suitable as a primary decision engine** for fund deployment without the upgrades described below.

---

## Known Limitations

### 1. Signal Taxonomy Is Heuristic — No Calibration Layer

Signals are currently defined by keyword lists and LLM pattern matching, not by calibrated statistical models. There is no backtesting against known events.

**What this means in practice:**
- "Business rescue" triggers a `distressed_asset` signal regardless of whether the company is actually at risk of liquidation or simply undergoing a routine operational restructuring
- A company filing a routine 10-K mentioning "debt covenant" in passing may score identically to a company actively in breach
- There is no minimum evidence threshold — one corroborating source produces the same signal type as five

**What's missing:** A calibration layer that maps keyword/LLM output to historical base rates. For example: *"Of the last 200 companies where we detected `credit_risk: high`, what % actually experienced a credit event within 90 days?"* Without this, the signal taxonomy is a well-structured hypothesis, not a validated detection system.

---

### 2. Severity Scores Are Not Grounded in Outcomes

`severity: critical` is assigned by the LLM based on language in the source material. It is not tied to:
- Historical PnL impact of similar events
- Actual price moves following equivalent filings
- Credit spread widening or equity drawdown in comparable situations

**What this means in practice:**
- A `critical` signal on a small-cap Nigerian company with thin trading volume is not comparable to a `critical` signal on a JSE Top 40 constituent — the severity label treats them identically
- There is no position-sizing guidance embedded in the severity score
- Two analysts reading the same brief may reach different conclusions about materiality because the severity score carries no quantitative anchor

**What's missing:** An outcome-linked scoring function trained on historical events where the ground truth (price move, credit event, deal completion) is known. Severity should map to expected PnL impact, not linguistic intensity.

---

### 3. The LLM Is Central to Signal Definition

Currently Claude both *detects* and *explains* signals. This conflates two architecturally distinct functions:

| Function | Current | Target |
|----------|---------|--------|
| Signal detection | LLM | Deterministic rules engine |
| Signal explanation | LLM | LLM (appropriate use) |
| Severity scoring | LLM | Outcome-calibrated model |
| Source weighting | None | Credibility-weighted aggregator |

**The core risk:** LLMs are non-deterministic. Running the same filing through the system twice can produce different signals. For a fund tech stack, this means the system cannot be audited against a fixed decision tree — which is a compliance problem, not just an engineering one. The LLM should explain signals, not define them.

**What's missing:** A deterministic first pass — structured rules, NER, financial entity extraction — that produces a stable signal candidate list. The LLM then contextualises and explains confirmed candidates. It never invents.

---

### 4. No Feedback Loop

The system has no mechanism to learn from:
- **False positives** — signals flagged but not materialised
- **Missed events** — deals or defaults that occurred but were not surfaced
- **Analyst corrections** — when a human analyst overrides or dismisses a signal

**What this means in practice:**
- Signal quality does not improve over time — the system makes the same mistakes in month 12 as in month 1
- There is no precision/recall measurement across signal types or markets
- The system cannot distinguish between a source it has found reliable (Reuters on Nigerian M&A) versus one it has found noisy (generic Google News aggregation)
- There is no weighting difference between a story corroborated by three independent sources and a story from a single low-credibility outlet

**What's missing:** A feedback schema, a corrections API, and a source reliability model that updates based on signal outcomes.

---

## Upgrade Roadmap

### Phase 1 — Backtested Signal Engine

**Goal:** Validate that detected signals have genuine predictive power before using them operationally.

**Approach:**
1. Build a historical event database — collect known M&A completions, defaults, leadership changes, and regulatory actions from public records (SEC, Bloomberg historical, African exchange archives, AVCA deal database) for 2018–2024
2. Run the current system in retrospective mode against historical filings from those periods
3. Measure per signal type: **precision** (of flagged events, how many materialised?), **recall** (of known events, how many were flagged?), and **lead time** (how many days before the event was the signal first detectable?)
4. Set minimum confidence thresholds per signal type based on empirical base rates
5. Publish a precision/recall card per signal type and per market (US vs African)

**Outcome:** Signal taxonomy becomes empirically grounded. The system ships with stated false positive rates that a fund risk committee can evaluate.

---

### Phase 2 — Separation of Concerns Architecture

**Goal:** Make signal detection deterministic and auditable. Confine LLM to explanation only.

```
Raw Data (filings, news, PE sources)
        │
        ▼
┌─────────────────────────────────────┐
│   Deterministic Signal Engine        │  ← Rules engine + NER + financial entity extraction
│                                      │    • Pattern matching on filing language
│                                      │    • Named entity recognition (company, person, amount)
│                                      │    • Structured financial event extraction
│                                      │    • Source credibility weighting
│                                      │    • Output: SignalCandidate[] with evidence pointers
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│   Outcome-Calibrated Severity Scorer │  ← Trained on historical event outcomes
│                                      │    • Features: entity type, market cap tier,
│                                      │      source count, filing type, keyword density
│                                      │    • Output: severity score + confidence interval
│                                      │    • African market tier awareness built in
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│   LLM Explanation Layer              │  ← Claude (appropriate use only)
│                                      │    • Contextualise confirmed signals
│                                      │    • Write analyst-readable reasoning
│                                      │    • Flag ambiguity and contradictions
│                                      │    • NEVER invents signals — only explains them
└──────────────────┬──────────────────┘
                   │
                   ▼
             AnalystBrief
```

**Hard architectural constraint:** If the deterministic engine produces zero signal candidates, the LLM produces zero signals — no exceptions. The LLM cannot override the engine.

---

### Phase 3 — Alpha Score Layer

**Goal:** Turn signals into investable rankings with actionable position guidance.

**Alpha Score (0–100):** A composite rank combining:
- Signal severity (outcome-calibrated, not LLM-assigned)
- Source credibility weight (Reuters > aggregator; AVCA deal data > Google News)
- Corroboration count (number of independent sources confirming)
- Recency decay (signal strength decays over time without reinforcement)
- Market liquidity tier (signal on a liquid instrument scores higher for actionability)

**Expected Move Estimate:** For public equities — estimated price impact based on comparable historical events. Example: *"8-K merger announcements of this type preceded an average 18% equity move within 10 trading days across 14 comparable cases."*

**Position Sizing Guidance:** Risk-adjusted signal strength expressed as a fraction of book, based on confidence interval and liquidity tier. Not a recommendation — a calibrated input to the portfolio manager's sizing decision.

**Output schema addition:**
```json
{
  "alpha_score": 74,
  "alpha_score_components": {
    "severity_calibrated": 0.82,
    "source_credibility": 0.91,
    "corroboration_count": 3,
    "recency_weight": 0.95,
    "liquidity_tier": "mid_cap"
  },
  "expected_move_estimate": {
    "direction": "positive",
    "magnitude_pct": "12–20%",
    "confidence": "medium",
    "comparable_events_n": 14
  }
}
```

---

### Phase 4 — Institutional Version

**Goal:** Deploy in a regulated fund environment with full compliance infrastructure.

**Audit Logs:**
- Every signal stored with immutable timestamp, source hash, model version, and prompt version
- Full decision trace exportable in structured format for compliance review
- Diff logging: if the same filing is reprocessed, what changed and why?
- Tamper-evident log chain for regulatory inspection

**Compliance Mode:**
- Configurable signal suppression (e.g. block `insider_activity` signals for funds with specific compliance walls)
- Mandatory human-in-the-loop flag for signals above a configurable severity threshold — brief cannot be acted on without analyst sign-off
- Output watermarking: every brief labelled AI-generated, unverified, not investment advice
- Information barrier enforcement: restrict brief distribution by analyst role

**Explainability Constraints:**
- Signals above `severity: high` require ≥ 2 independent source corroborations to appear in brief
- Confidence score below 0.60 triggers automatic `LOW CONFIDENCE — VERIFY BEFORE ACTING` flag
- LLM reasoning traces stored and version-controlled alongside model version for post-hoc review
- No severity upgrade without deterministic engine confirmation (Phase 2 dependency)

**Multi-user / Team Mode:**
- Analyst correction API: analysts mark signals as false positive, confirmed, or escalated
- Correction data feeds back to severity calibration model (closes the feedback loop from Limitation 4)
- Team brief: aggregate portfolio-level view across multiple companies in a watchlist
- Alert system: push notification when a monitored company crosses a severity threshold

---

## Summary Assessment

| Dimension | Current | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|-----------|---------|---------|---------|---------|---------|
| Signal detection | Heuristic LLM | Backtested heuristic | Deterministic engine | Deterministic engine | Deterministic + audited |
| Severity scoring | LLM opinion | Threshold-calibrated | Outcome-calibrated model | Alpha score | Alpha + position guidance |
| Explainability | LLM trace | LLM trace | Deterministic + LLM | Full component breakdown | Compliance-grade audit log |
| Feedback loop | None | Manual review | Corrections API | Semi-automated | Fully instrumented |
| African market depth | Exchange + news + PE | + backtested on African events | + African NER model | + Africa alpha tier | Institutional African coverage |
| Deployment fit | Research / analyst augmentation | Analyst augmentation | Supervised fund use | Fund decision support | Institutional deployment |

The current system is a strong foundation. Phases 1 and 2 are the critical path to fund deployment. Phases 3 and 4 are institutional hardening — the difference between a tool a PM uses and a system a CIO signs off on.

---

*Document maintained alongside codebase. Last updated: May 2026.*
