-- Cover portfolio/workspace foreign keys used by tenant joins and deletion checks.
-- Keep indexes idempotent so environments with an equivalent index can safely apply this migration.

create index if not exists organization_invites_created_by_idx
  on public.organization_invites (created_by);

create index if not exists organization_memberships_invited_by_idx
  on public.organization_memberships (invited_by);

create index if not exists organizations_archived_by_idx
  on public.organizations (archived_by);

create index if not exists organizations_created_by_idx
  on public.organizations (created_by);

create index if not exists portfolio_audit_events_actor_user_id_idx
  on public.portfolio_audit_events (actor_user_id);

create index if not exists portfolio_import_jobs_created_by_idx
  on public.portfolio_import_jobs (created_by);

create index if not exists portfolio_instruments_created_by_idx
  on public.portfolio_instruments (created_by);

create index if not exists portfolio_migration_receipts_user_id_idx
  on public.portfolio_migration_receipts (user_id);

create index if not exists portfolio_transactions_created_by_idx
  on public.portfolio_transactions (created_by);

-- The existing single-column instrument index does not cover this two-column FK.
create index if not exists portfolio_transactions_instrument_portfolio_fk_idx
  on public.portfolio_transactions (instrument_id, portfolio_id);

create index if not exists portfolio_transactions_source_import_id_idx
  on public.portfolio_transactions (source_import_id);

create index if not exists portfolio_valuations_created_by_idx
  on public.portfolio_valuations (created_by);

create index if not exists portfolios_archived_by_idx
  on public.portfolios (archived_by);

create index if not exists portfolios_created_by_idx
  on public.portfolios (created_by);
