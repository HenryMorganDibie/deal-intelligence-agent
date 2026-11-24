-- Account grants: the owner can give one account more (or less) than its plan includes, for a pilot, a partner or
-- a favour, without inventing a new plan.
--
-- Each limit left empty follows the plan. A grant can end on a date, after which the account is back on its plan's
-- limits without anyone remembering to undo it. Every limit in the product reads private.plan_of, so laying the
-- grant over the plan there makes API requests and keys, briefs and research runs, alerts (email, Slack, Teams and
-- webhooks) and CSV export all follow it. Election alerts read election_alerts_max from plan_limits.

create table if not exists public.account_grants (
  user_id uuid primary key references auth.users (id) on delete cascade,
  monthly_requests integer check (monthly_requests between 0 and 10000000),
  ai_monthly integer check (ai_monthly between 0 and 100000),
  alerts_max integer check (alerts_max between 0 and 10000),
  election_alerts_max integer check (election_alerts_max between 0 and 1000),
  max_keys integer check (max_keys between 0 and 100),
  exports boolean,
  expires_at timestamptz,
  note text check (note is null or length(note) <= 300),
  updated_at timestamptz not null default now()
);
alter table public.account_grants enable row level security;
revoke all on table public.account_grants from public, anon, authenticated;

create or replace function private.active_grant(p_user uuid)
returns public.account_grants
language sql
stable
security definer
set search_path to ''
as $$
  select g.* from public.account_grants g
   where g.user_id = p_user and (g.expires_at is null or g.expires_at > now());
$$;

create or replace function private.plan_of(p_user uuid)
returns public.api_plans
language plpgsql
stable
security definer
set search_path to ''
as $$
declare
  v public.api_plans;
  g public.account_grants;
begin
  select pl.* into v from public.api_plans pl
   where pl.plan = coalesce((select ap.plan from public.account_plans ap where ap.user_id = p_user), 'free');
  g := private.active_grant(p_user);
  if g.user_id is not null then
    v.monthly_requests := coalesce(g.monthly_requests, v.monthly_requests);
    v.ai_monthly := coalesce(g.ai_monthly, v.ai_monthly);
    v.alerts_max := coalesce(g.alerts_max, v.alerts_max);
    v.max_keys := coalesce(g.max_keys, v.max_keys);
    v.exports := coalesce(g.exports, v.exports);
  end if;
  return v;
end; $$;

create or replace function private.limits_of(p_user uuid)
returns jsonb
language sql
stable
security definer
set search_path to ''
as $$
  select jsonb_build_object(
    'plan', p.plan, 'label', p.label, 'exports', p.exports,
    'ai_monthly', p.ai_monthly,
    'ai_used', coalesce((select f.used from public.feature_usage f
                          where f.user_id = p_user and f.period = private.current_period() and f.feature = 'ai'), 0),
    'alerts_max', p.alerts_max,
    'alerts_used', (select count(*) from public.watchlists w where w.owner_user = p_user and w.deleted_at is null),
    'election_alerts_max', (private.active_grant(p_user)).election_alerts_max,
    'granted_until', (private.active_grant(p_user)).expires_at,
    'resets_at', (private.current_period() + interval '1 month'))
  from private.plan_of(p_user) p;
$$;

-- For the owner's page: every grant, active or ended, with the account's email. Server secret only.
create or replace function public.admin_grants(secret text)
returns jsonb
language plpgsql
stable
security definer
set search_path to ''
as $$
begin
  perform private.check_secret(secret);
  return coalesce((
    select jsonb_agg(jsonb_build_object(
             'email', u.email, 'monthly_requests', g.monthly_requests, 'ai_monthly', g.ai_monthly,
             'alerts_max', g.alerts_max, 'election_alerts_max', g.election_alerts_max, 'max_keys', g.max_keys,
             'exports', g.exports, 'expires_at', g.expires_at, 'note', g.note, 'updated_at', g.updated_at,
             'active', g.expires_at is null or g.expires_at > now())
           order by g.updated_at desc)
      from public.account_grants g join auth.users u on u.id = g.user_id
  ), '[]'::jsonb);
end; $$;

-- Set or clear one account's grant. p_grant holds the limits to set; a key missing or null follows the plan.
create or replace function public.admin_set_grant(secret text, p_email text, p_grant jsonb, p_expires_at timestamptz,
                                                  p_note text, p_clear boolean default false)
returns jsonb
language plpgsql
security definer
set search_path to ''
as $$
declare
  v_user uuid;
begin
  perform private.check_secret(secret);
  select u.id into v_user from auth.users u where lower(u.email) = lower(trim(p_email)) and u.deleted_at is null;
  if v_user is null then raise exception 'unknown_account' using errcode = 'P0002'; end if;
  if p_clear then
    delete from public.account_grants where user_id = v_user;
    return jsonb_build_object('email', lower(trim(p_email)), 'cleared', true);
  end if;
  insert into public.account_grants as g (user_id, monthly_requests, ai_monthly, alerts_max, election_alerts_max,
                                          max_keys, exports, expires_at, note, updated_at)
  values (v_user, (p_grant->>'monthly_requests')::integer, (p_grant->>'ai_monthly')::integer,
          (p_grant->>'alerts_max')::integer, (p_grant->>'election_alerts_max')::integer,
          (p_grant->>'max_keys')::integer, (p_grant->>'exports')::boolean, p_expires_at,
          nullif(left(trim(coalesce(p_note, '')), 300), ''), now())
  on conflict (user_id) do update
     set monthly_requests = excluded.monthly_requests, ai_monthly = excluded.ai_monthly,
         alerts_max = excluded.alerts_max, election_alerts_max = excluded.election_alerts_max,
         max_keys = excluded.max_keys, exports = excluded.exports, expires_at = excluded.expires_at,
         note = excluded.note, updated_at = now();
  return jsonb_build_object('email', lower(trim(p_email)), 'cleared', false);
end; $$;
