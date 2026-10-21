create or replace function public.behavioral_signal_stats(secret text, p_days int default 30)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare since_date date := (now() at time zone 'utc')::date - greatest(1,least(coalesce(p_days,30),365)) + 1;
begin
  perform private.check_secret(secret);
  return jsonb_build_object(
    'since',since_date,
    'days',greatest(1,least(coalesce(p_days,30),365)),
    'totals',(select coalesce(jsonb_object_agg(event_type,n),'{}'::jsonb) from
      (select event_type,count(*) n from public.behavioral_events where day>=since_date group by event_type) t),
    'top_deals',(select coalesce(jsonb_agg(jsonb_build_object(
      'deal_id',i.target_id,'unique_impression_visitors',i.visitors,'unique_openers',coalesce(o.visitors,0),
      'impressions',i.impressions,'opens',coalesce(o.opens,0),
      'active_days',i.active_days,
      'click_through_rate',case when i.impressions>0 then round(coalesce(o.opens,0)::numeric/i.impressions,4) else null end
    ) order by coalesce(o.visitors,0) desc,i.active_days desc),'[]'::jsonb)
    from (
      select target_id,count(*) impressions,count(distinct visitor) visitors,count(distinct day) active_days
      from public.behavioral_events where day>=since_date and event_type='deal_impression' and target_id is not null
      group by target_id having count(*)>=3
    ) i left join (
      select target_id,count(*) opens,count(distinct visitor) visitors
      from public.behavioral_events where day>=since_date and event_type='deal_opened' and target_id is not null
      group by target_id
    ) o on o.target_id=i.target_id),
    'top_briefs',(select coalesce(jsonb_agg(jsonb_build_object('brief_id',target_id,'unique_visitors',visitors,'active_days',active_days)
      order by visitors desc,active_days desc),'[]'::jsonb) from (
      select target_id,count(distinct visitor) visitors,count(distinct day) active_days
      from public.behavioral_events where day>=since_date and event_type='market_brief_opened' and target_id is not null
      group by target_id having count(distinct visitor)>=2 order by visitors desc,active_days desc limit 50
    ) ranked)
  );
end;
$$;
revoke execute on function public.behavioral_signal_stats(text,int) from public;
grant execute on function public.behavioral_signal_stats(text,int) to anon;
