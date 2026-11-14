-- A filed annual statement that is a scan (page images, no text) is queued with the company for the scheduled job,
-- which reads it by OCR. A company may now be queued for its filing alone, without a known website.
alter table public.company_web add column if not exists filing_url text
  check (filing_url is null or (filing_url like 'https://%' and char_length(filing_url) <= 600));
alter table public.company_web alter column website drop not null;
alter table public.company_web drop constraint if exists company_web_website_check;
alter table public.company_web add constraint company_web_website_check
  check (website is null or (website like 'http%' and char_length(website) <= 300));

drop function if exists public.company_web_request(text, text, text, text);
create or replace function public.company_web_request(secret text, p_name_key text, p_name text, p_website text,
                                                      p_filing_url text default null)
returns text language plpgsql security definer set search_path = '' as $$
declare s text;
begin
  perform private.check_secret(secret);
  insert into public.company_web (name_key, name, website, filing_url)
  values (p_name_key, left(p_name, 200), left(p_website, 300), left(p_filing_url, 600))
  on conflict (name_key) do update
     set website = coalesce(excluded.website, public.company_web.website),
         filing_url = coalesce(excluded.filing_url, public.company_web.filing_url),
         status = 'queued', requested_at = now(), attempts = 0
   where (public.company_web.status in ('done', 'failed')
          and coalesce(public.company_web.crawled_at, public.company_web.requested_at) < now() - interval '30 days')
      or (excluded.filing_url is not null and excluded.filing_url is distinct from public.company_web.filing_url)
      or (excluded.website is not null and public.company_web.website is null);
  select status into s from public.company_web where name_key = p_name_key;
  return s;
end; $$;

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
  select coalesce(jsonb_agg(jsonb_build_object('name_key', name_key, 'name', name, 'website', website,
                                               'filing_url', filing_url)), '[]'::jsonb)
    into rows from public.company_web where status = 'crawling' and taken_at >= now() - interval '5 seconds';
  return rows;
end; $$;
