-- Account grants: the owner can give one account more (or less) than its plan includes, for a pilot, a partner or
-- a favour, without inventing a new plan.
--
-- Each limit left empty follows the plan. A grant can end on a date, after which the account is back on its plan's
-- limits without anyone remembering to undo it. Every limit in the product reads private.plan_of, so laying the
-- grant over the plan there makes API requests and keys, briefs and research runs, alerts (email, Slack, Teams and
-- webhooks) and CSV export all follow it. Election alerts read election_alerts_max from plan_limits.
--
-- Institutional contracts differ by firm, so an Institutional account can also be limited to the API areas its
-- contract covers (api_scopes; empty means every area). Pro and Team always include every area of their plan.

create table if not exists public.account_grants (
  user_id uuid primary key references auth.users (id) on delete cascade,
  monthly_requests integer check (monthly_requests between 0 and 10000000),
  ai_monthly integer check (ai_monthly between 0 and 100000),
  alerts_max integer check (alerts_max between 0 and 10000),
  election_alerts_max integer check (election_alerts_max between 0 and 1000),
  max_keys integer check (max_keys between 0 and 100),
  exports boolean,
  api_scopes text[] check (api_scopes is null or api_scopes <@ array['deals', 'events', 'investors', 'countries',
    'markets', 'elections', 'election_results', 'election_alerts']::text[]),
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
             'exports', g.exports, 'api_scopes', to_jsonb(g.api_scopes), 'expires_at', g.expires_at, 'note', g.note, 'updated_at', g.updated_at,
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
                                          max_keys, exports, api_scopes, expires_at, note, updated_at)
  values (v_user, (p_grant->>'monthly_requests')::integer, (p_grant->>'ai_monthly')::integer,
          (p_grant->>'alerts_max')::integer, (p_grant->>'election_alerts_max')::integer,
          (p_grant->>'max_keys')::integer, (p_grant->>'exports')::boolean,
          case when jsonb_typeof(p_grant->'api_scopes') = 'array'
               then array(select jsonb_array_elements_text(p_grant->'api_scopes')) end,
          p_expires_at,
          nullif(left(trim(coalesce(p_note, '')), 300), ''), now())
  on conflict (user_id) do update
     set monthly_requests = excluded.monthly_requests, ai_monthly = excluded.ai_monthly,
         alerts_max = excluded.alerts_max, election_alerts_max = excluded.election_alerts_max,
         max_keys = excluded.max_keys, exports = excluded.exports, api_scopes = excluded.api_scopes,
         expires_at = excluded.expires_at,
         note = excluded.note, updated_at = now();
  return jsonb_build_object('email', lower(trim(p_email)), 'cleared', false);
end; $$;

-- The API's metering, now also told which area a request is for (p_scope): an Institutional account whose contract
-- does not cover that area is refused before the request is counted. Everything else is unchanged.
drop function if exists public.api_key_consume(text, text, boolean);
create or replace function public.api_key_consume(secret text, p_hash text, p_count boolean default true,
                                                  p_scope text default null)
returns jsonb
language plpgsql
security definer
set search_path to ''
as $$
declare
  v_key public.api_keys;
  v_plan public.api_plans;
  v_scopes text[];
  v_period date := private.current_period();
  v_used integer;
begin
  perform private.check_secret(secret);
  select * into v_key from public.api_keys k where k.key_hash = p_hash and k.revoked_at is null;
  if not found or private.is_suspended(v_key.user_id) then return jsonb_build_object('ok', false, 'reason', 'invalid_key'); end if;
  v_plan := private.plan_of(v_key.user_id);
  if v_plan.plan = 'institutional' and p_scope is not null then
    v_scopes := (private.active_grant(v_key.user_id)).api_scopes;
    if v_scopes is not null and not (p_scope = any(v_scopes)) then
      return jsonb_build_object('ok', false, 'reason', 'not_in_contract', 'plan', v_plan.plan, 'scope', p_scope,
                                'scopes', to_jsonb(v_scopes));
    end if;
  end if;
  if p_count and v_plan.monthly_requests = 0 then
    return jsonb_build_object('ok', false, 'reason', 'quota_exceeded', 'plan', v_plan.plan, 'limit', 0, 'used', 0,
                              'remaining', 0, 'resets_at', (v_period + interval '1 month'));
  end if;
  if p_count then
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
revoke all on function public.api_key_consume(text, text, boolean, text) from public, authenticated;
grant execute on function public.api_key_consume(text, text, boolean, text) to anon, service_role;

