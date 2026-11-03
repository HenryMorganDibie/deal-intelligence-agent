-- Watchlist alerts by email, sent to the signed-in account's verified address.
--
-- Additive only: a new table and new functions; no existing function is dropped or changed.
-- A subscription links one account to one watchlist. Anyone holding a watchlist's link can subscribe their own
-- account, never another address, so the feature cannot be used to send mail to a stranger. Each subscription has
-- its own random token for one-click unsubscribe. The table has row level security and no policies: accounts reach
-- it only through the functions below, and the API server only through the shared-secret functions.

create table if not exists public.watchlist_email_subscriptions (
  watchlist_id uuid not null references public.watchlists (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  unsubscribe_token text not null unique
    default replace(gen_random_uuid()::text, '-', '') || replace(gen_random_uuid()::text, '-', ''),
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (watchlist_id, user_id)
);
alter table public.watchlist_email_subscriptions enable row level security;
create index if not exists watchlist_email_subscriptions_user_idx on public.watchlist_email_subscriptions (user_id);

alter table public.watchlist_delivery_attempts add column if not exists channel text not null default 'webhook';
do $$ begin
  alter table public.watchlist_delivery_attempts add constraint watchlist_delivery_attempts_channel_check
    check (channel in ('webhook', 'email'));
exception when duplicate_object then null; end $$;

-- ── Called by a signed-in account (its own session token) ─────────────────────────────────────────────────────

-- Whether this account gets this watchlist's alerts by email, and the address they would go to.
create or replace function public.my_watchlist_email_alert(p_id uuid)
returns table (enabled boolean, email text, email_confirmed boolean)
language plpgsql stable security definer set search_path to '' as $$
declare v_uid uuid := auth.uid();
begin
  if v_uid is null then raise exception 'not_signed_in'; end if;
  if not public.mfa_satisfied() then raise exception 'second_factor_required'; end if;
  return query
    select coalesce(s.enabled, false), u.email::text, u.email_confirmed_at is not null
      from auth.users u
      left join public.watchlist_email_subscriptions s on s.user_id = u.id and s.watchlist_id = p_id
     where u.id = v_uid;
end; $$;

-- Turn this watchlist's email alerts on or off for this account. Requires a confirmed email address.
-- At most 20 watchlists per account send email.
create or replace function public.set_my_watchlist_email_alert(p_id uuid, p_enabled boolean)
returns boolean
language plpgsql security definer set search_path to '' as $$
declare v_uid uuid := auth.uid();
begin
  if v_uid is null then raise exception 'not_signed_in'; end if;
  if not public.mfa_satisfied() then raise exception 'second_factor_required'; end if;
  if not exists (select 1 from public.watchlists w where w.id = p_id and w.deleted_at is null) then
    raise exception 'watchlist_not_found';
  end if;
  if p_enabled then
    if not exists (select 1 from auth.users u where u.id = v_uid and u.email is not null and u.email_confirmed_at is not null) then
      raise exception 'email_not_confirmed';
    end if;
    if (select count(*) from public.watchlist_email_subscriptions s
         where s.user_id = v_uid and s.enabled and s.watchlist_id <> p_id) >= 20 then
      raise exception 'email_alert_limit';
    end if;
    insert into public.watchlist_email_subscriptions as s (watchlist_id, user_id, enabled)
    values (p_id, v_uid, true)
    on conflict (watchlist_id, user_id) do update set enabled = true, updated_at = now();
  else
    update public.watchlist_email_subscriptions s set enabled = false, updated_at = now()
     where s.watchlist_id = p_id and s.user_id = v_uid;
  end if;
  return p_enabled;
end; $$;

revoke all on function public.my_watchlist_email_alert(uuid) from public, anon;
revoke all on function public.set_my_watchlist_email_alert(uuid, boolean) from public, anon;
grant execute on function public.my_watchlist_email_alert(uuid) to authenticated;
grant execute on function public.set_my_watchlist_email_alert(uuid, boolean) to authenticated;

-- ── Called by the API server (shared secret) ─────────────────────────────────────────────────────────────────

-- Watchlists with somewhere to deliver: a webhook or at least one email subscriber.
create or replace function public.deliverable_watchlists(secret text)
returns setof public.watchlists
language plpgsql stable security definer set search_path to '' as $$
begin
  perform private.check_secret(secret);
  return query
    select w.* from public.watchlists w
     where w.deleted_at is null
       and (w.webhook_url is not null
            or exists (select 1 from public.watchlist_email_subscriptions s where s.watchlist_id = w.id and s.enabled));
end; $$;

-- Everyone who should receive a watchlist's alerts by email: enabled, confirmed address, account not banned.
create or replace function public.watchlist_email_recipients(secret text)
returns table (watchlist_id uuid, email text, display_name text, unsubscribe_token text)
language plpgsql stable security definer set search_path to '' as $$
begin
  perform private.check_secret(secret);
  return query
    select s.watchlist_id, u.email::text, p.display_name, s.unsubscribe_token
      from public.watchlist_email_subscriptions s
      join public.watchlists w on w.id = s.watchlist_id and w.deleted_at is null
      join auth.users u on u.id = s.user_id
      left join public.profiles p on p.user_id = s.user_id
     where s.enabled and u.email is not null and u.email_confirmed_at is not null
       and u.deleted_at is null and (u.banned_until is null or u.banned_until < now());
end; $$;

-- One-click unsubscribe from the link in an alert email. Idempotent; returns the watchlist's name.
create or replace function public.unsubscribe_watchlist_email(secret text, p_token text)
returns table (watchlist_name text)
language plpgsql security definer set search_path to '' as $$
begin
  perform private.check_secret(secret);
  if p_token is null or p_token !~ '^[0-9a-f]{64}$' then return; end if;
  return query
    with changed as (
      update public.watchlist_email_subscriptions s set enabled = false, updated_at = now()
       where s.unsubscribe_token = p_token
      returning s.watchlist_id
    )
    select w.name from changed c join public.watchlists w on w.id = c.watchlist_id;
end; $$;

-- The outcome of one email run for a watchlist, kept beside the webhook outcomes.
create or replace function public.record_watchlist_email_delivery(secret text, p_id uuid, p_delivered boolean,
  p_recipient_count integer, p_alert_count integer, p_error_code text)
returns void
language plpgsql security definer set search_path to '' as $$
begin
  perform private.check_secret(secret);
  if p_recipient_count < 1 or p_alert_count < 0 then raise exception 'invalid_delivery_metrics'; end if;
  if not exists (select 1 from public.watchlists w where w.id = p_id and w.deleted_at is null) then
    raise exception 'watchlist_not_found';
  end if;
  insert into public.watchlist_delivery_attempts
    (watchlist_id, delivered, attempt_count, http_status, alert_count, error_code, channel)
  values (p_id, p_delivered, 1, null, p_alert_count, left(p_error_code, 80), 'email');
  if p_delivered then update public.watchlists set last_delivered_at = now() where id = p_id; end if;
end; $$;

-- Like the other shared-secret functions, these are executable by the API's key; each checks the secret first.

-- Delivery history with the channel of each attempt (the older latest_watchlist_delivery stays for compatibility).
create or replace function public.watchlist_delivery_history(secret text, p_id uuid)
returns table (attempted_at timestamptz, delivered boolean, attempt_count integer, http_status integer,
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
     order by d.attempted_at desc limit 20;
end; $$;
