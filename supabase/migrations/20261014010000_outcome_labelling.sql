-- Automatic outcome labelling for hosted briefs (see src/engines/outcome_labeller.py).
-- A daily cron calls the API, which labels briefs twice: at 12+ days (price
-- reaction) and at 95+ days (after the 90-day confirmation window closes).
-- The API reads the outcome counts back to calibrate per market.

alter table public.briefs add column if not exists label_stage smallint not null default 0;

create table if not exists public.outcomes (
  brief_id uuid not null references public.briefs(id) on delete cascade,
  signal_type text not null,
  company text not null,
  ticker text,
  market text,
  detection_date date not null,
  event_confirmed boolean,
  payload jsonb not null,
  updated_at timestamptz not null default now(),
  primary key (brief_id, signal_type)
);
alter table public.outcomes enable row level security;   -- functions only

create table if not exists public.ground_truth_events (
  company text not null,
  signal_type text not null,
  event_date date not null,
  source text not null,
  primary key (company, signal_type, event_date, source)
);
alter table public.ground_truth_events enable row level security;

-- Briefs due for a labelling pass: stage 0 at 12+ days, stage 1 at 95+ days.
create or replace function public.briefs_to_label(secret text, max_n int)
returns table (id uuid, company text, ticker text, created_at timestamptz, label_stage smallint, brief jsonb)
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform private.check_secret(secret);
  return query
    select b.id, b.company, b.ticker, b.created_at, b.label_stage, b.brief
    from public.briefs b
    where b.ticker is not null
      and ((b.label_stage = 0 and b.created_at < now() - interval '12 days')
        or (b.label_stage = 1 and b.created_at < now() - interval '95 days'))
    order by b.created_at
    limit greatest(least(max_n, 200), 0);
end;
$$;

-- Store one brief's outcomes and the ground-truth events seen for its company.
create or replace function public.save_labels(secret text, p_brief_id uuid, p_stage smallint, p_outcomes jsonb, p_events jsonb)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform private.check_secret(secret);
  insert into public.outcomes (brief_id, signal_type, company, ticker, market, detection_date, event_confirmed, payload)
  select p_brief_id, o->>'signal_type', o->>'company_name', o->>'ticker', o->>'market',
         (o->>'detection_date')::date, (o->>'event_confirmed')::boolean, o
  from jsonb_array_elements(coalesce(p_outcomes, '[]'::jsonb)) o
  on conflict (brief_id, signal_type) do update
    set event_confirmed = excluded.event_confirmed, payload = excluded.payload, updated_at = now();
  insert into public.ground_truth_events (company, signal_type, event_date, source)
  select e->>'company_name', e->>'signal_type', (e->>'date')::date, e->>'source'
  from jsonb_array_elements(coalesce(p_events, '[]'::jsonb)) e
  on conflict do nothing;
  update public.briefs set label_stage = greatest(label_stage, p_stage) where id = p_brief_id;
end;
$$;

-- Confirmed / refuted counts per "signal_type|market", for calibration.
create or replace function public.outcome_stats(secret text)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  perform private.check_secret(secret);
  return coalesce((
    select jsonb_object_agg(k, jsonb_build_object('confirmed', c, 'refuted', r))
    from (
      select signal_type || '|' || market as k,
             count(*) filter (where event_confirmed) as c,
             count(*) filter (where not event_confirmed) as r
      from public.outcomes
      where event_confirmed is not null and market is not null
      group by 1
    ) s
  ), '{}'::jsonb);
end;
$$;

revoke execute on function public.briefs_to_label(text, int) from public;
revoke execute on function public.save_labels(text, uuid, smallint, jsonb, jsonb) from public;
revoke execute on function public.outcome_stats(text) from public;
grant execute on function public.briefs_to_label(text, int) to anon;
grant execute on function public.save_labels(text, uuid, smallint, jsonb, jsonb) to anon;
grant execute on function public.outcome_stats(text) to anon;
