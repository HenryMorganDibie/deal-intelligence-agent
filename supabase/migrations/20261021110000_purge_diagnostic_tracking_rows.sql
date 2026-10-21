-- One-off: remove the five diagnostic tracking rows sent while verifying the tracker (visitor zzdiagtest0001).
-- Applied and run once on 2026-10-21; the next migration turns the function into a no-op.
create or replace function private.purge_diagnostic_tracking_rows()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare n integer;
begin
  with a as (delete from public.product_actions where visitor = 'zzdiagtest0001' returning 1),
       b as (delete from public.behavioral_events where visitor = 'zzdiagtest0001' returning 1)
  select (select count(*) from a) + (select count(*) from b) into n;
  return n;
end;
$$;
