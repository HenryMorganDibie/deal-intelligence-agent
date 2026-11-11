-- Visible rows only, for API instances that serve pages: merged duplicates and excluded non-transactions (about a
-- third of the deals and events data) are never shown, so a cold instance need not download them. Ingestion keeps
-- reading every row (list_deals_page, list_events_page): a merged report must stay known so it is not re-added.
create or replace function public.list_visible_page(
  secret text, p_kind text, p_since date, p_limit integer, p_after_id text, p_max_id text
) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
  page_limit integer := greatest(1, least(coalesce(p_limit, 500), 1000));
  upper_id text;
  page_rows jsonb;
begin
  perform private.check_secret(secret);
  if p_kind = 'deals' then
    upper_id := coalesce(p_max_id, (select max(d.id) from public.deals d
                                     where (d.announced is null or d.announced >= p_since)
                                       and coalesce(d.data->>'merged_into', '') in ('', 'false') and coalesce(d.data->>'excluded', '') in ('', 'false')));
    select coalesce(jsonb_agg(page.data order by page.id asc), '[]'::jsonb) into page_rows
    from (select d.id, d.data from public.deals d
           where (d.announced is null or d.announced >= p_since)
             and coalesce(d.data->>'merged_into', '') in ('', 'false') and coalesce(d.data->>'excluded', '') in ('', 'false')
             and upper_id is not null and d.id <= upper_id and (p_after_id is null or d.id > p_after_id)
           order by d.id asc limit page_limit) page;
  elsif p_kind = 'events' then
    upper_id := coalesce(p_max_id, (select max(e.id) from public.events e
                                     where (e.day is null or e.day >= p_since)
                                       and coalesce(e.data->>'merged_into', '') in ('', 'false') and coalesce(e.data->>'excluded', '') in ('', 'false')));
    select coalesce(jsonb_agg(page.data order by page.id asc), '[]'::jsonb) into page_rows
    from (select e.id, e.data from public.events e
           where (e.day is null or e.day >= p_since)
             and coalesce(e.data->>'merged_into', '') in ('', 'false') and coalesce(e.data->>'excluded', '') in ('', 'false')
             and upper_id is not null and e.id <= upper_id and (p_after_id is null or e.id > p_after_id)
           order by e.id asc limit page_limit) page;
  else
    raise exception 'unknown_kind' using errcode = '22023';
  end if;
  return jsonb_build_object('max_id', upper_id, 'rows', page_rows);
end; $$;

revoke execute on function public.list_visible_page(text, text, date, integer, text, text) from public, authenticated;
grant execute on function public.list_visible_page(text, text, date, integer, text, text) to anon;
