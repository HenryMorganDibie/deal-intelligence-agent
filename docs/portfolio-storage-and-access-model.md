# Multi-user portfolio storage and access model

## Status

This is the implementation record for database-backed Markets portfolios. The six portfolio migrations are recorded in the hosted Deal Intelligence Supabase project as of 2026-10-25, and the live schema was independently checked: the portfolio tables exist, RLS is enabled, anonymous table access is denied, and the expected role-scoped policies are present. This verifies schema state, not end-to-end authentication or browser acceptance. Existing browser-local holdings remain separate until a signed-in user explicitly migrates them.

## Ownership model

A portfolio must have exactly one ownership mode:

- **Personal portfolio:** `owner_user_id` is set and `organization_id` is null. Only that signed-in user can access it.
- **Organization portfolio:** `organization_id` is set and `owner_user_id` is null. Access is based on current organization membership and role.

The database constraint prevents a portfolio from being simultaneously personal and organization-owned. A user's membership in one organization does not grant access to another organization's portfolios.

## Roles

| Role | Read portfolio | Edit instruments / transactions / valuation snapshots | Create shared portfolios | Manage organization membership |
| --- | --- | --- | --- | --- |
| Owner | Yes | Yes | Yes | Yes |
| Admin | Yes | Yes | Yes | Yes |
| Manager | Yes | Yes | Yes | No |
| Analyst | Yes | Yes | No | No |
| Viewer | Yes | No | No | No |

Personal portfolio owners can manage their own portfolio. Organization roles do not grant access to a user's separate personal portfolios.

## Data model

- `organizations` and `organization_memberships`: workspaces and role assignments.
- `portfolios`: personal or organization-owned portfolio metadata and reporting currency.
- `portfolio_instruments`: portfolio-scoped instrument details.
- `portfolio_transactions`: transaction ledger with typed buys, sells, cash movements, dividends, fees, transfers, splits, and adjustments. This is the source of truth for future position calculations.
- `portfolio_valuations`: immutable-style dated valuation snapshots and assumptions.
- `portfolio_import_jobs`: import status, row counts, and structured validation errors.
- `portfolio_audit_events`: append-only actor/action history; database triggers record portfolio, instrument, transaction, valuation, and import-job inserts/updates without copying financial values into audit details.

The database foundation now includes current-price/FX metadata, single-use hashed organization invite codes, atomic CSV/XLSX transaction imports, explicit retry-safe migration of browser-local holdings and valuation reviews, saved cloud valuation snapshots, and organization member/invite administration. Positions are derived from recorded transactions; live market quotes, performance attribution, and asynchronous large-file storage processing remain out of scope.

## Security controls

- RLS is enabled on every table introduced by the migration.
- The anonymous role receives no table privileges.
- Organization and portfolio policies use server-verified `auth.uid()`, membership records, and role checks. User-editable metadata is not used for authorization.
- Role-checking functions live in the non-exposed `private` schema, use a fixed empty search path, and are not executable by anonymous users.
- Organization creation inserts the creator's owner membership through a database trigger, so the organization cannot be created without an owner membership.
- Audit history allows append through database triggers and read by authorized users but exposes no client-side insert/update/delete policy.
- Portfolio and ledger records are not hard-deleted through the client API. Organization/portfolio archival fields are available so retention can be preserved.
- No service-role/secret key is used in browser code. Authenticated application requests use HTTP-only, same-site cookies and the signed-in user's access token so database RLS remains in force. The hosted migrations are already applied; do not re-apply them.
- Organization invite codes are random, hashed before storage, single-use, and expire after seven days. The raw code is returned only when generated; no email is sent by the current implementation.

## Release gates before enabling cloud portfolios

1. [ ] Configure and verify Supabase Auth email confirmation, password recovery, and allowed redirect URLs for production and the preview origins used for testing. Verify Google OAuth provider credentials and callback configuration in Supabase and Google Cloud.
2. [x] Add isolated pgTAP tests for unrelated users, separate organizations, role differences, personal-vs-shared boundaries, cross-tenant ID substitution, viewer restrictions, and ledger immutability. The current Web quality-gate run applies migrations to an isolated Supabase stack and passes these tests.
3. [x] Add migration `20261025010000_portfolio_foreign_key_indexes.sql` covering the 14 portfolio/workspace foreign keys flagged by the performance advisor. [ ] The migration is branch-only until the release is approved and applied; live advisor findings will remain until then.
4. [ ] Review Supabase security/performance advisor findings after the index migration is applied. The live project has RLS enabled on portfolio tables and anonymous table access is denied; migration receipts are intentionally inaccessible directly. Review broader pre-existing `SECURITY DEFINER` warnings separately rather than treating all findings as new portfolio defects.
5. [ ] Enable Supabase Auth leaked-password protection if the project plan supports it. The current Supabase organization is on the Free plan; Supabase documents this protection as available on Pro and above, so enabling it requires a plan upgrade. Do not upgrade or incur costs without Henry's explicit approval.
6. [x] Keep cloud CSV/XLSX transaction imports bounded at 5,000 rows per request; validate the full file before an atomic commit, reject duplicate external IDs, and make retries idempotent.
7. [x] Keep local-to-cloud migration explicit and preserve original browser data as a backup. The server checks reporting-currency compatibility and records an idempotency receipt.
8. [ ] Verify organization member listing, role changes/removal, and invite creation/acceptance/revocation in an authenticated browser.
9. [ ] Test browser interactions, keyboard accessibility, session expiry/refresh, mobile layouts, and regressions across existing app areas.
10. [ ] Verify a current-source preview/API deployment and run interactive smoke tests when Vercel can create a preview. Avoid repeated preview builds while rate-limited; GitHub Actions checks are not a substitute for browser acceptance.

## Acceptance matrix

- User A cannot read, update, or delete User B's personal portfolio or child rows.
- A member of Organization A cannot read or mutate Organization B's portfolios, transactions, import jobs, valuations, or audit events.
- A viewer can read shared portfolio data but cannot create or edit it.
- An analyst can create/update instruments, transactions, valuation snapshots, and import-job status, but cannot administer membership or delete ledger records.
- A manager can manage portfolio data and read audit history, but cannot promote themselves or another user to organization owner.
- Organization and portfolio records are not hard-deleted through client permissions; archival preserves their ledger and audit history. Organization membership and portfolio ownership checks must not depend on client-supplied role claims.
- An import that fails validation does not partially commit holdings or transactions.
- Existing browser-local data remains untouched until the user explicitly chooses to migrate it.
