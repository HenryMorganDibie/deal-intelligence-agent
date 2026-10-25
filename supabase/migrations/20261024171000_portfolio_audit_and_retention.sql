-- Retain portfolio and ledger history. Cloud portfolios are archived rather than
-- hard-deleted, and all material portfolio edits append an audit event.
begin;

alter table public.organizations
  add column if not exists archived_at timestamptz,
  add column if not exists archived_by uuid references auth.users(id) on delete set null;

alter table public.portfolios
  add column if not exists archived_at timestamptz,
  add column if not exists archived_by uuid references auth.users(id) on delete set null;

alter table public.portfolios
  drop constraint if exists portfolios_organization_id_fkey;
alter table public.portfolios
  add constraint portfolios_organization_id_fkey
  foreign key (organization_id) references public.organizations(id) on delete restrict;

drop policy if exists "organization owners can delete organizations" on public.organizations;
drop policy if exists "owners and portfolio managers can delete portfolios" on public.portfolios;
drop policy if exists "managers can delete instruments" on public.portfolio_instruments;
drop policy if exists "managers can delete transactions" on public.portfolio_transactions;
drop policy if exists "managers can delete valuation snapshots" on public.portfolio_valuations;

revoke delete on public.organizations, public.portfolios, public.portfolio_instruments,
  public.portfolio_transactions, public.portfolio_valuations, public.portfolio_import_jobs
  from authenticated;

create or replace function private.record_portfolio_audit()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_portfolio_id uuid;
  v_entity_id text;
  v_changed_fields text[];
begin
  if (select auth.uid()) is null then
    raise exception 'Authenticated actor required for portfolio changes';
  end if;

  if tg_table_name = 'portfolios' then
    v_portfolio_id := (to_jsonb(new)->>'id')::uuid;
  else
    v_portfolio_id := (to_jsonb(new)->>'portfolio_id')::uuid;
  end if;
  v_entity_id := to_jsonb(new)->>'id';

  if tg_op = 'UPDATE' then
    select coalesce(array_agg(n.key order by n.key), array[]::text[])
      into v_changed_fields
    from jsonb_each(to_jsonb(new)) as n
    where n.key <> 'updated_at'
      and (to_jsonb(old)->n.key) is distinct from n.value;
  else
    v_changed_fields := array[]::text[];
  end if;

  insert into public.portfolio_audit_events
    (portfolio_id, actor_user_id, action, entity_type, entity_id, details)
  values
    (v_portfolio_id, (select auth.uid()), lower(tg_op), tg_table_name, v_entity_id,
     jsonb_build_object('changed_fields', v_changed_fields));

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

revoke all on function private.record_portfolio_audit() from public, anon, authenticated;

create trigger portfolio_audit_portfolios
after insert or update on public.portfolios
for each row execute function private.record_portfolio_audit();

create trigger portfolio_audit_instruments
after insert or update on public.portfolio_instruments
for each row execute function private.record_portfolio_audit();

create trigger portfolio_audit_transactions
after insert or update on public.portfolio_transactions
for each row execute function private.record_portfolio_audit();

create trigger portfolio_audit_valuations
after insert or update on public.portfolio_valuations
for each row execute function private.record_portfolio_audit();

create trigger portfolio_audit_import_jobs
after insert or update on public.portfolio_import_jobs
for each row execute function private.record_portfolio_audit();

commit;
