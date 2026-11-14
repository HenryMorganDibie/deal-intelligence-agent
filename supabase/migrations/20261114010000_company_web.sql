-- Company websites read by web-harvester: a company is queued when someone looks it up and its website is known; the
-- scheduled job crawls the site's about, leadership, governance, subsidiary and contact pages (robots.txt permitting)
-- and stores the facts confirmed on those pages. A site is read again at most every 30 days. No direct table access
-- for any client role.
create table if not exists public.company_web (
  name_key text primary key check (char_length(name_key) between 2 and 120),
  name text not null check (char_length(name) <= 200),
  website text not null check (website like 'http%' and char_length(website) <= 300),
  status text not null default 'queued' check (status in ('queued', 'crawling', 'done', 'failed')),
  requested_at timestamptz not null default now(),
  taken_at timestamptz,
  crawled_at timestamptz,
  attempts integer not null default 0,
  facts jsonb,
  error text
);
create index if not exists company_web_next_idx on public.company_web (status, requested_at);
alter table public.company_web enable row level security;
revoke all on public.company_web from public, anon, authenticated;

-- Queue a company's site; one read more than 30 days old (or a failed one) is queued again.
create or replace function public.company_web_request(secret text, p_name_key text, p_name text, p_website text)
returns text language plpgsql security definer set search_path = '' as $$
declare s text;
begin
  perform private.check_secret(secret);
  insert into public.company_web (name_key, name, website)
  values (p_name_key, left(p_name, 200), left(p_website, 300))
  on conflict (name_key) do update
     set status = 'queued', requested_at = now(), website = excluded.website, attempts = 0
   where public.company_web.status in ('done', 'failed')
     and coalesce(public.company_web.crawled_at, public.company_web.requested_at) < now() - interval '30 days';
  select status into s from public.company_web where name_key = p_name_key;
  return s;
end; $$;

-- The next sites to crawl, oldest request first; a site taken but not finished within an hour is taken again, up to
-- three attempts.
create or replace function public.company_web_take(secret text, p_limit integer)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare rows jsonb;
begin
  perform private.check_secret(secret);
  with picked as (
    select name_key from public.company_web
     where (status = 'queued' or (status = 'crawling' and taken_at < now() - interval '1 hour')) and attempts < 3
     order by requested_at limit greatest(0, least(coalesce(p_limit, 0), 50)) for update skip locked)
  update public.company_web w set status = 'crawling', attempts = w.attempts + 1, taken_at = now()
    from picked where w.name_key = picked.name_key;
  select coalesce(jsonb_agg(jsonb_build_object('name_key', name_key, 'name', name, 'website', website)), '[]'::jsonb)
    into rows from public.company_web where status = 'crawling' and taken_at >= now() - interval '5 seconds';
  return rows;
end; $$;

create or replace function public.company_web_save(secret text, p_name_key text, p_status text, p_facts jsonb, p_error text)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  update public.company_web
     set status = case when p_status = 'failed' and attempts < 3 then 'queued' else p_status end,
         facts = coalesce(p_facts, facts), error = left(p_error, 300),
         crawled_at = case when p_status = 'done' then now() else crawled_at end
   where name_key = p_name_key;
  return found;
end; $$;

create or replace function public.company_web_get(secret text, p_name_key text)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return (select jsonb_build_object('name', name, 'website', website, 'status', status, 'crawled_at', crawled_at,
                                    'facts', facts)
            from public.company_web where name_key = p_name_key);
end; $$;
