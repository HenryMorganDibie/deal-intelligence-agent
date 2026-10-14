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
  Severity comes from rule-strength bands (stated thresholds, not data).
  Confidence is measured: the hit rate of past flags of the same type and severity in
  the walk-forward backtest (engines/measured.py), smoothed for small samples. The
  hosted service pools every labelled live outcome with the backtest observations
  hourly (outcome_rows RPC, measured.set_live), so rates and move ranges follow the
  market; a market's own live rate is used once it has 10 outcomes. Each signal also carries a
  7-component evidence-quality rubric (engines/confidence.py), shown in briefs.
  LLM writes: headline, evidence list, 2-3 sentence reasoning. Cannot change signal_type or severity.
  Fallback: if LLM API fails, deterministic output used directly (no crash).
      │
      ▼
Node 4 — AlphaScoringNode                              ← ZERO LLM
  0–100 composite score: severity×0.35 + credibility×0.25 + corroboration×0.20 + recency×0.10 + liquidity×0.10
  Weights are design choices, tested in the backtest: confirmation rate by alpha third
  13% / 25% / 40%, and within leadership (30% -> 62%) and M&A (4% -> 14%).
  Expected move: the measured market-adjusted 10-day return after the same kind of flag
  (interquartile range, median, n), or "insufficient history" below 10 observations.
  SHAP-style explainer: every point attributed to a specific component.
  Compliance flags: human review at alpha ≥70 or CRITICAL severity.
      │
      ▼
Node 5 — SignalInteractionEngine                       ← ZERO LLM
  14 typed interaction rules across 5 categories (reinforcing/cascading/escalating/converging/contradictory).
  Each rule carries a multiplier (up to 2.5×). It is recorded as a compound-adjusted
  score beside the alpha, not folded into it, because it has not been validated; it can
  still trigger human review. Example: CEO departure + covenant breach + insider selling
  → CASCADING distress (2.5×).
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
| Signal Interaction Engine | `engines/signal_interaction.py` | 17 direction-aware compound event rules, compound-adjusted scores (untested) |
| Calibration | `engines/calibration.py` | Severity bands + measured hit rates (`engines/measured.py`) |
| Adaptive Calibration | `engines/adaptive_calibration.py` | Outcome-aware severity adjustment from feedback |
| Confidence Decomposition | `engines/confidence.py` | 7-component evidence-quality breakdown attached to every signal |
| Semantic Extraction | `engines/semantic.py` | 9 typed financial clause categories |
| Alpha Scorer | `engines/alpha_scorer.py` | 0–100 composite + measured moves after similar flags |
| Alpha Explainer | `engines/alpha_explainer.py` | SHAP-style deterministic score attribution |
| Signal Registry | `engines/signal_registry.py` | Signal metadata; patterns derived from the engine's `SIGNAL_RULES` |
| Signal Interaction | `engines/signal_interaction.py` | Compound event detection, escalation |
| Feedback Loop | `engines/feedback.py` | False positive logging, source EMA, precision/recall |
| Audit Log | `engines/audit_log.py` | SHA-256 hash-chained immutable trail |
| Historical Warehouse | `engines/warehouse.py` | SQLite, 8 tables, full artifact storage |
| Replay Engine | `engines/replay.py` | Deterministic as-of-date historical reproduction |
| Backtesting Engine | `engines/backtest.py` | Precision/hit rate/10-day return/drawdown vs recorded outcomes |
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
SEC EDGAR (8-K with item codes, 10-K, 10-Q, SC 13D/13G, Form 4 open-market trades, DEF 14A), Yahoo Finance RSS, Google News US

### African Exchanges
Official disclosures are read directly from the exchanges' own systems and treated as filings (credibility 1.0):
- **NGX (Nigeria):** the exchange's corporate-disclosure document library, queried by symbol (or company name), full history within the lookback window.
- **NSE Kenya:** listed-company documents (results, announcements) in the exchange's document library, searched by company name.
- **JSE (South Africa):** SENS announcements by JSE code via Sharenet. Free access covers the current trading day only, so each run (and each monitoring cycle) captures that day's SENS; earlier JSE events come from news. The JSE's own site blocks automated access.

Exchange-related results from news search are kept as news, credited to their publisher. GSE, EGX, Casablanca and BRVM are covered through news and scraped sources.

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

Each item says what was done about it and what remains. Where what remains is data,
not code, the system now gathers that data itself.

### 1. Backtesting needs time to accumulate
**Done.** Outcomes are labelled automatically (`outcomes --auto-label` locally; a daily
Vercel cron for hosted briefs). For each prediction the labeller records the 5, 10 and
30-day price move and the same move net of a market benchmark (SPY for US listings, the
Satrix 40 tracker for JSE), and, for US companies, whether a confirming SEC filing followed
within 90 days (8-K Item 2.01/5.01 after an M&A signal, 5.02 after a leadership signal,
1.03/3.01 after distress, 2.04/2.06 after credit stress, 4.02 after an earnings
restatement signal, a tender offer or 13D for the matching types). Every such filing is
also kept as ground truth, so the backtest reports **recall and F1** with the missed
events listed, alongside precision over labelled predictions and benchmark-adjusted returns.

**Remains.** Statistical weight still needs volume: roughly 50 labelled outcomes per signal
type. Labelling starts 12 days after a brief and confirmation closes at 95 days, so numbers
firm up over the first few months of use. Regulatory actions have no confirming SEC form,
so they are scored on price reaction only.

### 2. African market calibration
**Done.** Every outcome records its market (`us` / `africa`), and adaptive calibration uses
observed precision for the company's own market once a signal type has 10 outcomes there,
so African severities calibrate on African results rather than US base rates. JSE outcomes
are benchmark-adjusted.

**Since done.** African outcomes are also confirmed by NGX and NSE Kenya disclosures and by
credible news (credibility 0.70 or more, completion language, company as subject), and NGX
and NSE Kenya prices come from the exchanges themselves (benchmarked to the NGX ASI and
NSE NASI) with a daily snapshot building their history.

**Remains.** Until 10 African outcomes accumulate per signal type, treat African severities
with the static tables' caution. The historical backtest's African sample is small (see
docs/BACKTEST.md).

### 3. LLM non-determinism
**Done.** Identical LLM requests (same provider, model, effort, prompts and token budget)
return the stored reply, so re-running or replaying an analysis over the same sources gives
the same wording (`data/llm_cache.json`, at most 2,000 entries; `DEAL_INTEL_LLM_CACHE=0`
disables it). Signal type, severity, confidence and alpha were already deterministic.

**Remains.** New sources produce new wording, by design. The cache is per machine; the
hosted API's serverless instances do not share one.

### 4. Market data covers listed companies only
Yahoo Finance covers US and major African listings. Private companies, OTC instruments and
thinly traded African stocks may return no prices; those outcomes are labelled from SEC
filings where available, otherwise left unlabelled (never counted as wrong). Manual
`outcomes --record` remains for anything else. A licensed feed (Bloomberg, Refinitiv) is the
only way to close this fully.

### 5. Entity graph
**Done.** Every Form 4 read during an analysis (routine ones included) names an officer,
director or 10% holder; they are added to the graph keyed by SEC CIK. A person found at two
analysed companies links them by board overlap, which contagion detection follows, from the
first analyses rather than after manual entry.

**Remains.** Links come from SEC insiders, so they cover US-listed companies. Lender and
acquisition edges are still added by hand (`graph` commands).

### 6. Detection is pattern-based, now in English and French
**Done.** The rule engine and semantic extractor read French as well as English: 64 French
patterns across all eight signal types (OPA, redressement judiciaire, avertissement sur
résultats, démission du directeur général, franchissement de seuil, sanctions by the
CREPMF, AMF-UMOA, AMMC, COBAC and others), French clause splitting and pronouns for
attribution, FCFA/XOF/MAD/TND amounts, and French news search for francophone Africa.

**Since done.** Portuguese and Arabic rules and news search; every national regulator and
central bank of the 54 countries is matched by the regulatory-action rules.

**Remains.** Detection is still patterns, not a trained model: unusual phrasings can be
missed. A FinBERT-style model would raise recall but does not fit the hosted function's
size limit, so it belongs in a separate service.

---

### 7. Signal Direction
Earnings surprises and insider activity can go either way. The expected direction is read
from the source text (English or French): a beat or raised guidance is positive, a miss or
warning negative; an open-market insider purchase is positive, a discretionary sale
negative. Positive-direction signals do not raise a company's risk score, and compound
events only narrate a direction the evidence states (17 direction-aware rules).

Form 4 filings are reduced to discretionary open-market trades for detection: purchases,
and sales of at least $1M not made under a Rule 10b5-1 plan. Every Form 4 in the lookback
window is read, paced to 8 requests per second under SEC's fair-access limit.

### 8. Replay Depends on Feedback State
Replay runs the same deterministic path as a live analysis. Adaptive calibration depends on
accumulated feedback and outcomes, so the statistics in use are recorded in each replay's
config snapshot to explain any difference from the original run.

### 9. Liquidity Tiers
Tiers come from live market capitalisation in USD (large ≥ $10B, mid ≥ $2B, small ≥ $300M),
converted from local currency where needed. Listings Yahoo does not cover (most NGX and NSE
Kenya names) fall back to a static list and exchange heuristics.

### 10. News Scoring and the Lookback Window
A news item's score is rule strength × publisher credibility. Every source must fall inside
the lookback window, measured from the as-of date for replays and from now otherwise.

### 11. Subject Attribution
A news item must name the company, and the triggering phrase must be about it:
- **Clause rule (deterministic).** A rule fires only if its trigger is in a clause about
  the company. Headlines split at separators and subordinating words (English and French).
  A clause counts as about the company if it names it; if it opens with a back-reference
  ("it", "the company", "elle", "le groupe") right after a clause the company led ("Shares
  of Acme jump after it beats estimates"); or if it follows a label that is just the name
  ("Acme: CEO resigns"). For subject-owned events (earnings, leadership, credit) the company
  must come before the trigger.
- **LLM check (when configured).** The explanation step also reports whether the evidence is
  about the company; a "no" is shown as an attribution doubt and requires human review.

It remains a heuristic: a back-reference after a clause the company did not lead is not
followed, trading a little recall for precision.

### 12. Deals database: extracted from reporting
Deals are extracted by rules from headlines (English, French, Portuguese), with every
source linked. On a held-out labelled set (evaluation/README.md) 82% [75–88] of extracted
records are genuine transactions, 92% [85–96] of deal-like headlines are caught, and 71%
[61–79] of records have every field right; missed duplicates and malformed party names are
the main weaknesses. Each record carries its own verification (engines/provenance.py):
sources grouped into independent stories, and every field marked corroborated, single
source, derived, classified, uncertain or not disclosed. Amounts are as reported, converted at the deal year's average official
rate. Undisclosed deals that no one reports cannot appear, and a headline that names no
African country or Africa is not placed. Raw headlines are kept, so an improved extractor
is re-applied with `deals --reextract`.

### 13. Financial statements: parsed, then checked
NGX and NSE Kenya statements are parsed from the filed PDFs: each line item's first two
figure columns are taken as the Group's current and prior year. Layouts vary, so every
figure carries a status from accounting identities (verified, inconsistent, unchecked) and
a statement is marked verified only when every check passes. Interim statements are listed
but not parsed (their column order varies). Other exchanges have no machine-readable
filings; Yahoo Finance covers JSE, EGX, Casablanca and foreign listings.

### 14. Country risk: public, annual data
Scores use World Bank indicators (annual, often a year old) and live spot FX; there is no
sovereign rating or bond-spread input, which are licensed. Components without data are
dropped and the weights re-normalised; the coverage figure says how much was available.

### 15. Research answers: grounded, not infallible
The LLM writes only from numbered evidence, invalid citations are removed and uncited
sentences are reported, but a cited sentence can still paraphrase its source loosely.
Every answer lists its evidence so a reader can check.

### 16. Coverage is uneven across the 54 countries
Every country gets news search in its languages, deals, events, regulators and country
risk. Machine-readable filings and prices exist for NGX and NSE Kenya (tier A), vendor data
for JSE, EGX and Casablanca (tier B); the other 49 are news-only (tier C). The coverage
page states this per country.

### 17. What is measured and what is a design choice
Measured: signal confidence (hit rates by type and severity), expected moves (market-
adjusted returns after similar flags), the evidence rubric's historical-precision
component, country risk inputs, deal amounts and FX conversion. Design choices, stated:
severity band thresholds, the alpha weights, the evidence rubric's other grades,
comparable-deal scoring and the risk formulas' scaling. Earlier versions carried hand-typed
expected-move ranges and materialisation rates attributed to academic studies that do not
publish such figures; they were replaced with the measured tables, and the alpha weights
were tested against outcomes (docs/BACKTEST.md, "Does alpha rank signals?"). The measured
tables rest on the backtest universe (docs/backtest_universe.csv, about 2,000 companies, re-run
monthly over 18 monthly dates); some signal types still have small samples, so every
figure carries its count.

---

## CLI Command Reference

```bash
# Analysis
python main.py analyse --company "GTBank" --ticker GTCO [--country NG] [--compliance] [--output json|markdown]

# Deals, countries, research, companies
python main.py deals --ingest | --backfill 24 | --reextract | --upload | --search TEXT [--country NG]
python main.py countries [--country SN] [--refresh]
python main.py research "QUESTION" [--no-news]
python main.py profile --company "Dangote Cement" --ticker DANGCEM.LG
python main.py backtest --historical --start 2024-01-15 --end 2025-06-15

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
python main.py outcomes --auto-label   # label past predictions automatically
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
| Alpha score layer | 0–100 composite + measured moves + SHAP explainer, validated in the backtest | ✅ Done |
| Compound event engine | 17 direction-aware interaction rules + escalation multipliers | ✅ Done |
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
| Backtesting framework | Precision, recall, F1, hit rate, abnormal return, drawdown | ✅ Done |
| Market data integration | yfinance auto-outcome fetching | ✅ Done |
| Portfolio intelligence | Portfolio risk aggregation + contagion clusters | ✅ Done |
| Entity resolution | Canonical registry + LEI/CIK/alias deduplication | ✅ Done |
| African market depth | 49 feeds + 48 PE/DFI sources + 7 exchanges | ✅ Done |
| Automatic outcome labelling | Benchmark-adjusted returns, SEC ground truth, recall/F1, per-market calibration | ✅ Done |
| French-language detection | Rules, extraction, attribution and news for francophone Africa | ✅ Done |
| Hybrid NLP detection | FinBERT/sentence-transformers alongside deterministic (separate service) | Next |
| ML severity model | Trained outcome model replacing the rule-strength bands | Next |
| Live market data (pro) | Bloomberg/Refinitiv for full coverage | Next |
| Hosted app | Open-access web app with shareable briefs (Next.js + Vercel) | ✅ Done |
| All 54 African countries | Registry, national news editions and languages, regulators, coverage tiers | ✅ Done |
| Deals database | PE, VC, debt, M&A, fund closes, exits, IPOs from 54-country feeds, two-year backfill | ✅ Done |
| Investors and funds | Roles, registry, profiles, LPs and GP activity | ✅ Done |
| Company financials | Verified NGX / NSE Kenya statements, Yahoo, SEC cross-check | ✅ Done |
| Country, currency, sector risk | World Bank-based scores, currency regimes, sector event balance | ✅ Done |
| Grounded research | Cited answers, checked citations, country and sector reports | ✅ Done |
| Monitoring and alerts | Daily event feed, watchlists, RSS, webhooks | ✅ Done |
| Historical backtest | Walk-forward replay, lift vs base rate, severity breakdown | ✅ Done |
| Research dashboard | Risk timelines, heatmaps, replay UI | Next |
| Multi-user team mode | Shared watchlists, portfolio briefs, role-based access | Planned |
| Proprietary dataset | Structured event intelligence dataset for model training | Long-term |

---

*Last updated: October 2026. Maintained alongside codebase.*
