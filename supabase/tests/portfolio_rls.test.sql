begin;
create extension if not exists pgtap with schema extensions;
select plan(30);
insert into auth.users(id,aud,role,email,encrypted_password,email_confirmed_at,created_at,updated_at) values
('10000000-0000-4000-8000-000000000001','authenticated','authenticated','portfolio-a@test.invalid','',now(),now(),now()),
('10000000-0000-4000-8000-000000000002','authenticated','authenticated','portfolio-b@test.invalid','',now(),now(),now()),
('10000000-0000-4000-8000-000000000003','authenticated','authenticated','portfolio-viewer@test.invalid','',now(),now(),now()) on conflict(id) do nothing;
set local role authenticated;
set local request.jwt.claim.sub='10000000-0000-4000-8000-000000000001';
insert into public.organizations(id,name,slug,created_by) values('20000000-0000-4000-8000-000000000001','Portfolio A Org','portfolio-a-org','10000000-0000-4000-8000-000000000001');
insert into public.portfolios(id,organization_id,name,base_currency,created_by) values('30000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000001','Shared A','USD','10000000-0000-4000-8000-000000000001');
insert into public.portfolios(id,owner_user_id,name,base_currency,created_by) values('30000000-0000-4000-8000-000000000002','10000000-0000-4000-8000-000000000001','Personal A','USD','10000000-0000-4000-8000-000000000001');
insert into public.portfolio_instruments(id,portfolio_id,name,currency,created_by)
values('40000000-0000-4000-8000-000000000001','30000000-0000-4000-8000-000000000001','Test Equity','USD','10000000-0000-4000-8000-000000000001');
insert into public.portfolio_transactions(id,portfolio_id,instrument_id,transaction_date,transaction_type,quantity,unit_price,cash_amount,fees,currency,created_by)
values('45000000-0000-4000-8000-000000000001','30000000-0000-4000-8000-000000000001','40000000-0000-4000-8000-000000000001',current_date,'BUY',2,10,-20,0,'USD','10000000-0000-4000-8000-000000000001');
insert into public.portfolio_valuations(id,portfolio_id,valuation_date,base_currency,model,snapshot,created_by)
values('46000000-0000-4000-8000-000000000001','30000000-0000-4000-8000-000000000001',current_date,'USD','test',jsonb_build_object('equity',20),'10000000-0000-4000-8000-000000000001');
insert into public.organization_invites(id,organization_id,token_hash,role,expires_at,created_by)
values('50000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000001',repeat('a',64),'viewer',now()+interval '1 day','10000000-0000-4000-8000-000000000001');
set local request.jwt.claim.sub='10000000-0000-4000-8000-000000000002';
insert into public.organizations(id,name,slug,created_by) values('20000000-0000-4000-8000-000000000002','Portfolio B Org','portfolio-b-org','10000000-0000-4000-8000-000000000002');
insert into public.portfolios(id,organization_id,name,base_currency,created_by) values('30000000-0000-4000-8000-000000000003','20000000-0000-4000-8000-000000000002','Shared B','USD','10000000-0000-4000-8000-000000000002');
select is((select count(*)::int from public.organizations),1,'User B sees only their organization');
select is((select count(*)::int from public.portfolios),1,'User B sees only their shared portfolio');
select is((select count(*)::int from public.portfolios where id='30000000-0000-4000-8000-000000000001'),0,'User B cannot see Organization A portfolio');
select is((select count(*)::int from public.portfolios where id='30000000-0000-4000-8000-000000000002'),0,'User B cannot see User A personal portfolio');
select is((select count(*)::int from public.portfolio_instruments where portfolio_id='30000000-0000-4000-8000-000000000001'),0,'User B cannot read User A instruments');
select is((select count(*)::int from public.portfolio_transactions where portfolio_id='30000000-0000-4000-8000-000000000001'),0,'User B cannot read User A transactions');
select is((select count(*)::int from public.portfolio_valuations where portfolio_id='30000000-0000-4000-8000-000000000001'),0,'User B cannot read User A valuation snapshots');
set local request.jwt.claim.sub='10000000-0000-4000-8000-000000000001';
select is((select count(*)::int from public.organization_memberships where organization_id='20000000-0000-4000-8000-000000000001'),1,'Organization creator becomes owner');
select is((select count(*)::int from public.portfolios),2,'User A sees personal and shared portfolios');
select throws_ok($$insert into public.portfolios(id,owner_user_id,name,base_currency,created_by) values('30000000-0000-4000-8000-000000000004','10000000-0000-4000-8000-000000000002','Impersonated','USD','10000000-0000-4000-8000-000000000001')$$,'42501',null,'Cannot create portfolio owned by another user');
select throws_ok($$insert into public.organization_memberships(organization_id,user_id,role,invited_by) values('20000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000003','analyst','10000000-0000-4000-8000-000000000001')$$,'42501',null,'Membership cannot bypass invite acceptance');
select is((public.commit_portfolio_transaction_import(
 '30000000-0000-4000-8000-000000000001',
 '60000000-0000-4000-8000-000000000001',
 'sample.csv',
 jsonb_build_array(jsonb_build_object(
  'transaction_date',to_char(current_date,'YYYY-MM-DD'),
  'transaction_type','BUY',
  'instrument_id','40000000-0000-4000-8000-000000000001',
  'quantity',2,'unit_price',10,'cash_amount',-20,'fees',0,'currency','USD','external_id','TEST-IMPORT-1'
 ))
)->>'accepted_rows')::int,1,'Analyst can atomically import a valid transaction');
select is((public.commit_portfolio_transaction_import(
 '30000000-0000-4000-8000-000000000001',
 '60000000-0000-4000-8000-000000000001',
 'sample.csv',
 jsonb_build_array(jsonb_build_object(
  'transaction_date',to_char(current_date,'YYYY-MM-DD'),
  'transaction_type','BUY',
  'instrument_id','40000000-0000-4000-8000-000000000001',
  'quantity',2,'unit_price',10,'cash_amount',-20,'fees',0,'currency','USD','external_id','TEST-IMPORT-1'
 ))
)->>'replayed')::boolean,true,'Retrying the same import key is idempotent');
select is((select count(*)::int from public.portfolio_transactions where portfolio_id='30000000-0000-4000-8000-000000000001' and external_id='TEST-IMPORT-1'),1,'Idempotent retry does not duplicate transactions');
set local request.jwt.claim.sub='10000000-0000-4000-8000-000000000003';
select is((select count(*)::int from public.portfolios),0,'Uninvited user sees no portfolios');
select ok(not has_function_privilege('anon','public.migrate_local_portfolio(uuid,uuid,text,jsonb,jsonb)','execute'),'Anonymous users cannot execute local migration RPC');
set local request.jwt.claim.sub='10000000-0000-4000-8000-000000000003';
select public.accept_organization_invite(repeat('a',64));
select is((select count(*)::int from public.portfolios),1,'Invited viewer can see only the organization portfolio they joined');
select is((select count(*)::int from public.portfolio_instruments where id='40000000-0000-4000-8000-000000000001'),1,'Invited viewer can read shared instruments');
select throws_ok($$insert into public.portfolio_instruments(portfolio_id,name,currency,created_by) values('30000000-0000-4000-8000-000000000001','Forbidden','USD','10000000-0000-4000-8000-000000000003')$$,'42501',null,'Viewer cannot create instruments');
select throws_ok($$select public.remove_organization_member('20000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000002')$$,'42501',null,'Viewer cannot administer organization membership');
set local request.jwt.claim.sub='10000000-0000-4000-8000-000000000001';
select is((public.migrate_local_portfolio(
 '30000000-0000-4000-8000-000000000002',
 '70000000-0000-4000-8000-000000000001',
 'USD',
 jsonb_build_array(jsonb_build_object('name','Migrated Equity','ticker','MIG','country','US','sector','Technology','assetType','Stock','currency','USD','quantity',3,'costPerUnit',12,'currentPrice',14,'fxToBase',1,'priceAsOf',to_char(current_date,'YYYY-MM-DD'),'fxAsOf',to_char(current_date,'YYYY-MM-DD'))),
 jsonb_build_array(jsonb_build_object('company','Test Corp','method','dcf','currency','USD','calculatedAt',to_char(current_date,'YYYY-MM-DD'),'perShareValue',15))
)->>'holdings_count')::int,1,'Local migration imports a valid holding');
select is((public.migrate_local_portfolio(
 '30000000-0000-4000-8000-000000000002',
 '70000000-0000-4000-8000-000000000001',
 'USD',
 jsonb_build_array(jsonb_build_object('name','Migrated Equity','ticker','MIG','country','US','sector','Technology','assetType','Stock','currency','USD','quantity',3,'costPerUnit',12,'currentPrice',14,'fxToBase',1,'priceAsOf',to_char(current_date,'YYYY-MM-DD'),'fxAsOf',to_char(current_date,'YYYY-MM-DD'))),
 jsonb_build_array(jsonb_build_object('company','Test Corp','method','dcf','currency','USD','calculatedAt',to_char(current_date,'YYYY-MM-DD'),'perShareValue',15))
)->>'valuations_count')::int,1,'Local migration imports a saved valuation review');
select is((public.migrate_local_portfolio(
 '30000000-0000-4000-8000-000000000002',
 '70000000-0000-4000-8000-000000000001',
 'USD',
 jsonb_build_array(jsonb_build_object('name','Migrated Equity','ticker','MIG','country','US','sector','Technology','assetType','Stock','currency','USD','quantity',3,'costPerUnit',12,'currentPrice',14,'fxToBase',1,'priceAsOf',to_char(current_date,'YYYY-MM-DD'),'fxAsOf',to_char(current_date,'YYYY-MM-DD'))),
 jsonb_build_array(jsonb_build_object('company','Test Corp','method','dcf','currency','USD','calculatedAt',to_char(current_date,'YYYY-MM-DD'),'perShareValue',15))
)->>'replayed')::boolean,true,'Retrying the same local migration is idempotent');
select is((select count(*)::int from public.portfolio_instruments where portfolio_id='30000000-0000-4000-8000-000000000002'),1,'Local migration retry does not duplicate holdings');
select throws_ok($$select public.migrate_local_portfolio('30000000-0000-4000-8000-000000000002',gen_random_uuid(),'NGN','[]'::jsonb,'[]'::jsonb)$$,'22023',null,'Local migration rejects a reporting currency that differs from the destination portfolio');
set local request.jwt.claim.sub='10000000-0000-4000-8000-000000000003';
select throws_ok($$select public.commit_portfolio_transaction_import('30000000-0000-4000-8000-000000000001',gen_random_uuid(),'viewer.csv','[]'::jsonb)$$,'42501',null,'Viewer cannot import transactions');
select ok(not has_table_privilege('authenticated','public.portfolio_transactions','update'),'Authenticated clients cannot rewrite ledger transactions');
select ok(not has_table_privilege('authenticated','public.portfolio_valuations','update'),'Authenticated clients cannot rewrite valuation snapshots');
select ok(not has_table_privilege('authenticated','public.portfolio_import_jobs','insert'),'Import jobs can only be created by the atomic import RPC');
select ok(not has_table_privilege('authenticated','public.portfolio_audit_events','insert'),'Clients cannot forge audit events');
select * from finish();
rollback;
