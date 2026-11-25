-- Daily price history before the daily snapshots began (28 October 2026), packed one row per listing per year:
-- `days` holds each trading day's day of the year and `closes` its close, in the same order. About 1,600 listings
-- since 2010 would be some 3.7 million one-row-per-day rows (about 400 MB); packed by year it is about 27,000 rows
-- and tens of MB, inside the free database. Filled by scripts/backfill_price_history.py; closes are as the source
-- reports them, adjusted for splits. market_history reads it after the snapshots and the NGX/NSE archive.

create table if not exists public.price_history_years (
  exchange text not null,
  symbol text not null,
  year smallint not null check (year between 1990 and 2100),
  days smallint[] not null,
  closes real[] not null,
  source text not null,
  updated_at timestamptz not null default now(),
  primary key (exchange, symbol, year),
  check (cardinality(days) = cardinality(closes))
);
alter table public.price_history_years enable row level security;
revoke all on public.price_history_years from anon, authenticated;

-- Save years of history: [{exchange, symbol, year, days: [...], closes: [...], source}, ...]. A year saved again is
-- replaced whole.
create or replace function public.upsert_price_history(secret text, p_rows jsonb)
returns int
language plpgsql
security definer
set search_path = ''
as $$
declare n int;
begin
  perform private.check_secret(secret);
  insert into public.price_history_years as h (exchange, symbol, year, days, closes, source, updated_at)
  select lower(r->>'exchange'), upper(r->>'symbol'), (r->>'year')::smallint,
         array(select jsonb_array_elements_text(r->'days')::smallint),
         array(select jsonb_array_elements_text(r->'closes')::real),
         r->>'source', now()
  from jsonb_array_elements(coalesce(p_rows, '[]'::jsonb)) r
  where jsonb_array_length(r->'days') = jsonb_array_length(r->'closes') and jsonb_array_length(r->'days') > 0
  on conflict (exchange, symbol, year) do update
    set days = excluded.days, closes = excluded.closes, source = excluded.source, updated_at = now();
  get diagnostics n = row_count;
  return n;
end; $$;

-- The years already saved for each listing on an exchange, so a backfill can resume: {symbol: [year, ...]}.
create or replace function public.price_history_years_saved(secret text, p_exchange text)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  perform private.check_secret(secret);
  return coalesce((select jsonb_object_agg(symbol, years) from (
    select symbol, jsonb_agg(year order by year) as years from public.price_history_years
    where exchange = lower(p_exchange) group by symbol) s), '{}'::jsonb);
end; $$;

create or replace function public.market_history(secret text, p_exchange text, p_symbol text, p_currency text default null,
                                                 p_since date default null)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  perform private.check_secret(secret);
  if p_exchange !~ '^[a-z]{2,8}$' or p_symbol !~ '^[A-Za-z0-9 ._&/-]{1,60}$' then
    raise exception 'invalid listing' using errcode = '22023';
  end if;
  return jsonb_build_object(
    'prices', coalesce((
      select jsonb_agg(jsonb_build_object('date', d, 'close', close, 'chg_1d', chg_1d, 'volume', volume,
                                          'value_traded', value_traded, 'mcap', mcap, 'source', source) order by d)
      from (
        select distinct on (d) d, close, chg_1d, volume, value_traded, mcap, source
        from (
          select (r->>'date')::date as d, (r->>'price')::numeric as close, (r->>'chg_1d')::numeric as chg_1d,
                 (r->>'volume')::numeric as volume, (r->>'value')::numeric as value_traded,
                 (r->>'mcap')::numeric as mcap, coalesce(r->>'source', 'daily snapshot') as source, 1 as pri, s.captured_at
          from public.market_snapshots s
          cross join lateral jsonb_array_elements(coalesce(s.payload->'rows', '[]'::jsonb)) r
          where s.kind = 'quotes' and s.scope = p_exchange
            and upper(r->>'symbol') = upper(p_symbol)
            and r->>'date' ~ '^\d{4}-\d{2}-\d{2}$'
            and jsonb_typeof(r->'price') = 'number' and (r->>'price')::numeric > 0
          union all
          select a.day, a.close, null, null, null, null, 'daily close archive', 2, null
          from public.african_prices a
          where a.market = p_exchange and upper(a.symbol) = upper(p_symbol) and a.close > 0
          union all
          select make_date(h.year, 1, 1) + (u.dd - 1), u.cc::numeric, null, null, null, null, h.source, 3, null
          from public.price_history_years h
          cross join lateral unnest(h.days, h.closes) as u(dd, cc)
          where h.exchange = p_exchange and h.symbol = upper(p_symbol) and u.cc > 0
            and (p_since is null or h.year >= extract(year from p_since))
        ) x
        where p_since is null or d >= p_since
        order by d, pri, captured_at desc nulls last
      ) y
    ), '[]'::jsonb),
    'fx', coalesce((
      select jsonb_object_agg(snapshot_date::text, rate)
      from (
        select distinct on (snapshot_date) snapshot_date, (payload->'rates'->>upper(p_currency))::numeric as rate
        from public.market_snapshots
        where kind = 'fx' and p_currency is not null
          and jsonb_typeof(payload->'rates'->upper(p_currency)) = 'number'
          and (p_since is null or snapshot_date >= p_since - 7)
        order by snapshot_date, captured_at desc
      ) f
    ), '{}'::jsonb)
  );
end;
$$;

revoke execute on function public.upsert_price_history(text, jsonb), public.price_history_years_saved(text, text),
  public.market_history(text, text, text, text, date) from public;
grant execute on function public.upsert_price_history(text, jsonb), public.price_history_years_saved(text, text),
  public.market_history(text, text, text, text, date) to anon;
