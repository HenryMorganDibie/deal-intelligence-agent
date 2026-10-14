-- Live outcome observations for the measured tables: one compact row per labelled signal,
-- pooled with the backtest so confidence and expected moves follow the market.
create or replace function public.outcome_rows(secret text)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  perform private.check_secret(secret);
  return coalesce((
    select jsonb_agg(jsonb_build_object(
      'signal_type', o.signal_type,
      'severity_at_detection', o.payload->>'severity_at_detection',
      'event_confirmed', o.event_confirmed,
      'direction_correct', (o.payload->>'direction_correct')::boolean,
      'abnormal_return_10d_pct', (o.payload->>'abnormal_return_10d_pct')::numeric,
      'market', o.market))
    from public.outcomes o
  ), '[]'::jsonb);
end;
$$;

revoke execute on function public.outcome_rows(text) from public;
grant execute on function public.outcome_rows(text) to anon;
