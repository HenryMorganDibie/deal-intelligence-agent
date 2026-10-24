-- Multi-user, multi-tenant portfolio storage.
-- This migration is intentionally additive. It is reviewed in Git first and is
-- not applied to the hosted database automatically.
begin;

create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated;

create table public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(btrim(name)) between 2 and 120),
  slug text not null unique check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' and length(slug) <= 80),
  created_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.organization_memberships (
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('owner', 'admin', 'manager', 'analyst', 'viewer')),
  invited_by uuid references auth.users(id) on delete set null,
  joined_at timestamptz not null default now(),
  primary key (organization_id, user_id)
);

create index organization_memberships_user_idx
  on public.organization_memberships (user_id, organization_id);

create table public.portfolios (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid references auth.users(id) on delete restrict,
  organization_id uuid references public.organizations(id) on delete cascade,
  name text not null check (length(btrim(name)) between 1 and 160),
  base_currency text not null default 'USD' check (base_currency ~ '^[A-Z]{3}$'),
  description text,
  created_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (
    (owner_user_id is not null and organization_id is null)
    or (owner_user_id is null and organization_id is not null)
  )
);

create index portfolios_owner_updated_idx
  on public.portfolios (owner_user_id, updated_at desc)
  where owner_user_id is not null;
create index portfolios_organization_updated_idx
  on public.portfolios (organization_id, updated_at desc)
  where organization_id is not null;

create table public.portfolio_instruments (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references public.portfolios(id) on delete cascade,
  name text not null check (length(btrim(name)) between 1 and 200),
  ticker text,
  market text,
  country text,
  sector text,
  asset_type text not null default 'Stock',
  currency text not null check (currency ~ '^[A-Z]{3}$'),
  external_identifier text,
  created_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index portfolio_instruments_portfolio_idx
  on public.portfolio_instruments (portfolio_id, name);
create index portfolio_instruments_ticker_idx
  on public.portfolio_instruments (ticker)
  where ticker is not null;

create table public.portfolio_transactions (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references public.portfolios(id) on delete cascade,
  instrument_id uuid references public.portfolio_instruments(id) on delete restrict,
  transaction_date date not null,
  transaction_type text not null check (
    transaction_type in (
      'BUY', 'SELL', 'DIVIDEND', 'DEPOSIT', 'WITHDRAWAL', 'FEE',
      'SPLIT', 'TRANSFER_IN', 'TRANSFER_OUT', 'ADJUSTMENT'
    )
  ),
  quantity numeric(24, 8) not null default 0 check (quantity >= 0),
  unit_price numeric(24, 8) not null default 0 check (unit_price >= 0),
  cash_amount numeric(24, 8) not null default 0,
  fees numeric(24, 8) not null default 0 check (fees >= 0),
  currency text not null check (currency ~ '^[A-Z]{3}$'),
  fx_to_base numeric(24, 12) check (fx_to_base is null or fx_to_base > 0),
  external_id text,
  notes text,
  source_import_id uuid,
  created_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (
    (transaction_type in ('BUY', 'SELL', 'SPLIT', 'TRANSFER_IN', 'TRANSFER_OUT', 'ADJUSTMENT')
      and instrument_id is not null and quantity > 0)
    or transaction_type in ('DIVIDEND', 'DEPOSIT', 'WITHDRAWAL', 'FEE')
  )
);

create index portfolio_transactions_date_idx
  on public.portfolio_transactions (portfolio_id, transaction_date desc, created_at desc);
create index portfolio_transactions_instrument_idx
  on public.portfolio_transactions (instrument_id, transaction_date);
create unique index portfolio_transactions_external_id_unique
  on public.portfolio_transactions (portfolio_id, external_id)
  where external_id is not null;

create table public.portfolio_valuations (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references public.portfolios(id) on delete cascade,
  valuation_date date not null,
  base_currency text not null check (base_currency ~ '^[A-Z]{3}$'),
  model text not null,
  snapshot jsonb not null check (jsonb_typeof(snapshot) = 'object'),
  notes text,
  created_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now()
);

create index portfolio_valuations_history_idx
  on public.portfolio_valuations (portfolio_id, valuation_date desc, created_at desc);

create table public.portfolio_import_jobs (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references public.portfolios(id) on delete cascade,
  source_format text not null check (source_format in ('csv', 'xlsx')),
  status text not null default 'pending' check (
    status in ('pending', 'validating', 'ready', 'committing', 'completed', 'failed', 'cancelled')
  ),
  original_filename text not null check (length(original_filename) between 1 and 255),
  storage_path text,
  total_rows integer not null default 0 check (total_rows >= 0),
  accepted_rows integer not null default 0 check (accepted_rows >= 0),
  rejected_rows integer not null default 0 check (rejected_rows >= 0),
  duplicate_rows integer not null default 0 check (duplicate_rows >= 0),
  error_report jsonb not null default '[]'::jsonb check (jsonb_typeof(error_report) = 'array'),
  created_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index portfolio_import_jobs_history_idx
  on public.portfolio_import_jobs (portfolio_id, created_at desc);

alter table public.portfolio_transactions
  add constraint portfolio_transactions_source_import_fkey
  foreign key (source_import_id) references public.portfolio_import_jobs(id) on delete set null;

create table public.portfolio_audit_events (
  id bigint generated always as identity primary key,
  portfolio_id uuid not null references public.portfolios(id) on delete cascade,
  actor_user_id uuid not null references auth.users(id) on delete restrict,
  action text not null check (length(btrim(action)) between 1 and 100),
  entity_type text not null check (length(btrim(entity_type)) between 1 and 100),
  entity_id text,
  details jsonb not null default '{}'::jsonb check (jsonb_typeof(details) = 'object'),
  created_at timestamptz not null default now()
);

create index portfolio_audit_history_idx
  on public.portfolio_audit_events (portfolio_id, created_at desc);

create or replace function private.has_org_role(p_organization_id uuid, p_minimum_role text default 'viewer')
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.organization_memberships as m
    where m.organization_id = p_organization_id
      and m.user_id = (select auth.uid())
      and case m.role
        when 'owner' then 5
        when 'admin' then 4
        when 'manager' then 3
        when 'analyst' then 2
        when 'viewer' then 1
        else 0
      end >= case p_minimum_role
        when 'owner' then 5
        when 'admin' then 4
        when 'manager' then 3
        when 'analyst' then 2
        when 'viewer' then 1
        else 99
      end
  );
$$;

create or replace function private.can_access_portfolio(p_portfolio_id uuid, p_minimum_role text default 'viewer')
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.portfolios as p
    where p.id = p_portfolio_id
      and (
        p.owner_user_id = (select auth.uid())
        or (
          p.organization_id is not null
          and private.has_org_role(p.organization_id, p_minimum_role)
        )
      )
  );
$$;

create or replace function private.add_organization_owner()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.created_by is null or new.created_by <> (select auth.uid()) then
    raise exception 'Organization creator must match the authenticated user';
  end if;

  insert into public.organization_memberships (organization_id, user_id, role)
  values (new.id, new.created_by, 'owner');

  return new;
end;
$$;

revoke all on function private.has_org_role(uuid, text) from public, anon;
revoke all on function private.can_access_portfolio(uuid, text) from public, anon;
revoke all on function private.add_organization_owner() from public, anon;
grant execute on function private.has_org_role(uuid, text) to authenticated;
grant execute on function private.can_access_portfolio(uuid, text) to authenticated;

create trigger organizations_add_owner
after insert on public.organizations
for each row execute function private.add_organization_owner();

alter table public.organizations enable row level security;
alter table public.organization_memberships enable row level security;
alter table public.portfolios enable row level security;
alter table public.portfolio_instruments enable row level security;
alter table public.portfolio_transactions enable row level security;
alter table public.portfolio_valuations enable row level security;
alter table public.portfolio_import_jobs enable row level security;
alter table public.portfolio_audit_events enable row level security;

create policy "organization members can read their organization"
on public.organizations for select to authenticated
using (private.has_org_role(id, 'viewer'));

create policy "authenticated users can create organizations for themselves"
on public.organizations for insert to authenticated
with check (created_by = (select auth.uid()));

create policy "organization admins can update organization details"
on public.organizations for update to authenticated
using (private.has_org_role(id, 'admin'))
with check (private.has_org_role(id, 'admin'));

create policy "organization owners can delete organizations"
on public.organizations for delete to authenticated
using (private.has_org_role(id, 'owner'));

create policy "members can read organization membership"
on public.organization_memberships for select to authenticated
using (private.has_org_role(organization_id, 'viewer'));

create policy "organization admins can add non-owner members"
on public.organization_memberships for insert to authenticated
with check (
  role <> 'owner'
  and invited_by = (select auth.uid())
  and private.has_org_role(organization_id, 'admin')
);

create policy "organization admins can update non-owner memberships"
on public.organization_memberships for update to authenticated
using (role <> 'owner' and private.has_org_role(organization_id, 'admin'))
with check (role <> 'owner' and private.has_org_role(organization_id, 'admin'));

create policy "organization admins can remove non-owner members"
on public.organization_memberships for delete to authenticated
using (role <> 'owner' and private.has_org_role(organization_id, 'admin'));

create policy "portfolio members can read portfolios"
on public.portfolios for select to authenticated
using (private.can_access_portfolio(id, 'viewer'));

create policy "users can create private portfolios or managers can create shared portfolios"
on public.portfolios for insert to authenticated
with check (
  (owner_user_id = (select auth.uid()) and organization_id is null)
  or (owner_user_id is null and organization_id is not null
      and private.has_org_role(organization_id, 'manager'))
);

create policy "owners and portfolio managers can update portfolios"
on public.portfolios for update to authenticated
using (
  (owner_user_id = (select auth.uid()) and organization_id is null)
  or (organization_id is not null and private.has_org_role(organization_id, 'manager'))
)
with check (
  (owner_user_id = (select auth.uid()) and organization_id is null)
  or (owner_user_id is null and organization_id is not null
      and private.has_org_role(organization_id, 'manager'))
);

create policy "owners and portfolio managers can delete portfolios"
on public.portfolios for delete to authenticated
using (
  (owner_user_id = (select auth.uid()) and organization_id is null)
  or (organization_id is not null and private.has_org_role(organization_id, 'manager'))
);

create policy "portfolio members can read instruments"
on public.portfolio_instruments for select to authenticated
using (private.can_access_portfolio(portfolio_id, 'viewer'));

create policy "analysts can create instruments"
on public.portfolio_instruments for insert to authenticated
with check (created_by = (select auth.uid()) and private.can_access_portfolio(portfolio_id, 'analyst'));

create policy "analysts can update instruments"
on public.portfolio_instruments for update to authenticated
using (private.can_access_portfolio(portfolio_id, 'analyst'))
with check (private.can_access_portfolio(portfolio_id, 'analyst'));

create policy "managers can delete instruments"
on public.portfolio_instruments for delete to authenticated
using (private.can_access_portfolio(portfolio_id, 'manager'));

create policy "portfolio members can read transactions"
on public.portfolio_transactions for select to authenticated
using (private.can_access_portfolio(portfolio_id, 'viewer'));

create policy "analysts can create transactions"
on public.portfolio_transactions for insert to authenticated
with check (
  created_by = (select auth.uid())
  and private.can_access_portfolio(portfolio_id, 'analyst')
);

create policy "analysts can update transactions"
on public.portfolio_transactions for update to authenticated
using (private.can_access_portfolio(portfolio_id, 'analyst'))
with check (
  created_by = (select auth.uid())
  and private.can_access_portfolio(portfolio_id, 'analyst')
);

create policy "managers can delete transactions"
on public.portfolio_transactions for delete to authenticated
using (private.can_access_portfolio(portfolio_id, 'manager'));

create policy "portfolio members can read valuation snapshots"
on public.portfolio_valuations for select to authenticated
using (private.can_access_portfolio(portfolio_id, 'viewer'));

create policy "analysts can save valuation snapshots"
on public.portfolio_valuations for insert to authenticated
with check (
  created_by = (select auth.uid())
  and private.can_access_portfolio(portfolio_id, 'analyst')
);

create policy "analysts can update valuation snapshots"
on public.portfolio_valuations for update to authenticated
using (private.can_access_portfolio(portfolio_id, 'analyst'))
with check (
  created_by = (select auth.uid())
  and private.can_access_portfolio(portfolio_id, 'analyst')
);

create policy "managers can delete valuation snapshots"
on public.portfolio_valuations for delete to authenticated
using (private.can_access_portfolio(portfolio_id, 'manager'));

create policy "portfolio members can read import jobs"
on public.portfolio_import_jobs for select to authenticated
using (private.can_access_portfolio(portfolio_id, 'viewer'));

create policy "analysts can create import jobs"
on public.portfolio_import_jobs for insert to authenticated
with check (
  created_by = (select auth.uid())
  and private.can_access_portfolio(portfolio_id, 'analyst')
);

create policy "analysts can update import jobs"
on public.portfolio_import_jobs for update to authenticated
using (private.can_access_portfolio(portfolio_id, 'analyst'))
with check (
  created_by = (select auth.uid())
  and private.can_access_portfolio(portfolio_id, 'analyst')
);

create policy "portfolio managers can read audit history"
on public.portfolio_audit_events for select to authenticated
using (private.can_access_portfolio(portfolio_id, 'manager'));

create policy "authorized portfolio writers can append audit history"
on public.portfolio_audit_events for insert to authenticated
with check (
  actor_user_id = (select auth.uid())
  and private.can_access_portfolio(portfolio_id, 'analyst')
);

revoke all on public.organizations, public.organization_memberships, public.portfolios,
  public.portfolio_instruments, public.portfolio_transactions, public.portfolio_valuations,
  public.portfolio_import_jobs, public.portfolio_audit_events from anon;

grant select, insert, update, delete on public.organizations, public.organization_memberships,
  public.portfolios, public.portfolio_instruments, public.portfolio_transactions,
  public.portfolio_valuations, public.portfolio_import_jobs to authenticated;
grant select, insert on public.portfolio_audit_events to authenticated;
grant usage, select on sequence public.portfolio_audit_events_id_seq to authenticated;

commit;
