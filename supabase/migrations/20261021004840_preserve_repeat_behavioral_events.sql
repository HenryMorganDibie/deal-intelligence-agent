alter table public.behavioral_events
  add column if not exists event_id uuid not null default gen_random_uuid();

drop index if exists public.behavioral_events_daily_unique_idx;
create unique index if not exists behavioral_events_event_id_unique_idx
  on public.behavioral_events(event_id);

create or replace function public.log_behavioral_event(
  secret text,
  p_visitor text,
  p_event_type text,
  p_target_id text default null,
  p_context jsonb default '{}'::jsonb,
  p_event_id uuid default null
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
  insert into public.behavioral_events(event_id,visitor,event_type,target_id,context)
  values(coalesce(p_event_id,gen_random_uuid()),left(p_visitor,40),p_event_type,nullif(p_target_id,''),p_context)
  on conflict(event_id) do nothing;
end;
$$;
revoke execute on function public.log_behavioral_event(text,text,text,text,jsonb,uuid) from public;
grant execute on function public.log_behavioral_event(text,text,text,text,jsonb,uuid) to anon;
