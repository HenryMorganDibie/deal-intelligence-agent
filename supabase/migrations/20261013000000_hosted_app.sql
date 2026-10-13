-- Hosted app schema: per-user briefs and a daily analysis quota.
-- Every read and write goes through the caller's own access token, so row level
-- security is the only access path; no service-role key is used.

create table public.briefs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  company text not null,
  ticker text,
  severity text,
  signal_count int not null default 0,
  llm_used boolean not null default false,
  brief jsonb not null,
  markdown text,
  created_at timestamptz not null default now()
);
create index briefs_user_created_idx on public.briefs (user_id, created_at desc);
alter table public.briefs enable row level security;
create policy "owner can read briefs" on public.briefs
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "owner can insert briefs" on public.briefs
  for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "owner can delete briefs" on public.briefs
  for delete to authenticated using ((select auth.uid()) = user_id);

create table public.usage (
  user_id uuid not null references auth.users(id) on delete cascade,
  day date not null default (now() at time zone 'utc')::date,
  runs int not null default 0,
  primary key (user_id, day)
);
alter table public.usage enable row level security;
create policy "owner can read usage" on public.usage
  for select to authenticated using ((select auth.uid()) = user_id);

-- Atomically reserve one analysis run for the calling user. The caller may ask
-- for a lower limit, never a higher one than the server-side cap of 10.
-- Returns the runs used today, or -1 when the limit is already reached.
create or replace function public.consume_run(daily_limit int)
returns int
language plpgsql
security definer
set search_path = ''
as $$
declare
  uid uuid := auth.uid();
  cap int := least(greatest(coalesce(daily_limit, 0), 0), 10);
  used int;
begin
  if uid is null then
    raise exception 'not authenticated';
  end if;
  insert into public.usage (user_id, day, runs)
  select uid, (now() at time zone 'utc')::date, 1
  where cap > 0
  on conflict (user_id, day) do update
    set runs = public.usage.runs + 1
    where public.usage.runs < cap
  returning runs into used;
  return coalesce(used, -1);
end;
$$;
revoke execute on function public.consume_run(int) from public, anon;
grant execute on function public.consume_run(int) to authenticated;
