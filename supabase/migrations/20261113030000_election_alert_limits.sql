-- Election alert allowances by plan (Free 0, Pro 2, Team 5, Institutional 25), enforced here. Additive: a new
-- create function taking the allowance; the earlier fixed-limit one is no longer called.
create or replace function public.election_alert_create_limited(secret text, p_owner uuid, p_name text, p_url text,
  p_filters jsonb, p_max integer)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare r public.election_alert_subs;
begin
  perform private.check_secret(secret);
  perform pg_advisory_xact_lock(hashtextextended('election_alerts:' || p_owner::text, 0));
  if (select count(*) from public.election_alert_subs where owner = p_owner) >= greatest(coalesce(p_max, 0), 0) then
    raise exception 'alert_limit' using errcode = '23514';
  end if;
  insert into public.election_alert_subs (owner, name, webhook_url, filters)
  values (p_owner, p_name, p_url, coalesce(p_filters, '{}'::jsonb)) returning * into r;
  return to_jsonb(r);
end; $$;
revoke execute on function public.election_alert_create_limited(text, uuid, text, text, jsonb, integer) from public, authenticated;
grant execute on function public.election_alert_create_limited(text, uuid, text, text, jsonb, integer) to anon;
