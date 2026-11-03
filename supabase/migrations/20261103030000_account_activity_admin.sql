-- Who has an account and who is using the app, for the owner's admin page. Additive only.
--
-- The app's sign-in gate re-checks each account at most every 30 minutes; at that moment it calls
-- touch_my_activity(), which records the account as active that day and its last-seen time. Nothing is recorded
-- per page view. admin_account_stats() is read only by the API server behind the shared secret and the admin key.

alter table public.profiles add column if not exists last_seen_at timestamptz;

create table if not exists public.account_activity (
  user_id uuid not null references auth.users (id) on delete cascade,
  day date not null,
  primary key (user_id, day)
);
alter table public.account_activity enable row level security;

create or replace function public.touch_my_activity()
returns void language plpgsql security definer set search_path to '' as $$
declare v_uid uuid := auth.uid();
begin
  if v_uid is null then return; end if;
  insert into public.account_activity (user_id, day) values (v_uid, (now() at time zone 'utc')::date)
  on conflict do nothing;
  update public.profiles set last_seen_at = now() where user_id = v_uid;
end; $$;
revoke all on function public.touch_my_activity() from public, anon;
grant execute on function public.touch_my_activity() to authenticated;

create or replace function public.admin_account_stats(secret text, p_days integer default 30)
returns jsonb language plpgsql stable security definer set search_path to '' as $$
declare
  v_days integer := greatest(1, least(coalesce(p_days, 30), 365));
  v_since date := (now() at time zone 'utc')::date - (v_days - 1);
  v_result jsonb;
begin
  perform private.check_secret(secret);
  with people as (
    select u.id, u.email::text as email, u.created_at, u.email_confirmed_at, u.last_sign_in_at,
           p.username, p.display_name, p.last_seen_at,
           coalesce((select array_agg(distinct i.provider order by i.provider) from auth.identities i where i.user_id = u.id),
                    array[]::text[]) as providers,
           exists (select 1 from auth.mfa_factors f where f.user_id = u.id and f.status = 'verified') as two_factor,
           (select count(*) from public.account_activity a where a.user_id = u.id and a.day >= v_since) as active_days,
           (select max(a.day) from public.account_activity a where a.user_id = u.id) as last_active_day,
           (select count(*) from public.watchlist_email_subscriptions s where s.user_id = u.id and s.enabled) as email_alerts
      from auth.users u
      left join public.profiles p on p.user_id = u.id
     where u.deleted_at is null and coalesce(u.email, '') not like '%.invalid'
  )
  select jsonb_build_object(
    'since', v_since,
    'days', v_days,
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
      'never_used', (select count(*) from people where last_active_day is null and last_seen_at is null)
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
               'two_factor', two_factor, 'email_alerts', email_alerts)
             order by coalesce(last_seen_at, last_active_day::timestamptz, created_at) desc)
        from (select * from people order by created_at desc limit 1000) recent
    ), '[]'::jsonb)
  ) into v_result;
  return v_result;
end; $$;
-- Like the other shared-secret functions, it is executable by the API's key and checks the secret first.
