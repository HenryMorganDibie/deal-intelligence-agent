# Markets Investment Intelligence — Implementation Checklist

**Working branch:** `feature/markets-investment-intelligence`  
**Target base:** `main`  
**Production safety:** Do not merge this work or push implementation commits to `main` until the pull request has been reviewed and the acceptance checks below pass.

This checklist is the source of truth for scope and completion. Mark an item complete only after verifying it against the code or test output. Do not mark planned functionality as implemented.

## Product decisions (agreed)

- [x] Africa-wide scope from day one, prioritising countries, exchanges and instruments with reliable data.
- [x] Markets owns investment discovery, valuation, portfolio intelligence and personal investment insights.
- [x] Research Copilot and deeper cross-platform investigations remain in the existing Research workspace.
- [x] Reuse existing company coverage, financials, research, events, watchlists and alert infrastructure where fit is verified.
- [x] Begin portfolio onboarding with manual entry and CSV import; consider broker connections later.
- [x] No trade execution, custody or automatic investment execution in the initial scope.
- [x] Make data quality, source provenance, freshness, uncertainty and counterarguments visible.

## Phase 0 — Repository and product audit

- [x] Inspect the current Markets page and navigation.
- [x] Inspect existing Companies and Research pages.
- [x] Inspect existing market API, financials, coverage, risk and portfolio modules.
- [x] Record existing functionality versus missing consumer-facing capabilities.
- [ ] Map the actual API response schemas used by Markets, Companies, Research, events, watchlists and portfolio/risk modules.
- [ ] Verify which existing endpoints are safe and available for the web app to call.
- [ ] Confirm supported markets/instruments and document known coverage limitations.

## Phase 1 — Safe foundation and Markets information architecture

- [x] Replace the Markets coming-soon page with a responsive Markets landing/overview backed by existing pulse and coverage endpoints.
- [x] Keep the existing top-level navigation stable; do not add Portfolio as another top-level item.
- [x] Add internal Markets destinations for Overview, Explore Companies, Valuation, My Portfolio and Investment Monitoring (links into existing Companies and Watchlists for shared capabilities).
- [x] Reuse existing components and existing `/api/pulse` and `/api/coverage` endpoints; avoid duplicate research or alert systems.
- [x] Show coverage context, latest available record date, source links for event items, and meaningful empty/error states on the overview.
- [ ] Extend freshness/source status to each individual data source and company/instrument profile.
- [x] Make the implemented overview navigation and company-search actions functional; no decorative or fake data visualisations were added.
- [x] Build and wire Valuation and My Portfolio destinations; route Investment Monitoring to existing Watchlists rather than duplicate alert infrastructure.
- [x] Use responsive layouts, labelled company search, semantic sections and existing app design conventions.
- [ ] Verify accessibility and keyboard navigation in a running preview.

## Phase 2 — Africa-wide coverage-aware market overview

- [ ] Present African scope from day one without implying equal data depth across all 54 countries.
- [ ] Use existing coverage metadata where available; do not hardcode unsupported coverage claims.
- [ ] Show country/exchange/instrument coverage and data freshness.
- [ ] Reuse existing market pulse, companies, events and news APIs after response contracts are verified.
- [ ] Distinguish research-ready, partial coverage and intelligence-only states based on actual available evidence.
- [ ] Test empty, stale, unavailable and partially populated markets.

## Phase 3 — Valuation and honest investment conclusions

- [x] Define typed scenario inputs and deterministic DCF outputs in the valuation workspace; automated unit tests and backend contract are still pending.
- [ ] Verify market price, currency, share count, reporting period and financial statement provenance before calculation.
- [x] Implement a clearly labelled five-year DCF scenario tool for positive unlevered free cash flow, with explicit model-fit limitations; additional methods and suitability detection remain pending.
- [x] Produce bear/base/bull scenarios and a discount-rate/terminal-growth sensitivity grid; model-calibrated ranges remain pending.
- [x] Explain assumptions and key limitations; source links are required and countercase research links to the existing Research workspace. Automated countercase synthesis remains pending.
- [x] Support cautious comparison labels based on entered price versus base DCF estimate; a formal fairly-valued band and automated data-quality/model-suitability gate remain pending.
- [x] Require company, financial source URL, reporting period, FCF, shares, cash and debt; require a dated quote and quote source URL before making a price comparison; refuse calculation for missing/invalid inputs and explicitly state source/model-fit limitations. Automated source verification and suitability gates remain pending.
- [ ] Keep deterministic calculations separate from LLM-written explanations.
- [ ] Add unit tests for calculations, edge cases, stale/missing inputs, currency mismatch and unsupported instruments.
- [ ] Create a human-reviewed benchmark of representative African listed companies before claiming accuracy.

## Phase 4 — Portfolio Intelligence inside Markets

- [x] Design a portfolio data model that supports manual entry and CSV import.
- [x] Start with browser-local storage and clear import/export/delete controls; do not upload private holdings to shared storage.
- [x] Validate CSV headers, required fields, numeric values and malformed quoted CSV; duplicate detection and full currency-code validation remain pending.
- [x] Implement country and sector exposure for holdings with entered current prices and valid FX conversion.
- [x] Add allocation/exposure by country, sector, asset type and holding currency for priced and FX-converted holdings; company positions are visible in the portfolio register. Missing price/FX holdings are excluded and called out.
- [x] Distinguish entered cost basis, entered-price value and indicative gain/loss for the same priced/FX-converted holdings. Allow users to refresh holding prices and FX rates in the register.
- [ ] Add realised gains, dividends, corporate actions and historical FX effects before presenting comprehensive performance.
- [ ] Reuse the existing portfolio risk engine only after verifying its assumptions and persistence limitations.
- [ ] Add portfolio-wide valuation insights only where constituent valuations pass quality gates.
- [ ] Add understandable concentration/risk explanations and links to company analysis.
- [ ] Test arithmetic invariants, missing prices, currency conversion, unsupported holdings and empty portfolios.
- [ ] Do not implement cloud-saved portfolios or cross-device sync until authentication and row-level ownership protections are implemented and tested.

## Phase 5 — Personal investment insights and monitoring

- [ ] Reuse existing watchlists, events and alert infrastructure where appropriate.
- [ ] Add portfolio-aware material-event and valuation-change alerts only when reliable inputs exist.
- [ ] Explain why each alert matters and link it to supporting evidence.
- [ ] Avoid noisy alerts and unsupported buy/sell instructions.
- [ ] Test duplicate events, stale data, missing coverage and alert failures.

## Phase 6 — Quality, regression and release readiness

- [ ] Run relevant backend unit and integration tests.
- [ ] Run frontend typecheck and production build after the latest valuation and portfolio changes; earlier preview build was READY for source commit `cd855181010fb3852e0afa7476e87a2403918251`.
- [ ] Run a standalone lint command and the broader relevant backend/unit integration test suite.
- [ ] Test the Markets pages at mobile and desktop sizes.
- [ ] Verify Companies, Research, Deals, Alerts, watchlists and other existing areas remain unaffected.
- [ ] Check accessibility, loading states, empty states, error states and keyboard navigation.
- [ ] Verify no secrets or private portfolio data are exposed.
- [ ] Review dependency, schema and migration changes; document any required environment setup.
- [ ] Update this checklist with evidence for each completed item.
- [ ] Open/update the PR with test results, screenshots or preview URL when available.
- [ ] Confirm latest Vercel preview is READY and `/app/markets`, `/app/markets/valuation` and `/app/markets/portfolio` return HTTP 200.
- [ ] Manually exercise interactive flows in a browser: company search, local persistence, CSV import/export, currency conversion and clear/delete.
- [ ] Obtain explicit approval before merging into `main`.
- [ ] After approval and merge, verify production status and run a post-deploy smoke check.

## Out of scope for the initial release

- [ ] No direct trading, custody, payment execution or automatic investment execution.
- [ ] No claim of complete/equal financial coverage across all African markets.
- [ ] No broker integration requirement for the initial portfolio MVP.
- [ ] No separate top-level Portfolio or Research Copilot navigation item.
- [ ] No fake market data or unverified valuation claims to fill visual space.

## Work log

| Date | Change | Verification | Status |
|---|---|---|---|
| 2026-10-24 | Created working branch and agreed-scope checklist | Branch created from `main`; checklist committed to feature branch | Done |
| 2026-10-24 | Replaced Markets placeholder with an API-backed overview | Uses `/api/pulse` and `/api/coverage`; includes company-profile search, recent event/source links, deal flow and coverage transparency | Typecheck passed; Vercel preview READY; route returned HTTP 200 |
| 2026-10-24 | Added initial Portfolio Intelligence workspace | Manual holdings, CSV import/template/export, browser-local storage, clear/delete controls, entered-price valuation and country/sector exposure with FX caveats | Typecheck passed; Vercel preview READY; route returned HTTP 200; interactive browser checks pending |
| 2026-10-24 | Corrected first portfolio preview build failure | Initial draft had a malformed CSV-template expression; corrected it and verified a subsequent source commit built successfully | Fixed on feature branch; no production merge/deployment |
| 2026-10-24 | Added valuation workspace and Markets internal navigation | Added a transparent five-year DCF scenario calculator with bear/base/bull assumptions, sourced input requirements, optional dated quote comparison and explicit limitations; connected Markets to Valuation, Portfolio and existing Watchlists | Vercel preview build for the newest commits is pending; automated calculation tests and interactive checks remain |
| 2026-10-24 | Expanded portfolio allocation | Added country, sector, asset-type and holding-currency exposure; changed initial holding currency to USD, stopped defaulting foreign exchange conversions to 1, and added editable current-price/FX fields | Code committed; latest preview verification pending |
| 2026-10-24 | Connected valuation to existing company data and quote provenance | Added a profile-prefill action that reuses returned financials where supported; unsupported currencies are rejected for automatic prefill; inferred shares require a dated quote and aligned currency; a price comparison requires quote date and source URL | CI production build passed before the latest quote-provenance changes; latest quality-gate run pending; Vercel deployment rate-limited until its retry window |
| 2026-10-24 | Strengthened valuation transparency | Added per-scenario FCF growth display, ordered bear/base/bull assumptions and a 3×3 discount-rate/terminal-growth sensitivity grid | Code committed; automated checks for latest commit pending |
