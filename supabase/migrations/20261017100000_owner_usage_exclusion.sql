drop function if exists public.visit_stats(text, int);

create function public.visit_stats(
  secret text, p_days int, p_excluded_visitor text, p_excluded_client_hash text
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  since date := (now() at time zone 'utc')::date - greatest(p_days, 1) + 1;
  result jsonb;
begin
  perform private.check_secret(secret);
  with filtered_visits as (
    select day, visitor, path
    from public.visits
    where day >= since and visitor is distinct from p_excluded_visitor
  ),
  filtered_actions as (
    select created_at, visitor, action
    from public.product_actions
    where created_at >= since::timestamp at time zone 'UTC'
      and visitor is distinct from p_excluded_visitor
  ),
  completed_runs as (
    select created_at,
           case
             when company like '[research]%' then 'research_completed'
             when company like '[report] country%' then 'country_report_completed'
             when company like '[report] sector%' then 'sector_report_completed'
             else 'brief_completed'
           end as action,
           'run:' || client_hash as visitor
    from public.runs
    where created_at >= since::timestamp at time zone 'UTC'
      and (status = 'done'
        or (status = 'research' and
          (company like '[research]%' or company like '[report] country%' or company like '[report] sector%')))
      and client_hash is distinct from p_excluded_client_hash
  ),
  day_counts as (
    select day, count(*) as views, count(distinct visitor) as visitors,
           count(distinct visitor) filter (where path like '/app%') as users
    from filtered_visits
    group by day
  ),
  page_counts as (
    select path, count(*) as views, count(distinct visitor) as visitors
    from filtered_visits
    group by path
    order by count(*) desc
    limit 15
  ),
  action_counts as (
    select action, count(*) as completions, count(distinct visitor) as clients
    from (
      select action, visitor from filtered_actions
      union all
      select action, visitor from completed_runs
    ) actions
    group by action
  ),
  feature_counts as (
    select feature, count(distinct visitor) as browsers, count(*) as page_views
    from (
      select case
               when path = '/app/deals' or path like '/app/deals/%' then 'Deals'
               when path = '/app/investors' or path like '/app/investors/%' then 'Investors'
               when path = '/app/research' then 'Research'
               when path = '/app/companies' then 'Company profiles'
               when path = '/app/countries' or path like '/app/countries/%' then 'Country risk'
               when path = '/app/coverage' then 'Coverage'
               when path = '/app/watchlists' or path like '/app/watchlists/%' then 'Watchlists'
               when path = '/app' then 'Brief workspace'
             end as feature,
             visitor
      from filtered_visits
    ) app_pages
    where feature is not null
    group by feature
  )
  select jsonb_build_object(
    'since', since,
    'totals', (
      select jsonb_build_object(
        'views', count(*),
        'visitors', count(distinct visitor),
        'users', count(distinct visitor) filter (where path like '/app%'),
        'returning_users', (
          select count(*) from (
            select visitor
            from filtered_visits
            where path like '/app%'
            group by visitor
            having count(distinct day) > 1
          ) returning_visitors
        )
      )
      from filtered_visits
    ),
    'days', coalesce((
      select jsonb_agg(jsonb_build_object(
        'day', day, 'views', views, 'visitors', visitors, 'users', users
      ) order by day desc)
      from day_counts
    ), '[]'::jsonb),
    'pages', coalesce((
      select jsonb_agg(jsonb_build_object('path', path, 'views', views, 'visitors', visitors))
      from page_counts
    ), '[]'::jsonb),
    'actions', coalesce((
      select jsonb_agg(jsonb_build_object(
        'action', action, 'completions', completions, 'clients', clients
      ) order by action)
      from action_counts
    ), '[]'::jsonb),
    'app_page_activity', coalesce((
      select jsonb_agg(jsonb_build_object(
        'feature', feature, 'browsers', browsers, 'page_views', page_views
      ) order by feature)
      from feature_counts
    ), '[]'::jsonb)
  ) into result;
  return result;
end;
$$;

revoke execute on function public.visit_stats(text, int, text, text) from public;
grant execute on function public.visit_stats(text, int, text, text) to anon;
