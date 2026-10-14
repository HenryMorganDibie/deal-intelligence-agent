-- Daily NGX / NSE Kenya closes (and the two All-Share indices), snapshotted by the
-- daily cron, because neither exchange publishes free per-stock history.
create table if not exists public.african_prices (
  market text not null,          -- 'ngx' | 'nse'
  symbol text not null,          -- exchange code, or '^ASI' / '^NASI'
  day date not null,
  close double precision not null,
  primary key (market, symbol, day)
);
alter table public.african_prices enable row level security;   -- functions only

create or replace function public.save_prices(secret text, p_rows jsonb)
returns int
language plpgsql
security definer
set search_path = ''
as $$
declare n int;
begin
  perform private.check_secret(secret);
  insert into public.african_prices (market, symbol, day, close)
  select r->>'market', r->>'symbol', (r->>'day')::date, (r->>'close')::double precision
  from jsonb_array_elements(coalesce(p_rows, '[]'::jsonb)) r
  on conflict (market, symbol, day) do update set close = excluded.close;
  get diagnostics n = row_count;
  return n;
end;
$$;

-- {"ngx": {"DANGCEM": {"2026-10-13": 1066.7}}, ...} for closes since p_since.
create or replace function public.get_prices(secret text, p_since date)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  perform private.check_secret(secret);
  return coalesce((
    select jsonb_object_agg(market, symbols) from (
      select market, jsonb_object_agg(symbol, days) as symbols from (
        select market, symbol, jsonb_object_agg(day::text, close) as days
        from public.african_prices where day >= p_since
        group by market, symbol
      ) s group by market
    ) m
  ), '{}'::jsonb);
end;
$$;

revoke execute on function public.save_prices(text, jsonb) from public;
revoke execute on function public.get_prices(text, date) from public;
grant execute on function public.save_prices(text, jsonb) to anon;
grant execute on function public.get_prices(text, date) to anon;
