-- Create the Custom Access Token Hook function
create or replace function public.custom_access_token_hook(event jsonb)
returns jsonb
language plpgsql
stable
as $$
declare
  claims jsonb;
  v_org_id text;
  v_role_id text;
  v_permissions jsonb;
begin
  select u."orgId", u."roleId"
    into v_org_id, v_role_id
    from public.users u
    where u.id = (event->>'user_id')::uuid;

  claims := event->'claims';

  if v_org_id is not null then
    select coalesce(jsonb_agg(rp."permissionKey"), '[]'::jsonb)
      into v_permissions
      from public.role_permissions rp
      where rp."roleId" = v_role_id;

    claims := jsonb_set(claims, '{app_org_id}', to_jsonb(v_org_id));
    claims := jsonb_set(claims, '{app_role_id}', to_jsonb(v_role_id));
    claims := jsonb_set(claims, '{app_permissions}', v_permissions);
  end if;

  event := jsonb_set(event, '{claims}', claims);
  return event;
end;
$$;
do $$ begin
  if not exists (select from pg_catalog.pg_roles where rolname = 'supabase_auth_admin') then
    create role supabase_auth_admin;
  end if;
  if not exists (select from pg_catalog.pg_roles where rolname = 'authenticated') then
    create role authenticated;
  end if;
  if not exists (select from pg_catalog.pg_roles where rolname = 'anon') then
    create role anon;
  end if;
end $$;

grant usage on schema public to supabase_auth_admin;
grant execute on function public.custom_access_token_hook to supabase_auth_admin;
revoke execute on function public.custom_access_token_hook from authenticated, anon, public;

grant select ("id", "orgId", "roleId") on public.users to supabase_auth_admin;
grant select ("roleId", "permissionKey") on public.role_permissions to supabase_auth_admin;

-- RLS bypass for supabase_auth_admin via policies
create policy "Allow auth admin to read users for token claims" on public.users
  as permissive for select
  to supabase_auth_admin
  using (true);

create policy "Allow auth admin to read role_permissions for token claims" on public.role_permissions
  as permissive for select
  to supabase_auth_admin
  using (true);
