-- Labelling for the yearly independent review. The owner creates a private link per annotator (A, B) and
-- for the adjudicator; only a SHA-256 hash of each link's token is stored. Annotators save labels through
-- the API; the export function hands the complete set to a scheduled workflow that commits it to the
-- repository next to the sample. Annotators never receive the system's decisions or each other's labels;
-- the adjudicator receives both annotators' labels to resolve disagreements.
create table if not exists public.review_annotators (
  token_hash text primary key check (token_hash ~ '^[0-9a-f]{64}$'),
  year int not null check (year between 2020 and 2100),
  role text not null check (role in ('a', 'b', 'adjudicator')),
  name text not null check (length(name) between 1 and 80),
  created_at timestamptz not null default now(),
  revoked boolean not null default false
);
create table if not exists public.review_labels (
  year int not null,
  role text not null check (role in ('a', 'b', 'adjudicator')),
  kind text not null check (kind in ('item', 'pair')),
  item_id text not null check (item_id ~ '^[rp][0-9]{3}$'),
  label jsonb not null check (jsonb_typeof(label) = 'object' and octet_length(label::text) <= 4000),
  annotator text not null,
  updated_at timestamptz not null default now(),
  primary key (year, role, kind, item_id)
);
alter table public.review_annotators enable row level security;
alter table public.review_labels enable row level security;
revoke all on public.review_annotators from public, anon, authenticated;
revoke all on public.review_labels from public, anon, authenticated;

create or replace function public.review_create_annotator(secret text, p_token_hash text, p_year int, p_role text, p_name text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  insert into public.review_annotators (token_hash, year, role, name) values (p_token_hash, p_year, p_role, left(p_name, 80));
end;
$$;

-- The caller's identity and their own labels; the adjudicator also receives both annotators' labels.
create or replace function public.review_session(secret text, p_token_hash text)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare me public.review_annotators;
begin
  perform private.check_secret(secret);
  select * into me from public.review_annotators where token_hash = p_token_hash and not revoked;
  if me is null then return null; end if;
  return jsonb_build_object(
    'year', me.year, 'role', me.role, 'name', me.name,
    'labels', coalesce((select jsonb_agg(jsonb_build_object('kind', kind, 'item_id', item_id, 'label', label))
                        from public.review_labels where year = me.year and role = me.role), '[]'::jsonb),
    'annotator_labels', case when me.role = 'adjudicator' then coalesce((
        select jsonb_agg(jsonb_build_object('role', role, 'kind', kind, 'item_id', item_id, 'label', label))
        from public.review_labels where year = me.year and role in ('a', 'b')), '[]'::jsonb) end);
end;
$$;

create or replace function public.review_save_label(secret text, p_token_hash text, p_kind text, p_item_id text, p_label jsonb)
returns boolean language plpgsql security definer set search_path = '' as $$
declare me public.review_annotators;
begin
  perform private.check_secret(secret);
  select * into me from public.review_annotators where token_hash = p_token_hash and not revoked;
  if me is null then return false; end if;
  insert into public.review_labels (year, role, kind, item_id, label, annotator)
  values (me.year, me.role, p_kind, p_item_id, p_label, me.name)
  on conflict (year, role, kind, item_id) do update
    set label = excluded.label, annotator = excluded.annotator, updated_at = now();
  return true;
end;
$$;

-- Completed rows per role: signed with the main judgement made.
create or replace function public.review_progress(secret text, p_year int)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return coalesce((select jsonb_object_agg(role || ':' || kind, n) from (
    select role, kind, count(*) filter (where
      (kind = 'item' and label->'is_transaction' is not null and jsonb_typeof(label->'is_transaction') <> 'null')
      or (kind = 'pair' and label->'same_transaction' is not null and jsonb_typeof(label->'same_transaction') <> 'null')) as n
    from public.review_labels where year = p_year group by role, kind) t), '{}'::jsonb);
end;
$$;

create or replace function public.review_export(secret text, p_year int)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return coalesce((select jsonb_agg(jsonb_build_object('role', role, 'kind', kind, 'item_id', item_id,
                                                       'label', label, 'annotator', annotator) order by role, kind, item_id)
                   from public.review_labels where year = p_year), '[]'::jsonb);
end;
$$;

revoke execute on function public.review_create_annotator(text, text, int, text, text) from public;
revoke execute on function public.review_session(text, text) from public;
revoke execute on function public.review_save_label(text, text, text, text, jsonb) from public;
revoke execute on function public.review_progress(text, int) from public;
revoke execute on function public.review_export(text, int) from public;
grant execute on function public.review_create_annotator(text, text, int, text, text) to anon;
grant execute on function public.review_session(text, text) to anon;
grant execute on function public.review_save_label(text, text, text, text, jsonb) to anon;
grant execute on function public.review_progress(text, int) to anon;
grant execute on function public.review_export(text, int) to anon;
