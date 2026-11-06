-- Incremental reads of deals and events, to keep database egress inside the free plan. Additive only.
--
-- The API keeps the whole deal and event history in memory. It used to download all of it (about 3.7 MB
-- compressed) every 15 minutes per running instance, although the data changes only when ingestion runs. Now an
-- instance asks store_version() whether anything changed (a few hundred bytes) and, if so, downloads only the rows
-- changed since its copy (list_changed_rows). Triggers keep updated_at current on every insert and update.

alter table public.events add column if not exists updated_at timestamptz not null default now();
create index if not exists deals_updated_at_idx on public.deals (updated_at);
create index if not exists events_updated_at_idx on public.events (updated_at);

create or replace function private.touch_updated_at()
returns trigger language plpgsql set search_path to '' as $$
begin
  new.updated_at := now();
  return new;
end; $$;

do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'deals_touch_updated_at') then
    create trigger deals_touch_updated_at before insert or update on public.deals
      for each row execute function private.touch_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'events_touch_updated_at') then
    create trigger events_touch_updated_at before insert or update on public.events
      for each row execute function private.touch_updated_at();
  end if;
end $$;

-- Row count and latest change for each store, over the same rows the page functions return.
create or replace function public.store_version(secret text, p_since date)
returns jsonb language plpgsql stable security definer set search_path to '' as $$
begin
  perform private.check_secret(secret);
  return jsonb_build_object(
    'deals', (select jsonb_build_object('count', count(*), 'changed', max(d.updated_at))
                from public.deals d where d.announced is null or d.announced >= p_since),
    'events', (select jsonb_build_object('count', count(*), 'changed', max(e.updated_at))
                 from public.events e where e.day is null or e.day >= p_since));
end; $$;

-- Rows changed after a time, oldest change first, at most p_limit (the caller reloads everything when the limit
-- is reached).
create or replace function public.list_changed_rows(secret text, p_kind text, p_since date,
                                                    p_changed_after timestamptz, p_limit integer default 2000)
returns jsonb language plpgsql stable security definer set search_path to '' as $$
declare
  lim integer := greatest(1, least(coalesce(p_limit, 2000), 5000));
  out_rows jsonb;
begin
  perform private.check_secret(secret);
  if p_kind = 'deals' then
    select coalesce(jsonb_agg(c.data order by c.updated_at), '[]'::jsonb) into out_rows from (
      select d.data, d.updated_at from public.deals d
       where (d.announced is null or d.announced >= p_since) and d.updated_at > p_changed_after
       order by d.updated_at limit lim) c;
  elsif p_kind = 'events' then
    select coalesce(jsonb_agg(c.data order by c.updated_at), '[]'::jsonb) into out_rows from (
      select e.data, e.updated_at from public.events e
       where (e.day is null or e.day >= p_since) and e.updated_at > p_changed_after
       order by e.updated_at limit lim) c;
  else
    raise exception 'unknown kind';
  end if;
  return jsonb_build_object('rows', out_rows, 'limit', lim);
end; $$;
-- Like the other shared-secret functions, these are executable by the API's key and check the secret first.
