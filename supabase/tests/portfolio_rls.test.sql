begin;
create extension if not exists pgtap with schema extensions;
select plan(10);
insert into auth.users(id,aud,role,email,encrypted_password,email_confirmed_at,created_at,updated_at) values
('10000000-0000-4000-8000-000000000001','authenticated','authenticated','portfolio-a@test.invalid','',now(),now(),now()),
('10000000-0000-4000-8000-000000000002','authenticated','authenticated','portfolio-b@test.invalid','',now(),now(),now()),
('10000000-0000-4000-8000-000000000003','authenticated','authenticated','portfolio-viewer@test.invalid','',now(),now(),now()) on conflict(id) do nothing;
set local role authenticated;
set local request.jwt.claim.sub='10000000-0000-4000-8000-000000000001';
insert into public.organizations(id,name,slug,created_by) values('20000000-0000-4000-8000-000000000001','Portfolio A Org','portfolio-a-org','10000000-0000-4000-8000-000000000001');
insert into public.portfolios(id,organization_id,name,base_currency,created_by) values('30000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000001','Shared A','USD','10000000-0000-4000-8000-000000000001');
insert into public.portfolios(id,owner_user_id,name,base_currency,created_by) values('30000000-0000-4000-8000-000000000002','10000000-0000-4000-8000-000000000001','Personal A','USD','10000000-0000-4000-8000-000000000001');
set local request.jwt.claim.sub='10000000-0000-4000-8000-000000000002';
insert into public.organizations(id,name,slug,created_by) values('20000000-0000-4000-8000-000000000002','Portfolio B Org','portfolio-b-org','10000000-0000-4000-8000-000000000002');
insert into public.portfolios(id,organization_id,name,base_currency,created_by) values('30000000-0000-4000-8000-000000000003','20000000-0000-4000-8000-000000000002','Shared B','USD','10000000-0000-4000-8000-000000000002');
select is((select count(*)::int from public.organizations),1,'User B sees only their organization');
select is((select count(*)::int from public.portfolios),1,'User B sees only their shared portfolio');
select is((select count(*)::int from public.portfolios where id='30000000-0000-4000-8000-000000000001'),0,'User B cannot see Organization A portfolio');
select is((select count(*)::int from public.portfolios where id='30000000-0000-4000-8000-000000000002'),0,'User B cannot see User A personal portfolio');
set local request.jwt.claim.sub='10000000-0000-4000-8000-000000000001';
select is((select count(*)::int from public.organization_memberships where organization_id='20000000-0000-4000-8000-000000000001'),1,'Organization creator becomes owner');
select is((select count(*)::int from public.portfolios),2,'User A sees personal and shared portfolios');
select throws_ok($$insert into public.portfolios(id,owner_user_id,name,base_currency,created_by) values('30000000-0000-4000-8000-000000000004','10000000-0000-4000-8000-000000000002','Impersonated','USD','10000000-0000-4000-8000-000000000001')$$,'42501',null,'Cannot create portfolio owned by another user');
select throws_ok($$insert into public.organization_memberships(organization_id,user_id,role,invited_by) values('20000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000003','analyst','10000000-0000-4000-8000-000000000001')$$,'42501',null,'Membership cannot bypass invite acceptance');
set local request.jwt.claim.sub='10000000-0000-4000-8000-000000000003';
select is((select count(*)::int from public.portfolios),0,'Uninvited user sees no portfolios');
select ok(not has_function_privilege('anon','public.migrate_local_portfolio(uuid,uuid,text,jsonb,jsonb)','execute'),'Anonymous users cannot execute local migration RPC');
select * from finish();
rollback;
