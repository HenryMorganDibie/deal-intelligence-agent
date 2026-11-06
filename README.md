# Deal Intelligence

> **Proprietary software. All rights reserved.** This repository is the private property of Henry Chukwunwike Dibie (Deal Intelligence). No licence is granted to use, copy, clone, modify or distribute any part of it. See [LICENSE](LICENSE). Licensing enquiries: info@deal-intelligence.app

Deal and market intelligence for **all 54 African countries** (and US listings): private deals, corporate events,
investors, listed markets, government securities, country risk, company briefs and source-grounded research, in one
signed-in web app.

**Live:** [deal-intelligence.app](https://deal-intelligence.app)

Built for PE and VC firms, DFIs, credit analysts, research houses and corporate finance teams.

---

## What it covers

| Area | What it does |
|---|---|
| **Deals** | 5,100+ PE, VC, debt and M&A transactions extracted from African business and private-capital news in English, French and Portuguese, refreshed twice a day: parties and their roles, amount in USD, stake, round, stage, sector, country, every source linked, field-level verification |
| **Corporate events** | 5,300+ events across the 54 countries (results, leadership changes, regulatory actions, listings, defaults), classified by a deterministic engine |
| **Investors and funds** | Investor, lender, acquirer, LP and GP roles; a registry of Africa-focused DFIs, multilaterals, PE, VC, sovereign and pension investors that resolves name variants; leaderboards, profiles, fund closes with their LPs; investors named in round articles are read automatically |
| **Listed markets** | Daily quotes for 24 exchanges (JSE, NGX, EGX, NSE Kenya, Casablanca, BRVM, GSE, SEM, Tunis, Botswana, Dar es Salaam, Lusaka, Malawi, Namibia, Rwanda, Zimbabwe, Uganda, Ethiopia, Victoria Falls, BVMAC, BODIVA, Algiers, Eswatini, MERJ), delayed intraday for JSE and NGX, indices, movers, sectors and dollar rates; a cross-exchange screener and company directory |
| **Government securities and rates** | Treasury bills from central banks and auction results (Nigeria, Kenya, Ghana, South Africa, Morocco, The Gambia, Seychelles, Tanzania, Zambia, Uganda, Malawi, Botswana, the eight WAEMU states and the CEMAC curve), each yield reconciled with the issuer's own price convention; individual Kenyan bonds; policy rates; bank deposit rates; Lagos and Nairobi ETFs; unlisted funds |
| **Portfolios and valuation** | Holdings valued at the latest closes, monitoring, comparisons; DCF and multiples with every input checked against exchange data and the filing it came from; country cost of equity with its build-up |
| **Company briefs** | Signals from SEC EDGAR, exchange disclosures and news, scored by a deterministic rule engine; the language model explains confirmed findings and cannot invent signals |
| **Research and reports** | Answers built only from numbered evidence (deals, events, risk, investors, live news), with citations checked and invalid ones removed; country and sector reports |
| **Country, currency and sector risk** | A 0 to 100 score for every country from World Bank governance and macro indicators, with each component shown; 42 currencies (regime, official vs parallel, depreciation, volatility); sector risk from adverse events and deal flow |
| **Watchlists and alerts** | Watchlists by company, country and event type with RSS, webhooks, and email alerts to the signed-in account's verified address (one-click unsubscribe) |
| **Evaluation** | Walk-forward historical backtest, live outcome labelling, and published held-out scores for deal extraction and attribution (see [Evaluation](#evaluation)) |

Data is what public sources carry: undisclosed private deals cannot appear, and most exchanges outside NGX and NSE
Kenya publish no machine-readable filings. The coverage page states this per country.

---

## How it is built

```
News, filings, exchanges, central banks
        │  collected on GitHub Actions (scheduled jobs, scripts/run_cron.py)
        ▼
Deterministic engines ── deals, events, investors, quotes, instruments, risk
        │  written through shared-secret database functions
        ▼
Supabase (Postgres, Auth) ── row level security; writes only via functions
        │
        ├── API (FastAPI on Vercel, api/index.py) ── public data cached at the edge
        └── Web app (Next.js 14 on Vercel, web/) ── sign-in required for /app
```

**Principles**

- **Deterministic first.** Signals, deals and events come from stated rules that give the same answer every time.
  The language model writes explanations and narratives only; if it is unavailable, briefs are still produced from
  the engine's findings and labelled as such.
- **Every figure has a source.** Deals link their stories, statements are checked with accounting identities, yields
  are reconciled with the issuer's prices, valuation inputs are checked against the filing.
- **Reported limits.** Coverage tiers per country, sample sizes and 95% intervals on every evaluation figure.

**Company brief pipeline (8 nodes)**

```
Request
  → DataCollection       SEC EDGAR, African exchange disclosures, 50 outlet feeds, 48 PE and institutional sources
  → DeterministicEngine  70+ rules, entity recognition, corroboration (no language model)
  → LLMExplanation       explains confirmed candidates only
  → AlphaScoring         0 to 100 composite with attribution and measured moves after similar flags
  → SignalInteraction    direction-aware compound event rules
  → BriefSynthesis       narrative only; signal data is locked
  → PostProcessing       warehouse, company memory, entity graph
  → AnalystBrief
```

---

## Hosted app

| Piece | Where | Notes |
|---|---|---|
| Web | Vercel project `deal-intelligence-app`, root `web/` | Landing page, sign-in, and the app (`/app`) |
| API | Vercel project `deal-intelligence-api`, repository root (`vercel.json`) | All routes are listed at the top of `src/hosted_market.py` |
| Database and auth | Supabase | Schema in `supabase/migrations/`; tables have row level security, writes go through functions that require `DEAL_INTEL_API_SECRET` |
| Scheduled jobs | GitHub Actions | See [Scheduled jobs](#scheduled-jobs); only the weekday market snapshot remains a Vercel cron (it must run from Europe) |
| Email | SendByte | Account emails (through Supabase SMTP) and watchlist alerts |

**App sections:** Deals, Investors, Companies, Markets (overview, screener, compare, investments, portfolio,
monitoring, valuation), Market briefs, Briefs, Research, Countries, Watchlists, Coverage, Evaluation.

**Accounts.** Opening the app requires an account. Sign-up takes an email, a unique username and a nickname; passwords
must be at least 12 characters with mixed character types, are checked against known data breaches, and must be typed
twice. Google sign-in, email confirmation, password reset, optional two-factor sign-in with an authenticator app
(enforced on the server for data access), and sign-out from all devices are supported. The edge middleware
(`web/middleware.ts`) verifies the session signature on every app request.

**Admin.** `/admin`, unlocked with `DEAL_INTEL_ADMIN_KEY`, shows anonymous visits and feature use, plus every
account: sign-up method, confirmation, username, last use and active days. Activity is recorded at most once per
30 minutes per account, never per page.

**Staying within Vercel's free allowance.** The hosting is kept inside the Hobby plan by design:

- Collection, ingestion, alerts and market refreshes run on GitHub Actions, not Vercel; only the weekday market
  snapshot is a Vercel cron.
- A deployment empties the edge cache and restarts every function, so each project redeploys only when something it
  serves changed (`deploy/vercel-ignore-api.sh`, `web/deploy/vercel-ignore-web.sh`; kept out of `scripts/`, which `.vercelignore` removes). Automatic data commits that
  only the jobs or the other project read no longer redeploy it.
- Public datasets are cached at the edge for 15 to 60 minutes, so repeat visits do not run functions, and the API
  domain disallows crawlers.
- Briefs, research answers and reports, the only long-running requests, are capped at 15 per visitor and 100 in
  total per day (`DEAL_INTEL_PER_VISITOR_DAILY`, `DEAL_INTEL_GLOBAL_DAILY`).
- The API answers more than 120 requests a minute from one IP with an immediate 429, before any database or
  model work (`DEAL_INTEL_IP_PER_MINUTE`), so traffic that bypasses the cache costs milliseconds.

### Environment

| Project | Variables |
|---|---|
| API | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `DEAL_INTEL_API_SECRET` (must match `private.config.api_secret`), `ALLOWED_ORIGINS`, `CRON_SECRET`, `DEAL_INTEL_APP_URL`, `DEAL_INTEL_ADMIN_KEY`, model keys (`OPENCODE_API_KEY`, `OLLAMA_API_KEY`, `GROQ_API_KEY`, optional `ANTHROPIC_API_KEY`), `SENDBYTE_API_KEY` |
| Web | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `AUTH_STATE_SECRET` |
| GitHub Actions secrets | `DEAL_INTEL_API_SECRET`, `GROQ_API_KEY`, `OLLAMA_API_KEY`, `OPENCODE_API_KEY`, `SENDBYTE_API_KEY`, `AFRICA_API_KEY` (optional) |

Secrets are stored only as Vercel sensitive variables or GitHub Actions secrets, never in the repository.

Model providers are tried in order and the next one is used on any failure; `DEAL_INTEL_PROVIDER` pins one.

---

## Scheduled jobs

The jobs run the API's own route handlers in-process on GitHub's runners (`scripts/run_cron.py`), so they cost no
Vercel function time.

| Workflow | When (UTC) | What it does |
|---|---|---|
| `scheduled-api-jobs.yml` | 04:11 and 15:11; 06:17; 06:53 | Deal and event ingestion with watchlist webhooks and emails; brief outcome labelling; showcase refresh |
| `live-deal-ingestion.yml` | 18:17 | Nightly ingestion pass, country risk snapshots, Corporate of the Week |
| `market-intraday.yml` | hourly 07:12 to 15:12, weekdays | Intraday quotes and government securities, ETFs, rates and funds |
| `market-snapshot.yml` | on demand | Snapshot (on Vercel, from Paris) and the instruments refresh |
| `enrich-round-investors.yml` | 19:04 | Reads round articles that name no investor and records the investors named |
| `feed-health.yml` | 03:29 | Checks every outlet feed and saves replacements for dead ones (below) |
| `daily-learning-pipeline.yml` | 04:37 and 14:37 | Macro signals and the daily research and evaluation refresh |
| `backtest.yml` | monthly | Walk-forward historical backtest |
| `historical-backfill.yml` | on demand | Deal history back to 2010, one month per call |
| `python-quality-gates.yml`, `web-quality-gates.yml` | every push | Tests, lint, type check, build, browser tests |

**Self-healing market prices.** Each exchange has an ordered list of vetted price sources
(`src/engines/price_sources.py`): its own website first, then established market-data sites (sikafinance.com,
stockanalysis.com). When the primary source returns nothing, the next is tried on the same run. A source is used
only if it prices at least a third of the companies already known and its prices agree with the last known ones
(median move within a factor of two); single implausible jumps are ignored, and shares no source prices keep their
old date so they read as stale. Rows record their source, and the daily health job tests every source. New sources
are added only after review: a price from an unvetted site could be wrong and would be shown as fact.

**Self-healing news feeds.** When an outlet's feed fails, comes back empty or stops updating, its replacement is found
from the outlet itself: the feed its homepage advertises, a standard feed address on its site, then Google News
limited to its site. Ingestion switches on the spot so no headlines are lost; the daily job saves lasting replacements
to `src/data/feed_overrides.json` and drops one when the original works again. A run fails only when an active outlet
cannot be reached at all; outlets that publish nothing anywhere are reported as dormant.

---

## Local development

```bash
# For authorised collaborators only; see LICENSE.
git clone https://github.com/HenryMorganDibie/deal-intelligence-agent
cd deal-intelligence-agent
pip install -r requirements.txt
uvicorn api.index:app --port 8787                      # API
cd web && npm install && npm run dev                   # http://localhost:3000
```

Point `NEXT_PUBLIC_API_URL` in `web/.env.local` at `http://localhost:8787`. Without database variables the API uses
local files in `data/`.

### Command line

```bash
python main.py deals --ingest                          # read every feed now
python main.py deals --search Moniepoint --country NG
python main.py countries --country SN                  # risk components and currency for one country
python main.py research "Which Kenyan fintechs raised money this year, and from whom?"
python main.py profile --company "Dangote Cement" --ticker DANGCEM.LG
python main.py analyse --company "GTBank" --ticker GTCO --output markdown
python main.py backtest --report
python main.py portfolio --name africa_fund --risk
python main.py replay --company "Credit Suisse" --date 2023-02-01
python main.py audit --verify
```

Other command groups: `outcomes`, `marketdata`, `entities`, `explain`, `monitor`, `feedback`, `calibration`,
`memory`, `registry`, `graph`. Run `python main.py <group> --help`.

---

## Project structure

```
deal-intelligence-agent/
├── api/
│   ├── index.py                 # hosted API (FastAPI): briefs, analysis, admin, caching rules
│   └── market_snapshot.py       # daily market snapshot, deployed in Paris
├── src/
│   ├── hosted_market.py         # API routes: deals, events, investors, markets, watchlists, research, cron jobs
│   ├── engines/                 # deterministic engines: deals, market_feed, feed_healing, markets, instruments,
│   │                            #   investors, financials, valuation, country_risk, research, watch, email_alerts,
│   │                            #   backtest, calibration, alpha scoring, audit log, entity graph, ...
│   ├── tools/                   # SEC EDGAR, African exchanges and feeds, global news
│   ├── agents/                  # brief pipeline (LangGraph) and model providers
│   └── data/                    # countries, indicators, measured outcomes, feed replacements
├── web/                         # Next.js app: landing, accounts, app, admin; middleware.ts gates /app
├── supabase/migrations/         # database schema and functions
├── scripts/                     # run_cron.py, check_feeds.py, data refresh scripts
├── evaluation/                  # labelled sets and scorers
├── docs/                        # backtest report and summaries
├── tests/                       # Python tests (data stores redirected to a temp dir)
├── ARCHITECTURE.md              # technical reference and limitations
└── LICENSE                      # proprietary
```

---

## Testing

```bash
pip install -r requirements-dev.txt && pytest -q      # 972 Python tests
cd web && npm run test:markets && npm run lint && npm run typecheck
```

The web gates also build the app and run Playwright browser tests (accounts, password rules, markets, admin). Tests
never touch the real `data/` directory or the hosted database.

## Evaluation

Signals, deals and attribution are measured on published, labelled sets with sample sizes and 95% intervals, with
development and held-out sets kept apart (`evaluation/README.md`):

```bash
python main.py backtest --evaluation          # signal outcomes: event confirmation and market reaction, separately
python -m evaluation.deals.score              # deal extraction, deduplication, identity resolution
python -m evaluation.attribution.score        # is a news event about the named company? (real headlines)
```

Held-out results (14 October 2026): 82% [75 to 88] of extracted deal records are genuine transactions, 92% [85 to 96]
of deal-like headlines are caught, and 71% [61 to 79] of records have every field right. On 400 real news headlines,
attribution finds 30% [20 to 42] of real events at 86% [65 to 95] precision, with false alarms on 1% of headlines
that report no event.

---

## Author

**Henry Chukwunwike Dibie**, ML Systems Engineer and Data Scientist
[github.com/HenryMorganDibie](https://github.com/HenryMorganDibie) · [linkedin.com/in/kinghenrymorgan](https://linkedin.com/in/kinghenrymorgan)

## Licence

Proprietary. Copyright (c) 2026 Henry Chukwunwike Dibie. All rights reserved. See [LICENSE](LICENSE).
