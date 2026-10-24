# Multi-user portfolio storage and access model

## Status

This is the first implementation slice for database-backed Markets portfolios. The migration is additive and has **not** been applied to the hosted Deal Intelligence database. The existing Markets UI remains browser-local until authentication, API integration, migration verification, and migration of local data are completed.

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

The first schema slice does not yet calculate positions from the ledger, process uploads asynchronously, write audit events automatically, or replace the localStorage adapter. Those require application/API integration and explicit tests.

## Security controls

- RLS is enabled on every table introduced by the migration.
- The anonymous role receives no table privileges.
- Organization and portfolio policies use server-verified `auth.uid()`, membership records, and role checks. User-editable metadata is not used for authorization.
- Role-checking functions live in the non-exposed `private` schema, use a fixed empty search path, and are not executable by anonymous users.
- Organization creation inserts the creator's owner membership through a database trigger, so the organization cannot be created without an owner membership.
- Audit history allows append through database triggers and read by authorized users but exposes no client-side insert/update/delete policy.
- Portfolio and ledger records are not hard-deleted through the client API. Organization/portfolio archival fields are available so retention can be preserved.
- The migration does not use a service-role key in the browser and does not touch the hosted schema.

## Required follow-up before enabling cloud portfolios

1. Add sign-up/sign-in/session refresh/sign-out for the Markets portfolio experience without requiring accounts to browse public research pages.
2. Add authenticated server-side portfolio routes and use the caller's Supabase access token so database RLS remains the authorization boundary.
3. Add organization invitation and membership administration, with safe invitation acceptance and protections against removing or demoting the last owner.
4. Add portfolio CRUD, transaction-ledger operations, position calculations, valuation snapshot persistence, and append-only audit writes.
5. Implement staged CSV/XLSX imports: validate and preview first, then commit in bounded batches; make retries idempotent and keep rejected rows/errors available to the user.
6. Provide an explicit, user-controlled import of existing localStorage holdings and valuation snapshots. Never silently upload browser-local financial data.
7. Add RLS integration tests for two unrelated users, two separate organizations, same-organization role differences, personal-vs-shared portfolio boundaries, and attempted cross-tenant ID substitution.
8. Run Supabase security/performance advisors and verify the migration against a disposable/local database before applying it to the hosted project.
9. Verify account email settings, redirect URLs, environment variables, recovery flow, rate limits, and privacy copy before enabling sign-up.

## Acceptance matrix

- User A cannot read, update, or delete User B's personal portfolio or child rows.
- A member of Organization A cannot read or mutate Organization B's portfolios, transactions, import jobs, valuations, or audit events.
- A viewer can read shared portfolio data but cannot create or edit it.
- An analyst can create/update instruments, transactions, valuation snapshots, and import-job status, but cannot administer membership or delete ledger records.
- A manager can manage portfolio data and read audit history, but cannot promote themselves or another user to organization owner.
- Organization and portfolio records are not hard-deleted through client permissions; archival preserves their ledger and audit history. Organization membership and portfolio ownership checks must not depend on client-supplied role claims.
- An import that fails validation does not partially commit holdings or transactions.
- Existing browser-local data remains untouched until the user explicitly chooses to migrate it.
