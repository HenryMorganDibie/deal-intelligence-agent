-- The free-to-paid funnel: when an account meets a plan limit, opens the plans, starts a checkout or pays. The owner's
-- admin page reads the summary to decide whether the free allowance is right, from data rather than guesses.
-- Events carry the account only; nothing about what was searched or read.

create table if not exists public.plan_events (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  event text not null check (event in ('limit_ai_month', 'limit_ai_day', 'limit_alert', 'limit_export',
                                       'see_plans', 'checkout_started', 'paid')),
  detail text check (char_length(detail) <= 60),
  created_at timestamptz not null default now()
);
create index if not exists plan_events_event_time on public.plan_events (event, created_at);
alter table public.plan_events enable row level security;
revoke all on public.plan_events from anon, authenticated;

create or replace function public.record_plan_event(secret text, p_user uuid, p_event text, p_detail text default null)
returns void
language plpgsql volatile security definer set search_path to ''
as $$
begin
  perform private.check_secret(secret);
  insert into public.plan_events (user_id, event, detail) values (p_user, p_event, left(p_detail, 60));
end; $$;

create or replace function public.plan_funnel(secret text, p_days integer default 30)
returns jsonb
language plpgsql stable security definer set search_path to ''
as $$
declare v_since timestamptz := now() - make_interval(days => greatest(1, least(p_days, 365)));
begin
  perform private.check_secret(secret);
  return jsonb_build_object(
    'days', p_days,
    'accounts', (select count(*) from auth.users),
    'free_accounts', (select count(*) from auth.users u where (private.plan_of(u.id)).plan = 'free'),
    'new_accounts', (select count(*) from auth.users where created_at >= v_since),
    'paying_accounts', (select count(*) from public.billing_subscriptions
                         where status in ('active', 'non_renewing', 'attention')),
    'free_using_briefs', (select count(distinct f.user_id) from public.feature_usage f
                           where f.feature = 'ai' and f.used > 0 and (private.plan_of(f.user_id)).plan = 'free'
                             and f.period >= date_trunc('month', v_since)::date),
    'events', coalesce((select jsonb_object_agg(event, jsonb_build_object('accounts', accounts, 'times', times))
                          from (select event, count(distinct user_id) accounts, count(*) times
                                  from public.plan_events where created_at >= v_since group by event) e), '{}'::jsonb));
end; $$;

revoke all on function public.record_plan_event(text, uuid, text, text), public.plan_funnel(text, integer)
  from public, authenticated;
grant execute on function public.record_plan_event(text, uuid, text, text), public.plan_funnel(text, integer) to anon;
