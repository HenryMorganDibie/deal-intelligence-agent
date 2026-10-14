-- Shared LLM reproducibility cache for the hosted API (serverless instances do
-- not share a disk). Same keys as data/llm_cache.json locally.
create table if not exists public.llm_cache (
  key text primary key,
  text text not null,
  created_at timestamptz not null default now()
);
alter table public.llm_cache enable row level security;

create or replace function public.llm_cache_get(secret text, p_key text)
returns text language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  return (select c.text from public.llm_cache c where c.key = p_key);
end; $$;

create or replace function public.llm_cache_put(secret text, p_key text, p_text text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  perform private.check_secret(secret);
  insert into public.llm_cache (key, text) values (p_key, p_text) on conflict (key) do nothing;
end; $$;

revoke execute on function public.llm_cache_get(text, text) from public;
revoke execute on function public.llm_cache_put(text, text, text) from public;
grant execute on function public.llm_cache_get(text, text) to anon;
grant execute on function public.llm_cache_put(text, text, text) to anon;
