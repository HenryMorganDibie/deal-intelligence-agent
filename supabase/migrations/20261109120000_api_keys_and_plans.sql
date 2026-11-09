-- Public API access: plans with a monthly request allowance, per-account API keys and metered usage.
--
-- Keys are generated here (pgcrypto), returned once in full and stored only as a SHA-256 hash, so neither the
-- database nor its backups hold a usable key. Every table is closed to direct access (RLS on, no policies);
-- accounts manage their keys through the *_my_* functions (auth.uid()), and the API meters calls through
-- api_key_consume, which needs the server secret.

create table if not exists public.api_plans (
  plan text primary key,
  label text not null,
  monthly_requests integer not null check (monthly_requests >= 0),
  max_keys integer not null default 5 check (max_keys between 1 and 50),
  sort integer not null default 0
);

insert into public.api_plans (plan, label, monthly_requests, max_keys, sort) values
  ('free', 'Free', 30, 2, 0),
  ('pro', 'Pro', 3000, 5, 1),
  ('team', 'Team', 15000, 10, 2),
  ('institutional', 'Institutional', 100000, 25, 3)
on conflict (plan) do nothing;

-- An account without a row here is on the free plan. Billing (or the owner, through admin_set_plan) writes it.
create table if not exists public.account_plans (
  user_id uuid primary key references auth.users (id) on delete cascade,
  plan text not null references public.api_plans (plan),
  source text not null default 'manual',
  updated_at timestamptz not null default now()
);

create table if not exists public.api_keys (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null check (char_length(name) between 1 and 60),
  prefix text not null,
  key_hash text not null unique,
  created_at timestamptz not null default now(),
  last_used_at timestamptz,
  revoked_at timestamptz
);
create index if not exists api_keys_user_idx on public.api_keys (user_id);

-- Usage is counted per account (not per key), so creating more keys never adds allowance.
create table if not exists public.api_usage (
  user_id uuid not null references auth.users (id) on delete cascade,
  period date not null,
  requests integer not null default 0,
  primary key (user_id, period)
);

alter table public.api_plans enable row level security;
alter table public.account_plans enable row level security;
alter table public.api_keys enable row level security;
alter table public.api_usage enable row level security;
revoke all on public.api_plans, public.account_plans, public.api_keys, public.api_usage from anon, authenticated;

create or replace function private.plan_of(p_user uuid)
returns public.api_plans
language sql stable security definer set search_path to ''
as $$
  select pl.* from public.api_plans pl
   where pl.plan = coalesce((select ap.plan from public.account_plans ap where ap.user_id = p_user), 'free');
$$;

create or replace function private.current_period()
returns date language sql stable set search_path to ''
as $$ select date_trunc('month', now() at time zone 'utc')::date; $$;

-- Accounts with two-factor on must have completed it in this session before touching keys.
create or replace function private.require_full_session()
returns uuid
language plpgsql stable security definer set search_path to ''
as $$
declare v_uid uuid := auth.uid();
begin
  if v_uid is null then raise exception 'not_authenticated' using errcode = '28000'; end if;
  if exists (select 1 from auth.mfa_factors f where f.user_id = v_uid and f.status = 'verified')
     and coalesce(auth.jwt() ->> 'aal', 'aal1') <> 'aal2' then
    raise exception 'second_factor_required' using errcode = '28000';
  end if;
  return v_uid;
end; $$;

create or replace function public.my_api_access()
returns jsonb
language plpgsql stable security definer set search_path to ''
as $$
declare
  v_uid uuid := private.require_full_session();
  v_plan public.api_plans := private.plan_of(v_uid);
  v_period date := private.current_period();
  v_used integer := coalesce((select u.requests from public.api_usage u where u.user_id = v_uid and u.period = v_period), 0);
begin
  return jsonb_build_object(
    'plan', jsonb_build_object('id', v_plan.plan, 'label', v_plan.label, 'monthly_requests', v_plan.monthly_requests,
                               'max_keys', v_plan.max_keys),
    'usage', jsonb_build_object('period', v_period, 'used', v_used,
                                'remaining', greatest(v_plan.monthly_requests - v_used, 0),
                                'resets_at', (v_period + interval '1 month')),
    'keys', coalesce((select jsonb_agg(jsonb_build_object('id', k.id, 'name', k.name, 'prefix', k.prefix,
                                                           'created_at', k.created_at, 'last_used_at', k.last_used_at)
                                       order by k.created_at desc)
                        from public.api_keys k where k.user_id = v_uid and k.revoked_at is null), '[]'::jsonb),
    'plans', (select jsonb_agg(jsonb_build_object('id', p.plan, 'label', p.label, 'monthly_requests', p.monthly_requests)
                               order by p.sort) from public.api_plans p));
end; $$;

create or replace function public.create_my_api_key(p_name text)
returns jsonb
language plpgsql volatile security definer set search_path to ''
as $$
declare
  v_uid uuid := private.require_full_session();
  v_plan public.api_plans := private.plan_of(v_uid);
  v_name text := btrim(coalesce(p_name, ''));
  v_key text;
  v_id uuid;
begin
  if char_length(v_name) not between 1 and 60 then raise exception 'invalid_name' using errcode = '22023'; end if;
  -- Serialise key creation per account so two concurrent requests cannot both pass the limit.
  perform pg_advisory_xact_lock(hashtextextended('api_keys:' || v_uid::text, 0));
  if (select count(*) from public.api_keys k where k.user_id = v_uid and k.revoked_at is null) >= v_plan.max_keys then
    raise exception 'key_limit' using errcode = '23514';
  end if;
  v_key := 'di_live_' || encode(extensions.gen_random_bytes(24), 'hex');
  insert into public.api_keys (user_id, name, prefix, key_hash)
  values (v_uid, v_name, left(v_key, 16), encode(extensions.digest(v_key, 'sha256'), 'hex'))
  returning id into v_id;
  return jsonb_build_object('id', v_id, 'name', v_name, 'prefix', left(v_key, 16), 'key', v_key);
end; $$;

create or replace function public.revoke_my_api_key(p_id uuid)
returns boolean
language plpgsql volatile security definer set search_path to ''
as $$
declare v_uid uuid := private.require_full_session();
begin
  update public.api_keys set revoked_at = now()
   where id = p_id and user_id = v_uid and revoked_at is null;
  return found;
end; $$;

-- Called by the API for every metered request. Counts the call only when it fits the allowance, in one
-- statement, so concurrent requests can never push an account past its limit.
create or replace function public.api_key_consume(secret text, p_hash text, p_count boolean default true)
returns jsonb
language plpgsql volatile security definer set search_path to ''
as $$
declare
  v_key public.api_keys;
  v_plan public.api_plans;
  v_period date := private.current_period();
  v_used integer;
begin
  perform private.check_secret(secret);
  select * into v_key from public.api_keys k where k.key_hash = p_hash and k.revoked_at is null;
  if not found then return jsonb_build_object('ok', false, 'reason', 'invalid_key'); end if;
  v_plan := private.plan_of(v_key.user_id);
  if p_count and v_plan.monthly_requests = 0 then
    return jsonb_build_object('ok', false, 'reason', 'quota_exceeded', 'plan', v_plan.plan, 'limit', 0, 'used', 0,
                              'remaining', 0, 'resets_at', (v_period + interval '1 month'));
  end if;
  if p_count then
    -- A new month inserts 1; an existing row increments only while under the allowance (no row back otherwise).
    insert into public.api_usage as u (user_id, period, requests) values (v_key.user_id, v_period, 1)
    on conflict (user_id, period) do update set requests = u.requests + 1
     where u.requests < v_plan.monthly_requests
    returning u.requests into v_used;
    if v_used is null then
      v_used := coalesce((select u.requests from public.api_usage u where u.user_id = v_key.user_id and u.period = v_period), 0);
      return jsonb_build_object('ok', false, 'reason', 'quota_exceeded', 'plan', v_plan.plan,
                                'limit', v_plan.monthly_requests, 'used', v_used, 'remaining', 0,
                                'resets_at', (v_period + interval '1 month'));
    end if;
    update public.api_keys set last_used_at = now() where id = v_key.id;
  else
    v_used := coalesce((select u.requests from public.api_usage u where u.user_id = v_key.user_id and u.period = v_period), 0);
  end if;
  return jsonb_build_object('ok', true, 'plan', v_plan.plan, 'limit', v_plan.monthly_requests, 'used', v_used,
                            'remaining', greatest(v_plan.monthly_requests - v_used, 0),
                            'resets_at', (v_period + interval '1 month'), 'key_id', v_key.id);
end; $$;

-- The owner moves an account between plans until billing does it automatically.
create or replace function public.admin_set_plan(secret text, p_email text, p_plan text)
returns jsonb
language plpgsql volatile security definer set search_path to ''
as $$
declare v_uid uuid;
begin
  perform private.check_secret(secret);
  if not exists (select 1 from public.api_plans where plan = p_plan) then
    raise exception 'unknown_plan' using errcode = '22023';
  end if;
  select id into v_uid from auth.users where lower(email) = lower(btrim(p_email)) and deleted_at is null;
  if v_uid is null then raise exception 'unknown_account' using errcode = '22023'; end if;
  if p_plan = 'free' then
    delete from public.account_plans where user_id = v_uid;
  else
    insert into public.account_plans (user_id, plan, source) values (v_uid, p_plan, 'manual')
    on conflict (user_id) do update set plan = excluded.plan, source = 'manual', updated_at = now();
  end if;
  return jsonb_build_object('email', lower(btrim(p_email)), 'plan', p_plan);
end; $$;

revoke all on function public.my_api_access(), public.create_my_api_key(text), public.revoke_my_api_key(uuid)
  from public, anon;
grant execute on function public.my_api_access(), public.create_my_api_key(text), public.revoke_my_api_key(uuid)
  to authenticated;
revoke all on function public.api_key_consume(text, text, boolean), public.admin_set_plan(text, text, text)
  from public, authenticated;
grant execute on function public.api_key_consume(text, text, boolean), public.admin_set_plan(text, text, text) to anon;
revoke all on function private.plan_of(uuid), private.current_period(), private.require_full_session() from public;
