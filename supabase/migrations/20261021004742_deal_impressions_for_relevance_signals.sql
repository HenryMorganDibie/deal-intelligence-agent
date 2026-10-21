alter table public.product_actions drop constraint if exists product_actions_action_check;
alter table public.product_actions add constraint product_actions_action_check check (action in (
  'deals_loaded', 'investors_loaded', 'events_loaded', 'risk_data_loaded',
  'company_data_loaded', 'watchlists_used', 'brief_opened', 'performance_data_loaded',
  'deal_search_submitted', 'deal_opened', 'research_submitted', 'market_brief_opened', 'deal_impression'
));

create or replace function public.log_product_action(secret text, p_visitor text, p_action text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  if p_visitor is null or p_visitor !~ '^[a-z0-9]{8,40}$' then raise exception 'invalid visitor id'; end if;
  if p_action is null or p_action not in (
    'deals_loaded', 'investors_loaded', 'events_loaded', 'risk_data_loaded',
    'company_data_loaded', 'watchlists_used', 'brief_opened', 'performance_data_loaded',
    'deal_search_submitted', 'deal_opened', 'research_submitted', 'market_brief_opened', 'deal_impression'
  ) then raise exception 'invalid product action'; end if;
  insert into public.product_actions(visitor, action) values (left(p_visitor,40),p_action)
  on conflict (day, visitor, action) do nothing;
end;
$$;
revoke execute on function public.log_product_action(text,text,text) from public;
grant execute on function public.log_product_action(text,text,text) to anon;

alter table public.behavioral_events drop constraint if exists behavioral_events_event_type_check;
alter table public.behavioral_events add constraint behavioral_events_event_type_check check (event_type in (
  'deal_search_submitted', 'deal_opened', 'research_submitted', 'market_brief_opened', 'deal_impression'
));

create or replace function public.log_behavioral_event(
  secret text, p_visitor text, p_event_type text, p_target_id text default null, p_context jsonb default '{}'::jsonb
)
returns void language plpgsql security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  if p_visitor is null or p_visitor !~ '^[a-z0-9]{8,40}$' then raise exception 'invalid visitor id'; end if;
  if p_event_type is null or p_event_type not in (
    'deal_search_submitted', 'deal_opened', 'research_submitted', 'market_brief_opened', 'deal_impression'
  ) then raise exception 'invalid behavioural event'; end if;
  if p_target_id is not null and (length(p_target_id)>160 or p_target_id ~ '[[:cntrl:]]') then raise exception 'invalid target id'; end if;
  if p_context is null or jsonb_typeof(p_context)<>'object' or octet_length(p_context::text)>1200 then raise exception 'invalid event context'; end if;
  insert into public.behavioral_events(visitor,event_type,target_id,context)
  values(left(p_visitor,40),p_event_type,nullif(p_target_id,''),p_context)
  on conflict(day,visitor,event_type,target_id) do nothing;
end;
$$;
revoke execute on function public.log_behavioral_event(text,text,text,text,jsonb) from public;
grant execute on function public.log_behavioral_event(text,text,text,text,jsonb) to anon;

create or replace function public.behavioral_signal_stats(secret text, p_days int default 30)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare since_date date := (now() at time zone 'utc')::date - greatest(1,least(coalesce(p_days,30),365)) + 1;
begin
  perform private.check_secret(secret);
  return jsonb_build_object(
    'since',since_date,'days',greatest(1,least(coalesce(p_days,30),365)),
    'totals',(select coalesce(jsonb_object_agg(event_type,n),'{}'::jsonb) from
      (select event_type,count(*) n from public.behavioral_events where day>=since_date group by event_type) t),
    'top_deals',(select coalesce(jsonb_agg(jsonb_build_object(
      'deal_id',target_id,'unique_openers',openers,'unique_impression_visitors',impressors,
      'active_days',active_days,'click_through_rate',case when impressions>0 then round(opens::numeric/impressions,4) else null end
    ) order by openers desc,active_days desc),'[]'::jsonb) from (
      select i.target_id,
        count(distinct i.visitor) filter(where i.event_type='deal_impression') impressors,
        count(distinct o.visitor) openers,
        count(distinct i.day) active_days,
        count(*) filter(where i.event_type='deal_impression') impressions,
        count(*) filter(where i.event_type='deal_opened') opens
      from public.behavioral_events i
      left join public.behavioral_events o on o.target_id=i.target_id and o.event_type='deal_opened' and o.day>=since_date
      where i.day>=since_date and i.target_id is not null and i.event_type in ('deal_impression','deal_opened')
      group by i.target_id having count(*) filter(where i.event_type='deal_impression')>=3
    ) ranked order by openers desc,active_days desc limit 100),
    'top_briefs',(select coalesce(jsonb_agg(jsonb_build_object('brief_id',target_id,'unique_visitors',visitors,'active_days',active_days)
      order by visitors desc,active_days desc),'[]'::jsonb) from (
      select target_id,count(distinct visitor) visitors,count(distinct day) active_days from public.behavioral_events
      where day>=since_date and event_type='market_brief_opened' and target_id is not null
      group by target_id having count(distinct visitor)>=2 order by visitors desc,active_days desc limit 50
    ) ranked)
  );
end;
$$;
revoke execute on function public.behavioral_signal_stats(text,int) from public;
grant execute on function public.behavioral_signal_stats(text,int) to anon;
