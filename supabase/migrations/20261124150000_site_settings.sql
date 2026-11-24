-- Owner controls that used to need a code change: site switches (an announcement banner, new sign-ups, AI briefs),
-- each plan's prices and limits, and which currencies checkout accepts.
--
-- Prices are safe to change here: billing creates a Paystack plan for each price the first time it is sold, and
-- people already subscribed keep the price they signed up at.

create table if not exists public.site_settings (
  key text primary key check (key in ('announcement', 'signups', 'ai')),
  value jsonb not null,
  updated_at timestamptz not null default now()
);
alter table public.site_settings enable row level security;
revoke all on table public.site_settings from public, anon, authenticated;

-- What the site and API read (no secret: none of it is private). Missing keys mean the default: no banner,
-- sign-ups open, AI briefs on.
create or replace function public.site_settings_public()
returns jsonb
language sql
stable
security definer
set search_path to ''
as $$
  select jsonb_build_object(
    'announcement', coalesce((select s.value from public.site_settings s where s.key = 'announcement'), '{"on": false}'::jsonb),
    'signups', coalesce((select s.value from public.site_settings s where s.key = 'signups'), '{"open": true}'::jsonb),
    'ai', coalesce((select s.value from public.site_settings s where s.key = 'ai'), '{"on": true}'::jsonb));
$$;
revoke all on function public.site_settings_public() from public;
grant execute on function public.site_settings_public() to anon, authenticated, service_role;

create or replace function public.admin_set_site_setting(secret text, p_key text, p_value jsonb)
returns jsonb
language plpgsql
security definer
set search_path to ''
as $$
begin
  perform private.check_secret(secret);
  if p_key not in ('announcement', 'signups', 'ai') or jsonb_typeof(p_value) <> 'object' then
    raise exception 'invalid_setting' using errcode = '22023';
  end if;
  insert into public.site_settings (key, value, updated_at) values (p_key, p_value, now())
  on conflict (key) do update set value = excluded.value, updated_at = now();
  return public.site_settings_public();
end; $$;

-- Everything the owner's Settings page shows: the switches, every plan with its prices and limits, the currencies.
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
    'currencies', private.billing_currencies(),
    'plans', (select jsonb_agg(jsonb_build_object(
                'plan', p.plan, 'label', p.label, 'price_month_ngn', p.price_month_ngn, 'price_year_ngn', p.price_year_ngn,
                'price_month_usd', p.price_month_usd, 'price_year_usd', p.price_year_usd,
                'monthly_requests', p.monthly_requests, 'ai_monthly', p.ai_monthly, 'alerts_max', p.alerts_max,
                'max_keys', p.max_keys, 'seats', p.seats, 'exports', p.exports, 'self_serve', p.self_serve)
              order by p.sort) from public.api_plans p));
end; $$;

-- Change one plan's prices or limits. Only the keys given change; prices are whole naira or dollars.
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
    exports = coalesce((p_fields->>'exports')::boolean, exports)
  where plan = p_plan;
  return public.admin_settings(secret);
end; $$;

-- Which currencies checkout offers: naira always, dollars when switched on.
create or replace function public.admin_set_currencies(secret text, p_usd boolean)
returns jsonb
language plpgsql
security definer
set search_path to ''
as $$
begin
  perform private.check_secret(secret);
  insert into public.billing_settings (key, value)
  values ('currencies', case when p_usd then '["NGN", "USD"]'::jsonb else '["NGN"]'::jsonb end)
  on conflict (key) do update set value = excluded.value;
  return private.billing_currencies();
end; $$;
