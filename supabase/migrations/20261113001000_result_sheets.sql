-- Polling-unit result sheets (INEC Form EC8A) as read by the vision model and checked (src/engines/result_sheets.py),
-- with a person's review. Totals count one sheet per polling unit: a verified sheet if there is one, otherwise the
-- latest provisional one (every check passed), never a sheet that needs review. Reached only through the
-- shared-secret functions below.
create table if not exists public.result_sheets (
  id uuid primary key default gen_random_uuid(),
  election text not null,
  pu_code text not null,
  status text not null check (status in ('needs_review', 'provisional', 'verified', 'rejected')),
  data jsonb not null,
  image_sha256 text not null,
  submitted_by uuid,
  reviewed_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  reviewed_at timestamptz,
  unique (election, image_sha256)
);
create index if not exists result_sheets_scope_idx on public.result_sheets (election, pu_code, status);
alter table public.result_sheets enable row level security;
revoke all on public.result_sheets from public, anon, authenticated;

create or replace function public.insert_result_sheet(secret text, p_row jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare r public.result_sheets;
begin
  perform private.check_secret(secret);
  insert into public.result_sheets (election, pu_code, status, data, image_sha256, submitted_by)
  values (p_row->>'election', p_row->>'pu_code', p_row->>'status', p_row->'data', p_row->>'image_sha256',
          nullif(p_row->>'submitted_by', '')::uuid)
  on conflict (election, image_sha256) do nothing
  returning * into r;
  if r.id is null then              -- the same image again: the stored reading, not a second one
    select * into r from public.result_sheets where election = p_row->>'election' and image_sha256 = p_row->>'image_sha256';
    return to_jsonb(r) || jsonb_build_object('duplicate', true);
  end if;
  return to_jsonb(r);
end; $$;

create or replace function public.get_result_sheet(secret text, p_id uuid)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return (select to_jsonb(s) from public.result_sheets s where s.id = p_id);
end; $$;

create or replace function public.review_result_sheet(secret text, p_id uuid, p_status text, p_data jsonb, p_reviewer uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare r public.result_sheets;
begin
  perform private.check_secret(secret);
  if p_status not in ('verified', 'rejected', 'needs_review') then
    raise exception 'invalid_status' using errcode = '22023';
  end if;
  update public.result_sheets set status = p_status, data = coalesce(p_data, data),
         pu_code = coalesce(p_data->>'pu_code', pu_code), reviewed_by = p_reviewer, reviewed_at = now(), updated_at = now()
   where id = p_id returning * into r;
  return to_jsonb(r);
end; $$;

create or replace function public.list_result_sheets(secret text, p_election text, p_state text default null,
  p_lga text default null, p_ward text default null, p_status text default null, p_limit integer default 50,
  p_offset integer default 0)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare prefix text := concat_ws('/', p_state, p_lga, p_ward);
begin
  perform private.check_secret(secret);
  return (select jsonb_build_object(
    'total', (select count(*) from public.result_sheets s where s.election = p_election
              and (prefix = '' or s.pu_code like prefix || '/%') and (p_status is null or s.status = p_status)),
    'sheets', coalesce(jsonb_agg(to_jsonb(t) order by t.updated_at desc), '[]'::jsonb))
    from (select id, election, pu_code, status, data, created_at, updated_at, reviewed_at from public.result_sheets s
          where s.election = p_election and (prefix = '' or s.pu_code like prefix || '/%')
            and (p_status is null or s.status = p_status)
          order by s.updated_at desc limit greatest(1, least(coalesce(p_limit, 50), 200))
          offset greatest(0, coalesce(p_offset, 0))) t);
end; $$;

-- Totals for a scope (the country, a state, an LGA or a ward), broken down one level below it.
create or replace function public.result_totals(secret text, p_election text, p_state text default null,
  p_lga text default null, p_ward text default null, p_verified_only boolean default false)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare prefix text := concat_ws('/', p_state, p_lga, p_ward);
begin
  perform private.check_secret(secret);
  return (
    with best as (
      select distinct on (s.pu_code) s.pu_code, s.status, s.data
      from public.result_sheets s
      where s.election = p_election and (prefix = '' or s.pu_code like prefix || '/%')
        and (s.status = 'verified' or (not p_verified_only and s.status = 'provisional'))
      order by s.pu_code, (s.status = 'verified') desc, s.updated_at desc),
    keyed as (
      select b.*, case when p_state is null then split_part(b.pu_code, '/', 1)
                       when p_lga is null then split_part(b.pu_code, '/', 2)
                       when p_ward is null then split_part(b.pu_code, '/', 3)
                       else b.pu_code end as grp
      from best b),
    units as (
      select case when p_state is null then u.state_code when p_lga is null then u.lga_code
                  when p_ward is null then u.ward_code else u.code end as grp,
             min(case when p_state is null then u.state when p_lga is null then u.lga
                      when p_ward is null then u.ward else u.name end) as name,
             count(*) as polling_units
      from public.polling_units u
      where (p_state is null or u.state_code = p_state) and (p_lga is null or u.lga_code = p_lga)
        and (p_ward is null or u.ward_code = p_ward)
      group by 1),
    votes as (
      select k.grp, v.key as party, sum(nullif(v.value, 'null')::int) as n
      from keyed k, jsonb_each_text(k.data->'votes') v group by k.grp, v.key),
    figs as (
      select grp, count(*) as sheets, count(*) filter (where status = 'verified') as verified,
             sum((data->'figures'->>'registered')::int) as registered, sum((data->'figures'->>'accredited')::int) as accredited,
             sum((data->'figures'->>'votes_cast')::int) as votes_cast, sum((data->'figures'->>'valid')::int) as valid,
             sum((data->'figures'->>'rejected')::int) as rejected
      from keyed group by grp),
    groups as (
      select u.grp as code, u.name, u.polling_units, coalesce(f.sheets, 0) as sheets, coalesce(f.verified, 0) as verified,
             f.registered, f.accredited, f.votes_cast, f.valid, f.rejected,
             coalesce((select jsonb_object_agg(v.party, v.n) from votes v where v.grp = u.grp and v.n is not null), '{}'::jsonb) as votes
      from units u left join figs f on f.grp = u.grp)
    select jsonb_build_object(
      'polling_units', coalesce(sum(g.polling_units), 0), 'sheets', coalesce(sum(g.sheets), 0),
      'verified', coalesce(sum(g.verified), 0), 'registered', sum(g.registered), 'accredited', sum(g.accredited),
      'votes_cast', sum(g.votes_cast), 'valid', sum(g.valid), 'rejected', sum(g.rejected),
      'votes', coalesce((select jsonb_object_agg(party, n) from (select party, sum(n) as n from votes group by party) x where n is not null), '{}'::jsonb),
      'groups', coalesce(jsonb_agg(to_jsonb(g) order by g.code) filter (where g.sheets > 0 or p_ward is null), '[]'::jsonb))
    from groups g);
end; $$;

revoke execute on function public.insert_result_sheet(text, jsonb) from public, authenticated;
revoke execute on function public.get_result_sheet(text, uuid) from public, authenticated;
revoke execute on function public.review_result_sheet(text, uuid, text, jsonb, uuid) from public, authenticated;
revoke execute on function public.list_result_sheets(text, text, text, text, text, text, integer, integer) from public, authenticated;
revoke execute on function public.result_totals(text, text, text, text, text, boolean) from public, authenticated;
grant execute on function public.insert_result_sheet(text, jsonb) to anon;
grant execute on function public.get_result_sheet(text, uuid) to anon;
grant execute on function public.review_result_sheet(text, uuid, text, jsonb, uuid) to anon;
grant execute on function public.list_result_sheets(text, text, text, text, text, text, integer, integer) to anon;
grant execute on function public.result_totals(text, text, text, text, text, boolean) to anon;
