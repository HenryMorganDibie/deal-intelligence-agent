-- Faster, observable company website enrichment. The worker runs independently every five minutes.
alter table public.company_web
  add column if not exists stage text not null default 'queued';

alter table public.company_web
  drop constraint if exists company_web_stage_check;

alter table public.company_web
  add constraint company_web_stage_check
  check (stage in ('queued', 'finding_website', 'fetching_pages', 'verifying', 'completed', 'failed'));

update public.company_web
   set stage = case status
     when 'done' then 'completed'
     when 'failed' then 'failed'
     when 'crawling' then 'fetching_pages'
     else 'queued'
   end;

create or replace function public.company_web_request(secret text, p_name_key text, p_name text, p_website text,
                                                      p_filing_url text default null)
returns text language plpgsql security definer set search_path = '' as $$
declare s text;
begin
  perform private.check_secret(secret);
  insert into public.company_web (name_key, name, website, filing_url, stage)
  values (p_name_key, left(p_name, 200), left(p_website, 300), left(p_filing_url, 600), 'queued')
  on conflict (name_key) do update
     set website = coalesce(excluded.website, public.company_web.website),
         filing_url = coalesce(excluded.filing_url, public.company_web.filing_url),
         status = 'queued', stage = 'queued', requested_at = now(), attempts = 0
   where (public.company_web.status in ('done', 'failed')
          and coalesce(public.company_web.crawled_at, public.company_web.requested_at) < now() - interval '30 days')
      or (excluded.filing_url is not null and excluded.filing_url is distinct from public.company_web.filing_url)
      or (excluded.website is not null and public.company_web.website is null);
  select status into s from public.company_web where name_key = p_name_key;
  return s;
end; $$;

-- The private budget row is claimed inside company_web_take, so Tavily is called at most once per hour
-- across all worker invocations without exposing another SECURITY DEFINER RPC endpoint.
create table if not exists private.company_web_search_budget (
  id smallint primary key check (id = 1),
  last_search_at timestamptz
);
insert into private.company_web_search_budget (id, last_search_at)
values (1, null) on conflict (id) do nothing;
alter table private.company_web_search_budget enable row level security;
revoke all on private.company_web_search_budget from public, anon, authenticated;

drop function if exists public.company_web_take(text, integer);
create function public.company_web_take(secret text, p_limit integer, p_search_enabled boolean default false)
returns jsonb language plpgsql security definer set search_path = '' as $company_web_take$
declare rows jsonb;
declare search_allowed boolean := false;
begin
  perform private.check_secret(secret);
  with picked as (
    select name_key from public.company_web
     where (status = 'queued' or (status = 'crawling' and taken_at < now() - interval '30 minutes')) and attempts < 3
     order by requested_at limit greatest(0, least(coalesce(p_limit, 0), 50)) for update skip locked)
  update public.company_web w
     set status = 'crawling', stage = case
           when w.website is null and w.filing_url is null then 'finding_website'
           else 'fetching_pages' end,
         attempts = w.attempts + 1, taken_at = now()
    from picked where w.name_key = picked.name_key;

  if p_search_enabled and exists (
    select 1 from public.company_web
     where status = 'crawling' and taken_at >= now() - interval '5 seconds'
       and website is null and filing_url is null
  ) then
    update private.company_web_search_budget
       set last_search_at = now()
     where id = 1 and (last_search_at is null or last_search_at < now() - interval '1 hour');
    search_allowed := found;
  end if;

  select coalesce(jsonb_agg(jsonb_build_object('name_key', name_key, 'name', name, 'website', website,
                                               'filing_url', filing_url, 'stage', stage,
                                               'search_allowed', search_allowed)), '[]'::jsonb)
    into rows from public.company_web where status = 'crawling' and taken_at >= now() - interval '5 seconds';
  return rows;
end; $company_web_take$;

drop function if exists public.company_web_save(text, text, text, jsonb, text);
create function public.company_web_save(secret text, p_name_key text, p_status text, p_facts jsonb, p_error text,
                                         p_stage text default null)
returns boolean language plpgsql security definer set search_path = '' as $$
declare next_status text;
declare next_stage text;
begin
  perform private.check_secret(secret);
  next_status := case when p_status = 'failed' and
                            (select attempts from public.company_web where name_key = p_name_key) < 3
                      then 'queued' else p_status end;
  next_stage := case when next_status = 'queued' then 'queued' else coalesce(p_stage, case
    when next_status = 'done' then 'completed'
    when next_status = 'failed' then 'failed'
    else 'fetching_pages' end) end;
  if next_stage not in ('queued', 'finding_website', 'fetching_pages', 'verifying', 'completed', 'failed') then
    raise exception 'invalid company enrichment stage';
  end if;
  update public.company_web
     set status = next_status, stage = next_stage,
         facts = coalesce(p_facts, facts), error = left(p_error, 300),
         crawled_at = case when p_status = 'done' then now() else crawled_at end
   where name_key = p_name_key;
  return found;
end; $$;

create or replace function public.company_web_get(secret text, p_name_key text)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return (select jsonb_build_object('name', name, 'website', website, 'status', status, 'stage', stage,
                                    'crawled_at', crawled_at, 'facts', facts)
            from public.company_web where name_key = p_name_key);
end; $$;
