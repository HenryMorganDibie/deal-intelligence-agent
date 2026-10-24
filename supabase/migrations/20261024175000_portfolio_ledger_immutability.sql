-- Keep financial history append-only and protect tenant ownership metadata.
begin;

drop policy if exists "analysts can update transactions" on public.portfolio_transactions;
drop policy if exists "analysts can update valuation snapshots" on public.portfolio_valuations;
drop policy if exists "analysts can create import jobs" on public.portfolio_import_jobs;
drop policy if exists "analysts can update import jobs" on public.portfolio_import_jobs;
drop policy if exists "authorized portfolio writers can append audit history" on public.portfolio_audit_events;

revoke update, delete on public.portfolio_transactions from authenticated;
revoke update, delete on public.portfolio_valuations from authenticated;
revoke insert, update, delete on public.portfolio_import_jobs from authenticated;
revoke insert on public.portfolio_audit_events from authenticated;
revoke usage, select on sequence public.portfolio_audit_events_id_seq from authenticated;

create or replace function private.prevent_portfolio_ownership_change()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_table_name = 'portfolios' then
    if new.owner_user_id is distinct from old.owner_user_id
       or new.organization_id is distinct from old.organization_id
       or new.base_currency is distinct from old.base_currency
       or new.created_by is distinct from old.created_by then
      raise exception using errcode = '42501',
        message = 'Portfolio ownership and reporting currency are immutable; create a new portfolio to change them';
    end if;
  elsif tg_table_name in ('portfolio_instruments', 'portfolio_transactions', 'portfolio_valuations', 'portfolio_import_jobs') then
    if new.portfolio_id is distinct from old.portfolio_id
       or new.created_by is distinct from old.created_by then
      raise exception using errcode = '42501',
        message = 'Portfolio ownership metadata cannot be reassigned';
    end if;
  end if;
  return new;
end;
$$;

revoke all on function private.prevent_portfolio_ownership_change() from public, anon, authenticated;

create trigger prevent_portfolio_ownership_change
before update on public.portfolios
for each row execute function private.prevent_portfolio_ownership_change();

create trigger prevent_instrument_portfolio_reassignment
before update on public.portfolio_instruments
for each row execute function private.prevent_portfolio_ownership_change();

create trigger prevent_transaction_portfolio_reassignment
before update on public.portfolio_transactions
for each row execute function private.prevent_portfolio_ownership_change();

create trigger prevent_valuation_portfolio_reassignment
before update on public.portfolio_valuations
for each row execute function private.prevent_portfolio_ownership_change();

create trigger prevent_import_job_portfolio_reassignment
before update on public.portfolio_import_jobs
for each row execute function private.prevent_portfolio_ownership_change();

commit;
