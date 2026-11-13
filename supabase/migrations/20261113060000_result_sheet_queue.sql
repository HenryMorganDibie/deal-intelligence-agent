-- Result sheets queued for reading: polling-unit sheet links an account imports in bulk (from IReV or its own
-- collection), read by the scheduled job within a daily budget, highest priority first. Each account's queue is its
-- own. No direct table access for any client role.
create table if not exists public.result_sheet_queue (
  id uuid primary key default gen_random_uuid(),
  owner uuid not null,
  election text not null,
  pu_code text not null,
  image_url text not null check (image_url like 'https://%' and char_length(image_url) <= 600),
  priority integer not null default 0,
  status text not null default 'queued' check (status in ('queued', 'reading', 'read', 'failed')),
  attempts integer not null default 0,
  error text,
  sheet_id uuid,
  created_at timestamptz not null default now(),
  taken_at timestamptz,
  done_at timestamptz,
  unique (owner, election, pu_code, image_url)
);
create index if not exists result_sheet_queue_next_idx on public.result_sheet_queue (status, priority desc, created_at);
alter table public.result_sheet_queue enable row level security;
revoke all on public.result_sheet_queue from public, anon, authenticated;

create or replace function public.sheet_queue_add(secret text, p_owner uuid, p_rows jsonb)
returns integer language plpgsql security definer set search_path = '' as $$
declare n int;
begin
  perform private.check_secret(secret);
  insert into public.result_sheet_queue (owner, election, pu_code, image_url, priority)
  select p_owner, r->>'election', r->>'pu_code', r->>'image_url', coalesce((r->>'priority')::int, 0)
  from jsonb_array_elements(p_rows) r
  on conflict (owner, election, pu_code, image_url) do nothing;
  get diagnostics n = row_count;
  return n;
end; $$;

-- The next sheets to read, at most p_limit and never more than the day's budget allows; a sheet taken but not
-- finished within 30 minutes (a job that stopped) is taken again, up to three attempts.
create or replace function public.sheet_queue_take(secret text, p_limit integer, p_budget integer)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare used int; n int; rows jsonb;
begin
  perform private.check_secret(secret);
  select count(*) into used from public.result_sheet_queue
   where taken_at >= date_trunc('day', now() at time zone 'utc') at time zone 'utc';
  n := greatest(0, least(coalesce(p_limit, 0), coalesce(p_budget, 0) - used));
  with picked as (
    select id from public.result_sheet_queue
     where (status = 'queued' or (status = 'reading' and taken_at < now() - interval '30 minutes')) and attempts < 3
     order by priority desc, created_at
     limit n for update skip locked)
  update public.result_sheet_queue q set status = 'reading', attempts = q.attempts + 1, taken_at = now()
    from picked where q.id = picked.id;
  select coalesce(jsonb_agg(to_jsonb(q)), '[]'::jsonb) into rows from public.result_sheet_queue q
   where q.status = 'reading' and q.taken_at >= now() - interval '5 seconds';
  return jsonb_build_object('rows', rows, 'used_today', used, 'budget', p_budget);
end; $$;

create or replace function public.sheet_queue_done(secret text, p_id uuid, p_status text, p_error text, p_sheet uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  update public.result_sheet_queue
     set status = case when p_status = 'failed' and attempts < 3 then 'queued' else p_status end,
         error = left(p_error, 300), sheet_id = p_sheet, done_at = now()
   where id = p_id;
  return found;
end; $$;

create or replace function public.sheet_queue_status(secret text, p_owner uuid, p_election text)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return jsonb_build_object(
    'by_status', (select coalesce(jsonb_object_agg(status, n), '{}'::jsonb) from
                   (select status, count(*) n from public.result_sheet_queue where owner = p_owner and election = p_election group by status) s),
    'failed', (select coalesce(jsonb_agg(jsonb_build_object('pu_code', pu_code, 'error', error) order by done_at desc), '[]'::jsonb)
               from (select pu_code, error, done_at from public.result_sheet_queue
                      where owner = p_owner and election = p_election and status = 'failed' order by done_at desc limit 20) f));
end; $$;

revoke execute on function public.sheet_queue_add(text, uuid, jsonb) from public, authenticated;
revoke execute on function public.sheet_queue_take(text, integer, integer) from public, authenticated;
revoke execute on function public.sheet_queue_done(text, uuid, text, text, uuid) from public, authenticated;
revoke execute on function public.sheet_queue_status(text, uuid, text) from public, authenticated;
grant execute on function public.sheet_queue_add(text, uuid, jsonb) to anon;
grant execute on function public.sheet_queue_take(text, integer, integer) to anon;
grant execute on function public.sheet_queue_done(text, uuid, text, text, uuid) to anon;
grant execute on function public.sheet_queue_status(text, uuid, text) to anon;
