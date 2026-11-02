-- Account profiles: a unique username and a display name for every account.
--
-- A sign-up passes username and display_name as user metadata; the trigger on auth.users creates the profile and
-- rejects an invalid or taken username, which fails the sign-up itself, so the rules hold even for requests that
-- reach Supabase Auth directly. Accounts created without a username (Google sign-in, accounts that predate this)
-- choose one through set_my_profile before the app opens. Users read only their own row; writes go through
-- set_my_profile, which applies the same rules.

create table if not exists public.profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  username text not null,
  display_name text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint profiles_username_format check (username ~ '^[a-z0-9][a-z0-9_]{1,18}[a-z0-9]$'),
  constraint profiles_display_name_length check (char_length(btrim(display_name)) between 1 and 40)
);
create unique index if not exists profiles_username_key on public.profiles (username);

alter table public.profiles enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'profiles' and policyname = 'profiles_read_own') then
    create policy profiles_read_own on public.profiles for select to authenticated using (user_id = (select auth.uid()));
  end if;
end $$;

-- Format and reserved names. Usernames are compared lowercase.
create or replace function private.valid_username(p text) returns boolean
language sql immutable set search_path to '' as $$
  select p is not null and p ~ '^[a-z0-9][a-z0-9_]{1,18}[a-z0-9]$'
     and p not in ('admin', 'administrator', 'root', 'superuser', 'support', 'help', 'info', 'contact', 'security',
                   'system', 'api', 'app', 'www', 'mail', 'email', 'noreply', 'no_reply', 'postmaster', 'abuse',
                   'deal', 'deals', 'dealintelligence', 'deal_intelligence', 'moderator', 'mod', 'staff', 'team',
                   'official', 'null', 'undefined', 'me', 'account', 'accounts', 'settings', 'login', 'signin',
                   'signup', 'register', 'billing', 'owner', 'test');
$$;

create or replace function private.handle_new_user() returns trigger
language plpgsql security definer set search_path to '' as $$
declare
  v_username text := lower(btrim(coalesce(new.raw_user_meta_data ->> 'username', '')));
  v_display text := btrim(coalesce(new.raw_user_meta_data ->> 'display_name', ''));
begin
  if v_username = '' then return new; end if;              -- chosen after sign-in (Google, older accounts)
  if not private.valid_username(v_username) then
    raise exception 'invalid_username' using errcode = '22023';
  end if;
  begin
    insert into public.profiles (user_id, username, display_name)
    values (new.id, v_username, left(coalesce(nullif(v_display, ''), v_username), 40));
  exception when unique_violation then
    raise exception 'username_taken' using errcode = '23505';
  end;
  return new;
end; $$;

do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'on_auth_user_created_profile') then
    create trigger on_auth_user_created_profile after insert on auth.users
      for each row execute function private.handle_new_user();
  end if;
end $$;

-- Whether a username can be taken (format, reserved names, not in use). Usernames are public handles.
create or replace function public.username_available(p_username text) returns boolean
language sql stable security definer set search_path to '' as $$
  select private.valid_username(lower(btrim(p_username)))
     and not exists (select 1 from public.profiles p where p.username = lower(btrim(p_username)));
$$;

-- Create or update the signed-in user's profile.
create or replace function public.set_my_profile(p_username text, p_display_name text) returns public.profiles
language plpgsql security definer set search_path to '' as $$
declare
  v_uid uuid := auth.uid();
  v_username text := lower(btrim(coalesce(p_username, '')));
  v_display text := btrim(coalesce(p_display_name, ''));
  v_row public.profiles;
begin
  if v_uid is null then raise exception 'not_authenticated' using errcode = '28000'; end if;
  if not private.valid_username(v_username) then raise exception 'invalid_username' using errcode = '22023'; end if;
  if char_length(v_display) not between 1 and 40 then raise exception 'invalid_display_name' using errcode = '22023'; end if;
  begin
    insert into public.profiles (user_id, username, display_name) values (v_uid, v_username, v_display)
    on conflict (user_id) do update set username = excluded.username, display_name = excluded.display_name,
                                        updated_at = now()
    returning * into v_row;
  exception when unique_violation then
    raise exception 'username_taken' using errcode = '23505';
  end;
  return v_row;
end; $$;

revoke all on function public.set_my_profile(text, text) from public, anon;
grant execute on function public.set_my_profile(text, text) to authenticated;
grant execute on function public.username_available(text) to anon, authenticated;
