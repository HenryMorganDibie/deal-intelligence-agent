-- Owner-only usage counts: one row per page view, keyed by an anonymous browser id (no IP, no cookies
-- beyond the id the browser generates). "Users" are visitors who opened the product itself (/app).
create table if not exists public.visits (
  day date not null default (now() at time zone 'utc')::date,
  visitor text not null,
  path text not null,
  created_at timestamptz not null default now()
);
create index if not exists visits_day_idx on public.visits (day);
alter table public.visits enable row level security;   -- functions only

create or replace function public.log_visit(secret text, p_visitor text, p_path text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform private.check_secret(secret);
  insert into public.visits (visitor, path) values (left(p_visitor, 40), left(p_path, 200));
end;
$$;

create or replace function public.visit_stats(secret text, p_days int)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  since date := (now() at time zone 'utc')::date - greatest(p_days, 1) + 1;
begin
  perform private.check_secret(secret);
  return jsonb_build_object(
    'since', since,
    'totals', (select jsonb_build_object(
        'views', count(*),
        'visitors', count(distinct visitor),
        'users', count(distinct visitor) filter (where path like '/app%'),
        'returning_users', (select count(*) from (
            select visitor from public.visits
            where day >= since and path like '/app%'
            group by visitor having count(distinct day) > 1) r))
      from public.visits where day >= since),
    'days', coalesce((select jsonb_agg(d order by d->>'day' desc) from (
        select jsonb_build_object('day', day, 'views', count(*), 'visitors', count(distinct visitor),
                                  'users', count(distinct visitor) filter (where path like '/app%')) d
        from public.visits where day >= since group by day) x), '[]'::jsonb),
    'pages', coalesce((select jsonb_agg(p) from (
        select jsonb_build_object('path', path, 'views', count(*), 'visitors', count(distinct visitor)) p
        from public.visits where day >= since group by path order by count(*) desc limit 15) y), '[]'::jsonb)
  );
end;
$$;

revoke execute on function public.log_visit(text, text, text) from public;
revoke execute on function public.visit_stats(text, int) from public;
grant execute on function public.log_visit(text, text, text) to anon;
grant execute on function public.visit_stats(text, int) to anon;
