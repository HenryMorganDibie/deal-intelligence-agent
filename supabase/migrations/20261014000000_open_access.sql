-- Open access: no accounts. Anyone can run an analysis; briefs are reachable by
-- their unguessable id (a shareable link). Writes and quota checks go through
-- functions that require a server-only secret held by the API, so the public
-- (publishable) key can read a brief by id and nothing else.
--
-- After applying, store the secret once (never commit it):
--   insert into private.config (key, value) values ('api_secret', '<secret>')
--     on conflict (key) do update set value = excluded.value;
-- and set the same value as DEAL_INTEL_API_SECRET on the API project.

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table if not exists private.config (
  key text primary key,
  value text not null
);

-- Briefs no longer belong to an account.
alter table public.briefs alter column user_id drop not null;
alter table public.briefs add column if not exists client_hash text;

-- Usage log: one row per analysis attempt, for rate limiting and for seeing how
-- many people use the app. client_hash is a salted hash of the caller's IP,
-- never the IP itself.
create table if not exists public.runs (
  id bigint generated always as identity primary key,
  client_hash text not null,
  company text not null,
  ticker text,
  status text not null default 'started',
  brief_id uuid references public.briefs(id) on delete set null,
  created_at timestamptz not null default now()
);
create index if not exists runs_client_created_idx on public.runs (client_hash, created_at desc);
create index if not exists runs_created_idx on public.runs (created_at desc);
alter table public.runs enable row level security;   -- no policies: functions only

create or replace function private.check_secret(secret text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if secret is null or secret <> (select value from private.config where key = 'api_secret') then
    raise exception 'forbidden' using errcode = '42501';
  end if;
end;
$$;

-- Reserve one run. Returns the run id, or raises 'client_limit' / 'global_limit'.
create or replace function public.start_run(
  secret text, p_client_hash text, p_company text, p_ticker text,
  per_client_daily int, global_daily int
)
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  since timestamptz := date_trunc('day', now() at time zone 'utc') at time zone 'utc';
  run_id bigint;
begin
  perform private.check_secret(secret);
  perform pg_advisory_xact_lock(hashtext('deal_intel_runs'));
  if (select count(*) from public.runs where client_hash = p_client_hash and created_at >= since) >= per_client_daily then
    raise exception 'client_limit';
  end if;
  if (select count(*) from public.runs where created_at >= since) >= global_daily then
    raise exception 'global_limit';
  end if;
  insert into public.runs (client_hash, company, ticker) values (p_client_hash, p_company, p_ticker)
  returning id into run_id;
  return run_id;
end;
$$;

-- Store a finished brief and close the run. Returns the brief id.
create or replace function public.finish_run(
  secret text, p_run_id bigint, p_company text, p_ticker text, p_severity text,
  p_signal_count int, p_llm_used boolean, p_brief jsonb, p_markdown text
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  new_id uuid;
  hash text;
begin
  perform private.check_secret(secret);
  select client_hash into hash from public.runs where id = p_run_id;
  insert into public.briefs (company, ticker, severity, signal_count, llm_used, brief, markdown, client_hash)
  values (p_company, p_ticker, p_severity, p_signal_count, p_llm_used, p_brief, p_markdown, hash)
  returning id into new_id;
  update public.runs set status = 'done', brief_id = new_id where id = p_run_id;
  return new_id;
end;
$$;

create or replace function public.fail_run(secret text, p_run_id bigint)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform private.check_secret(secret);
  update public.runs set status = 'failed' where id = p_run_id;
end;
$$;

-- Public: fetch one brief by id. Ids are random UUIDs, so this is a share link,
-- not a listing.
create or replace function public.get_brief(p_id uuid)
returns table (id uuid, company text, ticker text, brief jsonb, markdown text, created_at timestamptz)
language sql
stable
security definer
set search_path = ''
as $$
  select b.id, b.company, b.ticker, b.brief, b.markdown, b.created_at
  from public.briefs b where b.id = p_id;
$$;

-- Usage at a glance (run in the SQL editor): runs and distinct visitors per day.
create or replace view private.daily_usage as
  select date_trunc('day', created_at)::date as day,
         count(*) as runs,
         count(distinct client_hash) as visitors,
         count(*) filter (where status = 'done') as completed,
         count(*) filter (where status = 'failed') as failed
  from public.runs group by 1 order by 1 desc;

revoke execute on function private.check_secret(text) from public, anon, authenticated;
revoke execute on function public.start_run(text, text, text, text, int, int) from public;
revoke execute on function public.finish_run(text, bigint, text, text, text, int, boolean, jsonb, text) from public;
revoke execute on function public.fail_run(text, bigint) from public;
grant execute on function public.start_run(text, text, text, text, int, int) to anon;
grant execute on function public.finish_run(text, bigint, text, text, text, int, boolean, jsonb, text) to anon;
grant execute on function public.fail_run(text, bigint) to anon;
grant execute on function public.get_brief(uuid) to anon, authenticated;

-- The account-era objects (owner-only policies on briefs, the usage table and
-- consume_run()) are left in place but unused; signed-in users no longer exist.
revoke execute on function public.consume_run(int) from authenticated;
