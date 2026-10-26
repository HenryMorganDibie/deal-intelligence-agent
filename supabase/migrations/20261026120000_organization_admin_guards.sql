-- Organisation administration guards (markets audit, 26 October 2026).
-- 1. Only the owner may archive or restore an organisation, and nobody may change who created it. Admins could
--    previously set archived_at directly, which locks every member out, the owner included, with no way back.
-- 2. Removing a member revokes the invites they created, and an invite is honoured only while its creator is
--    still an administrator (an owner, for admin invites). A removed admin could otherwise rejoin with a code
--    they kept.
-- 3. Only the owner may remove an admin or change an admin's role, and nothing changes in an archived
--    organisation (these functions read the caller's role directly, so they did not see archiving).

create or replace function private.guard_organization_update()
returns trigger language plpgsql security definer set search_path = '' as $$
declare actor uuid := (select auth.uid());
begin
  if actor is null then return new; end if;                 -- service role and maintenance
  if new.created_by is distinct from old.created_by then
    raise exception using errcode = '42501', message = 'The organization creator cannot be changed';
  end if;
  if new.archived_at is distinct from old.archived_at and not exists (
      select 1 from public.organization_memberships m
      where m.organization_id = old.id and m.user_id = actor and m.role = 'owner') then
    raise exception using errcode = '42501', message = 'Only the owner can archive or restore the organization';
  end if;
  return new;
end $$;

drop trigger if exists organizations_guard_update on public.organizations;
create trigger organizations_guard_update before update on public.organizations
  for each row execute function private.guard_organization_update();

create or replace function public.remove_organization_member(p_organization_id uuid, p_user_id uuid)
returns boolean language plpgsql security definer set search_path = '' as $function$
declare actor uuid := (select auth.uid()); actor_role text; target_role text;
begin
  if actor is null then raise exception using errcode = '42501', message = 'Authentication required'; end if;
  if not private.has_org_role(p_organization_id, 'admin') then
    raise exception using errcode = '42501', message = 'Organization administration permission required';
  end if;
  select m.role into actor_role from public.organization_memberships m
   where m.organization_id = p_organization_id and m.user_id = actor;
  select m.role into target_role from public.organization_memberships m
   where m.organization_id = p_organization_id and m.user_id = p_user_id;
  if target_role is null or target_role = 'owner' then
    raise exception using errcode = '22023', message = 'Member not found or is the organization owner';
  end if;
  if target_role = 'admin' and actor_role <> 'owner' then
    raise exception using errcode = '42501', message = 'Only the owner can remove an admin';
  end if;
  update public.organization_invites set revoked_at = now()
   where organization_id = p_organization_id and created_by = p_user_id and revoked_at is null;
  delete from public.organization_memberships where organization_id = p_organization_id and user_id = p_user_id;
  return found;
end $function$;

create or replace function public.update_organization_member_role(p_organization_id uuid, p_user_id uuid, p_role text)
returns boolean language plpgsql security definer set search_path = '' as $function$
declare actor uuid := (select auth.uid()); actor_role text; target_role text;
begin
  if actor is null then raise exception using errcode = '42501', message = 'Authentication required'; end if;
  if not private.has_org_role(p_organization_id, 'admin') then
    raise exception using errcode = '42501', message = 'Organization administration permission required';
  end if;
  select m.role into actor_role from public.organization_memberships m
   where m.organization_id = p_organization_id and m.user_id = actor;
  if p_role not in ('admin', 'manager', 'analyst', 'viewer') then
    raise exception using errcode = '22023', message = 'Invalid member role';
  end if;
  select m.role into target_role from public.organization_memberships m
   where m.organization_id = p_organization_id and m.user_id = p_user_id;
  if target_role is null or target_role = 'owner' then
    raise exception using errcode = '22023', message = 'Member not found or is the organization owner';
  end if;
  if (p_role = 'admin' or target_role = 'admin') and actor_role <> 'owner' then
    raise exception using errcode = '42501', message = 'Only the owner can assign or change the admin role';
  end if;
  if target_role = 'admin' and p_role <> 'admin' then              -- a demoted admin's invites lapse
    update public.organization_invites set revoked_at = now()
     where organization_id = p_organization_id and created_by = p_user_id and revoked_at is null;
  end if;
  update public.organization_memberships set role = p_role
   where organization_id = p_organization_id and user_id = p_user_id;
  return found;
end $function$;

create or replace function public.accept_organization_invite(p_token_hash text)
returns jsonb language plpgsql security definer set search_path = '' as $function$
declare
  v_invite public.organization_invites%rowtype;
  v_already_member boolean;
begin
  if (select auth.uid()) is null then
    raise exception using errcode = '42501', message = 'Authentication required';
  end if;
  if p_token_hash !~ '^[a-f0-9]{64}$' then
    raise exception using errcode = '22023', message = 'Invalid or expired invitation';
  end if;
  select * into v_invite from public.organization_invites
   where token_hash = p_token_hash and revoked_at is null and expires_at > now() and use_count < max_uses
   for update;
  if not found then
    raise exception using errcode = '22023', message = 'Invalid or expired invitation';
  end if;
  if exists (select 1 from public.organizations where id = v_invite.organization_id and archived_at is not null) then
    raise exception using errcode = '22023', message = 'Invitation is no longer valid';
  end if;
  -- The creator must still hold the rights the invite needed when it was made.
  if not exists (
      select 1 from public.organization_memberships m
       where m.organization_id = v_invite.organization_id and m.user_id = v_invite.created_by
         and (m.role = 'owner' or (m.role = 'admin' and v_invite.role <> 'admin'))) then
    raise exception using errcode = '22023', message = 'Invitation is no longer valid';
  end if;
  select exists (select 1 from public.organization_memberships
                  where organization_id = v_invite.organization_id and user_id = (select auth.uid()))
    into v_already_member;
  if v_already_member then
    return jsonb_build_object(
      'organization_id', v_invite.organization_id,
      'role', (select m.role from public.organization_memberships as m
                where m.organization_id = v_invite.organization_id and m.user_id = (select auth.uid())),
      'already_member', true);
  end if;
  insert into public.organization_memberships (organization_id, user_id, role, invited_by)
  values (v_invite.organization_id, (select auth.uid()), v_invite.role, v_invite.created_by);
  update public.organization_invites set use_count = use_count + 1 where id = v_invite.id;
  return jsonb_build_object('organization_id', v_invite.organization_id, 'role', v_invite.role, 'already_member', false);
end $function$;
