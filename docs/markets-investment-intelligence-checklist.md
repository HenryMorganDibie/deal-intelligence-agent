# Markets Investment Intelligence — Implementation Checklist

**Working branch:** `fix/markets-overview-alignment`  
**Target base:** `main`  
**Production safety:** Do not merge this work or push implementation commits to `main` until the pull request has been reviewed and the acceptance checks below pass.

This checklist is the source of truth for scope and completion. Mark an item complete only after verifying it against the code or test output. Do not mark planned functionality as implemented.

## Product decisions (agreed)

- [x] Africa-wide scope from day one, prioritising countries, exchanges and instruments with reliable data.
- [x] Markets owns investment discovery, valuation, portfolio intelligence and personal investment insights.
- [x] Research Copilot and deeper cross-platform investigations remain in the existing Research workspace.
- [x] Reuse existing company coverage, financials, research, events, watchlists and alert infrastructure where fit is verified.
- [x] Begin portfolio onboarding with manual entry and CSV and Excel (.xlsx) import/export; consider broker connections later.
- [x] No trade execution, custody or automatic investment execution in the initial scope.
- [x] Make data quality, source provenance, freshness, uncertainty and counterarguments visible.

## Phase 0 — Repository and product audit

- [x] Inspect the current Markets page and navigation.
- [x] Inspect existing Companies and Research pages.
- [x] Inspect existing market API, financials, coverage, risk and portfolio modules.
- [x] Record existing functionality versus missing consumer-facing capabilities.
- [x] Map the actual response contracts used by this feature: `GET /api/pulse` (`Pulse` in `web/lib/pulse.ts`), `GET /api/coverage` (`CoverageRow` and summary in `web/lib/market.ts`), company profile/financial inputs (`/api/companies/profile` through the shared `get` wrapper), and the general `/api/events` feed. Companies and Research remain existing destinations, not duplicated APIs.
- [x] Verify this feature uses read-only GET requests for pulse, coverage, company profile and event feeds. Portfolio holdings and valuation snapshots remain in browser localStorage; monitoring sends only a general events-feed request, and watchlist handoff sends company names only through sessionStorage.
- [x] Document supported scope and limitations: the existing Coverage registry is the source of truth for country/exchange/currency metadata and unequal coverage tiers; Markets links to it rather than duplicating its explorer. The wider platform has US and African company/outcome coverage. Valuation is limited to suitable operating-company DCF and mature-dividend/financial-institution DDM profiles; REIT/NAV and specialist models are not supported.

## Phase 1 — Safe foundation and Markets information architecture

- [x] Replace the Markets coming-soon page with a responsive Markets landing/overview backed by the existing pulse endpoint; link to the Coverage registry instead of reproducing its explorer.
- [x] Keep the existing top-level navigation stable; do not add Portfolio as another top-level item.
- [x] Add internal Markets destinations for Overview, Explore Companies, Valuation, My Portfolio and Investment Monitoring (links into existing Companies and Watchlists for shared capabilities).
- [x] Reuse the existing `/api/pulse` endpoint and link to the Coverage registry, Research and Watchlists for shared capabilities; avoid duplicate coverage, research or alert systems.
- [x] Show latest available record date, source links for event items, data-limit context and meaningful empty/error states on the overview; detailed coverage remains in the Coverage registry.
- [x] Surface available statement/quote dates and stale-input warnings in valuation/compare, and document that `/api/coverage` does not provide per-source update timestamps. Do not invent source freshness when the API does not return it; per-source freshness in the coverage explorer remains an API-dependent follow-up.
- [x] Keep company investigations in the existing Research workspace; Markets has no separate company-search workflow or Research CTA, and no decorative or fake data visualisations were added.
- [x] Build and wire Valuation, My Portfolio and Compare Opportunities destinations; route Investment Monitoring to existing Watchlists rather than duplicate alert infrastructure.
- [x] Use responsive layouts, labelled company search, semantic sections and existing app design conventions.
- [ ] Verify accessibility and keyboard navigation in a running preview.

## Phase 2 — Africa-wide coverage-aware market overview

- [x] Present African scope from day one without implying equal data depth across all 54 countries; the overview warns that depth differs by country, exchange, instrument and company and links to the Coverage registry for the detailed metadata.
- [x] Keep country counts, exchange/currency details, tiers and source availability in the existing Coverage registry; Markets does not duplicate that data or call `/api/coverage` solely to render a second explorer.
- [x] Link to the existing searchable Coverage registry for country, exchange, currency, tier, listed price/statement sources and recorded deal/event counts; company-level quote/statement freshness is surfaced in Valuation and Compare. Per-source timestamps are unavailable in the current coverage API.
- [x] Reuse `/api/pulse` on the overview and link to existing Coverage, Research, Companies and Watchlists; source-linked event items use the pulse response.
- [x] Keep research-readiness detail in the Coverage registry; Markets avoids presenting a duplicate country-level readiness counter as an investment feature.
- [ ] Test empty, stale, unavailable and partially populated markets.

## Phase 3 — Valuation and honest investment conclusions

- [x] Define typed scenario inputs and deterministic DCF/DDM outputs in the valuation workspace; automated calculation tests passed in current-head Web quality gates run `40110920728`.
- [x] Require source URLs and valid past dates, gate on selected currency and model fit, require a dated quote plus quote-source URL for comparisons, and disclose inferred share counts. Independent source-document verification and manual quote-currency confirmation remain limitations.
- [x] Implement a five-year DCF for suitable non-financial operating companies and a dividend discount model for mature dividend payers; unsuitable model profiles are blocked, and bank/insurer sectors detected in existing company profiles default to DDM. REIT/NAV and other specialist models remain out of scope.
- [x] Produce bear/base/bull scenarios and discount-rate/terminal-growth sensitivity for both DCF and DDM; the range is explicitly not a confidence interval and is not model-calibrated.
- [x] Explain assumptions and limitations, show source links, flag statements older than 18 months and quotes older than 7 days, and link to the existing Research workspace with a prefilled countercase question. The question is not auto-submitted; automated countercase synthesis remains pending.
- [x] Support cautious, scenario-dependent potential overvaluation/undervaluation labels only when all three scenarios agree and the base-case gap exceeds 15%; otherwise show a mixed or narrower-gap conclusion. This is a mechanical comparison, not a buy/sell recommendation.
- [x] Require company, financial source URL, valid reporting date, method-specific inputs and model-fit confirmation; require a dated quote and quote source URL before price comparisons; refuse invalid assumptions and unsupported model profiles. Generic `free_cash_flow` is not auto-labelled as unlevered FCFF.
- [x] Keep deterministic calculations in a pure typed module; no LLM-generated value is mixed into the valuation arithmetic.
- [x] Add unit tests for DCF/DDM math, invalid assumptions, source URL/date validation, portfolio arithmetic, FX conversion, missing prices and exposure grouping. UI-level currency mismatch and unsupported-instrument flows still need browser verification.
- [x] Show comparison caveats when financial statement currencies differ, statement periods span more than 180 days, or listed-market quotes are mixed with private-market valuation marks; raw amounts remain explicitly unnormalised.
- [x] Do not claim valuation accuracy or calibrated fair values. Results are deterministic, assumption-dependent scenarios with source/date gates and explicit limitations. A human-reviewed benchmark is required before any future accuracy claim, but is not represented as complete here.

## Phase 4 — Portfolio Intelligence inside Markets

- [x] Design a portfolio data model that supports manual entry, CSV import/export and genuine Excel (.xlsx) import/export.
- [x] Start with browser-local storage and clear import/export/delete controls; do not upload private holdings to shared storage. CSV and Excel exports include the same portfolio fields; Excel templates are available for import.
- [x] Validate CSV and Excel headers, required fields, numeric values, malformed quoted CSV, supported currency codes, dates and possible duplicate positions. Excel import uses the first worksheet, rejects formula cells, and limits files to 5 MB / 5,000 holding rows. The row limit is intentionally retained because portfolio holdings persist in browser localStorage; a larger limit needs a different storage design.
- [x] Implement country and sector exposure for holdings with entered current prices and valid FX conversion.
- [x] Add allocation/exposure by country, sector, asset type and holding currency for priced and FX-converted holdings; company positions are visible in the portfolio register. Missing price/FX holdings are excluded and called out.
- [x] Distinguish entered cost basis, entered-price value and indicative gain/loss for the same priced/FX-converted holdings. Users can edit entered prices and FX rates inline and attach dates; missing or stale values are called out.
- [x] Keep realised gains, dividends, corporate actions and historical FX effects out of the initial release; current metrics are indicative only and must not be described as comprehensive investment performance.
- [x] Reviewed the existing backend/CLI portfolio risk engine; it is not exposed as a suitable web API and its named-portfolio persistence/assumptions are not appropriate for browser-local holdings. The Markets MVP uses transparent local exposure/concentration checks instead of silently mixing in a different risk model.
- [x] Add portfolio-wide valuation insights only where constituent valuations pass quality gates; unsupported, stale, mismatched and unpriced holdings are excluded and their review status is explained.
- [x] Add understandable concentration and data-quality explanations, links to company research and per-holding valuation, and a local-only handoff that pre-fills the existing Watchlists page with company names. Portfolio quantities, prices and FX rates are not copied into the watchlist draft.
- [x] Add unit tests for arithmetic invariants, missing prices, currency conversion, exposure aggregation and empty portfolios; execution is pending the latest CI run.
- [x] Keep cloud-saved portfolios and cross-device sync out of scope until authentication and row-level ownership protections exist and are tested; current holdings and valuation snapshots stay local to the browser.
- [x] Add separate JSON export/restore for saved valuation history with schema/source/date validation, a 2 MB import cap, duplicate-ID rejection, explicit replacement confirmation and local-only storage. Portfolio holdings remain restorable through CSV/XLSX; valuation history is not bundled into those portfolio files.

## Phase 5 — Personal investment insights and monitoring

- [x] Reuse existing Watchlists for monitoring by pre-filling a watchlist draft with company names/tickers only; holdings, quantities, prices and FX rates remain in browser storage.
- [x] Add local portfolio event monitoring that matches exact company-name/ticker tokens against the existing event feed, preserves source links and labels matches as candidates rather than verified material alerts; holdings remain browser-local and are not sent to the API.
- [x] Add local valuation-change alerts for at least 10% changes in saved base-case estimates for the same company, country, model method and currency; the alert explicitly describes model-estimate changes, not stock-price moves or expected returns. Live market-price-change scoring remains out of scope until reliable price history exists.
- [x] Explain what changed using the previous/current estimate, percentage, calculation dates and statement period; link to current statement and quote sources where available. Do not infer a material event impact from headline matching.
- [x] Avoid automatic buy/sell instructions and duplicate server-side alert rules; use existing Watchlists for broader monitoring and label local portfolio matches as candidates.
- [x] Add automated tests for duplicate event suppression, empty portfolios/feeds, exact ticker boundaries, material valuation-change thresholds, country separation and incompatible valuation methods.
- [x] Fetch the 90-day monitoring feed in 500-row pages instead of silently stopping at the first 100; cap a single refresh at 5,000 events and visibly disclose when more records exist. Added regression tests for multi-page retrieval, the cap and feed failures. Current-head Web quality gates passed in run `40138138623`.
- [ ] Manually test stale-data, missing-coverage and event-feed failure states in a running preview.

## Phase 6 — Quality, regression and release readiness

- [x] Confirm no backend/API/database/schema changes are introduced by this feature branch; backend tests are not applicable to the feature-only diff. Existing backend suites still require their normal independent checks before any unrelated backend changes ship.
- [x] Run frontend Markets unit tests, ESLint, TypeScript typecheck and production build. Current-head Web quality-gates run `40138138623` passed on head `60b95680a737c4a08d7a8146ff6e80cece02dc2c`, including the monitoring pagination and valuation-backup regression tests.
- [x] Run standalone frontend ESLint and the Markets unit-test suite; both passed in Web quality gates run `40101835044`. Backend code is unchanged by this PR.
- [ ] Test the Markets pages at mobile and desktop sizes.
- [ ] Verify Companies, Research, Deals, Alerts, watchlists and other existing areas remain unaffected.
- [ ] Check accessibility, loading states, empty states, error states and keyboard navigation.
- [x] Review data flow: portfolio holdings and valuation snapshots stay in browser-local storage and are not sent to the event API; no new secrets, dependencies or database schema changes were introduced.
- [x] Review dependency, schema and migration changes; the Excel feature adds the maintained, security-hardened `@stackline/xlsx` package, with no backend schema or environment-variable changes.
- [x] Update this checklist with evidence for each completed automated check; manual and preview-only checks remain open.
- [x] Update the draft PR with current-head automated test results and the remaining manual-interaction limitation; do not claim a current-head preview while Vercel is rate-limited.
- [x] Verify that the previously READY Vercel preview returned HTTP 200 for `/app/markets`, `/app/markets/valuation`, `/app/markets/portfolio`, `/app/markets/compare` and `/app/markets/monitoring` on commit `551cfef445d7b753610de2f82cbad8728edd5d70`. This is historical route evidence only; it predates the latest code. No backend code changed.
- [ ] Manually exercise interactive flows in a browser: local persistence, strict CSV and Excel import/export and malformed-file/formula rejection, currency conversion, clear/delete, valuation save/export/restore, keyboard navigation and monitoring pagination/cap/empty/error states. Vercel reports a build-rate-limit failure for the current branch, so a current-head preview is unavailable; manual acceptance remains open.
- [ ] Obtain explicit approval before merging into `main`.
- [ ] After approval and merge, verify production status and run a post-deploy smoke check.

## Out of scope for the initial release

- [x] No direct trading, custody, payment execution or automatic investment execution.
- [x] No claim of complete/equal financial coverage across all African markets.
- [x] No broker integration requirement for the initial portfolio MVP.
- [x] No separate top-level Portfolio or Research Copilot navigation item.
- [x] No fake market data or unverified valuation claims to fill visual space.

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
| 2026-10-24 | Added DCF/DDM suitability gates and tested portfolio calculations | Earlier market model unit tests, ESLint and TypeScript typecheck passed on source commit `1df9f8314ccbfd7bad4b7037e0f325d21ad97cb5` | Superseded by current-head verification below |
| 2026-10-24 | Full current-head frontend quality gates | GitHub Actions run `40102100229` on PR head `0f768391f5dcfa6c9feccbce3027501927c31611`: Markets unit tests, ESLint, TypeScript typecheck and production build all passed | Current-head automated checks passed; latest-code Vercel preview and manual browser verification remain blocked by deployment-rate limit |
| 2026-10-24 | Completed portfolio valuation summary and documented release gates | Portfolio-level weighted valuation gap is calculated only from holdings whose model fit, source dates, currency, quote/date match and FX freshness pass checks; checklist and PR now record current verification state | Implemented and automated-tested; manual/preview release gates still open |
| 2026-10-24 | Added local portfolio event monitoring and valuation-change insights | `/app/markets/monitoring` reads locally stored holdings, requests only the general 90-day `/api/events` feed, deduplicates and matches exact company names/ticker tokens, links candidate matches to sources, and flags at least 10% changes between saved model estimates. Up to 10 local valuation snapshots per company are retained. | Current-head unit tests, ESLint, TypeScript typecheck and production build passed; Vercel preview and browser verification remain blocked by rate limit |


| 2026-10-24 | Markets overview information-architecture correction | Removed the duplicate company-search workflow, the Research CTA card and the embedded country/exchange/currency coverage panel. Research and Coverage remain separate workspaces; Markets keeps pulse-based deal/event intelligence, valuation, opportunity comparison, portfolio intelligence and monitoring. | Latest correction committed as `4a7a241`; GitHub Actions run `40143183150` passed Markets tests, ESLint, TypeScript and production build. Current-head preview and interactive browser acceptance remain blocked by Vercel deployment limits. PR #17 remains draft; no merge |

## Current verification constraints

- The previously READY app preview is `https://deal-intelligence-65byuvhkv-henry-dibie-s-projects.vercel.app`; its five Markets routes returned HTTP 200 on an earlier commit. It is not a current-head deployment. Vercel is currently returning a build-rate-limit failure for this branch, so interactive acceptance against the latest code is blocked.
- Full Web quality gates passed on current code head `60b95680a737c4a08d7a8146ff6e80cece02dc2c` in run `40138138623`: Markets tests, ESLint, TypeScript typecheck and production build all succeeded, including monitoring pagination and valuation-backup tests. Earlier runs cover the CSV/XLSX regressions.
- The earlier preview's route smoke checks returned HTTP 200 for `/app/markets`, `/app/markets/valuation`, `/app/markets/portfolio`, `/app/markets/compare` and `/app/markets/monitoring`; those checks do not apply to the latest code. The API code was unchanged.
- Production `main` remains untouched by this correction. The original Markets feature PR #13 has already been merged; the targeted follow-up correction is isolated in draft PR #17 and must not be merged until browser acceptance and explicit approval.


| 2026-10-24 | Markets overview correction CI | GitHub Actions run `40134574134` passed on head `506dfb71d348ec26fad1edf784e3900e63ba6b44`: dependency install, Markets unit tests, ESLint, TypeScript typecheck and production build all succeeded. | Code-level quality gates green; preview acceptance followed on the current head |

## Follow-up verification log

| Date | Check | Result | Release implication |
|---|---|---|---|
| 2026-10-24 | Rechecked PR head and CI | Draft PR #13 targets `main`; full Web quality gates run `40108470299` passed on code head `f7829ee434db1a640b5cc58ecfa05b4ea28b80b5` | Keep branch isolated; complete manual acceptance checks |
| 2026-10-24 | Final portfolio UX hardening | Reporting-currency changes now clear stale FX dates; CSV export attaches/removes its download anchor and delays object-URL revocation. | Full Web quality gates run `40108470299` passed: Markets tests, ESLint, TypeScript and production build |
| 2026-10-24 | Probed the newest available READY Vercel preview | Current feature preview returned HTTP 200 for all five Markets routes; API preview returned HTTP 200 for `/api/pulse` and `/api/coverage`. Preview predates latest CSV parser commits. | Route smoke tests pass for the deployed feature version; current-head browser acceptance remains open |
| 2026-10-24 | Hardened portfolio CSV import/export | Extracted CSV parsing and serialization into `web/lib/markets-csv.ts`; parser rejects unclosed quotes, quotes inside unquoted fields and unexpected characters after closing quotes. Added six regression tests for BOM, CRLF, escaped quotes, commas, multiline fields, malformed input and round-trip export. CSV tests are included in `test:markets`. Also clear stale FX dates when changing reporting currency and defer download URL revocation to avoid interrupting CSV downloads. | Web quality gates run `40108470299` passed on code head `f7829ee434db1a640b5cc58ecfa05b4ea28b80b5`; current-head preview blocked by Vercel Free-plan deployment rate limit |

| 2026-10-24 | Added Excel (.xlsx) portfolio support | Added workbook import/export, Excel template download, first-sheet validation, formula rejection, 5 MB / 5,000-row limits, and round-trip / malformed-workbook / formula / size regression tests. CSV flow remains supported. | Code committed to feature branch; CI passed in run `40110920728`; browser interaction acceptance remains open; no merge |


| 2026-10-24 | Current-head Excel regression and quality gates | GitHub Actions run `40110920728` passed on head `fb51dce79ff0b6d03ec093f8509655b9504c1b45`: Markets tests, ESLint, TypeScript typecheck and production build succeeded. The earlier invalid-workbook test failure was fixed by checking the ZIP signature before parsing. | Automated gates green; interactive browser checks and exact-current-head preview verification remain release gates |


| 2026-10-24 | Final Markets overview polish and current-head verification | Removed repeated navigation links and the duplicate “Compare companies” link, leaving a focused Compare opportunities and Monitoring section. GitHub Actions run `40136786937` passed Markets tests, ESLint, TypeScript typecheck and production build on `551cfef445d7b753610de2f82cbad8728edd5d70`. Current-head Vercel app preview is READY; all five Markets routes return HTTP 200. | Code and route smoke checks passed; manual interactive browser acceptance and explicit approval before merge remain open |


| 2026-10-24 | Monitoring coverage hardening | Replaced the single-page 100-event request with bounded 500-row pagination, up to 5,000 events per refresh. The page now reports total available events when supplied by the API and warns explicitly when the safety cap leaves the pass incomplete. Added regression tests for pagination, cap disclosure and feed errors. | Current-head Web quality gates passed in run `40138138623`. Interactive browser acceptance, mobile/desktop, keyboard/accessibility, persistence and import/export remain open; no production merge. |


| 2026-10-24 | Local valuation-history backup and restore | Added a JSON export for saved valuation snapshots and a guarded restore path that validates version, dates, source URLs, required fields, duplicate IDs and a 5,000-snapshot limit before asking for confirmation. Import is capped at 2 MB and only replaces local valuation history; CSV/XLSX continue to back up holdings. Added regression tests for malformed and duplicate snapshot backups. | Current-head Web quality gates passed in run `40138138623`; interactive browser acceptance is still required. No production merge. |


| 2026-10-24 | Comparison and backup UX hardening | Compare Opportunities now surfaces explicit caveats for mixed financial-statement currencies, reporting periods separated by more than 180 days, and comparisons mixing listed quotes with private-market valuation marks. Saved valuation history can be exported/restored independently of the current calculation form, with separate status feedback. | Added on `fix/markets-overview-alignment`; current-head CI passed in run `40138138623`. Browser interaction acceptance remains a release gate. |


| 2026-10-24 | Current-head Markets reliability verification | Run `40138138623` passed on head `60b95680a737c4a08d7a8146ff6e80cece02dc2c`: Markets unit tests, ESLint, TypeScript typecheck and Next.js production build all succeeded. This includes the new event-pagination/cap tests and saved valuation-backup validation tests. | Automated code checks complete. Current-head Vercel preview is blocked by build-rate-limit; interactive browser acceptance, mobile/desktop, accessibility and regression checks remain open. PR #17 stays draft and production `main` remains untouched. |
| 2026-10-24 | Markets information architecture final boundary check | Removed the remaining Research CTA and embedded Coverage summary from Markets so neither workspace is duplicated in the overview. | Automated checks passed on `4a7a241`; newest code still requires a current-head preview and interactive browser acceptance. Production `main` untouched. |


## Multi-asset investment discovery — initial slice (2026-10-28)

- [x] Add a dedicated Markets route for investment instruments and link it from the Markets overview.
- [x] Add deterministic Treasury-bill calculator for face value, discount rate and tenor; show indicative purchase price, maturity income, holding-period return, simple annualized investment yield and bank discount yield separately.
- [x] Add deterministic fixed-coupon bond calculator for annual coupon income, current yield and indicative yield to maturity using a bisection solver; validate inputs and disclose simplified assumptions.
- [x] Link the instrument categories to official Nigerian source starting points: CBN government-securities rates, DMO FGN bond information, FMDQ market-data portal and SEC Nigeria NAV datasets.
- [x] Add unit tests for T-bill conventions, invalid inputs, par bond yield and premium/discount bond behaviour.
- [ ] Ingest and normalize dated instrument-level market observations. The new page does not yet claim to contain a live ETF, bond, T-bill, fund or fixed-deposit catalogue.
- [ ] Build source adapters and schema for instrument identity, issuer/provider, country, currency, observed price/rate/NAV, fees, maturity, source URL, published date, retrieval time and confidence/coverage status.
- [ ] Add ETF and fund comparison metrics, bond duration/credit fields, T-bill auction history, fixed-deposit terms and dedicated REIT metrics.
- [ ] Verify all calculator flows, responsive layout, accessibility and source-link behaviour in a running preview; run full Web quality gates before merge.
- [ ] Keep production `main` untouched until review and explicit approval.

