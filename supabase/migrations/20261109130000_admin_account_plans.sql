-- The owner's accounts list also shows each account's plan and this month's API use, so plans can be changed
-- from the admin page (admin_set_plan). Everything else in admin_account_stats is unchanged.
create or replace function public.admin_account_stats(secret text, p_days integer default 30)
returns jsonb
language plpgsql stable security definer set search_path to ''
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
      'api_users', (select count(*) from people where api_keys > 0)
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
               'plan', plan, 'api_used', api_used, 'api_keys', api_keys)
             order by coalesce(last_seen_at, last_active_day::timestamptz, created_at) desc)
        from (select * from people order by created_at desc limit 1000) recent
    ), '[]'::jsonb)
  ) into v_result;
  return v_result;
end; $function$;
