-- Election news: one row per story (several outlets' reports merged), tagged by candidate, party, state, topic
-- and race (src/engines/election_news.py). Reached only through the shared-secret functions below; no direct
-- table access for any client role.
create table if not exists public.election_news (
  id text primary key,
  day date,
  data jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists election_news_day_idx on public.election_news (day desc);
alter table public.election_news enable row level security;
revoke all on public.election_news from public, anon, authenticated;

-- New stories are inserted; a story that gained reports or tags is replaced.
create or replace function public.upsert_election_news(secret text, p_rows jsonb)
returns integer language plpgsql security definer set search_path = '' as $$
declare n int;
begin
  perform private.check_secret(secret);
  insert into public.election_news (id, day, data)
  select r->>'id', nullif(r->>'day', '')::date, r from jsonb_array_elements(p_rows) r
  on conflict (id) do update set data = excluded.data, day = excluded.day, updated_at = now()
    where public.election_news.data is distinct from excluded.data;
  get diagnostics n = row_count;
  return n;
end; $$;

-- Stories on or after a day, newest first.
create or replace function public.list_election_news(secret text, p_since date, p_limit integer default 5000)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return (select coalesce(jsonb_agg(s.data order by s.day desc, s.id), '[]'::jsonb)
          from (select data, day, id from public.election_news
                 where day >= p_since order by day desc, id limit greatest(1, least(coalesce(p_limit, 5000), 20000))) s);
end; $$;

revoke execute on function public.upsert_election_news(text, jsonb) from public, authenticated;
revoke execute on function public.list_election_news(text, date, integer) from public, authenticated;
grant execute on function public.upsert_election_news(text, jsonb) to anon;
grant execute on function public.list_election_news(text, date, integer) to anon;
