-- Two-factor enforced in the database, not only at the app gate: an account with a verified authenticator app can
-- read or write its data only from a session that completed the second step (aal2). Accounts without one are
-- unaffected. Restrictive policies are ANDed with every existing policy, so nothing that was allowed becomes wider.
-- profiles is left out: the app gate reads it to decide the sign-in step, and a username is not sensitive.

create or replace function public.mfa_satisfied() returns boolean
language sql stable security definer set search_path to '' as $$
  select coalesce(auth.jwt() ->> 'aal', '') = 'aal2'
      or not exists (select 1 from auth.mfa_factors f where f.user_id = auth.uid() and f.status = 'verified');
$$;
revoke all on function public.mfa_satisfied() from public, anon;
grant execute on function public.mfa_satisfied() to authenticated;

do $$
declare t text;
begin
  foreach t in array array['briefs', 'organization_invites', 'organization_memberships', 'organizations',
                           'portfolio_audit_events', 'portfolio_import_jobs', 'portfolio_instruments',
                           'portfolio_transactions', 'portfolio_valuations', 'portfolios', 'usage']
  loop
    if exists (select 1 from pg_tables where schemaname = 'public' and tablename = t)
       and not exists (select 1 from pg_policies where schemaname = 'public' and tablename = t and policyname = 'require_second_factor') then
      execute format('create policy require_second_factor on public.%I as restrictive for all to authenticated '
                     'using (public.mfa_satisfied()) with check (public.mfa_satisfied())', t);
    end if;
  end loop;
end $$;
