-- Paid plans through Paystack, in naira.
--
-- Prices live on api_plans (editable without a deploy). Paystack bills a fixed amount per plan code, so each
-- (plan, interval, amount) gets its own Paystack plan code: changing a price creates a new code for new
-- subscribers while existing subscribers keep the price they signed up at (the founding price).
--
-- The API (holding the server secret) is the only writer: it starts checkouts and applies Paystack's webhook
-- events, each recorded once in billing_events so a redelivered event is never applied twice. Accounts read their
-- own billing through my_billing(); prices are public through billing_catalog().

alter table public.api_plans add column if not exists price_month_ngn integer check (price_month_ngn >= 0);
alter table public.api_plans add column if not exists price_year_ngn integer check (price_year_ngn >= 0);
alter table public.api_plans add column if not exists seats integer not null default 1 check (seats between 1 and 500);
alter table public.api_plans add column if not exists self_serve boolean not null default false;

update public.api_plans set price_month_ngn = 0, price_year_ngn = 0, seats = 1, self_serve = false where plan = 'free';
update public.api_plans set price_month_ngn = 7500, price_year_ngn = 75000, seats = 1, self_serve = true where plan = 'pro';
update public.api_plans set price_month_ngn = 25000, price_year_ngn = 250000, seats = 5, self_serve = true where plan = 'team';
update public.api_plans set price_month_ngn = null, price_year_ngn = null, seats = 25, self_serve = false where plan = 'institutional';

create table if not exists public.billing_plan_codes (
  plan text not null references public.api_plans (plan),
  interval text not null check (interval in ('monthly', 'annually')),
  amount_kobo bigint not null check (amount_kobo > 0),
  plan_code text not null unique,
  created_at timestamptz not null default now(),
  primary key (plan, interval, amount_kobo)
);

create table if not exists public.billing_subscriptions (
  user_id uuid primary key references auth.users (id) on delete cascade,
  plan text not null references public.api_plans (plan),
  interval text check (interval in ('monthly', 'annually')),
  status text not null check (status in ('active', 'non_renewing', 'attention', 'cancelled')),
  customer_code text,
  subscription_code text unique,
  email_token text,
  next_payment_at timestamptz,
  updated_at timestamptz not null default now()
);

create table if not exists public.billing_events (
  event_key text primary key,
  received_at timestamptz not null default now()
);

alter table public.billing_plan_codes enable row level security;
alter table public.billing_subscriptions enable row level security;
alter table public.billing_events enable row level security;
revoke all on public.billing_plan_codes, public.billing_subscriptions, public.billing_events from anon, authenticated;

-- Public: the plans, their prices and what they include.
create or replace function public.billing_catalog()
returns jsonb
language sql stable security definer set search_path to ''
as $$
  select jsonb_agg(jsonb_build_object('id', p.plan, 'label', p.label, 'monthly_requests', p.monthly_requests,
                                      'seats', p.seats, 'self_serve', p.self_serve,
                                      'price_month_ngn', p.price_month_ngn, 'price_year_ngn', p.price_year_ngn)
                   order by p.sort)
    from public.api_plans p;
$$;

-- The signed-in account's plan and subscription.
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
      'plan', v_sub.plan, 'interval', v_sub.interval, 'status', v_sub.status,
      'next_payment_at', v_sub.next_payment_at, 'manageable', v_sub.subscription_code is not null) end,
    'catalog', public.billing_catalog());
end; $$;

-- API: the account behind a checkout or an event.
create or replace function public.billing_account(secret text, p_user uuid default null, p_email text default null)
returns jsonb
language plpgsql stable security definer set search_path to ''
as $$
declare v_uid uuid; v_email text; v_sub public.billing_subscriptions;
begin
  perform private.check_secret(secret);
  select u.id, u.email into v_uid, v_email from auth.users u
   where u.deleted_at is null and (u.id = p_user or (p_user is null and lower(u.email) = lower(btrim(p_email))));
  if v_uid is null then return null; end if;
  select * into v_sub from public.billing_subscriptions where user_id = v_uid;
  return jsonb_build_object('user_id', v_uid, 'email', v_email, 'plan', (private.plan_of(v_uid)).plan,
                            'subscription_code', v_sub.subscription_code, 'email_token', v_sub.email_token,
                            'status', v_sub.status);
end; $$;

create or replace function public.billing_price(secret text, p_plan text, p_interval text)
returns jsonb
language plpgsql stable security definer set search_path to ''
as $$
declare v_plan public.api_plans; v_amount bigint;
begin
  perform private.check_secret(secret);
  select * into v_plan from public.api_plans where plan = p_plan and self_serve;
  if v_plan.plan is null then raise exception 'unknown_plan' using errcode = '22023'; end if;
  v_amount := (case p_interval when 'monthly' then v_plan.price_month_ngn when 'annually' then v_plan.price_year_ngn end)::bigint * 100;
  if v_amount is null or v_amount <= 0 then raise exception 'no_price' using errcode = '22023'; end if;
  return jsonb_build_object('plan', v_plan.plan, 'label', v_plan.label, 'interval', p_interval, 'amount_kobo', v_amount,
                            'plan_code', (select c.plan_code from public.billing_plan_codes c
                                           where c.plan = p_plan and c.interval = p_interval and c.amount_kobo = v_amount));
end; $$;

create or replace function public.billing_save_plan_code(secret text, p_plan text, p_interval text, p_amount_kobo bigint, p_code text)
returns void
language plpgsql volatile security definer set search_path to ''
as $$
begin
  perform private.check_secret(secret);
  insert into public.billing_plan_codes (plan, interval, amount_kobo, plan_code) values (p_plan, p_interval, p_amount_kobo, p_code)
  on conflict (plan, interval, amount_kobo) do nothing;
end; $$;

-- API: the plan a paid code belongs to (for subscription events that carry only Paystack's plan code).
create or replace function public.billing_plan_for_code(secret text, p_code text)
returns jsonb
language plpgsql stable security definer set search_path to ''
as $$
begin
  perform private.check_secret(secret);
  return (select jsonb_build_object('plan', c.plan, 'interval', c.interval) from public.billing_plan_codes c where c.plan_code = p_code);
end; $$;

-- API: apply one Paystack event, once. Returns {"applied": false} for an event already applied.
create or replace function public.billing_apply(
  secret text, p_event_key text, p_user uuid, p_plan text, p_status text, p_interval text default null,
  p_customer text default null, p_subscription text default null, p_email_token text default null,
  p_next timestamptz default null)
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
                                                 email_token, next_payment_at)
  values (p_user, p_plan, p_interval, p_status, p_customer, p_subscription, p_email_token, p_next)
  on conflict (user_id) do update set
    plan = excluded.plan, status = excluded.status,
    interval = coalesce(excluded.interval, s.interval),
    customer_code = coalesce(excluded.customer_code, s.customer_code),
    subscription_code = coalesce(excluded.subscription_code, s.subscription_code),
    email_token = coalesce(excluded.email_token, s.email_token),
    next_payment_at = coalesce(excluded.next_payment_at, s.next_payment_at),
    updated_at = now();

  -- Paid access follows the subscription. A plan the owner set by hand ('manual') is never overridden.
  if p_status in ('active', 'non_renewing', 'attention') then
    insert into public.account_plans (user_id, plan, source) values (p_user, p_plan, 'paystack')
    on conflict (user_id) do update set plan = excluded.plan, source = 'paystack', updated_at = now()
      where public.account_plans.source <> 'manual';
  else
    delete from public.account_plans where user_id = p_user and source = 'paystack';
  end if;
  return jsonb_build_object('applied', true, 'plan', (private.plan_of(p_user)).plan);
end; $$;

revoke all on function public.billing_catalog() from public;
grant execute on function public.billing_catalog() to anon, authenticated;
revoke all on function public.my_billing() from public, anon;
grant execute on function public.my_billing() to authenticated;
revoke all on function public.billing_account(text, uuid, text), public.billing_price(text, text, text),
  public.billing_save_plan_code(text, text, text, bigint, text), public.billing_plan_for_code(text, text),
  public.billing_apply(text, text, uuid, text, text, text, text, text, text, timestamptz) from public, authenticated;
grant execute on function public.billing_account(text, uuid, text), public.billing_price(text, text, text),
  public.billing_save_plan_code(text, text, text, bigint, text), public.billing_plan_for_code(text, text),
  public.billing_apply(text, text, uuid, text, text, text, text, text, text, timestamptz) to anon;
