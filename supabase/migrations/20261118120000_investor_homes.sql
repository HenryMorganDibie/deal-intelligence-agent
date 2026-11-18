-- Investor home countries that the registry and headlines cannot supply.
--
-- Two sources write here: the owner, from the admin page's review list ("owner"), and the weekly article reader, which
-- picks up phrases such as "X, a London-based fund" from source articles it is allowed to read ("article"). The owner's
-- choice always wins: the reader never overwrites an owner row, and the owner can confirm, change or clear any row.
-- Readable only with the server secret, like the other admin data.

create table if not exists public.investor_homes (
  name_key text primary key check (length(name_key) between 1 and 160),
  name text not null check (length(name) between 1 and 160),
  country text check (country is null or country ~ '^[A-Z]{2}$'),   -- null: the owner marked it "no single country"
  source text not null check (source in ('owner', 'article')),
  evidence text check (evidence is null or length(evidence) <= 400),  -- the article sentence, for the reader's rows
  evidence_url text check (evidence_url is null or length(evidence_url) <= 600),
  updated_at timestamptz not null default now()
);
alter table public.investor_homes enable row level security;
revoke all on table public.investor_homes from public, anon, authenticated;

create or replace function public.investor_homes_all(secret text)
returns jsonb language plpgsql stable security definer set search_path to ''
as $function$
begin
  perform private.check_secret(secret);
  return coalesce((select jsonb_agg(jsonb_build_object('name_key', h.name_key, 'name', h.name, 'country', h.country,
                                                       'source', h.source, 'evidence', h.evidence,
                                                       'evidence_url', h.evidence_url, 'updated_at', h.updated_at))
                     from public.investor_homes h), '[]'::jsonb);
end; $function$;

-- The owner sets, changes or clears a country. p_clear removes the row entirely (back to "unknown").
create or replace function public.admin_set_investor_home(secret text, p_name_key text, p_name text, p_country text,
                                                          p_clear boolean default false)
returns jsonb language plpgsql security definer set search_path to ''
as $function$
begin
  perform private.check_secret(secret);
  if p_clear then
    delete from public.investor_homes where name_key = p_name_key;
    return jsonb_build_object('name_key', p_name_key, 'cleared', true);
  end if;
  insert into public.investor_homes (name_key, name, country, source, evidence, evidence_url, updated_at)
  values (p_name_key, left(p_name, 160), nullif(upper(p_country), ''), 'owner', null, null, now())
  on conflict (name_key) do update
     set name = excluded.name, country = excluded.country, source = 'owner', evidence = null, evidence_url = null,
         updated_at = now();
  return jsonb_build_object('name_key', p_name_key, 'country', nullif(upper(p_country), ''));
end; $function$;

-- The article reader adds what it found, never over an owner's row.
create or replace function public.record_investor_home_from_article(secret text, p_name_key text, p_name text,
                                                                    p_country text, p_evidence text, p_url text)
returns boolean language plpgsql security definer set search_path to ''
as $function$
begin
  perform private.check_secret(secret);
  insert into public.investor_homes (name_key, name, country, source, evidence, evidence_url, updated_at)
  values (p_name_key, left(p_name, 160), upper(p_country), 'article', left(p_evidence, 400), left(p_url, 600), now())
  on conflict (name_key) do update
     set country = excluded.country, evidence = excluded.evidence, evidence_url = excluded.evidence_url,
         updated_at = now()
   where public.investor_homes.source = 'article';
  return found;
end; $function$;
