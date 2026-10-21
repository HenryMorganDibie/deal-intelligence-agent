-- The one-off purge has run; leave a no-op so the function can never delete anything again.
create or replace function private.purge_diagnostic_tracking_rows()
returns integer
language sql
security definer
set search_path = ''
as $$ select 0 $$;
revoke execute on function private.purge_diagnostic_tracking_rows() from public, anon, authenticated;
