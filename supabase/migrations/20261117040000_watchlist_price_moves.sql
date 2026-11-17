-- Price-move alerts: a watchlist can also report when a listed company it follows closes up or down by at least
-- this many percent in a day. Null means off (the default). Set by the signed-in owner only.
alter table public.watchlists
  add column if not exists price_move_pct numeric
  check (price_move_pct is null or (price_move_pct >= 2 and price_move_pct <= 50));

create or replace function public.set_my_watchlist_price_moves(p_id uuid, p_pct numeric)
returns numeric
language plpgsql security definer set search_path to '' as $$
declare v_uid uuid := auth.uid();
begin
  if v_uid is null then raise exception 'not_signed_in'; end if;
  if not public.mfa_satisfied() then raise exception 'second_factor_required'; end if;
  if p_pct is not null and (p_pct < 2 or p_pct > 50) then raise exception 'invalid_threshold'; end if;
  update public.watchlists w set price_move_pct = p_pct
   where w.id = p_id and w.deleted_at is null and w.owner_user = v_uid;
  if not found then raise exception 'watchlist_not_found'; end if;
  return p_pct;
end; $$;

revoke all on function public.set_my_watchlist_price_moves(uuid, numeric) from public, anon;
grant execute on function public.set_my_watchlist_price_moves(uuid, numeric) to authenticated;
-- Price-move alerts can be reviewed and dismissed like events and deals.
create or replace function public.upsert_watchlist_review(secret text, p_id uuid, p_alert_key text, p_state text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  if p_alert_key is null or length(p_alert_key) < 3 or length(p_alert_key) > 300
     or p_alert_key !~ '^(event|deal|price):.+' then
    raise exception 'invalid_alert_key';
  end if;
  if p_state not in ('unreviewed', 'reviewed', 'dismissed') then
    raise exception 'invalid_review_state';
  end if;
  if not exists (select 1 from public.watchlists w where w.id = p_id and w.deleted_at is null) then
    raise exception 'watchlist_not_found';
  end if;
  if p_state = 'unreviewed' then
    delete from public.watchlist_alert_reviews r
    where r.watchlist_id = p_id and r.alert_key = p_alert_key;
  else
    insert into public.watchlist_alert_reviews (watchlist_id, alert_key, state, updated_at)
    values (p_id, p_alert_key, p_state, now())
    on conflict (watchlist_id, alert_key)
    do update set state = excluded.state, updated_at = excluded.updated_at;
  end if;
end; $$;
