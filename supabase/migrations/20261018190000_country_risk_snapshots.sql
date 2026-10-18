-- Auditable country-risk snapshots. No direct table access; all writes/reads use secret-checked RPCs.
create table if not exists public.country_risk_snapshots (
  country_iso2 text not null check (country_iso2 ~ '^[A-Z]{2}$'),
  country_iso3 text not null check (country_iso3 ~ '^[A-Z]{3}$'),
  country_name text not null,
  snapshot_date date not null,
  captured_at timestamptz not null,
  score numeric(5,1),
  tier text,
  coverage numeric(4,3) not null default 0,
  data_as_of date,
  source text not null,
  source_url text not null,
  method text not null,
  snapshot_kind text not null default 'observed_at_capture',
  payload jsonb not null,
  created_at timestamptz not null default now(),
  primary key (country_iso2, snapshot_date)
);
create index if not exists country_risk_snapshots_date_idx on public.country_risk_snapshots (snapshot_date desc);
alter table public.country_risk_snapshots enable row level security;
revoke all on public.country_risk_snapshots from public, anon, authenticated;

create or replace function public.upsert_country_risk_snapshots(secret text, p_rows jsonb)
returns int language plpgsql security definer set search_path = '' as $$
declare n int;
begin
  perform private.check_secret(secret);
  if jsonb_typeof(p_rows) <> 'array' or jsonb_array_length(p_rows) <> 54 then
    raise exception 'expected exactly 54 country risk snapshots';
  end if;
  insert into public.country_risk_snapshots (
    country_iso2, country_iso3, country_name, snapshot_date, captured_at, score, tier,
    coverage, data_as_of, source, source_url, method, snapshot_kind, payload
  )
  select r->>'iso2', r->>'iso3', r->>'country_name', (r->>'snapshot_date')::date,
         (r->>'captured_at')::timestamptz, nullif(r->>'score','')::numeric, r->>'tier',
         coalesce(nullif(r->>'coverage','')::numeric, 0), nullif(r->>'data_as_of','')::date,
         r->>'source', r->>'source_url', r->>'method', coalesce(r->>'snapshot_kind','observed_at_capture'), r
  from jsonb_array_elements(p_rows) r
  on conflict (country_iso2, snapshot_date) do update set
    country_iso3 = excluded.country_iso3, country_name = excluded.country_name,
    captured_at = excluded.captured_at, score = excluded.score, tier = excluded.tier,
    coverage = excluded.coverage, data_as_of = excluded.data_as_of, source = excluded.source,
    source_url = excluded.source_url, method = excluded.method, snapshot_kind = excluded.snapshot_kind,
    payload = excluded.payload;
  get diagnostics n = row_count;
  return n;
end; $$;

create or replace function public.list_country_risk_snapshots(secret text, p_iso2 text, p_limit int default 30)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  if p_iso2 !~ '^[A-Z]{2}$' then raise exception 'invalid country code'; end if;
  return (
    select coalesce(jsonb_agg(jsonb_build_object(
      'iso2', country_iso2, 'iso3', country_iso3, 'country_name', country_name,
      'snapshot_date', snapshot_date, 'captured_at', captured_at, 'score', score, 'tier', tier,
      'coverage', coverage, 'data_as_of', data_as_of, 'source', source, 'source_url', source_url,
      'method', method, 'snapshot_kind', snapshot_kind
    ) order by snapshot_date), '[]'::jsonb)
    from (
      select * from public.country_risk_snapshots where country_iso2 = p_iso2
      order by snapshot_date desc limit greatest(1, least(coalesce(p_limit, 30), 365))
    ) s
  );
end; $$;

revoke execute on function public.upsert_country_risk_snapshots(text, jsonb) from public;
revoke execute on function public.list_country_risk_snapshots(text, text, int) from public;
grant execute on function public.upsert_country_risk_snapshots(text, jsonb) to anon;
grant execute on function public.list_country_risk_snapshots(text, text, int) to anon;
