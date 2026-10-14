-- Showcase briefs: the pipeline run daily on a fixed list of companies for the public site.
-- Kept apart from visitors' briefs, so the site never reveals what anyone searched and
-- repeated daily runs never enter the live outcome statistics.
create table if not exists public.showcase (
  id uuid primary key default gen_random_uuid(),
  company text not null,
  ticker text,
  market text,
  summary jsonb not null,
  brief jsonb not null,
  markdown text,
  created_at timestamptz not null default now()
);
create index if not exists showcase_created_idx on public.showcase (created_at desc);
alter table public.showcase enable row level security;   -- functions only

create or replace function public.save_showcase(secret text, p_company text, p_ticker text, p_market text,
                                                p_summary jsonb, p_brief jsonb, p_markdown text)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  new_id uuid;
begin
  perform private.check_secret(secret);
  insert into public.showcase (company, ticker, market, summary, brief, markdown)
  values (p_company, p_ticker, p_market, p_summary, p_brief, p_markdown)
  returning id into new_id;
  return new_id;
end;
$$;

-- Public: summaries of recent showcase briefs (newest first).
create or replace function public.recent_showcase(p_days int)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(jsonb_agg(s.summary || jsonb_build_object('id', s.id, 'created_at', s.created_at)
                            order by s.created_at desc), '[]'::jsonb)
  from (select * from public.showcase
        where created_at >= now() - make_interval(days => greatest(least(p_days, 60), 1))
        order by created_at desc limit 80) s;
$$;

-- Brief pages resolve showcase briefs as well as visitors' briefs.
create or replace function public.get_brief(p_id uuid)
returns table (id uuid, company text, ticker text, brief jsonb, markdown text, created_at timestamptz)
language sql
stable
security definer
set search_path = ''
as $$
  select b.id, b.company, b.ticker, b.brief, b.markdown, b.created_at from public.briefs b where b.id = p_id
  union all
  select s.id, s.company, s.ticker, s.brief, s.markdown, s.created_at from public.showcase s where s.id = p_id;
$$;

revoke execute on function public.save_showcase(text, text, text, text, jsonb, jsonb, text) from public;
grant execute on function public.save_showcase(text, text, text, text, jsonb, jsonb, text) to anon;
grant execute on function public.recent_showcase(int) to anon;
