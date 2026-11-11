-- Billing in naira and US dollars.
--
-- Each plan has a price in both currencies. Paystack bills a fixed amount in one currency per plan code, so plan
-- codes are kept per (plan, interval, currency, amount). Which currencies are offered is a setting
-- (billing_settings.currencies): dollars are offered only once the Paystack account accepts USD, so a customer is
-- never sent to a checkout that would fail.

alter table public.api_plans add column if not exists price_month_usd integer check (price_month_usd >= 0);
alter table public.api_plans add column if not exists price_year_usd integer check (price_year_usd >= 0);
update public.api_plans set price_month_usd = 0, price_year_usd = 0 where plan = 'free';
update public.api_plans set price_month_usd = 7, price_year_usd = 70 where plan = 'pro';
update public.api_plans set price_month_usd = 24, price_year_usd = 240 where plan = 'team';

alter table public.billing_plan_codes add column if not exists currency text not null default 'NGN'
  check (currency in ('NGN', 'USD'));
alter table public.billing_plan_codes rename column amount_kobo to amount_minor;
alter table public.billing_plan_codes drop constraint if exists billing_plan_codes_pkey;
alter table public.billing_plan_codes add primary key (plan, interval, currency, amount_minor);

alter table public.billing_subscriptions add column if not exists currency text check (currency in ('NGN', 'USD'));

create table if not exists public.billing_settings (
  key text primary key,
  value jsonb not null
);
alter table public.billing_settings enable row level security;
revoke all on public.billing_settings from anon, authenticated;
insert into public.billing_settings (key, value) values ('currencies', '["NGN"]') on conflict (key) do nothing;

create or replace function private.billing_currencies()
returns jsonb language sql stable security definer set search_path to ''
as $$ select coalesce((select value from public.billing_settings where key = 'currencies'), '["NGN"]'::jsonb); $$;

create or replace function public.billing_catalog()
returns jsonb
language sql stable security definer set search_path to ''
as $$
  select jsonb_agg(jsonb_build_object('id', p.plan, 'label', p.label, 'monthly_requests', p.monthly_requests,
                                      'seats', p.seats, 'self_serve', p.self_serve,
                                      'price_month_ngn', p.price_month_ngn, 'price_year_ngn', p.price_year_ngn,
                                      'price_month_usd', p.price_month_usd, 'price_year_usd', p.price_year_usd,
                                      'currencies', private.billing_currencies(),
                                      'ai_monthly', p.ai_monthly, 'alerts_max', p.alerts_max, 'exports', p.exports)
                   order by p.sort)
    from public.api_plans p;
$$;

drop function if exists public.billing_price(text, text, text);
create or replace function public.billing_price(secret text, p_plan text, p_interval text, p_currency text default 'NGN')
returns jsonb
language plpgsql stable security definer set search_path to ''
as $$
declare v_plan public.api_plans; v_amount bigint;
begin
  perform private.check_secret(secret);
  if not private.billing_currencies() ? p_currency then
    raise exception 'currency_unavailable' using errcode = '22023';
  end if;
  select * into v_plan from public.api_plans where plan = p_plan and self_serve;
  if v_plan.plan is null then raise exception 'unknown_plan' using errcode = '22023'; end if;
  v_amount := (case
    when p_currency = 'NGN' and p_interval = 'monthly' then v_plan.price_month_ngn
    when p_currency = 'NGN' and p_interval = 'annually' then v_plan.price_year_ngn
    when p_currency = 'USD' and p_interval = 'monthly' then v_plan.price_month_usd
    when p_currency = 'USD' and p_interval = 'annually' then v_plan.price_year_usd end)::bigint * 100;
  if v_amount is null or v_amount <= 0 then raise exception 'no_price' using errcode = '22023'; end if;
  return jsonb_build_object('plan', v_plan.plan, 'label', v_plan.label, 'interval', p_interval, 'currency', p_currency,
                            'amount_minor', v_amount,
                            'plan_code', (select c.plan_code from public.billing_plan_codes c
                                           where c.plan = p_plan and c.interval = p_interval and c.currency = p_currency
                                             and c.amount_minor = v_amount));
end; $$;

drop function if exists public.billing_save_plan_code(text, text, text, bigint, text);
create or replace function public.billing_save_plan_code(secret text, p_plan text, p_interval text, p_currency text,
                                                         p_amount_minor bigint, p_code text)
returns void
language plpgsql volatile security definer set search_path to ''
as $$
begin
  perform private.check_secret(secret);
  insert into public.billing_plan_codes (plan, interval, currency, amount_minor, plan_code)
  values (p_plan, p_interval, p_currency, p_amount_minor, p_code)
  on conflict (plan, interval, currency, amount_minor) do nothing;
end; $$;

create or replace function public.billing_plan_for_code(secret text, p_code text)
returns jsonb
language plpgsql stable security definer set search_path to ''
as $$
begin
  perform private.check_secret(secret);
  return (select jsonb_build_object('plan', c.plan, 'interval', c.interval, 'currency', c.currency)
            from public.billing_plan_codes c where c.plan_code = p_code);
end; $$;

drop function if exists public.billing_apply(text, text, uuid, text, text, text, text, text, text, timestamptz);
create or replace function public.billing_apply(
  secret text, p_event_key text, p_user uuid, p_plan text, p_status text, p_interval text default null,
  p_customer text default null, p_subscription text default null, p_email_token text default null,
  p_next timestamptz default null, p_currency text default null)
returns jsonb
language plpgsql volatile security definer set search_path to ''
as $$
begin
  perform private.check_secret(secret);
  if p_status not in ('active', 'non_renewing', 'attention', 'cancelled') then
    raise exception 'bad_status' using errcode = '22023';
  end if;
  insert into public.billing_events (event_key) values (p_event_key) on conflict do nothing;
  if not found then return jsonb_build_object('applied', false); end if;

  insert into public.billing_subscriptions as s (user_id, plan, interval, status, customer_code, subscription_code,
                                                 email_token, next_payment_at, currency)
  values (p_user, p_plan, p_interval, p_status, p_customer, p_subscription, p_email_token, p_next, p_currency)
  on conflict (user_id) do update set
    plan = excluded.plan, status = excluded.status,
    interval = coalesce(excluded.interval, s.interval),
    customer_code = coalesce(excluded.customer_code, s.customer_code),
    subscription_code = coalesce(excluded.subscription_code, s.subscription_code),
    email_token = coalesce(excluded.email_token, s.email_token),
    next_payment_at = coalesce(excluded.next_payment_at, s.next_payment_at),
    currency = coalesce(excluded.currency, s.currency),
    updated_at = now();

  if p_status in ('active', 'non_renewing', 'attention') then
    insert into public.account_plans (user_id, plan, source) values (p_user, p_plan, 'paystack')
    on conflict (user_id) do update set plan = excluded.plan, source = 'paystack', updated_at = now()
      where public.account_plans.source <> 'manual';
  else
    delete from public.account_plans where user_id = p_user and source = 'paystack';
  end if;
  return jsonb_build_object('applied', true, 'plan', (private.plan_of(p_user)).plan);
end; $$;

create or replace function public.my_billing()
returns jsonb
language plpgsql stable security definer set search_path to ''
as $$
declare
  v_uid uuid := auth.uid();
  v_sub public.billing_subscriptions;
begin
  if v_uid is null then raise exception 'not_authenticated' using errcode = '28000'; end if;
  select * into v_sub from public.billing_subscriptions where user_id = v_uid;
  return jsonb_build_object(
    'plan', (private.plan_of(v_uid)).plan,
    'source', (select ap.source from public.account_plans ap where ap.user_id = v_uid),
    'subscription', case when v_sub.user_id is null then null else jsonb_build_object(
      'plan', v_sub.plan, 'interval', v_sub.interval, 'status', v_sub.status, 'currency', v_sub.currency,
      'next_payment_at', v_sub.next_payment_at, 'manageable', v_sub.subscription_code is not null) end,
    'catalog', public.billing_catalog());
end; $$;

revoke all on function private.billing_currencies() from public;
revoke all on function public.billing_price(text, text, text, text),
  public.billing_save_plan_code(text, text, text, text, bigint, text),
  public.billing_apply(text, text, uuid, text, text, text, text, text, text, timestamptz, text) from public, authenticated;
grant execute on function public.billing_price(text, text, text, text),
  public.billing_save_plan_code(text, text, text, text, bigint, text),
  public.billing_apply(text, text, uuid, text, text, text, text, text, text, timestamptz, text) to anon;
