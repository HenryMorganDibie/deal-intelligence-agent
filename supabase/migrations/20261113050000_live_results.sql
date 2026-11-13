-- Live results announced constituency by constituency (The Gambia, 5 December 2026): one row per constituency,
-- replaced when the commission's figure is corrected, with every earlier version kept in history. Entered by the
-- service's operators through the API; read by the live tracker. No direct table access for any client role.
create table if not exists public.live_results (
  election text not null,
  area text not null,
  data jsonb not null,
  history jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now(),
  primary key (election, area)
);
alter table public.live_results enable row level security;
revoke all on public.live_results from public, anon, authenticated;

create or replace function public.live_result_upsert(secret text, p_election text, p_area text, p_data jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare r public.live_results;
begin
  perform private.check_secret(secret);
  insert into public.live_results (election, area, data) values (p_election, p_area, p_data)
  on conflict (election, area) do update
    set history = (public.live_results.history || jsonb_build_array(public.live_results.data || jsonb_build_object('replaced_at', now()))),
        data = excluded.data, updated_at = now()
  returning * into r;
  return r.data || jsonb_build_object('updated_at', r.updated_at, 'versions', jsonb_array_length(r.history) + 1);
end; $$;

create or replace function public.live_result_list(secret text, p_election text)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return (select coalesce(jsonb_agg(l.data || jsonb_build_object('updated_at', l.updated_at,
            'versions', jsonb_array_length(l.history) + 1) order by l.area), '[]'::jsonb)
          from public.live_results l where l.election = p_election);
end; $$;

create or replace function public.live_result_delete(secret text, p_election text, p_area text)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  delete from public.live_results where election = p_election and area = p_area;
  return found;
end; $$;

revoke execute on function public.live_result_upsert(text, text, text, jsonb) from public, authenticated;
revoke execute on function public.live_result_list(text, text) from public, authenticated;
revoke execute on function public.live_result_delete(text, text, text) from public, authenticated;
grant execute on function public.live_result_upsert(text, text, text, jsonb) to anon;
grant execute on function public.live_result_list(text, text) to anon;
grant execute on function public.live_result_delete(text, text, text) to anon;
