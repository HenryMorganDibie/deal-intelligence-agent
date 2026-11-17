-- The owner can suspend, reinstate or delete an account from the admin page.
--
-- Suspend: Supabase Auth's own ban (auth.users.banned_until = infinity), so sign-in and token refresh are refused by
-- Auth itself, and every session is ended at once. The account's API keys, alert emails, alert webhooks and election
-- alerts stop while it is suspended; nothing is deleted, so reinstating restores everything.
-- Delete: the auth user is removed and every row that belongs only to that account goes with it (the foreign keys
-- cascade). Where the account created shared records other people rely on (a cloud portfolio, an organisation),
-- deleting would break them, so the account is anonymised instead: its email, name, sign-in methods, sessions,
-- second factors and personal data are erased and it can never sign in again; the shared records stay.
-- All functions are callable only with the server secret (private.check_secret), like the other admin functions.

create table if not exists private.account_moderation (
  user_id uuid primary key references auth.users (id) on delete cascade,
  reason text not null default '' check (length(reason) <= 300),
  suspended_at timestamptz not null default now()
);

create table if not exists private.account_moderation_log (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(),
  action text not null check (action in ('suspended', 'reinstated', 'deleted', 'anonymised')),
  account text not null,          -- masked email (a***@domain), so the log outlives a deleted account without its address
  reason text not null default ''
);

create or replace function private.is_suspended(p_user uuid)
returns boolean language sql stable security definer set search_path to ''
as $$ select coalesce((select u.banned_until > now() from auth.users u where u.id = p_user), false) $$;

create or replace function private.mask_email(p_email text)
returns text language sql immutable set search_path to ''
as $$ select case when position('@' in coalesce(p_email, '')) > 1
                  then left(p_email, 1) || '***' || substring(p_email from position('@' in p_email))
                  else '***' end $$;

-- What the API needs before acting: the account, whether it is suspended, and its Paystack subscription (so renewal
-- can be cancelled at Paystack before an account is suspended or deleted).
create or replace function public.admin_account_lookup(secret text, p_email text)
returns jsonb language plpgsql stable security definer set search_path to ''
as $function$
declare v jsonb;
begin
  perform private.check_secret(secret);
  select jsonb_build_object(
           'user_id', u.id, 'email', u.email, 'suspended', coalesce(u.banned_until > now(), false),
           'subscription_code', b.subscription_code, 'email_token', b.email_token, 'subscription_status', b.status)
    into v
    from auth.users u
    left join public.billing_subscriptions b on b.user_id = u.id
   where lower(u.email) = lower(trim(p_email)) and u.deleted_at is null and coalesce(u.email, '') not like '%.invalid';
  if v is null then raise exception 'unknown_account'; end if;
  return v;
end; $function$;

create or replace function public.admin_set_account_suspended(secret text, p_email text, p_suspend boolean, p_reason text default '')
returns jsonb language plpgsql security definer set search_path to ''
as $function$
declare
  v_id uuid;
  v_email text;
  v_reason text := left(trim(coalesce(p_reason, '')), 300);
begin
  perform private.check_secret(secret);
  select u.id, u.email into v_id, v_email from auth.users u
   where lower(u.email) = lower(trim(p_email)) and u.deleted_at is null and coalesce(u.email, '') not like '%.invalid';
  if v_id is null then raise exception 'unknown_account'; end if;
  if p_suspend then
    update auth.users set banned_until = 'infinity', updated_at = now() where id = v_id;
    delete from auth.sessions where user_id = v_id;              -- refresh tokens go with their sessions
    delete from auth.refresh_tokens where user_id = v_id::text;
    insert into private.account_moderation (user_id, reason) values (v_id, v_reason)
    on conflict (user_id) do update set reason = excluded.reason, suspended_at = now();
  else
    update auth.users set banned_until = null, updated_at = now() where id = v_id;
    delete from private.account_moderation where user_id = v_id;
  end if;
  insert into private.account_moderation_log (action, account, reason)
  values (case when p_suspend then 'suspended' else 'reinstated' end, private.mask_email(v_email), v_reason);
  return jsonb_build_object('email', v_email, 'suspended', p_suspend);
end; $function$;

create or replace function public.admin_delete_account(secret text, p_email text, p_confirm text, p_reason text default '')
returns jsonb language plpgsql security definer set search_path to ''
as $function$
declare
  v_id uuid;
  v_email text;
  v_mode text := 'deleted';
  v_fk record;
begin
  perform private.check_secret(secret);
  select u.id, u.email into v_id, v_email from auth.users u
   where lower(u.email) = lower(trim(p_email)) and u.deleted_at is null and coalesce(u.email, '') not like '%.invalid';
  if v_id is null then raise exception 'unknown_account'; end if;
  if lower(trim(coalesce(p_confirm, ''))) <> lower(v_email) then raise exception 'confirmation_mismatch'; end if;
  begin
    delete from auth.users where id = v_id;
  exception when foreign_key_violation then
    -- Shared records (portfolios, organisations) point at this account: erase the person, keep those records.
    v_mode := 'anonymised';
    for v_fk in
      select c.conrelid::regclass as tbl, a.attname as col
        from pg_constraint c
        join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any (c.conkey)
       where c.contype = 'f' and c.confrelid = 'auth.users'::regclass and c.confdeltype = 'c'
         and c.connamespace <> 'auth'::regnamespace
    loop
      execute format('delete from %s where %I = $1', v_fk.tbl, v_fk.col) using v_id;
    end loop;
    delete from auth.sessions where user_id = v_id;
    delete from auth.refresh_tokens where user_id = v_id::text;
    delete from auth.mfa_factors where user_id = v_id;
    delete from auth.identities where user_id = v_id;
    update auth.users
       set email = 'deleted-' || v_id || '@deleted.invalid', phone = null, encrypted_password = '',
           raw_user_meta_data = '{}'::jsonb, banned_until = 'infinity', deleted_at = now(), updated_at = now()
     where id = v_id;
  end;
  insert into private.account_moderation_log (action, account, reason)
  values (v_mode, private.mask_email(v_email), left(trim(coalesce(p_reason, '')), 300));
  return jsonb_build_object('email', v_email, 'result', v_mode);
end; $function$;

create or replace function public.admin_moderation_log(secret text)
returns jsonb language plpgsql stable security definer set search_path to ''
as $function$
begin
  perform private.check_secret(secret);
  return coalesce((select jsonb_agg(jsonb_build_object('at', l.at, 'action', l.action, 'account', l.account, 'reason', l.reason)
                                    order by l.at desc)
                     from (select * from private.account_moderation_log order by at desc limit 50) l), '[]'::jsonb);
end; $function$;

-- A suspended account's keys stop working (they answer as an invalid key) and its alerts stop going out.
create or replace function public.api_key_consume(secret text, p_hash text, p_count boolean default true)
returns jsonb language plpgsql security definer set search_path to ''
as $function$
declare
  v_key public.api_keys;
  v_plan public.api_plans;
  v_period date := private.current_period();
  v_used integer;
begin
  perform private.check_secret(secret);
  select * into v_key from public.api_keys k where k.key_hash = p_hash and k.revoked_at is null;
  if not found or private.is_suspended(v_key.user_id) then return jsonb_build_object('ok', false, 'reason', 'invalid_key'); end if;
  v_plan := private.plan_of(v_key.user_id);
  if p_count and v_plan.monthly_requests = 0 then
    return jsonb_build_object('ok', false, 'reason', 'quota_exceeded', 'plan', v_plan.plan, 'limit', 0, 'used', 0,
                              'remaining', 0, 'resets_at', (v_period + interval '1 month'));
  end if;
  if p_count then
    insert into public.api_usage as u (user_id, period, requests) values (v_key.user_id, v_period, 1)
    on conflict (user_id, period) do update set requests = u.requests + 1
     where u.requests < v_plan.monthly_requests
    returning u.requests into v_used;
    if v_used is null then
      v_used := coalesce((select u.requests from public.api_usage u where u.user_id = v_key.user_id and u.period = v_period), 0);
      return jsonb_build_object('ok', false, 'reason', 'quota_exceeded', 'plan', v_plan.plan,
                                'limit', v_plan.monthly_requests, 'used', v_used, 'remaining', 0,
                                'resets_at', (v_period + interval '1 month'));
    end if;
    update public.api_keys set last_used_at = now() where id = v_key.id;
  else
    v_used := coalesce((select u.requests from public.api_usage u where u.user_id = v_key.user_id and u.period = v_period), 0);
  end if;
  return jsonb_build_object('ok', true, 'plan', v_plan.plan, 'limit', v_plan.monthly_requests, 'used', v_used,
                            'remaining', greatest(v_plan.monthly_requests - v_used, 0),
                            'resets_at', (v_period + interval '1 month'), 'key_id', v_key.id);
end; $function$;

create or replace function public.api_key_account(secret text, p_key_id uuid)
returns uuid language plpgsql stable security definer set search_path to ''
as $function$
begin
  perform private.check_secret(secret);
  return (select k.user_id from public.api_keys k
           where k.id = p_key_id and k.revoked_at is null and not private.is_suspended(k.user_id));
end; $function$;

create or replace function public.election_alert_active(secret text)
returns jsonb language plpgsql stable security definer set search_path to ''
as $function$
begin
  perform private.check_secret(secret);
  return (select coalesce(jsonb_agg(to_jsonb(s)), '[]'::jsonb) from public.election_alert_subs s
           where s.active and not private.is_suspended(s.owner));
end; $function$;

create or replace function public.election_alert_recipient(secret text, p_owner uuid)
returns text language plpgsql stable security definer set search_path to ''
as $function$
begin
  perform private.check_secret(secret);
  return (select u.email from auth.users u
           where u.id = p_owner and u.email_confirmed_at is not null and not private.is_suspended(u.id));
end; $function$;

create or replace function public.deliverable_watchlists(secret text)
returns setof public.watchlists language plpgsql stable security definer set search_path to ''
as $function$
begin
  perform private.check_secret(secret);
  return query
    select w.* from public.watchlists w
     where w.deleted_at is null
       and (w.owner_user is null or not private.is_suspended(w.owner_user))
       and (w.webhook_url is not null
            or exists (select 1 from public.watchlist_email_subscriptions s where s.watchlist_id = w.id and s.enabled));
end; $function$;

create or replace function public.webhook_watchlists(secret text)
returns setof public.watchlists language plpgsql stable security definer set search_path to ''
as $function$
begin
  perform private.check_secret(secret);
  return query select * from public.watchlists w
                where w.webhook_url is not null and w.deleted_at is null
                  and (w.owner_user is null or not private.is_suspended(w.owner_user));
end; $function$;

-- The accounts list shows who is suspended and why, and whether a paid subscription is running.
create or replace function public.admin_account_stats(secret text, p_days integer default 30)
returns jsonb language plpgsql stable security definer set search_path to ''
as $function$
declare
  v_days integer := greatest(1, least(coalesce(p_days, 30), 365));
  v_since date := (now() at time zone 'utc')::date - (v_days - 1);
  v_period date := private.current_period();
  v_result jsonb;
begin
  perform private.check_secret(secret);
  with people as (
    select u.id, u.email::text as email, u.created_at, u.email_confirmed_at, u.last_sign_in_at,
           p.username, p.display_name, p.last_seen_at,
           coalesce(u.banned_until > now(), false) as suspended,
           (select m.reason from private.account_moderation m where m.user_id = u.id) as suspension_reason,
           (select b.status from public.billing_subscriptions b where b.user_id = u.id) as subscription_status,
           coalesce((select array_agg(distinct i.provider order by i.provider) from auth.identities i where i.user_id = u.id),
                    array[]::text[]) as providers,
           exists (select 1 from auth.mfa_factors f where f.user_id = u.id and f.status = 'verified') as two_factor,
           (select count(*) from public.account_activity a where a.user_id = u.id and a.day >= v_since) as active_days,
           (select max(a.day) from public.account_activity a where a.user_id = u.id) as last_active_day,
           (select count(*) from public.watchlist_email_subscriptions s where s.user_id = u.id and s.enabled) as email_alerts,
           coalesce((select ap.plan from public.account_plans ap where ap.user_id = u.id), 'free') as plan,
           coalesce((select au.requests from public.api_usage au where au.user_id = u.id and au.period = v_period), 0) as api_used,
           (select count(*) from public.api_keys k where k.user_id = u.id and k.revoked_at is null) as api_keys
      from auth.users u
      left join public.profiles p on p.user_id = u.id
     where u.deleted_at is null and coalesce(u.email, '') not like '%.invalid'
  )
  select jsonb_build_object(
    'since', v_since,
    'days', v_days,
    'plans', (select jsonb_agg(jsonb_build_object('id', pl.plan, 'label', pl.label, 'monthly_requests', pl.monthly_requests)
                               order by pl.sort) from public.api_plans pl),
    'totals', jsonb_build_object(
      'accounts', (select count(*) from people),
      'confirmed', (select count(*) from people where email_confirmed_at is not null),
      'unconfirmed', (select count(*) from people where email_confirmed_at is null),
      'with_username', (select count(*) from people where username is not null),
      'two_factor', (select count(*) from people where two_factor),
      'google', (select count(*) from people where 'google' = any(providers)),
      'new_in_period', (select count(*) from people where created_at >= v_since),
      'active_7d', (select count(*) from people where last_active_day >= (now() at time zone 'utc')::date - 6),
      'active_in_period', (select count(*) from people where active_days > 0),
      'returning_in_period', (select count(*) from people where active_days >= 2),
      'never_used', (select count(*) from people where last_active_day is null and last_seen_at is null),
      'paid', (select count(*) from people where plan <> 'free'),
      'api_users', (select count(*) from people where api_keys > 0),
      'suspended', (select count(*) from people where suspended)
    ),
    'daily', coalesce((
      select jsonb_agg(jsonb_build_object(
               'day', d.day,
               'signups', (select count(*) from people where (created_at at time zone 'utc')::date = d.day),
               'active', (select count(*) from public.account_activity a join people on people.id = a.user_id
                           where a.day = d.day))
             order by d.day)
        from (select generate_series(v_since, (now() at time zone 'utc')::date, interval '1 day')::date as day) d
    ), '[]'::jsonb),
    'accounts', coalesce((
      select jsonb_agg(jsonb_build_object(
               'email', email, 'username', username, 'display_name', display_name,
               'created_at', created_at, 'confirmed', email_confirmed_at is not null,
               'last_sign_in_at', last_sign_in_at,
               'last_seen_at', coalesce(last_seen_at, last_active_day::timestamptz),
               'active_days', active_days, 'providers', to_jsonb(providers),
               'two_factor', two_factor, 'email_alerts', email_alerts,
               'plan', plan, 'api_used', api_used, 'api_keys', api_keys,
               'suspended', suspended, 'suspension_reason', suspension_reason,
               'subscription_status', subscription_status)
             order by coalesce(last_seen_at, last_active_day::timestamptz, created_at) desc)
        from (select * from people order by created_at desc limit 1000) recent
    ), '[]'::jsonb)
  ) into v_result;
  return v_result;
end; $function$;

revoke all on function private.is_suspended(uuid) from public, anon, authenticated;
revoke all on table private.account_moderation, private.account_moderation_log from public, anon, authenticated;
