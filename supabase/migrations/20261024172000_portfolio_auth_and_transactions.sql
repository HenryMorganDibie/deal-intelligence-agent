-- Cloud portfolio application fields, invitation codes, and transaction integrity.
begin;

alter table public.portfolio_instruments
  add column if not exists current_price numeric(24, 8)
    check (current_price is null or current_price > 0),
  add column if not exists price_as_of date,
  add column if not exists fx_to_base numeric(24, 12)
    check (fx_to_base is null or fx_to_base > 0),
  add column if not exists fx_as_of date;

alter table public.portfolio_instruments
  add constraint portfolio_instruments_id_portfolio_unique unique (id, portfolio_id);

alter table public.portfolio_transactions
  drop constraint if exists portfolio_transactions_instrument_id_fkey;
alter table public.portfolio_transactions
  add constraint portfolio_transactions_instrument_portfolio_fkey
  foreign key (instrument_id, portfolio_id)
  references public.portfolio_instruments(id, portfolio_id)
  on delete restrict;

create table public.organization_invites (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  token_hash text not null unique check (token_hash ~ '^[a-f0-9]{64}$'),
  role text not null check (role in ('admin', 'manager', 'analyst', 'viewer')),
  expires_at timestamptz not null,
  max_uses integer not null default 1 check (max_uses = 1),
  use_count integer not null default 0 check (use_count >= 0 and use_count <= max_uses),
  revoked_at timestamptz,
  created_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  check (expires_at > created_at)
);

create index organization_invites_org_idx
  on public.organization_invites (organization_id, created_at desc);

alter table public.organization_invites enable row level security;
revoke all on public.organization_invites from anon, authenticated;
grant insert on public.organization_invites to authenticated;

create policy "organization admins can create limited-use invites"
on public.organization_invites for insert to authenticated
with check (
  created_by = (select auth.uid())
  and role <> 'owner'
  and private.has_org_role(organization_id, 'admin')
  and (role <> 'admin' or private.has_org_role(organization_id, 'owner'))
  and max_uses = 1
  and expires_at > now()
  and expires_at <= now() + interval '7 days'
);

create or replace function public.accept_organization_invite(p_token_hash text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_invite public.organization_invites%rowtype;
  v_already_member boolean;
begin
  if (select auth.uid()) is null then
    raise exception using errcode = '42501', message = 'Authentication required';
  end if;

  if p_token_hash !~ '^[a-f0-9]{64}$' then
    raise exception using errcode = '22023', message = 'Invalid or expired invitation';
  end if;

  select *
    into v_invite
  from public.organization_invites
  where token_hash = p_token_hash
    and revoked_at is null
    and expires_at > now()
    and use_count < max_uses
  for update;

  if not found then
    raise exception using errcode = '22023', message = 'Invalid or expired invitation';
  end if;

  if exists (
    select 1 from public.organizations
    where id = v_invite.organization_id and archived_at is not null
  ) then
    raise exception using errcode = '22023', message = 'Invitation is no longer valid';
  end if;

  select exists (
    select 1 from public.organization_memberships
    where organization_id = v_invite.organization_id and user_id = (select auth.uid())
  ) into v_already_member;

  if v_already_member then
    return jsonb_build_object(
      'organization_id', v_invite.organization_id,
      'role', (select m.role from public.organization_memberships as m
               where m.organization_id = v_invite.organization_id
                 and m.user_id = (select auth.uid())),
      'already_member', true
    );
  end if;

  insert into public.organization_memberships (organization_id, user_id, role, invited_by)
  values (v_invite.organization_id, (select auth.uid()), v_invite.role, v_invite.created_by);

  update public.organization_invites
  set use_count = use_count + 1
  where id = v_invite.id;

  return jsonb_build_object(
    'organization_id', v_invite.organization_id,
    'role', v_invite.role,
    'already_member', false
  );
end;
$$;

revoke all on function public.accept_organization_invite(text) from public, anon;
grant execute on function public.accept_organization_invite(text) to authenticated;

commit;
