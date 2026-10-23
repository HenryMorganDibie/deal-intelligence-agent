-- Durable review state for no-account watchlists. The UUID is the private watchlist key.
create table if not exists public.watchlist_alert_reviews (
  watchlist_id uuid not null references public.watchlists(id) on delete cascade,
  alert_key text not null check (length(alert_key) between 3 and 300),
  state text not null check (state in ('unreviewed', 'reviewed', 'dismissed')),
  updated_at timestamptz not null default now(),
  primary key (watchlist_id, alert_key)
);

alter table public.watchlist_alert_reviews enable row level security;

create or replace function public.list_watchlist_reviews(secret text, p_id uuid)
returns table(alert_key text, state text, updated_at timestamptz)
language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  if not exists (select 1 from public.watchlists w where w.id = p_id and w.deleted_at is null) then
    raise exception 'watchlist_not_found';
  end if;
  return query
    select r.alert_key, r.state, r.updated_at
    from public.watchlist_alert_reviews r
    where r.watchlist_id = p_id
    order by r.updated_at desc;
end; $$;

create or replace function public.upsert_watchlist_review(secret text, p_id uuid, p_alert_key text, p_state text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  if p_alert_key is null or length(p_alert_key) < 3 or length(p_alert_key) > 300
     or p_alert_key !~ '^(event|deal):.+' then
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

revoke all on table public.watchlist_alert_reviews from public, anon, authenticated;
revoke execute on function public.list_watchlist_reviews(text, uuid) from public;
revoke execute on function public.upsert_watchlist_review(text, uuid, text, text) from public;
grant execute on function public.list_watchlist_reviews(text, uuid) to anon;
grant execute on function public.upsert_watchlist_review(text, uuid, text, text) to anon;
