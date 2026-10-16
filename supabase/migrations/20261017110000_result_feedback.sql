create table if not exists public.result_feedback (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  client_hash text not null,
  result_type text not null check (result_type in ('brief', 'research', 'country_report', 'sector_report')),
  result_id uuid not null,
  category text not null check (category in (
    'incorrect_signal', 'wrong_company', 'missed_event', 'unsupported_claim', 'outdated_data', 'other'
  )),
  note text not null default '' check (char_length(note) <= 1000),
  reviewed_at timestamptz
);
create index if not exists result_feedback_created_idx on public.result_feedback (created_at desc);
create index if not exists result_feedback_client_created_idx on public.result_feedback (client_hash, created_at desc);
alter table public.result_feedback enable row level security;
revoke all on public.result_feedback from public, anon, authenticated;

create or replace function public.submit_result_feedback(
  secret text, p_client_hash text, p_result_type text, p_result_id uuid, p_category text, p_note text
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  feedback_id uuid;
  day_start timestamptz := date_trunc('day', now() at time zone 'utc') at time zone 'utc';
begin
  perform private.check_secret(secret);
  if p_client_hash is null or p_client_hash !~ '^[a-f0-9]{32}$' then
    raise exception 'invalid client hash';
  end if;
  if p_result_type not in ('brief', 'research', 'country_report', 'sector_report') then
    raise exception 'invalid result type';
  end if;
  if p_category not in (
    'incorrect_signal', 'wrong_company', 'missed_event', 'unsupported_claim', 'outdated_data', 'other'
  ) then
    raise exception 'invalid feedback category';
  end if;
  if char_length(coalesce(p_note, '')) > 1000 then
    raise exception 'feedback note too long';
  end if;
  if (select count(*) from public.result_feedback
      where client_hash = p_client_hash and created_at >= day_start) >= 10 then
    raise exception 'feedback_limit';
  end if;
  insert into public.result_feedback (client_hash, result_type, result_id, category, note)
  values (p_client_hash, p_result_type, p_result_id, p_category, coalesce(p_note, ''))
  returning id into feedback_id;
  return feedback_id;
end;
$$;

create or replace function public.list_result_feedback(secret text, p_limit int default 100)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  items jsonb;
begin
  perform private.check_secret(secret);
  select coalesce(jsonb_agg(to_jsonb(f) order by f.created_at desc), '[]'::jsonb)
  into items
  from (
    select id, created_at, result_type, result_id, category, note, reviewed_at
    from public.result_feedback
    order by created_at desc
    limit greatest(1, least(coalesce(p_limit, 100), 100))
  ) f;
  return items;
end;
$$;

create or replace function public.review_result_feedback(secret text, p_feedback_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  changed int;
begin
  perform private.check_secret(secret);
  update public.result_feedback
  set reviewed_at = coalesce(reviewed_at, now())
  where id = p_feedback_id;
  get diagnostics changed = row_count;
  return changed > 0;
end;
$$;

revoke execute on function public.submit_result_feedback(text, text, text, uuid, text, text) from public;
revoke execute on function public.list_result_feedback(text, int) from public;
revoke execute on function public.review_result_feedback(text, uuid) from public;
grant execute on function public.submit_result_feedback(text, text, text, uuid, text, text) to anon;
grant execute on function public.list_result_feedback(text, int) to anon;
grant execute on function public.review_result_feedback(text, uuid) to anon;
