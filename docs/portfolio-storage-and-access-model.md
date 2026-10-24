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

## Required follow-up before enabling cloud portfolios

1. Configure and verify the Supabase Auth email confirmation, recovery, redirect URLs (including the web origin's /auth/callback route), and web-project environment variables.
2. Add automated RLS integration tests for two unrelated users, two separate organizations, same-organization role differences, personal-vs-shared portfolio boundaries, and attempted cross-tenant ID substitution.
3. The migrations have passed isolated local Supabase/pgTAP CI and are recorded as applied in the hosted project. Review Supabase security/performance advisor findings before enabling the feature; the current project-level advisor output also includes pre-existing platform-wide findings that need triage.
4. Keep the cloud CSV/XLSX transaction importer bounded at 5,000 rows per request; it validates the full file before an atomic commit, rejects duplicate external IDs, and makes retries idempotent.
5. Keep local-to-cloud migration explicit and preserve the original browser data as a backup. The server checks reporting-currency compatibility and records an idempotency receipt.
6. Member listing/role changes/removal and invite revocation are implemented through restricted admin RPCs. Verify these workflows in the browser before enabling cloud access.
7. Test browser interactions, keyboard accessibility, session expiry/refresh, mobile layouts, and regression across existing app areas.
8. Verify current preview/API deployment tied to the latest source head when a preview can be created. Avoid repeated preview builds while Vercel is rate-limited; GitHub Actions checks are not a substitute for interactive browser acceptance.

## Acceptance matrix

- User A cannot read, update, or delete User B's personal portfolio or child rows.
- A member of Organization A cannot read or mutate Organization B's portfolios, transactions, import jobs, valuations, or audit events.
- A viewer can read shared portfolio data but cannot create or edit it.
- An analyst can create/update instruments, transactions, valuation snapshots, and import-job status, but cannot administer membership or delete ledger records.
- A manager can manage portfolio data and read audit history, but cannot promote themselves or another user to organization owner.
- Organization and portfolio records are not hard-deleted through client permissions; archival preserves their ledger and audit history. Organization membership and portfolio ownership checks must not depend on client-supplied role claims.
- An import that fails validation does not partially commit holdings or transactions.
- Existing browser-local data remains untouched until the user explicitly chooses to migrate it.
