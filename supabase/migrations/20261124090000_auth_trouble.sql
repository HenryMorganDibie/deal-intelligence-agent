-- Sign-in trouble: failed sign-ups, sign-ins and password resets, so the owner can see who is stuck and help.
--
-- A person who cannot create an account never appears among the accounts, so their trouble was invisible. The
-- auth route records each failure here: the address typed, what went wrong, never a password. Rows are kept for
-- 30 days. Recording is open to the site's own key, so it is capped: one row per address and reason every ten
-- minutes, and at most 300 rows an hour in all.

create table if not exists private.auth_trouble (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(),
  action text not null check (action in ('sign-up', 'sign-in', 'recover-password', 'reset-password', 'change-password')),
  reason text not null check (length(reason) between 1 and 300),
  email text check (email is null or length(email) <= 254)
);
create index if not exists auth_trouble_at on private.auth_trouble (at desc);
create index if not exists auth_trouble_email on private.auth_trouble (email, at desc);

create or replace function public.record_auth_trouble(p_action text, p_reason text, p_email text default null)
returns void
language plpgsql
security definer
set search_path to ''
as $$
declare
  v_email text := nullif(lower(trim(coalesce(p_email, ''))), '');
  v_reason text := left(trim(coalesce(p_reason, '')), 300);
begin
  if p_action not in ('sign-up', 'sign-in', 'recover-password', 'reset-password', 'change-password') or v_reason = '' then
    return;
  end if;
  if v_email is not null and (length(v_email) > 254 or v_email !~ '^[^\s@]+@[^\s@]+\.[^\s@]+$') then
    v_email := null;
  end if;
  delete from private.auth_trouble where at < now() - interval '30 days';
  if (select count(*) from private.auth_trouble where at > now() - interval '1 hour') >= 300 then
    return;
  end if;
  if exists (select 1 from private.auth_trouble t
              where t.email is not distinct from v_email and t.reason = v_reason and t.action = p_action
                and t.at > now() - interval '10 minutes') then
    return;
  end if;
  insert into private.auth_trouble (action, reason, email) values (p_action, v_reason, v_email);
end; $$;

revoke all on function public.record_auth_trouble(text, text, text) from public;
grant execute on function public.record_auth_trouble(text, text, text) to anon, authenticated, service_role;

-- For the owner's admin page: recent trouble grouped by address, newest first, with whether that address now has
-- a working account. Callable only with the server secret, like the other admin functions.
create or replace function public.admin_auth_trouble(secret text, p_days integer default 14)
returns jsonb
language plpgsql
stable
security definer
set search_path to ''
as $$
declare
  v_days integer := greatest(1, least(coalesce(p_days, 14), 30));
begin
  perform private.check_secret(secret);
  return coalesce((
    select jsonb_agg(jsonb_build_object(
             'email', g.email, 'attempts', g.attempts, 'first_at', g.first_at, 'last_at', g.last_at,
             'actions', to_jsonb(g.actions), 'last_reason', g.last_reason, 'reasons', to_jsonb(g.reasons),
             'has_account', u.id is not null,
             'confirmed', coalesce(u.email_confirmed_at is not null, false),
             'signed_in_since', coalesce(u.last_sign_in_at > g.last_at, false))
           order by g.last_at desc)
      from (
        select t.email, count(*) as attempts, min(t.at) as first_at, max(t.at) as last_at,
               array_agg(distinct t.action) as actions, (array_agg(t.reason order by t.at desc))[1] as last_reason,
               array_agg(distinct t.reason) as reasons
          from private.auth_trouble t
         where t.at > now() - make_interval(days => v_days)
         group by t.email
         order by max(t.at) desc
         limit 200
      ) g
      left join lateral (
        select x.id, x.email_confirmed_at, x.last_sign_in_at from auth.users x
         where g.email is not null and lower(x.email) = g.email and x.deleted_at is null limit 1
      ) u on true
  ), '[]'::jsonb);
end; $$;

revoke all on function public.admin_auth_trouble(text, integer) from public;
grant execute on function public.admin_auth_trouble(text, integer) to anon, authenticated, service_role;

revoke all on table private.auth_trouble from public, anon, authenticated;
