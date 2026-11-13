-- Result sheets belong to the account that submitted them. A client's sheets, reviews and the totals built from
-- them are visible only to that account and never feed another account's numbers. The shared election
-- intelligence (news, incidents, polling units) is unaffected.
--
-- Additive only: a new column, new functions beside the earlier ones (which the API no longer calls), and a lookup
-- of the account behind an API key. Sheets stored before this have no owner and are visible to no one. The image
-- fingerprint stored for duplicate detection now includes the owner, so the same image from two accounts is two
-- separate sheets under the existing (election, image_sha256) constraint.

alter table public.result_sheets add column if not exists owner uuid references auth.users (id) on delete cascade;
create index if not exists result_sheets_owner_scope_idx on public.result_sheets (owner, election, pu_code, status);

-- The account behind an API key, for data kept per account.
create or replace function public.api_key_account(secret text, p_key_id uuid)
returns uuid language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return (select k.user_id from public.api_keys k where k.id = p_key_id and k.revoked_at is null);
end; $$;

create or replace function public.result_sheet_insert(secret text, p_owner uuid, p_row jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare r public.result_sheets;
begin
  perform private.check_secret(secret);
  if p_owner is null then raise exception 'owner_required' using errcode = '22023'; end if;
  insert into public.result_sheets (owner, election, pu_code, status, data, image_sha256, submitted_by)
  values (p_owner, p_row->>'election', p_row->>'pu_code', p_row->>'status', p_row->'data', p_row->>'image_sha256', p_owner)
  on conflict (election, image_sha256) do nothing
  returning * into r;
  if r.id is null then
    select * into r from public.result_sheets
     where owner = p_owner and election = p_row->>'election' and image_sha256 = p_row->>'image_sha256';
    return to_jsonb(r) || jsonb_build_object('duplicate', true);
  end if;
  return to_jsonb(r);
end; $$;

create or replace function public.result_sheet_get(secret text, p_owner uuid, p_id uuid)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return (select to_jsonb(s) from public.result_sheets s where s.id = p_id and s.owner = p_owner);
end; $$;

create or replace function public.result_sheet_review(secret text, p_owner uuid, p_id uuid, p_status text, p_data jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare r public.result_sheets;
begin
  perform private.check_secret(secret);
  if p_status not in ('verified', 'rejected', 'needs_review') then
    raise exception 'invalid_status' using errcode = '22023';
  end if;
  update public.result_sheets set status = p_status, data = coalesce(p_data, data),
         pu_code = coalesce(p_data->>'pu_code', pu_code), reviewed_by = p_owner, reviewed_at = now(), updated_at = now()
   where id = p_id and owner = p_owner returning * into r;
  return to_jsonb(r);
end; $$;

create or replace function public.result_sheet_list(secret text, p_owner uuid, p_election text, p_state text default null,
  p_lga text default null, p_ward text default null, p_status text default null, p_limit integer default 50,
  p_offset integer default 0)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare prefix text := concat_ws('/', p_state, p_lga, p_ward);
begin
  perform private.check_secret(secret);
  return (select jsonb_build_object(
    'total', (select count(*) from public.result_sheets s where s.owner = p_owner and s.election = p_election
              and (prefix = '' or s.pu_code like prefix || '/%') and (p_status is null or s.status = p_status)),
    'sheets', coalesce(jsonb_agg(to_jsonb(t) order by t.updated_at desc), '[]'::jsonb))
    from (select id, election, pu_code, status, data, created_at, updated_at, reviewed_at from public.result_sheets s
          where s.owner = p_owner and s.election = p_election and (prefix = '' or s.pu_code like prefix || '/%')
            and (p_status is null or s.status = p_status)
          order by s.updated_at desc limit greatest(1, least(coalesce(p_limit, 50), 200))
          offset greatest(0, coalesce(p_offset, 0))) t);
end; $$;

create or replace function public.result_sheet_totals(secret text, p_owner uuid, p_election text, p_state text default null,
  p_lga text default null, p_ward text default null, p_verified_only boolean default false)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare prefix text := concat_ws('/', p_state, p_lga, p_ward);
begin
  perform private.check_secret(secret);
  return (
    with best as (
      select distinct on (s.pu_code) s.pu_code, s.status, s.data
      from public.result_sheets s
      where s.owner = p_owner and s.election = p_election and (prefix = '' or s.pu_code like prefix || '/%')
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

revoke execute on function public.api_key_account(text, uuid) from public, authenticated;
revoke execute on function public.result_sheet_insert(text, uuid, jsonb) from public, authenticated;
revoke execute on function public.result_sheet_get(text, uuid, uuid) from public, authenticated;
revoke execute on function public.result_sheet_review(text, uuid, uuid, text, jsonb) from public, authenticated;
revoke execute on function public.result_sheet_list(text, uuid, text, text, text, text, text, integer, integer) from public, authenticated;
revoke execute on function public.result_sheet_totals(text, uuid, text, text, text, text, boolean) from public, authenticated;
grant execute on function public.api_key_account(text, uuid) to anon;
grant execute on function public.result_sheet_insert(text, uuid, jsonb) to anon;
grant execute on function public.result_sheet_get(text, uuid, uuid) to anon;
grant execute on function public.result_sheet_review(text, uuid, uuid, text, jsonb) to anon;
grant execute on function public.result_sheet_list(text, uuid, text, text, text, text, text, integer, integer) to anon;
grant execute on function public.result_sheet_totals(text, uuid, text, text, text, text, boolean) to anon;
