-- Company-submitted facts: a person at a company adds what no public source has (headcount, revenue range, founding
-- year, a description, the latest round). Shown as "submitted by the company, not verified", never mixed with
-- verified data.
--
-- Ownership check, done here so nothing a browser sends can fake it: the submitter's confirmed email must be at the
-- domain of the company's website as stored by the enrichment worker (public.company_web). A match publishes the
-- facts; a company with no stored website is held for the owner's review; a mismatch or a free-mail address is
-- refused. The owner can publish or remove any submission. No direct table access for any client role.

create table if not exists public.company_claims (
  id uuid primary key default gen_random_uuid(),
  name_key text not null check (char_length(name_key) between 2 and 120),
  company text not null check (char_length(company) between 2 and 200),
  submitted_by uuid not null references auth.users (id) on delete cascade,
  submitter_email text not null,
  email_domain text not null,
  site_domain text,
  status text not null check (status in ('published', 'pending', 'removed')),
  facts jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (name_key, submitted_by)
);
create index if not exists company_claims_key_idx on public.company_claims (name_key, status, updated_at desc);
alter table public.company_claims enable row level security;
revoke all on public.company_claims from public, anon, authenticated;

-- 'https://www.Acme.co.ke/about' -> 'acme.co.ke'
create or replace function private.host_of(p_url text) returns text
language sql immutable set search_path = '' as $$
  select nullif(regexp_replace(lower(split_part(regexp_replace(coalesce(p_url, ''), '^[a-zA-Z]+://', ''), '/', 1)),
                               '^www\.', ''), '');
$$;

-- Only these fields, each checked; anything else is dropped.
create or replace function private.clean_company_facts(p jsonb) returns jsonb
language plpgsql stable set search_path = '' as $$
declare out jsonb := '{}'::jsonb; v text; n numeric;
begin
  if p is null or jsonb_typeof(p) <> 'object' then raise exception 'invalid_facts'; end if;
  v := nullif(btrim(p->>'employees'), '');
  if v is not null then
    if v not in ('1-10', '11-50', '51-200', '201-500', '501-1000', '1000+') then raise exception 'invalid_employees'; end if;
    out := out || jsonb_build_object('employees', v);
  end if;
  v := nullif(btrim(p->>'revenue_usd'), '');
  if v is not null then
    if v not in ('under 1m', '1m-5m', '5m-20m', '20m-100m', 'over 100m') then raise exception 'invalid_revenue'; end if;
    out := out || jsonb_build_object('revenue_usd', v);
  end if;
  v := nullif(btrim(p->>'founded'), '');
  if v is not null then
    if v !~ '^\d{4}$' then raise exception 'invalid_founded'; end if;      -- checked before the cast below
    if v::int < 1800 or v::int > extract(year from now())::int then raise exception 'invalid_founded'; end if;
    out := out || jsonb_build_object('founded', v::int);
  end if;
  v := nullif(btrim(p->>'total_raised_usd'), '');
  if v is not null then
    begin n := v::numeric; exception when others then raise exception 'invalid_raised'; end;
    if n < 0 or n > 100000000000 then raise exception 'invalid_raised'; end if;
    out := out || jsonb_build_object('total_raised_usd', n);
  end if;
  v := nullif(btrim(p->>'latest_round'), '');
  if v is not null then out := out || jsonb_build_object('latest_round', left(v, 60)); end if;
  v := nullif(btrim(p->>'headquarters'), '');
  if v is not null then out := out || jsonb_build_object('headquarters', left(v, 80)); end if;
  v := nullif(btrim(p->>'description'), '');
  if v is not null then out := out || jsonb_build_object('description', left(v, 600)); end if;
  if out = '{}'::jsonb then raise exception 'no_facts'; end if;
  return out;
end; $$;

create or replace function public.submit_company_facts(p_name_key text, p_company text, p_facts jsonb)
returns text
language plpgsql security definer set search_path to '' as $$
declare
  v_uid uuid := auth.uid();
  v_email text; v_confirmed timestamptz; v_domain text; v_site text; v_status text; v_facts jsonb;
begin
  if v_uid is null then raise exception 'not_signed_in'; end if;
  if not public.mfa_satisfied() then raise exception 'second_factor_required'; end if;
  if p_name_key is null or char_length(p_name_key) not between 2 and 120
     or p_company is null or char_length(btrim(p_company)) not between 2 and 200 then
    raise exception 'invalid_company';
  end if;
  select email, email_confirmed_at into v_email, v_confirmed from auth.users where id = v_uid;
  if v_email is null or v_confirmed is null then raise exception 'email_not_confirmed'; end if;
  v_domain := lower(split_part(v_email, '@', 2));
  if v_domain in ('gmail.com', 'googlemail.com', 'yahoo.com', 'yahoo.co.uk', 'outlook.com', 'hotmail.com', 'live.com',
                  'icloud.com', 'me.com', 'aol.com', 'proton.me', 'protonmail.com', 'gmx.com', 'mail.com',
                  'yandex.com', 'zoho.com') then
    raise exception 'company_email_required';
  end if;
  v_facts := private.clean_company_facts(p_facts);
  select private.host_of(w.website) into v_site from public.company_web w where w.name_key = p_name_key;
  if v_site is null then
    v_status := 'pending';                                   -- nothing to check against: the owner reviews it
  elsif v_domain = v_site or v_domain like '%.' || v_site or v_site like '%.' || v_domain then
    v_status := 'published';
  else
    raise exception 'email_domain_mismatch';
  end if;
  insert into public.company_claims (name_key, company, submitted_by, submitter_email, email_domain, site_domain,
                                     status, facts)
  values (p_name_key, btrim(p_company), v_uid, v_email, v_domain, v_site, v_status, v_facts)
  on conflict (name_key, submitted_by) do update
     set facts = excluded.facts, company = excluded.company, submitter_email = excluded.submitter_email,
         email_domain = excluded.email_domain, site_domain = excluded.site_domain, updated_at = now(),
         -- a removed submission stays removed; resubmitting does not restore it
         status = case when public.company_claims.status = 'removed' then 'removed' else excluded.status end;
  select status into v_status from public.company_claims where name_key = p_name_key and submitted_by = v_uid;
  return v_status;
end; $$;
revoke all on function public.submit_company_facts(text, text, jsonb) from public, anon;
grant execute on function public.submit_company_facts(text, text, jsonb) to authenticated;

-- The latest published submission for a company, for its profile: the facts and the email domain, never the email.
create or replace function public.company_claims_for(secret text, p_name_key text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare r jsonb;
begin
  perform private.check_secret(secret);
  select jsonb_build_object('facts', c.facts, 'email_domain', c.email_domain, 'updated_at', c.updated_at)
    into r
    from public.company_claims c
   where c.name_key = p_name_key and c.status = 'published'
   order by c.updated_at desc
   limit 1;
  return r;
end; $$;

-- The owner's review list and decisions.
create or replace function public.admin_company_claims(secret text, p_status text default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return coalesce((
    select jsonb_agg(jsonb_build_object('id', c.id, 'company', c.company, 'name_key', c.name_key,
                                        'email', c.submitter_email, 'email_domain', c.email_domain,
                                        'site_domain', c.site_domain, 'status', c.status, 'facts', c.facts,
                                        'updated_at', c.updated_at) order by c.updated_at desc)
      from (select * from public.company_claims
             where p_status is null or status = p_status
             order by updated_at desc limit 200) c), '[]'::jsonb);
end; $$;

create or replace function public.admin_set_company_claim(secret text, p_id uuid, p_status text)
returns text language plpgsql security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  if p_status not in ('published', 'pending', 'removed') then raise exception 'invalid_status'; end if;
  update public.company_claims set status = p_status, updated_at = now() where id = p_id;
  if not found then raise exception 'claim_not_found'; end if;
  return p_status;
end; $$;
-- The three functions above are guarded by the API's shared secret, like every other server-side function: the API
-- calls them with the publishable key, so their default execute grant stays.
