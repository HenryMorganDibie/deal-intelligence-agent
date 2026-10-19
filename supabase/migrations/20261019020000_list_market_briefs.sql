create or replace function public.list_market_briefs(p_limit int default 20)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', b.id,
    'title', b.title,
    'created_at', b.created_at,
    'scope_label', b.report->>'scope_label',
    'period_start', b.report->>'period_start',
    'period_end', b.report->>'period_end',
    'transaction_count', coalesce(b.report->'metrics'->>'transaction_count', '0')
  ) order by b.created_at desc), '[]'::jsonb)
  from (
    select id, title, created_at, report
    from public.market_briefs
    order by created_at desc
    limit greatest(least(coalesce(p_limit, 20), 50), 1)
  ) b;
$$;
revoke execute on function public.list_market_briefs(int) from public;
grant execute on function public.list_market_briefs(int) to anon, authenticated;