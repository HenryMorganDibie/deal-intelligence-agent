-- Public, opaque-link market briefs, kept separate from company signal briefs and outcome calibration.
create table if not exists public.market_briefs (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  report jsonb not null,
  markdown text not null,
  created_at timestamptz not null default now()
);
create index if not exists market_briefs_created_idx on public.market_briefs (created_at desc);
alter table public.market_briefs enable row level security;

create or replace function public.save_market_brief(secret text, p_title text, p_report jsonb, p_markdown text)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  new_id uuid;
begin
  perform private.check_secret(secret);
  insert into public.market_briefs (title, report, markdown)
  values (p_title, p_report, p_markdown)
  returning id into new_id;
  return new_id;
end;
$$;

create or replace function public.get_market_brief(p_id uuid)
returns table (id uuid, title text, report jsonb, markdown text, created_at timestamptz)
language sql
stable
security definer
set search_path = ''
as $$
  select b.id, b.title, b.report, b.markdown, b.created_at
  from public.market_briefs b where b.id = p_id;
$$;

revoke execute on function public.save_market_brief(text, text, jsonb, text) from public, authenticated;
grant execute on function public.save_market_brief(text, text, jsonb, text) to anon;
grant execute on function public.get_market_brief(uuid) to anon, authenticated;
