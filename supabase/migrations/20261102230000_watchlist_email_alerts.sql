-- Watchlist alerts by email (SendByte), with double opt-in and one-click unsubscribe.
--
-- An address is stored as pending with a random token; nothing but the confirmation message is sent until the
-- recipient confirms with that token. Every alert carries the token for unsubscribing. The address and token are
-- read only by the API server (security definer functions behind the shared secret; the table has RLS and no
-- policies), and the public watchlist endpoint strips them.

alter table public.watchlists
  add column if not exists notify_email text,
  add column if not exists email_status text not null default 'none',
  add column if not exists email_token text,
  add column if not exists email_requested_at timestamptz,
  add column if not exists email_confirmed_at timestamptz;

alter table public.watchlists drop constraint if exists watchlists_email_status_check;
alter table public.watchlists add constraint watchlists_email_status_check
  check (email_status in ('none', 'pending', 'confirmed', 'unsubscribed'));

create unique index if not exists watchlists_email_token_key on public.watchlists (email_token) where email_token is not null;
create index if not exists watchlists_notify_email_idx on public.watchlists (notify_email) where notify_email is not null;

alter table public.watchlist_delivery_attempts add column if not exists channel text not null default 'webhook';
alter table public.watchlist_delivery_attempts drop constraint if exists watchlist_delivery_attempts_channel_check;
alter table public.watchlist_delivery_attempts add constraint watchlist_delivery_attempts_channel_check
  check (channel in ('webhook', 'email'));

-- Ask for confirmation of an address. At most 3 requests per address a day across all watchlists, so the form
-- cannot be used to flood someone's inbox. Returns 'pending', or 'confirmed' when that address is already
-- confirmed on this watchlist (no new message is needed).
create or replace function public.set_watchlist_email(secret text, p_id uuid, p_email text, p_token text)
returns text language plpgsql security definer set search_path to '' as $$
declare v_email text := lower(trim(p_email)); v_row public.watchlists;
begin
  perform private.check_secret(secret);
  if v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' or length(v_email) > 254 then raise exception 'invalid_email'; end if;
  if p_token is null or length(p_token) < 32 then raise exception 'invalid_token'; end if;
  select * into v_row from public.watchlists w where w.id = p_id and w.deleted_at is null;
  if not found then raise exception 'watchlist_not_found'; end if;
  if v_row.notify_email = v_email and v_row.email_status = 'confirmed' then return 'confirmed'; end if;
  if (select count(*) from public.watchlists w
      where w.notify_email = v_email and w.email_requested_at > now() - interval '24 hours') >= 3 then
    raise exception 'email_rate_limit';
  end if;
  update public.watchlists
     set notify_email = v_email, email_status = 'pending', email_token = p_token,
         email_requested_at = now(), email_confirmed_at = null
   where id = p_id;
  return 'pending';
end; $$;

-- Confirm with the token from the confirmation message (valid for 7 days).
create or replace function public.confirm_watchlist_email(secret text, p_token text)
returns table(id uuid, name text, email_status text) language plpgsql security definer set search_path to '' as $$
begin
  perform private.check_secret(secret);
  return query
    update public.watchlists w
       set email_status = 'confirmed', email_confirmed_at = coalesce(w.email_confirmed_at, now())
     where w.email_token = p_token and w.deleted_at is null
       and (w.email_status = 'confirmed'
            or (w.email_status = 'pending' and w.email_requested_at > now() - interval '7 days'))
    returning w.id, w.name, w.email_status;
end; $$;

-- Stop alert emails for the watchlist the token belongs to. Idempotent.
create or replace function public.unsubscribe_watchlist_email(secret text, p_token text)
returns table(id uuid, name text, email_status text) language plpgsql security definer set search_path to '' as $$
begin
  perform private.check_secret(secret);
  return query
    update public.watchlists w set email_status = 'unsubscribed'
     where w.email_token = p_token and w.email_status in ('pending', 'confirmed', 'unsubscribed')
    returning w.id, w.name, w.email_status;
end; $$;

-- Watchlists with somewhere to deliver: a webhook or a confirmed email address.
create or replace function public.alert_watchlists(secret text)
returns setof public.watchlists language plpgsql stable security definer set search_path to '' as $$
begin
  perform private.check_secret(secret);
  return query select * from public.watchlists w
   where w.deleted_at is null and (w.webhook_url is not null or w.email_status = 'confirmed');
end; $$;

-- Deleting a watchlist also forgets its address and token.
create or replace function public.remove_watchlist(secret text, p_id uuid)
returns void language plpgsql security definer set search_path to '' as $$
begin
  perform private.check_secret(secret);
  update public.watchlists
     set deleted_at = now(), webhook_url = null, notify_email = null, email_token = null,
         email_status = case when email_status = 'none' then 'none' else 'unsubscribed' end
   where id = p_id;
end; $$;

-- Delivery outcomes now name their channel.
drop function if exists public.record_watchlist_delivery(text, uuid, boolean, integer, integer, integer, text);
create or replace function public.record_watchlist_delivery(secret text, p_id uuid, p_delivered boolean,
  p_attempt_count integer, p_http_status integer, p_alert_count integer, p_error_code text,
  p_channel text default 'webhook')
returns void language plpgsql security definer set search_path to '' as $$
begin
  perform private.check_secret(secret);
  if p_attempt_count not between 1 and 3 or p_alert_count < 0 then raise exception 'invalid_delivery_metrics'; end if;
  if p_channel not in ('webhook', 'email') then raise exception 'invalid_channel'; end if;
  if not exists (select 1 from public.watchlists w where w.id = p_id and w.deleted_at is null) then
    raise exception 'watchlist_not_found';
  end if;
  insert into public.watchlist_delivery_attempts
    (watchlist_id, delivered, attempt_count, http_status, alert_count, error_code, channel)
  values (p_id, p_delivered, p_attempt_count, p_http_status, p_alert_count, left(p_error_code, 80), p_channel);
  if p_delivered then update public.watchlists set last_delivered_at = now() where id = p_id; end if;
end; $$;

drop function if exists public.latest_watchlist_delivery(text, uuid);
create or replace function public.latest_watchlist_delivery(secret text, p_id uuid)
returns table(attempted_at timestamptz, delivered boolean, attempt_count integer, http_status integer,
              alert_count integer, error_code text, channel text)
language plpgsql stable security definer set search_path to '' as $$
begin
  perform private.check_secret(secret);
  if not exists (select 1 from public.watchlists w where w.id = p_id and w.deleted_at is null) then
    raise exception 'watchlist_not_found';
  end if;
  return query
    select d.attempted_at, d.delivered, d.attempt_count, d.http_status, d.alert_count, d.error_code, d.channel
    from public.watchlist_delivery_attempts d where d.watchlist_id = p_id
    order by d.attempted_at desc limit 10;
end; $$;

-- Like the other watchlist functions, these are executable by the API's key; each checks the shared secret first.
