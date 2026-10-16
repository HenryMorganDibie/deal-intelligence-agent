-- Record successful app feature responses without storing prompts or query contents.
create table if not exists public.product_actions (
  day date not null default (now() at time zone 'utc')::date,
  created_at timestamptz not null default now(),
  visitor text not null,
  action text not null check (action in (
    'deals_loaded', 'investors_loaded', 'events_loaded', 'risk_data_loaded',
    'company_data_loaded', 'watchlists_used', 'brief_opened', 'performance_data_loaded'
  ))
);
create index if not exists product_actions_created_action_idx
  on public.product_actions (created_at, action);
create unique index if not exists product_actions_daily_unique_idx
  on public.product_actions (day, visitor, action);
alter table public.product_actions enable row level security;
revoke all on public.product_actions from public, anon, authenticated;

create or replace function public.log_product_action(secret text, p_visitor text, p_action text)
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
  if p_action is null or p_action not in (
    'deals_loaded', 'investors_loaded', 'events_loaded', 'risk_data_loaded',
    'company_data_loaded', 'watchlists_used', 'brief_opened', 'performance_data_loaded'
  ) then
    raise exception 'invalid product action';
  end if;
  insert into public.product_actions (visitor, action)
  values (left(p_visitor, 40), p_action)
  on conflict (day, visitor, action) do nothing;
end;
$$;

create or replace function public.visit_stats(secret text, p_days int)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  since date := (now() at time zone 'utc')::date - greatest(p_days, 1) + 1;
begin
  perform private.check_secret(secret);
  return jsonb_build_object(
    'since', since,
    'totals', (select jsonb_build_object(
        'views', count(*),
        'visitors', count(distinct visitor),
        'users', count(distinct visitor) filter (where path like '/app%'),
        'returning_users', (select count(*) from (
            select visitor from public.visits
            where day >= since and path like '/app%'
            group by visitor having count(distinct day) > 1) r))
      from public.visits where day >= since),
    'days', coalesce((select jsonb_agg(d order by d->>'day' desc) from (
        select jsonb_build_object('day', day, 'views', count(*), 'visitors', count(distinct visitor),
                                  'users', count(distinct visitor) filter (where path like '/app%')) d
        from public.visits where day >= since group by day) x), '[]'::jsonb),
    'pages', coalesce((select jsonb_agg(p) from (
        select jsonb_build_object('path', path, 'views', count(*), 'visitors', count(distinct visitor)) p
        from public.visits where day >= since group by path order by count(*) desc limit 15) y), '[]'::jsonb),
    'actions', coalesce((select jsonb_agg(jsonb_build_object(
        'action', action, 'completions', completions, 'clients', clients) order by action)
      from (
        select action, count(*) as completions, count(distinct visitor) as clients
        from (
          select action, visitor
          from public.product_actions
          where created_at >= since::timestamp at time zone 'UTC'
          union all
          select case
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
        ) completed
        group by action
      ) counts), '[]'::jsonb),
    'app_page_activity', coalesce((select jsonb_agg(jsonb_build_object(
        'feature', feature, 'browsers', browsers, 'page_views', page_views) order by feature)
      from (
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
          from public.visits
          where day >= since
        ) app_pages
        where feature is not null
        group by feature
      ) page_counts), '[]'::jsonb)
  );
end;
$$;

revoke execute on function public.log_product_action(text, text, text) from public;
grant execute on function public.log_product_action(text, text, text) to anon;
revoke execute on function public.visit_stats(text, int) from public;
grant execute on function public.visit_stats(text, int) to anon;
