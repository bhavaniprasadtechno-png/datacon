# JWT-Embedded RBAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut `SupabaseAuthGuard`'s DB cost from ~400ms (4 sequential Prisma relation-loading round trips for RBAC + suspension) to ~100ms (1 round trip for suspension only), by moving `orgId`/`roleId`/`permissions` into the JWT via a Supabase Custom Access Token Hook.

**Architecture:** A Postgres function (`custom_access_token_hook`), enabled via Supabase Dashboard, injects `app_org_id`/`app_role_id`/`app_permissions` into the JWT at mint/refresh time. `SupabaseAuthGuard` reads RBAC from `getClaims()`'s decoded output instead of querying for it, and narrows its DB query to a single flat suspension check. No fallback for tokens missing the new claims — they're rejected, forcing re-login.

**Tech Stack:** Supabase Auth Hooks (Postgres function), `supabase-js` `auth.getClaims()`, NestJS 10, Prisma 5.22, Jest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-29-jwt-embedded-rbac-design.md` — every task implements a decision from that doc.
- Suspension enforcement must remain a live, per-request DB check with zero caching/staleness — this is the one guarantee that cannot regress (spec Decision 2).
- No fallback for missing claims (spec Decision 3) — do not add one "to be safe."
- Project: `datacon-staging-ew`, ref `yicblouwgguhmfvwqdhm`.
- Enabling the Auth Hook in Supabase Dashboard is a **user-only step** — no Supabase CLI or MCP tool covers Auth Hook *enablement* (confirmed against the same tool limitations documented in the JWT-signing-key migration plan; `apply_migration`/`execute_sql` can create the Postgres function itself, just not wire it into Auth's hook config).
- Do not commit anything unless the user explicitly asks for it in that turn (project `CLAUDE.md` rule).

---

### Task 1: Create the Custom Access Token Hook function

**Files:**
- Create: `app/packages/prisma/migrations/<timestamp>_custom_access_token_hook/migration.sql` (repo-tracked copy, matching this project's existing migration convention)

**Interfaces:**
- Produces: `public.custom_access_token_hook(event jsonb) returns jsonb` — a Postgres function Supabase Auth will call once enabled in Task 3.

This task is precondition → action → verification, not TDD — there's no application code to unit test (same shape as the JWT-signing-key migration plan's Dashboard-adjacent tasks).

- [ ] **Step 1: Confirm the exact schema this function depends on**

Already confirmed via `packages/prisma/schema.prisma`:
- `users` table: columns `id` (uuid, PK — matches `auth.users.id`), `"orgId"`, `"roleId"`.
- `role_permissions` table: columns `"roleId"`, `"permissionKey"`.

- [ ] **Step 2: Write the migration SQL**

```sql
-- app/packages/prisma/migrations/<timestamp>_custom_access_token_hook/migration.sql
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

grant usage on schema public to supabase_auth_admin;
grant execute on function public.custom_access_token_hook to supabase_auth_admin;
revoke execute on function public.custom_access_token_hook from authenticated, anon, public;

grant select ("id", "orgId", "roleId") on public.users to supabase_auth_admin;
grant select ("roleId", "permissionKey") on public.role_permissions to supabase_auth_admin;

-- Both tables already carry an `org_isolation` RLS policy (from the
-- multi-tenant-workspaces migration) keyed on `current_setting('app.current_org_id')`
-- — a session var `supabase_auth_admin` never sets. A plain GRANT is not enough;
-- without an explicit policy for this role, RLS silently filters every row and
-- the hook would see v_org_id/v_role_id as null for every user. This mirrors
-- Supabase's own documented pattern for exactly this situation.
create policy "Allow auth admin to read users for token claims" on public.users
  as permissive for select
  to supabase_auth_admin
  using (true);

create policy "Allow auth admin to read role_permissions for token claims" on public.role_permissions
  as permissive for select
  to supabase_auth_admin
  using (true);
```

Deliberately **not** revoking existing `SELECT` grants on `users`/`role_permissions` from other roles (unlike the Supabase docs' own example, which revokes because its `profiles`/`user_roles` tables were created fresh for the hook). These are existing core app tables with an existing grant/RLS structure (`app_user` role, RLS policies) this plan doesn't fully enumerate — revoking blindly risks breaking something unrelated. Only additive grants and policies here.

- [ ] **Step 3: Apply the migration to the live project**

```
mcp__supabase-2__apply_migration({
  project_id: "yicblouwgguhmfvwqdhm",
  name: "custom_access_token_hook",
  query: <the SQL above>
})
```

- [ ] **Step 4: Verify the function and policies exist**

```sql
select proname, prosecdef from pg_proc where proname = 'custom_access_token_hook';
select tablename, policyname, roles from pg_policies
  where tablename in ('users', 'role_permissions') and policyname like 'Allow auth admin%';
```
via `mcp__supabase-2__execute_sql`. Expected: one row from the first query, two rows from the second.

- [ ] **Step 5: Save the same SQL as a repo-tracked migration file**

Write the identical SQL to `app/packages/prisma/migrations/<timestamp>_custom_access_token_hook/migration.sql` (use today's date-time in the same `YYYYMMDDHHMMSS` format as sibling migration folders) so it's tracked alongside the rest of the schema history, matching this repo's existing convention. This does not re-apply anything (Step 3 already applied it live) — it's purely for repo history/reproducibility.

- [ ] **Step 6: Checkpoint**

Report the function is created and verified. The function existing does **not** yet mean it's active — Task 3 (Dashboard) is what actually wires it into token issuance. Do not expect any claims to appear in tokens yet.

---

### Task 2: Rewrite `SupabaseAuthGuard` for claims-based RBAC

**Files:**
- Modify: `app/api/src/auth/guards/supabase-auth.guard.ts`
- Modify: `app/api/src/auth/guards/supabase-auth.guard.spec.ts`

**Interfaces:**
- Consumes: `getClaims()`'s decoded output — now expected to carry `app_org_id: string`, `app_role_id: string`, `app_permissions: string[]` (once Task 1+3 are live; this task's own tests mock these directly, so it doesn't need Task 3 done first).
- Produces: same `AuthenticatedUser` shape as before (`{ id, orgId, roleId, permissions }`) — `PermissionsGuard` and everything downstream is unaffected.

This task can be fully implemented and tested before Task 3 (Dashboard) happens — it only needs mocked claims, not a real token carrying them.

- [ ] **Step 1: Write the failing tests**

Replace the two RBAC-dependent tests in `supabase-auth.guard.spec.ts` — `"throws Unauthorized when no local profile row exists for the verified user"` and `"attaches req.user with role permissions when the token and profile are valid"` — and the shared-tx test, with these (keep the SUSPENDED tests and the no-token/getClaims-error tests as-is, adjusting their mocked `getClaims` responses to include the new claims where the test expects to reach that far):

```typescript
// Replace the existing "attaches req.user..." test with:
it("attaches req.user built from the token's claims when RBAC claims and an active profile are present", async () => {
  jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
    auth: {
      getClaims: jest.fn().mockResolvedValue({
        data: {
          claims: {
            sub: "11111111-1111-1111-1111-111111111111",
            app_org_id: "acme-corp",
            app_role_id: "admin",
            app_permissions: ["manage_users"],
          },
        },
        error: null,
      }),
    },
  } as never);
  const findUnique = jest.fn().mockResolvedValue({
    status: "ACTIVE",
    org: { status: "ACTIVE" },
  });
  const prisma = { user: { findUnique } } as unknown as PrismaService;
  const guard = new SupabaseAuthGuard(prisma);
  const req: { headers: Record<string, string>; user?: unknown } = { headers: { authorization: "Bearer good" } };
  const ctx = { switchToHttp: () => ({ getRequest: () => req }) } as unknown as ExecutionContext;

  const result = await guard.canActivate(ctx);

  expect(result).toBe(true);
  expect(req.user).toEqual({
    id: "11111111-1111-1111-1111-111111111111",
    orgId: "acme-corp",
    roleId: "admin",
    permissions: ["manage_users"],
  });
  // narrowed query — no `include`, just the suspension-relevant fields
  expect(findUnique).toHaveBeenCalledWith({
    where: { id: "11111111-1111-1111-1111-111111111111" },
    select: { status: true, org: { select: { status: true } } },
  });
});

it("throws Unauthorized when the token is missing the RBAC claims (pre-hook or stale token)", async () => {
  jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
    auth: {
      getClaims: jest.fn().mockResolvedValue({
        data: { claims: { sub: "11111111-1111-1111-1111-111111111111" } }, // no app_org_id/app_role_id/app_permissions
        error: null,
      }),
    },
  } as never);
  const guard = new SupabaseAuthGuard({} as PrismaService);
  await expect(guard.canActivate(contextWith({ authorization: "Bearer stale" }))).rejects.toThrow(UnauthorizedException);
});

it("throws Unauthorized when no local profile row exists for the verified user", async () => {
  jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
    auth: {
      getClaims: jest.fn().mockResolvedValue({
        data: {
          claims: { sub: "ghost-id", app_org_id: "acme-corp", app_role_id: "admin", app_permissions: [] },
        },
        error: null,
      }),
    },
  } as never);
  const prisma = { user: { findUnique: jest.fn().mockResolvedValue(null) } } as unknown as PrismaService;
  const guard = new SupabaseAuthGuard(prisma);
  await expect(guard.canActivate(contextWith({ authorization: "Bearer good" }))).rejects.toThrow(UnauthorizedException);
});

it("looks up the suspension status on the request-scoped transaction when one is open, instead of a separate query", async () => {
  jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
    auth: {
      getClaims: jest.fn().mockResolvedValue({
        data: {
          claims: {
            sub: "11111111-1111-1111-1111-111111111111",
            app_org_id: "acme-corp",
            app_role_id: "admin",
            app_permissions: ["manage_users"],
          },
        },
        error: null,
      }),
    },
  } as never);
  const baseFindUnique = jest.fn();
  const txFindUnique = jest.fn().mockResolvedValue({ status: "ACTIVE", org: { status: "ACTIVE" } });
  const prisma = { user: { findUnique: baseFindUnique } } as unknown as PrismaService;
  const guard = new SupabaseAuthGuard(prisma);
  const req: { headers: Record<string, string>; user?: unknown } = { headers: { authorization: "Bearer good" } };
  const ctx = { switchToHttp: () => ({ getRequest: () => req }) } as unknown as ExecutionContext;

  const result = await requestTxStorage.run(
    { tx: { user: { findUnique: txFindUnique } } as never, rlsSet: false },
    () => guard.canActivate(ctx),
  );

  expect(result).toBe(true);
  expect(txFindUnique).toHaveBeenCalledTimes(1);
  expect(baseFindUnique).not.toHaveBeenCalled();
});
```

Update the two existing SUSPENDED tests' mocked `getClaims` to include `app_org_id`/`app_role_id`/`app_permissions` in the claims (they'll fail at the "missing claims" check otherwise, before ever reaching the suspension check they're meant to test), and update their mocked `user.findUnique` responses to the narrower `{ status, org: { status } }` shape (drop `orgId`/`roleId`/`role.permissions` from the mock — the guard no longer reads them from this query).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app/api && npx jest src/auth/guards/supabase-auth.guard.spec.ts`
Expected: FAIL — guard still reads RBAC from the DB query, not claims; still uses the old `include` shape.

- [ ] **Step 3: Rewrite the guard**

```typescript
// app/api/src/auth/guards/supabase-auth.guard.ts
import { CanActivate, ExecutionContext, ForbiddenException, Injectable, UnauthorizedException } from "@nestjs/common";
import { PrismaService } from "../../prisma/prisma.service";
import { requestTxStorage } from "../../prisma/request-transaction.storage";
import { getSupabaseAdminClient } from "../supabase-admin.client";
import { AuthenticatedUser } from "../token.types";

function bearerToken(req: { headers?: Record<string, unknown> }): string | undefined {
  const header = req.headers?.["authorization"];
  return typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : undefined;
}

@Injectable()
export class SupabaseAuthGuard implements CanActivate {
  constructor(private readonly prisma: PrismaService) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const req = context.switchToHttp().getRequest();
    const token = bearerToken(req);
    if (!token) throw new UnauthorizedException("Missing bearer token.");

    const { data, error } = await getSupabaseAdminClient().auth.getClaims(token);
    const claims = data?.claims;
    const userId = claims?.sub as string | undefined;
    if (error || !userId) throw new UnauthorizedException("Invalid or expired token.");

    const orgId = claims?.app_org_id as string | undefined;
    const roleId = claims?.app_role_id as string | undefined;
    const permissions = claims?.app_permissions as string[] | undefined;
    if (!orgId || !roleId || !permissions) {
      throw new UnauthorizedException("Session missing required claims — please sign in again.");
    }

    const reqTx = requestTxStorage.getStore();
    const client = (reqTx?.tx ?? this.prisma) as unknown as Pick<PrismaService, "user">;
    const status = await client.user.findUnique({
      where: { id: userId },
      select: { status: true, org: { select: { status: true } } },
    });
    if (!status) throw new UnauthorizedException("No profile for this account.");
    if (status.status === "SUSPENDED" || status.org.status === "SUSPENDED") {
      throw new ForbiddenException("This account has been suspended.");
    }

    const authedUser: AuthenticatedUser = { id: userId, orgId, roleId, permissions };
    req.user = authedUser;
    return true;
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd app/api && npx jest src/auth/guards/supabase-auth.guard.spec.ts`
Expected: PASS (all tests)

- [ ] **Step 5: Type-check and run the full suite**

Run: `cd app/api && npx tsc --noEmit -p tsconfig.json && npx jest`
Expected: no errors; all tests pass.

Do not commit — see Global Constraints.

---

### Task 3: Enable the Auth Hook (Dashboard — user only)

**Files:** none

**Interfaces:**
- Consumes: `custom_access_token_hook` function (Task 1)
- Produces: Supabase Auth now calls the hook at every token mint/refresh

- [ ] **Step 1: Navigate to Auth Hooks settings**

Dashboard → project `datacon-staging-ew` → Authentication → Hooks.

- [ ] **Step 2: Select the Custom Access Token hook**

Choose "Custom Access Token" hook type → select `public.custom_access_token_hook` from the function dropdown → Save/Enable.

- [ ] **Step 3: Checkpoint**

Confirm with the user the hook shows as enabled before proceeding to Task 4's verification (which needs a real token minted after this point).

---

### Task 4: Verify end-to-end

**Files:** none (verification only)

- [ ] **Step 1: Force a fresh token**

User logs out and back in (or waits for silent refresh) so the browser holds a token minted after Task 3. Per spec Decision 3, any old token now gets rejected by the guard — this step is not optional, it's required for the guard to work at all post-deploy.

- [ ] **Step 2: Decode and confirm the new claims**

```bash
echo "$ACCESS_TOKEN" | cut -d. -f2 | base64 -d
```
Expected: `app_org_id`, `app_role_id`, `app_permissions` present alongside the standard claims.

- [ ] **Step 3: Confirm a stale (pre-hook) token is rejected**

Using the old token captured earlier in this session (or any token minted before Task 3): confirm the guard now returns 401, not the old behavior.

- [ ] **Step 4: Re-run the real-browser timing trace**

Same method used throughout this session (`performance.clearResourceTimings()` + click-timer + `performance.getEntriesByType('resource')`). Confirm the guard's DB portion drops from ~400ms toward ~100ms on a route protected by `SupabaseAuthGuard` (e.g. `/chat/conversations`).

- [ ] **Step 5: Confirm suspension is still instant**

Suspend a test user via the platform-admin UI while they have an active session; confirm their very next request is blocked (403) immediately — not after any delay. This is the one guarantee that must not regress.

- [ ] **Step 6: Checkpoint**

Report final numbers (before/after) and confirm all checks passed. Remove the temporary `[perf]` `console.log` lines added earlier in this session (`supabase-auth.guard.ts`, `request-transaction.middleware.ts`) — they were diagnostic only, not meant to ship.

---

## Explicitly out of scope (per spec)

- `AuthService.me()` / `/auth/me` — separate code path, not touched.
- Caching the suspension check — rejected, breaks the one guarantee that must stay live.
- `PlatformAdminGuard` / platform-admin route tree — untouched.
- Shortening the access-token TTL.
