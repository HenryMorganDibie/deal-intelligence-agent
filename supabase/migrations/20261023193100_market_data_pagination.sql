-- Bounded JSON-array pages for hosted market history.
-- Keyset pagination by immutable primary key avoids offset shifts between requests.
-- Each call aggregates at most 500 rows; existing RPCs remain for compatibility.

create or replace function public.list_deals_page(
  secret text, p_since date, p_limit integer, p_after_id text, p_max_id text
) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
  page_limit integer := greatest(1, least(coalesce(p_limit, 500), 1000));
  upper_id text;
  page_rows jsonb;
begin
  perform private.check_secret(secret);
  if p_max_id is null then
    select max(d.id) into upper_id
    from public.deals d
    where (d.announced is null or d.announced >= p_since);
  else
    upper_id := p_max_id;
  end if;
  select coalesce(jsonb_agg(page.data order by page.id asc), '[]'::jsonb)
    into page_rows
  from (
    select d.id, d.data
    from public.deals d
    where (d.announced is null or d.announced >= p_since)
      and upper_id is not null
      and d.id <= upper_id
      and (p_after_id is null or d.id > p_after_id)
    order by d.id asc
    limit page_limit
  ) page;
  return jsonb_build_object('max_id', upper_id, 'rows', page_rows);
end; $$;

create or replace function public.list_events_page(
  secret text, p_since date, p_limit integer, p_after_id text, p_max_id text
) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
  page_limit integer := greatest(1, least(coalesce(p_limit, 500), 1000));
  upper_id text;
  page_rows jsonb;
begin
  perform private.check_secret(secret);
  if p_max_id is null then
    select max(e.id) into upper_id
    from public.events e
    where (e.day is null or e.day >= p_since);
  else
    upper_id := p_max_id;
  end if;
  select coalesce(jsonb_agg(page.data order by page.id asc), '[]'::jsonb)
    into page_rows
  from (
    select e.id, e.data
    from public.events e
    where (e.day is null or e.day >= p_since)
      and upper_id is not null
      and e.id <= upper_id
      and (p_after_id is null or e.id > p_after_id)
    order by e.id asc
    limit page_limit
  ) page;
  return jsonb_build_object('max_id', upper_id, 'rows', page_rows);
end; $$;

revoke execute on function public.list_deals_page(text, date, integer, text, text) from public;
revoke execute on function public.list_events_page(text, date, integer, text, text) from public;
grant execute on function public.list_deals_page(text, date, integer, text, text) to anon;
grant execute on function public.list_events_page(text, date, integer, text, text) to anon;
