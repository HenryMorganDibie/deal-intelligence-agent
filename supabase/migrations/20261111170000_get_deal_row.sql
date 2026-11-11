-- One deal by id, for public deal pages and their preview cards: a crawler opening a deal page costs a few KB of
-- database egress instead of a full copy of every deal and event (about 12 MB) on a cold API instance.
create or replace function public.get_deal_row(secret text, p_id text)
returns jsonb
language plpgsql stable security definer set search_path to ''
as $$
begin
  perform private.check_secret(secret);
  return (select d.data from public.deals d where d.id = p_id);
end; $$;

revoke all on function public.get_deal_row(text, text) from public, authenticated;
grant execute on function public.get_deal_row(text, text) to anon;
