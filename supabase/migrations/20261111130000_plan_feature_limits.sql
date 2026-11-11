-- What each plan includes beyond API requests: AI runs a month (briefs, research and market briefs together),
-- alerts, and bulk CSV export. Limits live on api_plans, so they change without a deploy.
--
-- Alerts created by a signed-in account record it (watchlists.owner_user); older anonymous watchlists keep working.
-- AI runs are counted per account per month in one atomic statement, so concurrent requests cannot overrun a limit.

alter table public.api_plans add column if not exists ai_monthly integer not null default 3 check (ai_monthly >= 0);
alter table public.api_plans add column if not exists alerts_max integer not null default 3 check (alerts_max >= 0);
alter table public.api_plans add column if not exists exports boolean not null default false;

update public.api_plans set ai_monthly = 3, alerts_max = 3, exports = false where plan = 'free';
update public.api_plans set ai_monthly = 100, alerts_max = 100, exports = true where plan = 'pro';
update public.api_plans set ai_monthly = 500, alerts_max = 500, exports = true where plan = 'team';
update public.api_plans set ai_monthly = 2000, alerts_max = 2000, exports = true where plan = 'institutional';

alter table public.watchlists add column if not exists owner_user uuid references auth.users (id) on delete set null;
create index if not exists watchlists_owner_idx on public.watchlists (owner_user) where deleted_at is null;

create table if not exists public.feature_usage (
  user_id uuid not null references auth.users (id) on delete cascade,
  period date not null,
  feature text not null check (feature in ('ai')),
  used integer not null default 0,
  primary key (user_id, period, feature)
);
alter table public.feature_usage enable row level security;
revoke all on public.feature_usage from anon, authenticated;

create or replace function private.limits_of(p_user uuid)
returns jsonb
language sql stable security definer set search_path to ''
as $$
  select jsonb_build_object(
    'plan', p.plan, 'label', p.label, 'exports', p.exports,
    'ai_monthly', p.ai_monthly,
    'ai_used', coalesce((select f.used from public.feature_usage f
                          where f.user_id = p_user and f.period = private.current_period() and f.feature = 'ai'), 0),
    'alerts_max', p.alerts_max,
    'alerts_used', (select count(*) from public.watchlists w where w.owner_user = p_user and w.deleted_at is null),
    'resets_at', (private.current_period() + interval '1 month'))
  from private.plan_of(p_user) p;
$$;

-- API: an account's limits and use.
create or replace function public.plan_limits(secret text, p_user uuid)
returns jsonb
language plpgsql stable security definer set search_path to ''
as $$
begin
  perform private.check_secret(secret);
  return private.limits_of(p_user);
end; $$;

-- API: count one AI run if the account has one left this month. {"ok": false, ...} when the limit is reached.
create or replace function public.consume_feature(secret text, p_user uuid, p_feature text)
returns jsonb
language plpgsql volatile security definer set search_path to ''
as $$
declare v_limit integer; v_used integer; v_period date := private.current_period();
begin
  perform private.check_secret(secret);
  if p_feature <> 'ai' then raise exception 'unknown_feature' using errcode = '22023'; end if;
  v_limit := (private.plan_of(p_user)).ai_monthly;
  insert into public.feature_usage as f (user_id, period, feature, used) values (p_user, v_period, p_feature, 1)
  on conflict (user_id, period, feature) do update set used = f.used + 1 where f.used < v_limit
  returning used into v_used;
  if v_used is null or v_used > v_limit then
    return jsonb_build_object('ok', false, 'limit', v_limit, 'resets_at', (v_period + interval '1 month'));
  end if;
  return jsonb_build_object('ok', true, 'limit', v_limit, 'used', v_used);
end; $$;

-- API: record the account that created an alert.
create or replace function public.set_watchlist_owner(secret text, p_id uuid, p_user uuid)
returns void
language plpgsql volatile security definer set search_path to ''
as $$
begin
  perform private.check_secret(secret);
  update public.watchlists set owner_user = p_user where id = p_id and owner_user is null;
end; $$;

-- The signed-in account's limits and use, for the app.
create or replace function public.my_limits()
returns jsonb
language plpgsql stable security definer set search_path to ''
as $$
declare v_uid uuid := auth.uid();
begin
  if v_uid is null then raise exception 'not_authenticated' using errcode = '28000'; end if;
  return private.limits_of(v_uid);
end; $$;

-- The catalog shows the limits too.
create or replace function public.billing_catalog()
returns jsonb
language sql stable security definer set search_path to ''
as $$
  select jsonb_agg(jsonb_build_object('id', p.plan, 'label', p.label, 'monthly_requests', p.monthly_requests,
                                      'seats', p.seats, 'self_serve', p.self_serve,
                                      'price_month_ngn', p.price_month_ngn, 'price_year_ngn', p.price_year_ngn,
                                      'ai_monthly', p.ai_monthly, 'alerts_max', p.alerts_max, 'exports', p.exports)
                   order by p.sort)
    from public.api_plans p;
$$;

revoke all on function private.limits_of(uuid) from public;
revoke all on function public.plan_limits(text, uuid), public.consume_feature(text, uuid, text),
  public.set_watchlist_owner(text, uuid, uuid) from public, authenticated;
grant execute on function public.plan_limits(text, uuid), public.consume_feature(text, uuid, text),
  public.set_watchlist_owner(text, uuid, uuid) to anon;
revoke all on function public.my_limits() from public, anon;
grant execute on function public.my_limits() to authenticated;
