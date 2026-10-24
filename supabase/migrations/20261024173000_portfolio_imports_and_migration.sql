-- Atomic transaction imports and explicit local-to-cloud migration.
begin;
alter table public.portfolio_import_jobs add column if not exists idempotency_key uuid;
create unique index if not exists portfolio_import_jobs_idempotency_unique on public.portfolio_import_jobs(portfolio_id,idempotency_key) where idempotency_key is not null;
create table public.portfolio_migration_receipts (
 id uuid primary key default gen_random_uuid(),
 portfolio_id uuid not null references public.portfolios(id) on delete restrict,
 migration_key uuid not null,
 user_id uuid not null references auth.users(id) on delete restrict,
 holdings_count integer not null check(holdings_count >= 0),
 valuations_count integer not null check(valuations_count >= 0),
 created_at timestamptz not null default now(),
 unique(portfolio_id,migration_key)
);
alter table public.portfolio_migration_receipts enable row level security;
revoke all on public.portfolio_migration_receipts from public,anon,authenticated;
drop policy if exists "organization admins can add non-owner members" on public.organization_memberships;
revoke insert on public.organization_memberships from authenticated;

create or replace function public.commit_portfolio_transaction_import(p_portfolio_id uuid,p_import_key uuid,p_filename text,p_rows jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare
 u uuid := (select auth.uid()); existing public.portfolio_import_jobs%rowtype;
 job uuid; r jsonb; idx integer:=0; q numeric; price numeric; cash numeric; fee numeric; fx numeric;
 typ text; cur text; dt date; inst uuid; ext text;
begin
 if u is null or not private.can_access_portfolio(p_portfolio_id,'analyst') then raise exception using errcode='42501',message='Portfolio access denied'; end if;
 if p_import_key is null or length(btrim(coalesce(p_filename,''))) not between 1 and 255 or jsonb_typeof(p_rows)<>'array' or jsonb_array_length(p_rows) not between 1 and 5000 then raise exception using errcode='22023',message='Invalid import payload'; end if;
 select * into existing from public.portfolio_import_jobs where portfolio_id=p_portfolio_id and idempotency_key=p_import_key;
 if found then
  if existing.status<>'completed' then raise exception using errcode='55000',message='Import is already in progress'; end if;
  return jsonb_build_object('import_id',existing.id,'total_rows',existing.total_rows,'accepted_rows',existing.accepted_rows,'rejected_rows',existing.rejected_rows,'replayed',true);
 end if;
 for r in select value from jsonb_array_elements(p_rows) loop
  idx:=idx+1;
  if jsonb_typeof(r)<>'object' then raise exception using errcode='22023',message=format('Row %s must be an object',idx); end if;
  typ:=upper(coalesce(r->>'transaction_type','')); cur:=coalesce(r->>'currency','');
  if typ not in ('BUY','SELL','DIVIDEND','DEPOSIT','WITHDRAWAL','FEE','SPLIT','TRANSFER_IN','TRANSFER_OUT','ADJUSTMENT') or cur !~ '^[A-Z]{3}$' or coalesce(r->>'transaction_date','') !~ '^\d{4}-\d{2}-\d{2}$' then raise exception using errcode='22023',message=format('Row %s has invalid type, currency or date',idx); end if;
  dt:=(r->>'transaction_date')::date; if dt>current_date then raise exception using errcode='22023',message=format('Row %s has a future date',idx); end if;
  q:=coalesce(nullif(r->>'quantity','')::numeric,0); price:=coalesce(nullif(r->>'unit_price','')::numeric,0); cash:=coalesce(nullif(r->>'cash_amount','')::numeric,0); fee:=coalesce(nullif(r->>'fees','')::numeric,0); fx:=nullif(r->>'fx_to_base','')::numeric;
  if q<0 or price<0 or fee<0 or abs(cash)>9999999999999999 or q>9999999999999999 or price>9999999999999999 or fee>9999999999999999 or (fx is not null and (fx<=0 or fx>999999999999)) then raise exception using errcode='22023',message=format('Row %s has invalid numeric values',idx); end if;
  if typ in ('BUY','SELL','SPLIT','TRANSFER_IN','TRANSFER_OUT','ADJUSTMENT') then
   if coalesce(r->>'instrument_id','') !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' or q<=0 then raise exception using errcode='22023',message=format('Row %s requires instrument and positive quantity',idx); end if;
   inst:=(r->>'instrument_id')::uuid;
   if not exists(select 1 from public.portfolio_instruments i where i.id=inst and i.portfolio_id=p_portfolio_id and i.currency=cur) then raise exception using errcode='22023',message=format('Row %s instrument/currency mismatch',idx); end if;
  end if;
  ext:=nullif(btrim(r->>'external_id'),'');
  if ext is not null and exists(select 1 from public.portfolio_transactions t where t.portfolio_id=p_portfolio_id and t.external_id=ext) then raise exception using errcode='23505',message=format('Row %s external_id already exists',idx); end if;
 end loop;
 insert into public.portfolio_import_jobs(portfolio_id,source_format,status,original_filename,total_rows,accepted_rows,rejected_rows,duplicate_rows,created_by,idempotency_key)
 values(p_portfolio_id,case when lower(p_filename) like '%.xlsx' then 'xlsx' else 'csv' end,'committing',btrim(p_filename),jsonb_array_length(p_rows),0,0,0,u,p_import_key) returning id into job;
 idx:=0;
 for r in select value from jsonb_array_elements(p_rows) loop
  idx:=idx+1; typ:=upper(r->>'transaction_type'); dt:=(r->>'transaction_date')::date;
  inst:=nullif(r->>'instrument_id','')::uuid; q:=coalesce(nullif(r->>'quantity','')::numeric,0); price:=coalesce(nullif(r->>'unit_price','')::numeric,0); cash:=coalesce(nullif(r->>'cash_amount','')::numeric,0); fee:=coalesce(nullif(r->>'fees','')::numeric,0); cur:=r->>'currency'; fx:=nullif(r->>'fx_to_base','')::numeric;
  ext:=coalesce(nullif(btrim(r->>'external_id'),''),p_import_key::text||':'||idx::text);
  insert into public.portfolio_transactions(portfolio_id,instrument_id,transaction_date,transaction_type,quantity,unit_price,cash_amount,fees,currency,fx_to_base,external_id,notes,source_import_id,created_by)
  values(p_portfolio_id,case when typ in ('BUY','SELL','SPLIT','TRANSFER_IN','TRANSFER_OUT','ADJUSTMENT') then inst else null end,dt,typ,q,price,cash,fee,cur,fx,ext,left(nullif(btrim(r->>'notes'),''),500),job,u);
 end loop;
 update public.portfolio_import_jobs set status='completed',accepted_rows=idx,updated_at=now() where id=job;
 return jsonb_build_object('import_id',job,'total_rows',idx,'accepted_rows',idx,'rejected_rows',0,'replayed',false);
end $$;
revoke all on function public.commit_portfolio_transaction_import(uuid,uuid,text,jsonb) from public,anon;
grant execute on function public.commit_portfolio_transaction_import(uuid,uuid,text,jsonb) to authenticated;

create or replace function public.migrate_local_portfolio(p_portfolio_id uuid,p_migration_key uuid,p_base_currency text,p_holdings jsonb,p_valuations jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare
 u uuid:=(select auth.uid()); prior public.portfolio_migration_receipts%rowtype; h jsonb; v jsonb; inst uuid; n integer:=0; vn integer:=0; nm text; cur text; qty numeric; cost numeric; px numeric; fx numeric;
begin
 if u is null or not private.can_access_portfolio(p_portfolio_id,'analyst') then raise exception using errcode='42501',message='Portfolio access denied'; end if;
 if p_migration_key is null or p_base_currency !~ '^[A-Z]{3}$' or jsonb_typeof(p_holdings)<>'array' or jsonb_array_length(p_holdings)>5000 or jsonb_typeof(p_valuations)<>'array' or jsonb_array_length(p_valuations)>1000 then raise exception using errcode='22023',message='Invalid local portfolio migration payload'; end if;
 select * into prior from public.portfolio_migration_receipts where portfolio_id=p_portfolio_id and migration_key=p_migration_key;
 if found then if prior.user_id<>u then raise exception using errcode='42501',message='Migration receipt access denied'; end if; return jsonb_build_object('holdings_count',prior.holdings_count,'valuations_count',prior.valuations_count,'replayed',true); end if;
 for h in select value from jsonb_array_elements(p_holdings) loop
  nm:=btrim(coalesce(h->>'name','')); cur:=upper(coalesce(h->>'currency','')); qty:=nullif(h->>'quantity','')::numeric; cost:=nullif(h->>'costPerUnit','')::numeric; px:=nullif(h->>'currentPrice','')::numeric; fx:=nullif(h->>'fxToBase','')::numeric;
  if length(nm) not between 1 and 200 or cur !~ '^[A-Z]{3}$' or qty is null or qty<=0 or qty>9999999999999999 or cost is null or cost<0 or cost>9999999999999999 or (px is not null and (px<=0 or px>9999999999999999)) or (fx is not null and (fx<=0 or fx>999999999999)) or coalesce(h->>'assetType','Other') not in ('Stock','ETF','Bond','Treasury bill','Money-market fund','Mutual fund','REIT','Fixed deposit','Other') then raise exception using errcode='22023',message='A local holding has invalid values'; end if;
 end loop;
 for v in select value from jsonb_array_elements(p_valuations) loop
  if jsonb_typeof(v)<>'object' or coalesce(v->>'company','')='' or coalesce(v->>'method','') not in ('dcf','ddm') or coalesce(v->>'currency','') !~ '^[A-Z]{3}$' or coalesce(v->>'calculatedAt','') !~ '^\d{4}-\d{2}-\d{2}' then raise exception using errcode='22023',message='A local valuation has invalid values'; end if;
 end loop;
 for h in select value from jsonb_array_elements(p_holdings) loop
  nm:=btrim(h->>'name'); cur:=upper(h->>'currency'); qty:=(h->>'quantity')::numeric; cost:=(h->>'costPerUnit')::numeric; px:=nullif(h->>'currentPrice','')::numeric; fx:=nullif(h->>'fxToBase','')::numeric;
  insert into public.portfolio_instruments(portfolio_id,name,ticker,country,sector,asset_type,currency,current_price,price_as_of,fx_to_base,fx_as_of,created_by)
  values(p_portfolio_id,nm,nullif(upper(btrim(coalesce(h->>'ticker',''))),''),nullif(btrim(coalesce(h->>'country','')),''),nullif(btrim(coalesce(h->>'sector','')),''),coalesce(h->>'assetType','Other'),cur,px,nullif(h->>'priceAsOf','')::date,fx,nullif(h->>'fxAsOf','')::date,u) returning id into inst;
  insert into public.portfolio_transactions(portfolio_id,instrument_id,transaction_date,transaction_type,quantity,unit_price,currency,created_by,notes)
  values(p_portfolio_id,inst,current_date,'ADJUSTMENT',qty,cost,cur,u,'Migrated from browser-local portfolio');
  n:=n+1;
 end loop;
 for v in select value from jsonb_array_elements(p_valuations) loop
  insert into public.portfolio_valuations(portfolio_id,valuation_date,base_currency,model,snapshot,created_by)
  values(p_portfolio_id,(v->>'calculatedAt')::date,upper(v->>'currency'),v->>'method',v,u); vn:=vn+1;
 end loop;
 insert into public.portfolio_migration_receipts(portfolio_id,migration_key,user_id,holdings_count,valuations_count) values(p_portfolio_id,p_migration_key,u,n,vn);
 return jsonb_build_object('holdings_count',n,'valuations_count',vn,'replayed',false);
end $$;
revoke all on function public.migrate_local_portfolio(uuid,uuid,text,jsonb,jsonb) from public,anon;
grant execute on function public.migrate_local_portfolio(uuid,uuid,text,jsonb,jsonb) to authenticated;
commit;
