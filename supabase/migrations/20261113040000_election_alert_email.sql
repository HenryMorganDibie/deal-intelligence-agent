-- Election alerts by email: an alert can go to the account's confirmed email address, to a webhook, or both. The
-- address is never stored on the alert: it is read from the account at send time, so only the account's own,
-- confirmed address can receive it. Emails carry a one-click unsubscribe that pauses the alert.
alter table public.election_alert_subs add column if not exists email boolean not null default false;
alter table public.election_alert_subs alter column webhook_url drop not null;
alter table public.election_alert_subs drop constraint if exists election_alert_subs_webhook_url_check;
alter table public.election_alert_subs drop constraint if exists election_alert_subs_destination_check;
alter table public.election_alert_subs add constraint election_alert_subs_webhook_url_check
  check (webhook_url is null or (webhook_url like 'https://%' and char_length(webhook_url) <= 500));
alter table public.election_alert_subs add constraint election_alert_subs_destination_check
  check (webhook_url is not null or email);

create or replace function public.election_alert_create_v3(secret text, p_owner uuid, p_name text, p_url text,
  p_filters jsonb, p_max integer, p_email boolean)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare r public.election_alert_subs;
begin
  perform private.check_secret(secret);
  perform pg_advisory_xact_lock(hashtextextended('election_alerts:' || p_owner::text, 0));
  if (select count(*) from public.election_alert_subs where owner = p_owner) >= greatest(coalesce(p_max, 0), 0) then
    raise exception 'alert_limit' using errcode = '23514';
  end if;
  if coalesce(p_email, false) and not exists (select 1 from auth.users u where u.id = p_owner and u.email_confirmed_at is not null) then
    raise exception 'email_not_confirmed' using errcode = '22023';
  end if;
  insert into public.election_alert_subs (owner, name, webhook_url, filters, email)
  values (p_owner, p_name, nullif(p_url, ''), coalesce(p_filters, '{}'::jsonb), coalesce(p_email, false)) returning * into r;
  return to_jsonb(r);
end; $$;

-- The account's confirmed address, for sending; null if unconfirmed.
create or replace function public.election_alert_recipient(secret text, p_owner uuid)
returns text language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return (select u.email from auth.users u where u.id = p_owner and u.email_confirmed_at is not null);
end; $$;

-- Pause or resume an alert (the unsubscribe link pauses it).
create or replace function public.election_alert_set_active(secret text, p_id uuid, p_active boolean)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare r public.election_alert_subs;
begin
  perform private.check_secret(secret);
  update public.election_alert_subs set active = p_active where id = p_id returning * into r;
  return case when r.id is null then null else jsonb_build_object('id', r.id, 'name', r.name, 'active', r.active) end;
end; $$;

revoke execute on function public.election_alert_create_v3(text, uuid, text, text, jsonb, integer, boolean) from public, authenticated;
revoke execute on function public.election_alert_recipient(text, uuid) from public, authenticated;
revoke execute on function public.election_alert_set_active(text, uuid, boolean) from public, authenticated;
grant execute on function public.election_alert_create_v3(text, uuid, text, text, jsonb, integer, boolean) to anon;
grant execute on function public.election_alert_recipient(text, uuid) to anon;
grant execute on function public.election_alert_set_active(text, uuid, boolean) to anon;
