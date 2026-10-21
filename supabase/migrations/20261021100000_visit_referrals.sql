-- Where visitors come from. The landing page of each browser session records the referring site's host
-- (never the full URL) and any campaign tags (utm_source, utm_medium, utm_campaign). The owner's usage page
-- groups them into channels and also counts engaged browsers, since single-view browsers include crawlers
-- and link previews.
alter table public.visits
  add column if not exists referrer text,
  add column if not exists utm_source text,
  add column if not exists utm_medium text,
  add column if not exists utm_campaign text;

-- The three-argument log_visit stays for older API deployments; this one also records the source.
create or replace function public.log_visit_with_source(
  secret text, p_visitor text, p_path text,
  p_referrer text, p_utm_source text, p_utm_medium text, p_utm_campaign text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform private.check_secret(secret);
  insert into public.visits (visitor, path, referrer, utm_source, utm_medium, utm_campaign)
  values (
    left(p_visitor, 40), left(p_path, 200),
    case when p_referrer ~ '^[a-z0-9.-]{1,100}$' then p_referrer end,
    case when p_utm_source ~ '^[A-Za-z0-9._+-]{1,60}$' then lower(p_utm_source) end,
    case when p_utm_medium ~ '^[A-Za-z0-9._+-]{1,60}$' then lower(p_utm_medium) end,
    case when p_utm_campaign ~ '^[A-Za-z0-9._+-]{1,60}$' then lower(p_utm_campaign) end);
end;
$$;
revoke execute on function public.log_visit_with_source(text, text, text, text, text, text, text) from public;
grant execute on function public.log_visit_with_source(text, text, text, text, text, text, text) to anon;

-- A readable channel for a referrer host or utm_source.
create or replace function private.visit_channel(p_source text)
returns text
language sql
immutable
set search_path = ''
as $$
  select case
    when s is null or s = '' then 'Direct or unknown'
    when s ~ '(^|\.)google\.' or s = 'google' then 'Google'
    when s ~ '(^|\.)bing\.com$' or s = 'bing' then 'Bing'
    when s ~ '(^|\.)duckduckgo\.com$' or s = 'duckduckgo' then 'DuckDuckGo'
    when s ~ '(^|\.)yahoo\.' or s = 'yahoo' then 'Yahoo'
    when s ~ '(^|\.)(linkedin\.com|lnkd\.in)$' or s = 'linkedin' then 'LinkedIn'
    when s ~ '^(t\.co|(.*\.)?twitter\.com|(.*\.)?x\.com)$' or s in ('twitter', 'x') then 'X (Twitter)'
    when s ~ '(^|\.)(facebook\.com|fb\.com|fb\.me)$' or s in ('facebook', 'fb') then 'Facebook'
    when s ~ '(^|\.)instagram\.com$' or s = 'instagram' then 'Instagram'
    when s ~ '(^|\.)(whatsapp\.com|wa\.me)$' or s = 'whatsapp' then 'WhatsApp'
    when s ~ '^(t\.me|(.*\.)?telegram\.org)$' or s = 'telegram' then 'Telegram'
    when s ~ '(^|\.)reddit\.com$' or s = 'reddit' then 'Reddit'
    when s = 'news.ycombinator.com' or s in ('hackernews', 'hn') then 'Hacker News'
    when s ~ '(^|\.)github\.com$' or s = 'github' then 'GitHub'
    when s ~ '(^|\.)(chatgpt\.com|openai\.com)$' or s = 'chatgpt' then 'ChatGPT'
    when s ~ '(^|\.)perplexity\.ai$' or s = 'perplexity' then 'Perplexity'
    when s ~ '(^|\.)(mail\.google\.com|outlook\.(live|office)\.com)$' or s in ('email', 'newsletter') then 'Email'
    else s
  end
  from (select regexp_replace(lower(p_source), '^www\.', '') as s) x
$$;

create or replace function public.visit_stats(secret text, p_days integer, p_excluded_visitor text, p_excluded_client_hash text)
returns jsonb
language plpgsql
stable security definer
set search_path to ''
as $function$
declare
  since date := (now() at time zone 'utc')::date - greatest(p_days, 1) + 1;
  result jsonb;
begin
  perform private.check_secret(secret);
  with filtered_visits as (
    select day, visitor, path, created_at, referrer, utm_source, utm_medium, utm_campaign
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
  -- A browser is engaged when it viewed two or more pages or used a feature successfully.
  engaged as (
    select visitor from filtered_visits group by visitor having count(*) >= 2
    union
    select visitor from filtered_actions
  ),
  -- Each browser's source: its earliest attributed landing in the window, otherwise direct or unknown.
  visitor_source as (
    select distinct on (visitor) visitor,
           private.visit_channel(coalesce(utm_source, referrer)) as channel,
           referrer, utm_source, utm_medium, utm_campaign
    from filtered_visits
    order by visitor, (coalesce(utm_source, referrer) is null), created_at
  ),
  source_counts as (
    select s.channel, count(*) as browsers, count(e.visitor) as engaged_browsers,
           sum(v.views) as views
    from visitor_source s
    left join engaged e using (visitor)
    join (select visitor, count(*) as views from filtered_visits group by visitor) v using (visitor)
    group by s.channel
  ),
  referrer_counts as (
    select referrer, count(*) as browsers
    from visitor_source
    where referrer is not null
    group by referrer
    order by count(*) desc
    limit 15
  ),
  campaign_counts as (
    select utm_campaign as campaign, max(utm_source) as source, max(utm_medium) as medium,
           count(*) as browsers, count(e.visitor) as engaged_browsers
    from visitor_source s
    left join engaged e using (visitor)
    where utm_campaign is not null
    group by utm_campaign
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
        'engaged_visitors', (select count(*) from engaged where visitor in (select visitor from filtered_visits)),
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
    'sources', coalesce((
      select jsonb_agg(jsonb_build_object(
        'source', channel, 'browsers', browsers, 'engaged_browsers', engaged_browsers, 'views', views
      ) order by browsers desc, channel)
      from source_counts
    ), '[]'::jsonb),
    'referrers', coalesce((
      select jsonb_agg(jsonb_build_object('referrer', referrer, 'browsers', browsers) order by browsers desc, referrer)
      from referrer_counts
    ), '[]'::jsonb),
    'campaigns', coalesce((
      select jsonb_agg(jsonb_build_object(
        'campaign', campaign, 'source', source, 'medium', medium,
        'browsers', browsers, 'engaged_browsers', engaged_browsers
      ) order by browsers desc, campaign)
      from campaign_counts
    ), '[]'::jsonb),
    'attribution_since', (select min(day) from public.visits where referrer is not null or utm_source is not null),
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
$function$;
