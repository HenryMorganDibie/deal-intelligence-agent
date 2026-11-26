-- Company websites are read again when they change, and at least every 30 days, without anyone opening the profile.
-- Until now a read site was queued again only when someone looked the company up and the read was over 30 days old,
-- so a company nobody opened kept its first read for ever. A scheduled check (scripts/company_web.py refresh) now
-- fetches each read site's home page about once a week and fingerprints its links to governance, board and report
-- pages and to report PDFs; a changed fingerprint (a new annual report, a new board page) queues a full re-read, and
-- so does a read more than 30 days old.

alter table public.company_web add column if not exists fingerprint text;
alter table public.company_web add column if not exists checked_at timestamptz;

-- Read sites due a change check: not checked in the last 7 days, the longest unchecked first.
create or replace function public.company_web_due_checks(secret text, p_limit int)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return coalesce((select jsonb_agg(jsonb_build_object('name_key', name_key, 'name', name, 'website', website,
                                                       'crawled_at', crawled_at))
    from (select name_key, name, website, crawled_at from public.company_web
          where status = 'done' and website is not null
            and (checked_at is null or checked_at < now() - interval '7 days')
          order by checked_at nulls first, crawled_at
          limit greatest(0, least(coalesce(p_limit, 0), 200))) d), '[]'::jsonb);
end; $$;

-- Record a check. A fingerprint that differs from the stored one, or a read over 30 days old, queues a re-read.
-- p_fingerprint null means the home page could not be read this time: only the 30-day rule applies.
-- Returns 'queued' or 'unchanged'.
create or replace function public.company_web_checked(secret text, p_name_key text, p_fingerprint text)
returns text language plpgsql security definer set search_path = '' as $$
declare old_fp text; read_at timestamptz; st text;
begin
  perform private.check_secret(secret);
  select fingerprint, crawled_at, status into old_fp, read_at, st from public.company_web where name_key = p_name_key;
  if st is distinct from 'done' then
    return 'unchanged';
  end if;
  if (p_fingerprint is not null and old_fp is not null and p_fingerprint <> old_fp)
     or read_at is null or read_at < now() - interval '30 days' then
    update public.company_web
       set status = 'queued', stage = 'queued', requested_at = now(), attempts = 0, checked_at = now(),
           fingerprint = coalesce(p_fingerprint, fingerprint)
     where name_key = p_name_key;
    return 'queued';
  end if;
  update public.company_web set checked_at = now(), fingerprint = coalesce(p_fingerprint, fingerprint)
   where name_key = p_name_key;
  return 'unchanged';
end; $$;

revoke execute on function public.company_web_due_checks(text, int), public.company_web_checked(text, text, text)
  from public;
grant execute on function public.company_web_due_checks(text, int), public.company_web_checked(text, text, text)
  to anon;
