-- Daily price history for one listed share, from what the platform already stores: every daily quotes snapshot
-- (all 24 exchanges, since late October 2026) and the older daily-close archive kept for NGX and NSE Kenya.
-- Each snapshot row carries the date of its own price, so one trading day is counted once: a share that did not
-- trade keeps its last trading date and is not repeated. Where both sources hold a day, the snapshot (which also
-- has volume, value traded and market value) wins. Also returns the currency's dollar rate for each stored day,
-- so the API can give a dollar close beside the local one.

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
                 (r->>'mcap')::numeric as mcap, r->>'source' as source, 1 as pri, s.captured_at
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

revoke execute on function public.market_history(text, text, text, text, date) from public;
grant execute on function public.market_history(text, text, text, text, date) to anon;
