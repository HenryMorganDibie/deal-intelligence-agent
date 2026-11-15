# Deal Intelligence

> **Proprietary software. All rights reserved.** This repository is the private property of Henry Chukwunwike Dibie (Deal Intelligence). No licence is granted to use, copy, clone, modify or distribute any part of it. See [LICENSE](LICENSE). Licensing enquiries: info@deal-intelligence.app

**Deal Intelligence is an African financial and market intelligence platform.** It brings together private-market transactions, listed securities and other investment instruments, corporate events, investors and funds, company financials and governance, country and currency risk, valuation and portfolio research, and election intelligence. Its core promise is traceable evidence: figures, classifications and research should lead back to the source that supports them.

**Live platform:** [deal-intelligence.app](https://deal-intelligence.app)  
**Developer documentation:** [deal-intelligence.app/developers](https://deal-intelligence.app/developers)  
**API:** [api.deal-intelligence.app](https://api.deal-intelligence.app)

Built for private-equity and venture-capital firms, development finance institutions, investment and credit analysts, research teams, asset managers, and corporate-finance teams.

Deal Intelligence is research and data software. It does not provide investment advice, execute trades, arrange securities transactions, or hold client funds.

---

## Platform capabilities

### African private markets and corporate activity

| Area | Capability |
|---|---|
| **Deals** | Private-equity, venture-capital, debt, M&A, fundraises, listings and other reported transactions across African markets. Records capture parties and roles, disclosed amounts, currency-normalised values, stakes, rounds, stages, sectors, countries and source links where reported. |
| **Corporate events** | Company and market events such as results, leadership changes, regulatory actions, listings, defaults, distress and other material developments. Event classification is rule-based and separate from deal extraction. |
| **Investors and funds** | Investor and fund registry, name resolution, investor roles, profiles, deal participation, fund closes and LP relationships. |
| **Comparables** | Search and compare reported transactions using available attributes such as sector, country, transaction type and disclosed value. |
| **Country and sector research** | Country risk, currency risk, sector risk, deal activity and event context, with underlying observations and sources exposed where available. |

Deal coverage is built from public reporting and disclosures across African markets. Country inclusion does not mean equal deal volume, source depth or verification in every market. Undisclosed transactions cannot be represented, and an absent record is not evidence that no transaction occurred.

### Listed markets and multi-asset data

- Listed-company discovery, company directory, exchange overview, quotes, movers, sectors and cross-market screening.
- The exchange universe represents 24 African exchanges. Listing, quote, filing and statement depth differs by country and source; the Coverage registry describes the available data and verification tier rather than implying that every exchange has equivalent live data.
- Market snapshots include dated prices, index levels, movers, sector views, market capitalisation where available, and local- and USD-denominated return context. Intraday or delayed quotes are available only for selected sources and exchanges; the observation date is shown so stale prices are not mistaken for current ones.
- Multi-asset discovery includes exchange-traded funds listed in Johannesburg, Lagos and Nairobi; Treasury bills sourced from central-bank and regional auctions; selected government-bond auction and benchmark-yield references; listed property securities; policy rates; selected bank-deposit rates; and limited unlisted-fund reference data such as reported assets under management. It does not provide a complete security master, all bond inventories, fund returns or every country's auction data.
- Treasury-bill observations come from central-bank or regional auction sources. Quoting conventions and day-count bases are preserved rather than silently normalised where the source does not establish them.
- Market snapshots, FX conversion and instrument data carry dates so stale or differently dated observations are not mistaken for live prices.

This is public-source market information, not an execution venue or a complete inventory of every security or fund in each market.

### Companies, portfolios and valuation

- Company profiles combine exchange, filing, financial-statement and news data where available. NGX and NSE Kenya audited statements are parsed and checked against accounting identities; other listed-company financials depend on the source available for that listing.
- Company governance research extracts board members and roles, committees, substantial shareholders, subsidiaries and corporate-registration details from filed annual reports. Company websites can also be crawled for board, management, group structure and contact facts. Extracted facts are checked against the cited page; names or percentages that cannot be verified are omitted rather than silently completed.
- Company briefs surface source-backed signals from filings, exchange disclosures and news, with the underlying evidence available for review.
- Valuation supports evidence-gated DCF and dividend-discount (DDM) workflows, scenario analysis and sensitivity review. Model suitability, statement dates, quote dates, source URLs, currencies and missing inputs are checked; unsupported or stale inputs should prevent a confident valuation conclusion.
- Reported transaction comparables and listed-company multiples provide additional context where comparable data exists. Country cost-of-equity build-ups expose their component assumptions.
- Portfolio tools support holdings, multi-currency exposure, CSV/XLSX workflows, transaction and valuation review, and available market-price/FX refreshes. The database-backed personal and organization portfolio model has separate ownership, role, RLS and audit controls; its implementation and release caveats are documented in [the portfolio storage and access model](docs/portfolio-storage-and-access-model.md).

A missing quote, stale input, unsupported asset or incomplete filing should remain visible as a limitation rather than being filled with an invented value.

### Research, reports and monitoring

- Research answers retrieve relevant deals, corporate events, investors, company profiles, country and currency risk, market context and current news. Optional open-web search can add company pages, filings and reports when configured. Evidence is numbered, citations are checked against the retrieved sources, and unsupported or uncited claims are surfaced rather than treated as verified.
- Country and sector research reports assemble source-backed evidence into structured sections; the language model helps explain the evidence rather than becoming the source of truth.
- Watchlists can follow companies, countries and event types. A separate Corporate of the Week selection highlights up to five companies with verified, source-linked operating events from the latest seven complete days; transaction headlines already represented in Latest Deals and non-corporate political or sports stories are excluded.
- Watchlist updates can be delivered by email, RSS and supported webhook formats, including Slack, Microsoft Teams, Discord and Google Chat.
- Evaluation tools track labelled extraction, attribution and signal outcomes; results are published with sample sizes and uncertainty intervals.

### Election intelligence

Election intelligence is a distinct research capability, not a corporate-deal feed. It monitors election news and reported incidents across configured country profiles, with deeper structured candidate, constituency and polling-unit coverage for Nigeria. Configured live-results contests include The Gambia's presidential election and Nigeria's 2027 presidential and governorship elections.

Current functionality in the repository includes:

- Election profiles, dates, electoral bodies, regions and monitored sources.
- News collection, article enrichment, cross-outlet story merging and tagging by election, party, candidate or public figure, state or region, topic and race.
- Incident classification and severity, including reported violence, thuggery, abduction, arson, ballot snatching, vote buying, intimidation, election-technology failures, logistics, arrests and hate speech.
- Nigeria-specific coverage including candidates, constituencies, states, LGAs, wards and polling-unit reference data.
- Live-results tracking records results as electoral commissions declare them, entered by authorised operators and retained with version history. This is distinct from the Nigerian polling-unit result-sheet workflow: submitted EC8A sheets are read by a vision model, checked against polling-unit references and arithmetic rules, and remain provisional until a human reviewer verifies them. A sheet that passes automated checks is not, by itself, an official declared result.
- Published polls and poll summaries where available.
- Election alerts with filters for election, incident type, severity, geography, candidates, parties and topics, delivered through supported webhook channels.
- CSV exports and API access subject to plan and endpoint permissions.

Election profiles, dates, result availability and feature entitlements vary by contest. See the [Election API documentation](https://deal-intelligence.app/developers#elections) for current endpoints and plan restrictions.

---

## Data coverage and evidence

Deal Intelligence is designed around source traceability rather than an opaque aggregate score.

- **Geography:** country-risk indicators and country-level reference coverage span all 54 African countries. Private-market deals, corporate events, listed-company data and machine-readable filings vary materially by country; the coverage registry exposes those differences.
- **Exchanges:** the exchange universe represents 24 African exchanges. Individual datasets differ in listing coverage, price freshness, financial-statement availability and machine-readable disclosure depth.
- **Currencies:** country and currency-risk data covers currencies represented by the source datasets; official and parallel-market observations are distinguished where available.
- **Languages:** African private-market news collection includes English, French and Portuguese sources.
- **Evidence:** deal and event records retain source links and available verification details. Market observations retain source and date information.
- **Confidence and uncertainty:** corroboration, source quality, data freshness and measured historical performance are surfaced where relevant.

Coverage is not uniform. The current coverage model distinguishes stronger official filing and price sources from markets where verification relies on vendor data or credible news, and from countries where the platform provides country, news and deal context without a complete listed-company data feed. Some private transactions do not disclose amounts or counterparties, and some instruments have only periodic official observations. See the live [Coverage](https://deal-intelligence.app/coverage), [Methodology](https://deal-intelligence.app/methodology) and [Limits](https://deal-intelligence.app/limits) pages for current country-level detail and known limitations.

---

## How the system works

    Public sources
      news, filings, exchange disclosures, central banks, election bodies
            |
            v
    Collection and scheduled refresh
      GitHub Actions, source-specific collectors, article enrichment
            |
            v
    Deterministic data and signal engines
      African deals, corporate events, company governance, investors, instruments, country risk, elections
            |
            v
    Supabase
      Postgres, Auth, row-level security, controlled database functions
            |
            +-----------------------------+
            |                             |
            v                             v
    FastAPI hosted API                Next.js web platform
    Vercel                            Vercel
            |                             |
            +---------- public and authenticated product experiences

### Research and signal principles

**Deterministic first.** Deal extraction, corporate-event classification, signal detection, severity rules, source checks and compound-event logic are handled by reproducible engines. Language models assist with explanation, research synthesis and reading long company documents, but extracted facts are checked against source text and models do not decide whether a deterministic deal or signal exists.

**Evidence before narrative.** The system retains source references and supporting evidence. Research answers are assembled from retrieved material, and unsupported citations or snippets are not intended to survive post-processing.

**Measured, not implied.** Evaluation uses labelled examples and held-out data where available. Published metrics should be read with sample sizes, confidence intervals, evaluation dates and task definitions. A backtest or extraction score is not a guarantee of future investment performance.

**Fail visibly.** Stale prices, missing data, uncertain source conventions and unsupported coverage should be represented as such rather than silently presented as current or complete.

For the deeper component-level design, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Hosted platform

| Component | Deployment / location | Responsibility |
|---|---|---|
| Web application | Vercel project deal-intelligence-app, root web/ | Public website, authentication, account settings and product interfaces |
| Hosted API | Vercel project deal-intelligence-api, api/index.py and src/ | FastAPI endpoints, market data, research, scheduled-job handlers and API access |
| Database and authentication | Supabase | Postgres, Auth, row-level security, database functions and application data |
| Scheduled collection and refresh | GitHub Actions | Ingestion, election collection, market refresh, enrichment, evaluation and maintenance |
| Email and notifications | SendByte and Supabase Auth email configuration | Product email, account messages and supported alerts |
| Payments | Paystack integration | Subscription checkout and billing |

### Public pages and authenticated application

The web application is not a single /app page. It has public product and information pages, account and billing pages, and authenticated product routes. Middleware in web/middleware.ts verifies and refreshes sessions, enforces required profile and MFA state, and rewrites authenticated short routes to their internal application pages.

Public pages include the product overview, platform, pricing, methodology, coverage, limits, attribution and developer documentation. Public deal, market and research information is exposed only where the application explicitly supports it.

Authenticated product areas include Deals, Investors, Companies and company governance, company briefs, Markets and multi-asset investment discovery, portfolios, valuation, monitoring, Research, Countries, Market briefs, Watchlists, election news, incidents, results, candidates, polling units, election alerts, API-key management and account security.

Legacy /app/... URLs redirect to current short routes. Access is determined by middleware and endpoint-level authorization, not by the route name alone.

### Accounts, security and plans

The account system supports email registration and confirmation, Google sign-in, password reset, profile completion, optional authenticator-based MFA and session sign-out. Password policy and account state are enforced by the application and authentication layer.

The developer API uses account-issued API keys. API usage, quotas and access to certain endpoints are plan-controlled. The public developer page documents current monthly request allowances, key limits, endpoint parameters and election-specific restrictions. Pricing and plan catalogues are served by the application; consult the live [Pricing](https://deal-intelligence.app/pricing) page rather than relying on hard-coded prices in this README.

The product uses Paystack for subscription payments. Deal Intelligence is research and data software; it does not execute trades, provide brokerage services or hold customer funds.

### Admin and operational controls

The private admin interface is protected by a server-side admin secret. It provides operational visibility into anonymous visits, feature usage and account activity. Account activity updates are throttled and are not written on every page view.

Public API responses are cached where appropriate. Expensive research and brief-generation requests have configurable daily limits, and the API applies per-IP rate limiting. Database writes use controlled server-side functions and secrets; service credentials must never be exposed to the browser.

### Deployment variables

The following names describe configuration used by the current code and workflows. Actual values belong only in Vercel environment settings or GitHub Actions secrets.

| Runtime | Configuration examples |
|---|---|
| API / FastAPI | SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, DEAL_INTEL_API_SECRET, CRON_SECRET, ALLOWED_ORIGINS, DEAL_INTEL_APP_URL, DEAL_INTEL_ADMIN_KEY |
| Web / Next.js | NEXT_PUBLIC_API_URL, NEXT_PUBLIC_SITE_URL, NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY, AUTH_STATE_SECRET, and the server-only API proxy secret where configured |
| Model and research integrations | GROQ_API_KEY, OLLAMA_API_KEY, OPENCODE_API_KEY, OPENROUTER_API_KEY, GEMINI_API_KEY and optional ANTHROPIC_API_KEY; DEAL_INTEL_PROVIDER can pin the provider |
| Collection and notifications | SENDBYTE_API_KEY, optional TAVILY_API_KEY and optional AFRICA_API_KEY |
| GitHub Actions | Repository secrets for the API secret and only the provider or integration keys required by each workflow |

Not every integration is required for every deployment or workflow. Configure only the integrations being used. Never commit secret values, production tokens or private configuration files.

---

## Scheduled jobs and automation

Most collection and maintenance tasks run on GitHub-hosted runners. scripts/run_cron.py invokes the API's route handlers in-process, keeping scheduled ingestion and refresh work out of Vercel request execution.

The workflow inventory changes as the platform evolves. The following are the principal current workflows; their YAML files are the source of truth for exact schedules, manual inputs and permissions.

| Workflow | Purpose |
|---|---|
| scheduled-api-jobs.yml | Twice-daily deal and event ingestion, outcome labelling and showcase refresh; hourly election-news collection, article enrichment and queued result-sheet processing |
| live-deal-ingestion.yml | Nightly rolling ingestion, country-risk snapshots and Corporate of the Week refresh |
| market-intraday.yml | Weekday intraday market quotes and instrument refresh |
| market-snapshot.yml | Market snapshot and instrument refresh |
| enrich-round-investors.yml | Investor enrichment from financing-round articles |
| feed-health.yml | News-feed health checks and replacement discovery |
| daily-learning-pipeline.yml | Macro-signal refresh, reference-data updates and research/evaluation maintenance |
| refresh-country-history.yml | Historical World Bank country-indicator refresh |
| historical-backfill.yml | On-demand historical deal and event backfill |
| backtest.yml | Scheduled walk-forward evaluation |
| independent-review-sample.yml, research-benchmark-review.yml, review-labels-import.yml | Independent review sampling, benchmark review and labelled-review imports |
| polling-units.yml | Manual loading of INEC polling-unit reference data |
| sens-capture.yml | Weekday JSE SENS announcement capture |
| corporate-of-week.yml, content-drafts.yml | Editorial and showcase content workflows |
| billing-status.yml | Manual Paystack billing-configuration check |
| python-quality-gates.yml, web-quality-gates.yml | Automated Python and web quality checks |

GitHub may start scheduled workflows later than their cron time. Jobs should therefore be safe to retry and should not be treated as real-time execution guarantees.

### Resilient source collection

Market-price sources are ordered and validated. When a primary source is unavailable, a vetted fallback can be tried; implausible jumps are rejected and observations that cannot be refreshed retain their original dates so they can be recognised as stale.

News-feed health checks look for publisher-advertised or standard replacement feeds and can use a site-scoped Google News feed as a fallback. Replacements are recorded for later runs and reverted when the original feed recovers. This improves collection resilience but does not guarantee that every publisher or source is continuously available.

---

## Developer API

The hosted REST API is documented at [deal-intelligence.app/developers](https://deal-intelligence.app/developers). It includes endpoints for:

- Deals, individual deal records and comparable transactions.
- Corporate events, investors, investor profiles and fund information.
- Country and currency risk, coverage and sector risk.
- Company profiles, financial statements and valuation evidence.
- Market overview, screening, search, quotes and instrument data.
- Watchlists, feeds, research, country and sector reports, and evaluation.
- Election profiles, news, incidents, live results, candidates, polls, polling-unit reference data, result-sheet workflows, alerts and exports.

API access uses account-issued keys and plan-based quotas. The developer documentation is the authoritative reference for endpoint paths, request parameters, response shapes, rate limits and feature entitlements. Do not infer that an endpoint is available to every plan simply because it exists in the codebase.

---

## Local development

This is a proprietary repository. Clone and run it only if you are authorised to access the code.

    git clone https://github.com/HenryMorganDibie/deal-intelligence-agent
    cd deal-intelligence-agent
    python -m venv .venv
    # Activate the virtual environment, then:
    pip install -r requirements.txt
    uvicorn api.index:app --reload --port 8787

In another terminal:

    cd web
    npm install
    npm run dev

Configure the web app's local environment (for example, web/.env.local) with the appropriate local API URL and the Supabase settings for the environment you are authorised to use. Do not point local development at production data unless explicitly intended and authorised.

Without hosted database configuration, some Python engines can use local files under data/; hosted account, billing and multi-user features require their backing services.

### Command line

The Python CLI in main.py includes commands for analysis, deals, country risk, research, company profiles, backtests, portfolios, outcomes, market data, entity resolution, explainability, monitoring, feedback, calibration, memory, registry, graph and audit operations.

Examples:

    python main.py --help
    python main.py deals --help
    python main.py deals --ingest
    python main.py deals --search Moniepoint --country NG
    python main.py countries --country SN
    python main.py research "Which Kenyan fintechs raised money this year, and from whom?"
    python main.py profile --company "Dangote Cement" --ticker DANGCEM.LG
    python main.py analyse --company "GTBank" --ticker GTCO --output markdown
    python main.py backtest --report
    python main.py portfolio --name africa_fund --risk
    python main.py audit --verify

Some commands require external provider credentials or a configured database. Run each command's --help for its current arguments.

---

## Repository map

    deal-intelligence-agent/
    ├── api/
    │   ├── index.py                 # FastAPI application and router registration
    │   └── market_snapshot.py       # Scheduled market snapshot handler
    ├── src/
    │   ├── hosted_market.py         # Hosted market, company, research and cron API routes
    │   ├── election_*.py             # Election news, results, polls, alerts and exports
    │   ├── engines/                  # Deal, event, market, risk, investor, instrument,
    │   │                             # portfolio, valuation and research engines
    │   ├── agents/                   # Analyst-brief pipeline and model-provider integrations
    │   ├── tools/                    # Filing, exchange, news and market-data collectors
    │   └── data/                     # Country, election, source, indicator and reference datasets
    ├── web/
    │   ├── app/                      # Public pages, accounts, API routes and product pages
    │   ├── components/               # Shared UI and product components
    │   ├── lib/                      # API clients, market models and application utilities
    │   └── middleware.ts             # Session verification, access control and route rewrites
    ├── supabase/
    │   ├── migrations/               # Database schema, RPCs, auth and access-control changes
    │   └── tests/                    # Database policy tests
    ├── scripts/                      # Scheduled jobs, ingestion, refresh and data-loading scripts
    ├── .github/workflows/            # Scheduled workflows and quality gates
    ├── evaluation/                   # Labelled datasets, scorers and evaluation methodology
    ├── docs/                         # Architecture, portfolio access and technical notes
    ├── tests/                        # Python regression and engine tests
    ├── ARCHITECTURE.md               # Detailed architecture reference
    └── LICENSE                       # Proprietary terms

---

## Quality checks

Install development dependencies and run the Python suite:

    pip install -r requirements-dev.txt
    pytest -q

Run the web checks from web/:

    npm run test:markets
    npm run lint
    npm run typecheck
    npm run build

The GitHub Actions quality gates also run the repository's configured browser tests. Check the workflow files for the exact test matrix and required environment. Tests should use isolated fixtures or test configuration and must not mutate production data.

---

## Evaluation

Evaluation is task-specific. Deal extraction, entity resolution, event attribution and signal outcomes are different problems and should not be represented by one blended accuracy number.

The repository includes labelled evaluation sets and scorers under evaluation/, plus walk-forward outcome tooling. Typical commands include:

    python main.py backtest --evaluation
    python -m evaluation.deals.score
    python -m evaluation.attribution.score

Published results should always be read alongside the evaluation date, held-out sample, label definitions, confidence intervals and known coverage limitations. Do not treat historical signal outcomes as investment-return forecasts or a guarantee of future performance. See [Evaluation](https://deal-intelligence.app/review) and [Methodology](https://deal-intelligence.app/methodology) for public explanations.

---

## Author

**Henry Chukwunwike Dibie**  
[GitHub](https://github.com/HenryMorganDibie) · [LinkedIn](https://linkedin.com/in/kinghenrymorgan)

## Licence

Proprietary. Copyright (c) 2026 Henry Chukwunwike Dibie. All rights reserved. See [LICENSE](LICENSE).
