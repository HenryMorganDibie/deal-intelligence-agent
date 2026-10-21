create table if not exists public.behavioral_events (
  day date not null default (now() at time zone 'utc')::date,
  created_at timestamptz not null default now(),
  visitor text not null,
  event_type text not null check (event_type in (
    'deal_search_submitted', 'deal_opened', 'research_submitted', 'market_brief_opened'
  )),
  target_id text,
  context jsonb not null default '{}'::jsonb,
  constraint behavioral_events_context_size check (octet_length(context::text) <= 1200)
);
create index if not exists behavioral_events_day_type_idx
  on public.behavioral_events (day, event_type);
create index if not exists behavioral_events_target_idx
  on public.behavioral_events (event_type, target_id, day)
  where target_id is not null;
create unique index if not exists behavioral_events_daily_unique_idx
  on public.behavioral_events (day, visitor, event_type, target_id)
  nulls not distinct;

alter table public.behavioral_events enable row level security;
revoke all on public.behavioral_events from public, anon, authenticated;

create or replace function public.log_behavioral_event(
  secret text, p_visitor text, p_event_type text, p_target_id text default null, p_context jsonb default '{}'::jsonb
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform private.check_secret(secret);
  if p_visitor is null or p_visitor !~ '^[a-z0-9]{8,40}$' then
    raise exception 'invalid visitor id';
  end if;
  if p_event_type is null or p_event_type not in (
    'deal_search_submitted', 'deal_opened', 'research_submitted', 'market_brief_opened'
  ) then
    raise exception 'invalid behavioural event';
  end if;
  if p_target_id is not null and (length(p_target_id) > 160 or p_target_id ~ '[[:cntrl:]]') then
    raise exception 'invalid target id';
  end if;
  if p_context is null or jsonb_typeof(p_context) <> 'object' or octet_length(p_context::text) > 1200 then
    raise exception 'invalid event context';
  end if;
  insert into public.behavioral_events(visitor, event_type, target_id, context)
  values (left(p_visitor, 40), p_event_type, nullif(p_target_id, ''), p_context)
  on conflict (day, visitor, event_type, target_id) do nothing;
end;
$$;
revoke execute on function public.log_behavioral_event(text, text, text, text, jsonb) from public;
grant execute on function public.log_behavioral_event(text, text, text, text, jsonb) to anon;

create or replace function public.behavioral_signal_stats(secret text, p_days int default 30)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare since_date date := (now() at time zone 'utc')::date - greatest(1, least(coalesce(p_days,30),365)) + 1;
begin
  perform private.check_secret(secret);
  return jsonb_build_object(
    'since', since_date,
    'days', greatest(1, least(coalesce(p_days,30),365)),
    'totals', (select coalesce(jsonb_object_agg(event_type, n), '{}'::jsonb) from (
      select event_type, count(*) n from public.behavioral_events where day >= since_date group by event_type
    ) totals),
    'top_deals', (select coalesce(jsonb_agg(jsonb_build_object('deal_id',target_id,'unique_visitors',visitors,'active_days',active_days)
       order by visitors desc, active_days desc), '[]'::jsonb) from (
      select target_id, count(distinct visitor) visitors, count(distinct day) active_days
      from public.behavioral_events
      where day >= since_date and event_type='deal_opened' and target_id is not null
      group by target_id having count(distinct visitor) >= 2
      order by visitors desc, active_days desc limit 100
    ) ranked),
    'top_briefs', (select coalesce(jsonb_agg(jsonb_build_object('brief_id',target_id,'unique_visitors',visitors,'active_days',active_days)
       order by visitors desc, active_days desc), '[]'::jsonb) from (
      select target_id, count(distinct visitor) visitors, count(distinct day) active_days
      from public.behavioral_events
      where day >= since_date and event_type='market_brief_opened' and target_id is not null
      group by target_id having count(distinct visitor) >= 2
      order by visitors desc, active_days desc limit 50
    ) ranked)
  );
end;
$$;
revoke execute on function public.behavioral_signal_stats(text, int) from public;
grant execute on function public.behavioral_signal_stats(text, int) to anon;
