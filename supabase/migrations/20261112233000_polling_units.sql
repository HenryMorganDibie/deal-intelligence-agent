-- Polling units: INEC's delimitation of Nigeria into states, LGAs, wards (registration areas) and polling units,
-- keyed by INEC's code SS/LL/WW/UUU. Loaded from scripts/data/polling_units_*.csv.gz (scripts/load_polling_units.py).
-- Reached only through the shared-secret functions below, each returning one level of the hierarchy, so a lookup
-- never downloads the whole table.
create table if not exists public.polling_units (
  code text primary key,
  state_code text not null,
  state text not null,
  lga_code text not null,
  lga text not null,
  ward_code text not null,
  ward text not null,
  unit_code text not null,
  name text not null,
  kind text not null check (kind in ('existing', 'new')),
  source text not null,
  updated_at timestamptz not null default now()
);
create index if not exists polling_units_hierarchy_idx on public.polling_units (state_code, lga_code, ward_code, unit_code);
create index if not exists polling_units_name_idx on public.polling_units (lower(name) text_pattern_ops);
alter table public.polling_units enable row level security;
revoke all on public.polling_units from public, anon, authenticated;

create or replace function public.upsert_polling_units(secret text, p_rows jsonb, p_source text)
returns integer language plpgsql security definer set search_path = '' as $$
declare n int;
begin
  perform private.check_secret(secret);
  insert into public.polling_units (code, state_code, state, lga_code, lga, ward_code, ward, unit_code, name, kind, source)
  select r->>'code', r->>'state_code', r->>'state', r->>'lga_code', r->>'lga', r->>'ward_code', r->>'ward',
         r->>'unit_code', r->>'name', r->>'kind', p_source
  from jsonb_array_elements(p_rows) r
  on conflict (code) do update set state = excluded.state, lga = excluded.lga, ward = excluded.ward,
    name = excluded.name, kind = excluded.kind, source = excluded.source, updated_at = now()
  where (public.polling_units.state, public.polling_units.lga, public.polling_units.ward, public.polling_units.name,
         public.polling_units.kind) is distinct from (excluded.state, excluded.lga, excluded.ward, excluded.name, excluded.kind);
  get diagnostics n = row_count;
  return n;
end; $$;

-- One level at a time: no state gives the states; a state gives its LGAs; a state and LGA give its wards.
create or replace function public.polling_unit_areas(secret text, p_state text default null, p_lga text default null)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  if p_state is null then
    return (select coalesce(jsonb_agg(x order by x->>'code'), '[]'::jsonb) from (
      select jsonb_build_object('code', state_code, 'name', min(state), 'lgas', count(distinct lga_code),
                                'wards', count(distinct lga_code || ward_code), 'polling_units', count(*)) x
      from public.polling_units group by state_code) s);
  elsif p_lga is null then
    return (select coalesce(jsonb_agg(x order by x->>'code'), '[]'::jsonb) from (
      select jsonb_build_object('code', lga_code, 'name', min(lga), 'wards', count(distinct ward_code), 'polling_units', count(*)) x
      from public.polling_units where state_code = p_state group by lga_code) s);
  end if;
  return (select coalesce(jsonb_agg(x order by x->>'code'), '[]'::jsonb) from (
    select jsonb_build_object('code', ward_code, 'name', min(ward), 'polling_units', count(*),
                              'new_units', count(*) filter (where kind = 'new')) x
    from public.polling_units where state_code = p_state and lga_code = p_lga group by ward_code) s);
end; $$;

-- Polling units in a ward, or matching a name (optionally within a state), at most 500 per call.
create or replace function public.polling_unit_list(secret text, p_state text default null, p_lga text default null,
  p_ward text default null, p_q text default null, p_limit integer default 100, p_offset integer default 0)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare lim int := greatest(1, least(coalesce(p_limit, 100), 500));
begin
  perform private.check_secret(secret);
  if p_ward is null and coalesce(btrim(p_q), '') = '' then
    raise exception 'ward_or_query_required' using errcode = '22023';
  end if;
  return (select jsonb_build_object('total', (select count(*) from public.polling_units u
            where (p_state is null or u.state_code = p_state) and (p_lga is null or u.lga_code = p_lga)
              and (p_ward is null or u.ward_code = p_ward)
              and (coalesce(btrim(p_q), '') = '' or lower(u.name) like '%' || lower(btrim(p_q)) || '%')),
          'units', coalesce(jsonb_agg(to_jsonb(t) order by t.code), '[]'::jsonb))
    from (select code, state_code, state, lga_code, lga, ward_code, ward, unit_code, name, kind
          from public.polling_units u
          where (p_state is null or u.state_code = p_state) and (p_lga is null or u.lga_code = p_lga)
            and (p_ward is null or u.ward_code = p_ward)
            and (coalesce(btrim(p_q), '') = '' or lower(u.name) like '%' || lower(btrim(p_q)) || '%')
          order by code limit lim offset greatest(0, coalesce(p_offset, 0))) t);
end; $$;

create or replace function public.polling_unit_get(secret text, p_code text)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return (select to_jsonb(t) from (select code, state_code, state, lga_code, lga, ward_code, ward, unit_code, name, kind,
                                          source, updated_at from public.polling_units where code = p_code) t);
end; $$;

revoke execute on function public.upsert_polling_units(text, jsonb, text) from public, authenticated;
revoke execute on function public.polling_unit_areas(text, text, text) from public, authenticated;
revoke execute on function public.polling_unit_list(text, text, text, text, text, integer, integer) from public, authenticated;
revoke execute on function public.polling_unit_get(text, text) from public, authenticated;
grant execute on function public.upsert_polling_units(text, jsonb, text) to anon;
grant execute on function public.polling_unit_areas(text, text, text) to anon;
grant execute on function public.polling_unit_list(text, text, text, text, text, integer, integer) to anon;
grant execute on function public.polling_unit_get(text, text) to anon;
