-- Harden archived-tenant access and expose safe workspace administration RPCs.
begin;
create or replace function private.has_org_role(p_organization_id uuid,p_minimum_role text default 'viewer')
returns boolean language sql stable security definer set search_path='' as $
 select exists(
  select 1 from public.organization_memberships m
  join public.organizations o on o.id=m.organization_id
  where o.archived_at is null
   and m.organization_id=p_organization_id and m.user_id=(select auth.uid())
   and case m.role when 'owner' then 5 when 'admin' then 4 when 'manager' then 3 when 'analyst' then 2 when 'viewer' then 1 else 0 end
     >= case p_minimum_role when 'owner' then 5 when 'admin' then 4 when 'manager' then 3 when 'analyst' then 2 when 'viewer' then 1 else 99 end
 );
$;
revoke all on function private.has_org_role(uuid,text) from public,anon;
grant execute on function private.has_org_role(uuid,text) to authenticated;

create or replace function private.can_access_portfolio(p_portfolio_id uuid,p_minimum_role text default 'viewer')
returns boolean language sql stable security definer set search_path='' as $$
 select exists(
  select 1 from public.portfolios p
  where p.id=p_portfolio_id and p.archived_at is null
   and (p.organization_id is null or exists(select 1 from public.organizations o where o.id=p.organization_id and o.archived_at is null))
   and (p.owner_user_id=(select auth.uid()) or (p.organization_id is not null and private.has_org_role(p.organization_id,p_minimum_role)))
 );
$$;
revoke all on function private.can_access_portfolio(uuid,text) from public,anon;
grant execute on function private.can_access_portfolio(uuid,text) to authenticated;

drop policy if exists "organization members can read their organization" on public.organizations;
create policy "active organization members can read their organization"
on public.organizations for select to authenticated
using (archived_at is null and private.has_org_role(id,'viewer'));

drop policy if exists "organization admins can update non-owner memberships" on public.organization_memberships;
drop policy if exists "organization admins can remove non-owner members" on public.organization_memberships;
revoke update, delete on public.organization_memberships from authenticated;

create or replace function public.list_organization_members(p_organization_id uuid)
returns table(user_id uuid,email text,role text,joined_at timestamptz)
language plpgsql security definer set search_path='' as $$
begin
 if (select auth.uid()) is null or not private.has_org_role(p_organization_id,'admin') then
  raise exception using errcode='42501',message='Organization administration permission required';
 end if;
 return query select m.user_id,u.email::text,m.role,m.joined_at
 from public.organization_memberships m join auth.users u on u.id=m.user_id
 where m.organization_id=p_organization_id order by case m.role when 'owner' then 1 when 'admin' then 2 when 'manager' then 3 when 'analyst' then 4 else 5 end,m.joined_at;
end $$;

create or replace function public.list_organization_invites(p_organization_id uuid)
returns table(id uuid,role text,expires_at timestamptz,use_count integer,max_uses integer,revoked_at timestamptz,created_at timestamptz)
language plpgsql security definer set search_path='' as $$
begin
 if (select auth.uid()) is null or not private.has_org_role(p_organization_id,'admin') then
  raise exception using errcode='42501',message='Organization administration permission required';
 end if;
 return query select i.id,i.role,i.expires_at,i.use_count,i.max_uses,i.revoked_at,i.created_at
 from public.organization_invites i where i.organization_id=p_organization_id order by i.created_at desc limit 100;
end $$;

create or replace function public.update_organization_member_role(p_organization_id uuid,p_user_id uuid,p_role text)
returns boolean language plpgsql security definer set search_path='' as $$
declare actor uuid:=(select auth.uid()); actor_role text;
begin
 if actor is null then raise exception using errcode='42501',message='Authentication required'; end if;
 select m.role into actor_role from public.organization_memberships m where m.organization_id=p_organization_id and m.user_id=actor;
 if actor_role is null or actor_role not in ('owner','admin') then raise exception using errcode='42501',message='Organization administration permission required'; end if;
 if p_role not in ('admin','manager','analyst','viewer') then raise exception using errcode='22023',message='Invalid member role'; end if;
 if p_role='admin' and actor_role<>'owner' then raise exception using errcode='42501',message='Only the owner can assign admin role'; end if;
 if not exists(select 1 from public.organization_memberships m where m.organization_id=p_organization_id and m.user_id=p_user_id and m.role<>'owner') then
  raise exception using errcode='22023',message='Member not found or is the organization owner';
 end if;
 update public.organization_memberships set role=p_role where organization_id=p_organization_id and user_id=p_user_id;
 return found;
end $$;

create or replace function public.remove_organization_member(p_organization_id uuid,p_user_id uuid)
returns boolean language plpgsql security definer set search_path='' as $$
declare actor uuid:=(select auth.uid()); actor_role text; target_role text;
begin
 if actor is null then raise exception using errcode='42501',message='Authentication required'; end if;
 select m.role into actor_role from public.organization_memberships m where m.organization_id=p_organization_id and m.user_id=actor;
 if actor_role not in ('owner','admin') then raise exception using errcode='42501',message='Organization administration permission required'; end if;
 select m.role into target_role from public.organization_memberships m where m.organization_id=p_organization_id and m.user_id=p_user_id;
 if target_role is null or target_role='owner' then raise exception using errcode='22023',message='Member not found or is the organization owner'; end if;
 delete from public.organization_memberships where organization_id=p_organization_id and user_id=p_user_id;
 return found;
end $$;

create or replace function public.revoke_organization_invite(p_invite_id uuid)
returns boolean language plpgsql security definer set search_path='' as $$
declare org uuid;
begin
 if (select auth.uid()) is null then raise exception using errcode='42501',message='Authentication required'; end if;
 select i.organization_id into org from public.organization_invites i where i.id=p_invite_id;
 if org is null or not private.has_org_role(org,'admin') then raise exception using errcode='42501',message='Organization administration permission required'; end if;
 update public.organization_invites set revoked_at=now() where id=p_invite_id and revoked_at is null and expires_at>now() and use_count<max_uses;
 return found;
end $$;

revoke all on function public.list_organization_members(uuid) from public,anon;
revoke all on function public.list_organization_invites(uuid) from public,anon;
revoke all on function public.update_organization_member_role(uuid,uuid,text) from public,anon;
revoke all on function public.remove_organization_member(uuid,uuid) from public,anon;
revoke all on function public.revoke_organization_invite(uuid) from public,anon;
grant execute on function public.list_organization_members(uuid) to authenticated;
grant execute on function public.list_organization_invites(uuid) to authenticated;
grant execute on function public.update_organization_member_role(uuid,uuid,text) to authenticated;
grant execute on function public.remove_organization_member(uuid,uuid) to authenticated;
grant execute on function public.revoke_organization_invite(uuid) to authenticated;
commit;
