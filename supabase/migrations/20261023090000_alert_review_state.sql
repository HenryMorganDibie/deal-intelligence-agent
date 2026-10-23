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


-- Retain a bounded audit trail of webhook delivery outcomes for operational debugging.
create table if not exists public.watchlist_delivery_attempts (
  id bigint generated always as identity primary key,
  watchlist_id uuid not null references public.watchlists(id) on delete cascade,
  attempted_at timestamptz not null default now(),
  delivered boolean not null,
  attempt_count integer not null check (attempt_count between 1 and 3),
  http_status integer,
  alert_count integer not null default 0 check (alert_count >= 0),
  error_code text
);
create index if not exists watchlist_delivery_attempts_recent_idx
  on public.watchlist_delivery_attempts (watchlist_id, attempted_at desc);
alter table public.watchlist_delivery_attempts enable row level security;

create or replace function public.record_watchlist_delivery(
  secret text, p_id uuid, p_delivered boolean, p_attempt_count integer,
  p_http_status integer, p_alert_count integer, p_error_code text
) returns void language plpgsql security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  if p_attempt_count not between 1 and 3 or p_alert_count < 0 then
    raise exception 'invalid_delivery_metrics';
  end if;
  if not exists (select 1 from public.watchlists w where w.id = p_id and w.deleted_at is null) then
    raise exception 'watchlist_not_found';
  end if;
  insert into public.watchlist_delivery_attempts
    (watchlist_id, delivered, attempt_count, http_status, alert_count, error_code)
  values (p_id, p_delivered, p_attempt_count, p_http_status, p_alert_count, left(p_error_code, 80));
  if p_delivered then
    update public.watchlists set last_delivered_at = now() where id = p_id;
  end if;
end; $$;

create or replace function public.latest_watchlist_delivery(secret text, p_id uuid)
returns table(attempted_at timestamptz, delivered boolean, attempt_count integer,
              http_status integer, alert_count integer, error_code text)
language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  if not exists (select 1 from public.watchlists w where w.id = p_id and w.deleted_at is null) then
    raise exception 'watchlist_not_found';
  end if;
  return query
    select d.attempted_at, d.delivered, d.attempt_count, d.http_status, d.alert_count, d.error_code
    from public.watchlist_delivery_attempts d
    where d.watchlist_id = p_id
    order by d.attempted_at desc
    limit 10;
end; $$;

revoke all on table public.watchlist_delivery_attempts from public, anon, authenticated;
revoke execute on function public.record_watchlist_delivery(text, uuid, boolean, integer, integer, integer, text) from public;
revoke execute on function public.latest_watchlist_delivery(text, uuid) from public;
grant execute on function public.record_watchlist_delivery(text, uuid, boolean, integer, integer, integer, text) to anon;
grant execute on function public.latest_watchlist_delivery(text, uuid) to anon;
