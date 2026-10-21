-- Extend the existing product-action tracker; no new API endpoint is introduced.
-- The existing daily uniqueness guard prevents repeated events from one browser
-- inflating the same action's daily count.
alter table public.product_actions
  drop constraint if exists product_actions_action_check;

alter table public.product_actions
  add constraint product_actions_action_check check (action in (
    'deals_loaded', 'investors_loaded', 'events_loaded', 'risk_data_loaded',
    'company_data_loaded', 'watchlists_used', 'brief_opened', 'performance_data_loaded',
    'deal_search_submitted', 'deal_opened', 'research_submitted', 'market_brief_opened'
  ));

create or replace function public.log_product_action(secret text, p_visitor text, p_action text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform private.check_secret(secret);
  if p_visitor is null or p_visitor !~ '^[a-z0-9]{8,40}$' then
    raise exception 'invalid visitor id';
  end if;
  if p_action is null or p_action not in (
    'deals_loaded', 'investors_loaded', 'events_loaded', 'risk_data_loaded',
    'company_data_loaded', 'watchlists_used', 'brief_opened', 'performance_data_loaded',
    'deal_search_submitted', 'deal_opened', 'research_submitted', 'market_brief_opened'
  ) then
    raise exception 'invalid product action';
  end if;
  insert into public.product_actions (visitor, action)
  values (left(p_visitor, 40), p_action)
  on conflict (day, visitor, action) do nothing;
end;
$$;

revoke execute on function public.log_product_action(text, text, text) from public;
grant execute on function public.log_product_action(text, text, text) to anon;
