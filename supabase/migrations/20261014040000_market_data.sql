-- Deals database, corporate-event feed and watchlists (monitoring and alerts).
-- All access goes through functions that require the API secret, like the
-- rest of the hosted app; the tables have RLS on and no policies.

create table if not exists public.deals (
  id text primary key,
  announced date,
  deal_type text not null,
  country text,
  sector text,
  data jsonb not null,
  updated_at timestamptz not null default now()
);
create index if not exists deals_announced_idx on public.deals (announced desc);
alter table public.deals enable row level security;

create table if not exists public.events (
  id text primary key,
  day date,
  signal_type text not null,
  country text,
  sector text,
  data jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists events_day_idx on public.events (day desc);
alter table public.events enable row level security;

-- A watchlist has no owner account: its random id is the capability (like a
-- brief's share link). client_hash only rate-limits creation.
create table if not exists public.watchlists (
  id uuid primary key default gen_random_uuid(),
  name text not null default 'Watchlist',
  companies text[] not null default '{}',
  countries text[] not null default '{}',
  signal_types text[] not null default '{}',
  include_deals boolean not null default true,
  webhook_url text,
  client_hash text,
  last_delivered_at timestamptz,
  created_at timestamptz not null default now()
);
alter table public.watchlists enable row level security;

create or replace function public.upsert_deals(secret text, p_rows jsonb)
returns int language plpgsql security definer set search_path = '' as $$
declare n int;
begin
  perform private.check_secret(secret);
  insert into public.deals (id, announced, deal_type, country, sector, data, updated_at)
  select r->>'id', nullif(r->>'announced', '')::date, r->>'deal_type', r->>'country', r->>'sector', r, now()
  from jsonb_array_elements(p_rows) r
  on conflict (id) do update set announced = excluded.announced, deal_type = excluded.deal_type,
    country = excluded.country, sector = excluded.sector, data = excluded.data, updated_at = now();
  get diagnostics n = row_count;
  return n;
end; $$;

create or replace function public.list_deals(secret text, p_since date)
returns setof jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return query select d.data from public.deals d
    where d.announced is null or d.announced >= p_since order by d.announced desc nulls last;
end; $$;

create or replace function public.upsert_events(secret text, p_rows jsonb)
returns int language plpgsql security definer set search_path = '' as $$
declare n int;
begin
  perform private.check_secret(secret);
  insert into public.events (id, day, signal_type, country, sector, data)
  select r->>'id', nullif(r->>'day', '')::date, r->>'signal_type', r->>'country', r->>'sector', r
  from jsonb_array_elements(p_rows) r
  on conflict (id) do nothing;
  get diagnostics n = row_count;
  return n;
end; $$;

create or replace function public.list_events(secret text, p_since date)
returns setof jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return query select e.data from public.events e
    where e.day is null or e.day >= p_since order by e.day desc nulls last;
end; $$;

create or replace function public.create_watchlist(
  secret text, p_client_hash text, p_name text, p_companies text[], p_countries text[],
  p_signal_types text[], p_include_deals boolean, p_webhook_url text
) returns uuid language plpgsql security definer set search_path = '' as $$
declare new_id uuid;
begin
  perform private.check_secret(secret);
  if (select count(*) from public.watchlists w where w.client_hash = p_client_hash) >= 20 then
    raise exception 'watchlist_limit';
  end if;
  insert into public.watchlists (name, companies, countries, signal_types, include_deals, webhook_url, client_hash)
  values (coalesce(nullif(p_name, ''), 'Watchlist'), coalesce(p_companies, '{}'), coalesce(p_countries, '{}'),
          coalesce(p_signal_types, '{}'), coalesce(p_include_deals, true), nullif(p_webhook_url, ''), p_client_hash)
  returning id into new_id;
  return new_id;
end; $$;

create or replace function public.get_watchlist(secret text, p_id uuid)
returns setof public.watchlists language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return query select * from public.watchlists w where w.id = p_id;
end; $$;

create or replace function public.delete_watchlist(secret text, p_id uuid)
returns void language plpgsql security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  delete from public.watchlists w where w.id = p_id;
end; $$;

create or replace function public.webhook_watchlists(secret text)
returns setof public.watchlists language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return query select * from public.watchlists w where w.webhook_url is not null;
end; $$;

create or replace function public.mark_delivered(secret text, p_id uuid, p_at timestamptz)
returns void language plpgsql security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  update public.watchlists set last_delivered_at = p_at where id = p_id;
end; $$;

-- Research questions and reports share the per-visitor daily limit with analyses.
create or replace function public.finish_research(secret text, p_run_id bigint)
returns void language plpgsql security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  update public.runs set status = 'research' where id = p_run_id;
end; $$;

do $$
declare f text;
begin
  foreach f in array array[
    'upsert_deals(text, jsonb)', 'list_deals(text, date)', 'upsert_events(text, jsonb)', 'list_events(text, date)',
    'create_watchlist(text, text, text, text[], text[], text[], boolean, text)', 'get_watchlist(text, uuid)',
    'delete_watchlist(text, uuid)', 'webhook_watchlists(text)', 'mark_delivered(text, uuid, timestamptz)',
    'finish_research(text, bigint)']
  loop
    execute format('revoke execute on function public.%s from public', f);
    execute format('grant execute on function public.%s to anon', f);
  end loop;
end $$;
