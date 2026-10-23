-- Bounded JSON-array pages for hosted market history.
-- Each call aggregates at most 500 rows instead of sorting/aggregating the full history.
-- Existing list_deals/list_events RPCs remain available for backward compatibility.

create or replace function public.list_deals_page(
  secret text, p_since date, p_limit integer, p_offset integer
) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
  page_limit integer := greatest(1, least(coalesce(p_limit, 500), 1000));
  page_offset integer := greatest(0, coalesce(p_offset, 0));
begin
  perform private.check_secret(secret);
  return (
    select coalesce(jsonb_agg(page.data order by page.announced desc nulls last, page.id asc), '[]'::jsonb)
    from (
      select d.id, d.announced, d.data
      from public.deals d
      where d.announced is null or d.announced >= p_since
      order by d.announced desc nulls last, d.id asc
      limit page_limit offset page_offset
    ) page
  );
end; $$;

create or replace function public.list_events_page(
  secret text, p_since date, p_limit integer, p_offset integer
) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
  page_limit integer := greatest(1, least(coalesce(p_limit, 500), 1000));
  page_offset integer := greatest(0, coalesce(p_offset, 0));
begin
  perform private.check_secret(secret);
  return (
    select coalesce(jsonb_agg(page.data order by page.day desc nulls last, page.id asc), '[]'::jsonb)
    from (
      select e.id, e.day, e.data
      from public.events e
      where e.day is null or e.day >= p_since
      order by e.day desc nulls last, e.id asc
      limit page_limit offset page_offset
    ) page
  );
end; $$;

revoke execute on function public.list_deals_page(text, date, integer, integer) from public;
revoke execute on function public.list_events_page(text, date, integer, integer) from public;
grant execute on function public.list_deals_page(text, date, integer, integer) to anon;
grant execute on function public.list_events_page(text, date, integer, integer) to anon;
