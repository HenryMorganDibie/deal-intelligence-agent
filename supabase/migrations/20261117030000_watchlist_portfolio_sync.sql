-- Keep a portfolio's alerts watchlist in step with its holdings. The signed-in owner adds and removes company names;
-- names typed into the watchlist by hand are never removed unless the caller names them. Only company names are
-- sent: quantities and prices stay in the browser.
create or replace function public.update_my_watchlist_companies(p_id uuid, p_add text[], p_remove text[])
returns text[]
language plpgsql security definer set search_path to '' as $$
declare
  v_uid uuid := auth.uid();
  v_current text[];
  v_next text[];
begin
  if v_uid is null then raise exception 'not_signed_in'; end if;
  if not public.mfa_satisfied() then raise exception 'second_factor_required'; end if;
  select w.companies into v_current from public.watchlists w
   where w.id = p_id and w.deleted_at is null and w.owner_user = v_uid
   for update;
  if not found then raise exception 'watchlist_not_found'; end if;
  if coalesce(cardinality(p_add), 0) > 200 or coalesce(cardinality(p_remove), 0) > 200 then
    raise exception 'too_many_companies';
  end if;

  -- Keep current names not being removed (case-insensitive), then append new names not already present.
  select coalesce(array_agg(c order by ord), '{}') into v_next
    from unnest(coalesce(v_current, '{}')) with ordinality as t(c, ord)
   where lower(btrim(c)) <> all (select lower(btrim(r)) from unnest(coalesce(p_remove, '{}')) r);
  select v_next || coalesce(array_agg(a order by ord), '{}') into v_next
    from (select distinct on (lower(btrim(x))) left(btrim(x), 80) as a, ord
            from unnest(coalesce(p_add, '{}')) with ordinality as t(x, ord)
           where btrim(x) <> '' order by lower(btrim(x)), ord) n
   where lower(a) <> all (select lower(btrim(c)) from unnest(v_next) c);

  if cardinality(v_next) > 200 then raise exception 'too_many_companies'; end if;
  if cardinality(v_next) = 0 and cardinality(coalesce((select w.countries from public.watchlists w where w.id = p_id), '{}')) = 0 then
    raise exception 'watchlist_empty';
  end if;
  update public.watchlists w set companies = v_next where w.id = p_id;
  return v_next;
end; $$;

revoke all on function public.update_my_watchlist_companies(uuid, text[], text[]) from public, anon;
grant execute on function public.update_my_watchlist_companies(uuid, text[], text[]) to authenticated;
