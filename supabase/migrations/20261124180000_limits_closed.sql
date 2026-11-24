-- Three gaps in the owner's controls, closed:
--  1. Pausing sign-ups now stops every new account, Google included: a guard on auth.users refuses the insert.
--  2. Team seats are real: people in an organisation created by a Team or Institutional account share that plan,
--     up to its seats (the owner counts as one), and draw on one shared allowance of briefs and API requests.
--     Organisations still work for everyone (portfolio sharing); only sharing the plan is limited by seats.
--  3. News and private-capital sources can be switched off from admin (site setting "sources").

-- ── 1. Sign-up pause covers every way in ─────────────────────────────────────
create or replace function private.guard_signups()
returns trigger
language plpgsql
security definer
set search_path to ''
as $$
begin
  if coalesce((select (s.value->>'open')::boolean from public.site_settings s where s.key = 'signups'), true) = false then
    raise exception 'signups_paused' using errcode = 'P0001';
  end if;
  return new;
end; $$;
drop trigger if exists guard_signups on auth.users;
create trigger guard_signups before insert on auth.users for each row execute function private.guard_signups();

-- ── 3. Source switches (stored with the other site settings) ─────────────────
alter table public.site_settings drop constraint if exists site_settings_key_check;
alter table public.site_settings add constraint site_settings_key_check
  check (key in ('announcement', 'signups', 'ai', 'sources'));

create or replace function public.disabled_sources()
returns jsonb
language sql
stable
security definer
set search_path to ''
as $$
  select coalesce((select s.value->'off' from public.site_settings s where s.key = 'sources'), '[]'::jsonb);
$$;
revoke all on function public.disabled_sources() from public;
grant execute on function public.disabled_sources() to anon, authenticated, service_role;

create or replace function public.admin_set_site_setting(secret text, p_key text, p_value jsonb)
returns jsonb
language plpgsql
security definer
set search_path to ''
as $$
begin
  perform private.check_secret(secret);
  if p_key not in ('announcement', 'signups', 'ai', 'sources') or jsonb_typeof(p_value) <> 'object' then
    raise exception 'invalid_setting' using errcode = '22023';
  end if;
  insert into public.site_settings (key, value, updated_at) values (p_key, p_value, now())
  on conflict (key) do update set value = excluded.value, updated_at = now();
  return public.site_settings_public();
end; $$;

-- ── 2. Team seats ─────────────────────────────────────────────────────────────
-- Whose plan an account uses: its own, or that of the owner of an organisation it belongs to, when that plan has
-- more than one seat, is better than its own, and the account is among the first members to join (seats less the
-- owner). A suspended owner shares nothing.
create or replace function private.plan_holder(p_user uuid)
returns uuid
language sql
stable
security definer
set search_path to ''
as $$
  with own as (
    select coalesce((select pl.sort from public.account_plans ap join public.api_plans pl on pl.plan = ap.plan
                      where ap.user_id = p_user), 0) as sort
  ),
  owners as (
    select distinct o.created_by as owner, pl.seats, pl.sort
      from public.organization_memberships m
      join public.organizations o on o.id = m.organization_id and o.archived_at is null
      join public.account_plans ap on ap.user_id = o.created_by
      join public.api_plans pl on pl.plan = ap.plan
     where m.user_id = p_user and o.created_by <> p_user and pl.seats > 1
       and not private.is_suspended(o.created_by)
  ),
  seated as (
    select w.owner, w.sort
      from owners w
     where (select count(*) from (
              select m2.user_id, min(m2.joined_at) as first_joined
                from public.organization_memberships m2
                join public.organizations o2 on o2.id = m2.organization_id and o2.archived_at is null
               where o2.created_by = w.owner and m2.user_id <> w.owner
               group by m2.user_id) earlier
             where earlier.first_joined <= (select min(m3.joined_at) from public.organization_memberships m3
                                              join public.organizations o3 on o3.id = m3.organization_id
                                             where o3.created_by = w.owner and m3.user_id = p_user)
           ) <= w.seats - 1
  )
  select coalesce((select s.owner from seated s, own where s.sort > own.sort order by s.sort desc limit 1), p_user);
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
  v_holder uuid := private.plan_holder(p_user);
begin
  select pl.* into v from public.api_plans pl
   where pl.plan = coalesce((select ap.plan from public.account_plans ap where ap.user_id = v_holder), 'free');
  g := private.active_grant(v_holder);
  if g.user_id is not null then
    v.monthly_requests := coalesce(g.monthly_requests, v.monthly_requests);
    v.ai_monthly := coalesce(g.ai_monthly, v.ai_monthly);
    v.alerts_max := coalesce(g.alerts_max, v.alerts_max);
    v.max_keys := coalesce(g.max_keys, v.max_keys);
    v.exports := coalesce(g.exports, v.exports);
  end if;
  return v;
end; $$;

-- Briefs and research runs: one allowance for everyone sharing a plan.
create or replace function public.consume_feature(secret text, p_user uuid, p_feature text)
returns jsonb
language plpgsql
security definer
set search_path to ''
as $$
declare
  v_limit integer;
  v_used integer;
  v_period date := private.current_period();
  v_holder uuid := private.plan_holder(p_user);
begin
  perform private.check_secret(secret);
  if p_feature <> 'ai' then raise exception 'unknown_feature' using errcode = '22023'; end if;
  v_limit := (private.plan_of(p_user)).ai_monthly;
  insert into public.feature_usage as f (user_id, period, feature, used) values (v_holder, v_period, p_feature, 1)
  on conflict (user_id, period, feature) do update set used = f.used + 1 where f.used < v_limit
  returning used into v_used;
  if v_used is null or v_used > v_limit then
    return jsonb_build_object('ok', false, 'limit', v_limit, 'resets_at', (v_period + interval '1 month'));
  end if;
  return jsonb_build_object('ok', true, 'limit', v_limit, 'used', v_used);
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
                          where f.user_id = private.plan_holder(p_user) and f.period = private.current_period()
                            and f.feature = 'ai'), 0),
    'alerts_max', p.alerts_max,
    'alerts_used', (select count(*) from public.watchlists w where w.owner_user = p_user and w.deleted_at is null),
    'election_alerts_max', (private.active_grant(private.plan_holder(p_user))).election_alerts_max,
    'granted_until', (private.active_grant(private.plan_holder(p_user))).expires_at,
    'shared_from_owner', private.plan_holder(p_user) <> p_user,
    'resets_at', (private.current_period() + interval '1 month'))
  from private.plan_of(p_user) p;
$$;

create or replace function public.my_api_access()
returns jsonb
language plpgsql
stable
security definer
set search_path to ''
as $$
declare
  v_uid uuid := private.require_full_session();
  v_plan public.api_plans := private.plan_of(v_uid);
  v_period date := private.current_period();
  v_used integer := coalesce((select u.requests from public.api_usage u
                               where u.user_id = private.plan_holder(v_uid) and u.period = v_period), 0);
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

-- API requests: one allowance for everyone sharing a plan; the plan holder's contract decides the API areas.
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
  v_holder uuid;
  v_scopes text[];
  v_period date := private.current_period();
  v_used integer;
begin
  perform private.check_secret(secret);
  select * into v_key from public.api_keys k where k.key_hash = p_hash and k.revoked_at is null;
  if not found or private.is_suspended(v_key.user_id) then return jsonb_build_object('ok', false, 'reason', 'invalid_key'); end if;
  v_plan := private.plan_of(v_key.user_id);
  v_holder := private.plan_holder(v_key.user_id);
  if v_plan.plan = 'institutional' and p_scope is not null then
    v_scopes := (private.active_grant(v_holder)).api_scopes;
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
    insert into public.api_usage as u (user_id, period, requests) values (v_holder, v_period, 1)
    on conflict (user_id, period) do update set requests = u.requests + 1
     where u.requests < v_plan.monthly_requests
    returning u.requests into v_used;
    if v_used is null then
      v_used := coalesce((select u.requests from public.api_usage u where u.user_id = v_holder and u.period = v_period), 0);
      return jsonb_build_object('ok', false, 'reason', 'quota_exceeded', 'plan', v_plan.plan,
                                'limit', v_plan.monthly_requests, 'used', v_used, 'remaining', 0,
                                'resets_at', (v_period + interval '1 month'));
    end if;
    update public.api_keys set last_used_at = now() where id = v_key.id;
  else
    v_used := coalesce((select u.requests from public.api_usage u where u.user_id = v_holder and u.period = v_period), 0);
  end if;
  return jsonb_build_object('ok', true, 'plan', v_plan.plan, 'limit', v_plan.monthly_requests, 'used', v_used,
                            'remaining', greatest(v_plan.monthly_requests - v_used, 0),
                            'resets_at', (v_period + interval '1 month'), 'key_id', v_key.id);
end; $$;
revoke all on function public.api_key_consume(text, text, boolean, text) from public, authenticated;
grant execute on function public.api_key_consume(text, text, boolean, text) to anon, service_role;

-- Seats become editable with the other plan terms, and the settings page shows the switches for sources.
create or replace function public.admin_update_plan(secret text, p_plan text, p_fields jsonb)
returns jsonb
language plpgsql
security definer
set search_path to ''
as $$
begin
  perform private.check_secret(secret);
  if not exists (select 1 from public.api_plans where plan = p_plan) then
    raise exception 'unknown_plan' using errcode = 'P0002';
  end if;
  update public.api_plans set
    price_month_ngn = coalesce((p_fields->>'price_month_ngn')::integer, price_month_ngn),
    price_year_ngn = coalesce((p_fields->>'price_year_ngn')::integer, price_year_ngn),
    price_month_usd = coalesce((p_fields->>'price_month_usd')::integer, price_month_usd),
    price_year_usd = coalesce((p_fields->>'price_year_usd')::integer, price_year_usd),
    monthly_requests = coalesce((p_fields->>'monthly_requests')::integer, monthly_requests),
    ai_monthly = coalesce((p_fields->>'ai_monthly')::integer, ai_monthly),
    alerts_max = coalesce((p_fields->>'alerts_max')::integer, alerts_max),
    max_keys = coalesce((p_fields->>'max_keys')::integer, max_keys),
    seats = coalesce((p_fields->>'seats')::integer, seats),
    exports = coalesce((p_fields->>'exports')::boolean, exports)
  where plan = p_plan;
  return public.admin_settings(secret);
end; $$;

create or replace function public.admin_settings(secret text)
returns jsonb
language plpgsql
stable
security definer
set search_path to ''
as $$
begin
  perform private.check_secret(secret);
  return jsonb_build_object(
    'site', public.site_settings_public(),
    'sources_off', public.disabled_sources(),
    'currencies', private.billing_currencies(),
    'plans', (select jsonb_agg(jsonb_build_object(
                'plan', p.plan, 'label', p.label, 'price_month_ngn', p.price_month_ngn, 'price_year_ngn', p.price_year_ngn,
                'price_month_usd', p.price_month_usd, 'price_year_usd', p.price_year_usd,
                'monthly_requests', p.monthly_requests, 'ai_monthly', p.ai_monthly, 'alerts_max', p.alerts_max,
                'max_keys', p.max_keys, 'seats', p.seats, 'exports', p.exports, 'self_serve', p.self_serve)
              order by p.sort) from public.api_plans p));
end; $$;
