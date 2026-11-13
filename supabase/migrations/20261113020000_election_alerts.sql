-- Election alerts: an account's subscriptions to election incidents or coverage, pushed to a webhook (Slack, Teams,
-- Discord, Google Chat or JSON) by the hourly election-news job. Each story is sent to a subscription at most once:
-- the job claims it before sending and releases the claim if delivery fails. Additive only.
create table if not exists public.election_alert_subs (
  id uuid primary key default gen_random_uuid(),
  owner uuid not null references auth.users (id) on delete cascade,
  name text not null check (char_length(name) between 1 and 80),
  webhook_url text not null check (webhook_url like 'https://%' and char_length(webhook_url) <= 500),
  filters jsonb not null default '{}'::jsonb,
  active boolean not null default true,
  created_at timestamptz not null default now()
);
create index if not exists election_alert_subs_owner_idx on public.election_alert_subs (owner);
create table if not exists public.election_alert_sent (
  sub_id uuid not null references public.election_alert_subs (id) on delete cascade,
  story_id text not null,
  sent_at timestamptz not null default now(),
  primary key (sub_id, story_id)
);
alter table public.election_alert_subs enable row level security;
alter table public.election_alert_sent enable row level security;
revoke all on public.election_alert_subs, public.election_alert_sent from public, anon, authenticated;

create or replace function public.election_alert_create(secret text, p_owner uuid, p_name text, p_url text, p_filters jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare r public.election_alert_subs;
begin
  perform private.check_secret(secret);
  perform pg_advisory_xact_lock(hashtextextended('election_alerts:' || p_owner::text, 0));
  if (select count(*) from public.election_alert_subs where owner = p_owner) >= 10 then
    raise exception 'alert_limit' using errcode = '23514';
  end if;
  insert into public.election_alert_subs (owner, name, webhook_url, filters)
  values (p_owner, p_name, p_url, coalesce(p_filters, '{}'::jsonb)) returning * into r;
  return to_jsonb(r);
end; $$;

create or replace function public.election_alert_list(secret text, p_owner uuid)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return (select coalesce(jsonb_agg(to_jsonb(s) || jsonb_build_object('sent',
            (select count(*) from public.election_alert_sent x where x.sub_id = s.id)) order by s.created_at), '[]'::jsonb)
          from public.election_alert_subs s where s.owner = p_owner);
end; $$;

create or replace function public.election_alert_delete(secret text, p_owner uuid, p_id uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  delete from public.election_alert_subs where id = p_id and owner = p_owner;
  return found;
end; $$;

-- Every active subscription, for the delivery job.
create or replace function public.election_alert_active(secret text)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return (select coalesce(jsonb_agg(to_jsonb(s)), '[]'::jsonb) from public.election_alert_subs s where s.active);
end; $$;

-- Claim stories for a subscription; returns only those not sent before.
create or replace function public.election_alert_claim(secret text, p_sub uuid, p_story_ids text[])
returns text[] language plpgsql security definer set search_path = '' as $$
declare claimed text[];
begin
  perform private.check_secret(secret);
  with ins as (
    insert into public.election_alert_sent (sub_id, story_id)
    select p_sub, unnest(p_story_ids) on conflict do nothing returning story_id)
  select coalesce(array_agg(story_id), '{}') into claimed from ins;
  return claimed;
end; $$;

create or replace function public.election_alert_release(secret text, p_sub uuid, p_story_ids text[])
returns integer language plpgsql security definer set search_path = '' as $$
declare n int;
begin
  perform private.check_secret(secret);
  delete from public.election_alert_sent where sub_id = p_sub and story_id = any(p_story_ids);
  get diagnostics n = row_count;
  return n;
end; $$;

revoke execute on function public.election_alert_create(text, uuid, text, text, jsonb) from public, authenticated;
revoke execute on function public.election_alert_list(text, uuid) from public, authenticated;
revoke execute on function public.election_alert_delete(text, uuid, uuid) from public, authenticated;
revoke execute on function public.election_alert_active(text) from public, authenticated;
revoke execute on function public.election_alert_claim(text, uuid, text[]) from public, authenticated;
revoke execute on function public.election_alert_release(text, uuid, text[]) from public, authenticated;
grant execute on function public.election_alert_create(text, uuid, text, text, jsonb) to anon;
grant execute on function public.election_alert_list(text, uuid) to anon;
grant execute on function public.election_alert_delete(text, uuid, uuid) to anon;
grant execute on function public.election_alert_active(text) to anon;
grant execute on function public.election_alert_claim(text, uuid, text[]) to anon;
grant execute on function public.election_alert_release(text, uuid, text[]) to anon;
