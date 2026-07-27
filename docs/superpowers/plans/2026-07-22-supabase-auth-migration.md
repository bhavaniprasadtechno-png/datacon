# Supabase Migration (DB + Auth) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Datacon's custom bcrypt/JWT auth with Supabase Auth, and move the app's primary Postgres from local Docker to the existing `datacon-staging-ew` Supabase project (`yicblouwgguhmfvwqdhm`), keeping the existing custom RBAC (Role/Permission) layer intact.

**Architecture:** The web app authenticates directly against Supabase Auth via `supabase-js` (sign-in/up/out, silent session refresh); it sends the Supabase access token as `Authorization: Bearer` to the NestJS API. NestJS verifies the token locally via `supabase.auth.getClaims()` (JWKS-based) in a new `SupabaseAuthGuard`, then joins the verified user id against the existing `Role`/`Permission` tables (now living in the same Supabase Postgres) to build the same `AuthenticatedUser` shape the rest of the app already expects. `PermissionsGuard`, `CurrentUser`, `RequirePermissions`/`RequireAnyPermission` are unchanged.

**Tech Stack:** NestJS 10, Prisma 5, `@supabase/supabase-js` v2, React 19 + Zustand 5, Jest.

**Reference spec:** `docs/superpowers/specs/2026-07-22-supabase-auth-migration-design.md`

## Global Constraints

- Supabase project: `datacon-staging-ew`, project ref/id `yicblouwgguhmfvwqdhm`, currently empty (no tables) — schema-first migration, no data backfill.
- Prisma keeps using a privileged direct Postgres connection (not the Supabase anon/authenticated client) — no RLS policies are part of this migration.
- `SUPABASE_SERVICE_ROLE_KEY` must only ever exist in `api/.env` (server-side) — never in `web/`.
- Seed/demo password stays `Datacon123!` (already documented in `app/README.md` and `packages/prisma/seed.ts`) — do not change it.
- `app/ai`'s `require_internal_auth` (static shared secret) is out of scope — do not touch `app/ai/**`.
- Do not commit any changes unless the user explicitly asks in that turn (per repo `CLAUDE.md`).

---

## Task 1: Dependencies and environment variables

**Files:**
- Modify: `app/api/package.json`
- Modify: `app/web/package.json`
- Modify: `app/packages/prisma/package.json`
- Modify: `app/api/.env.example`, `app/api/.env`
- Modify: `app/packages/prisma/.env.example`, `app/packages/prisma/.env`
- Create: `app/web/.env.example`, `app/web/.env`

**Interfaces:**
- Produces: env vars `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (api + prisma seed), `SUPABASE_ANON_KEY` (web), consumed by Task 2 (seed), Task 3 (guard), Task 8 (web client).

- [ ] **Step 1: Get the Supabase project's URL and anon key**

Run (via the `supabase-2` MCP tool, project id `yicblouwgguhmfvwqdhm`):
```
mcp__supabase-2__get_project_url(project_id="yicblouwgguhmfvwqdhm")
mcp__supabase-2__get_publishable_keys(project_id="yicblouwgguhmfvwqdhm")
```
Expected: a `https://yicblouwgguhmfvwqdhm.supabase.co` URL and an anon/publishable key string. The service-role key is **not** returned by MCP tools (by design) — get it from the Supabase dashboard → Project Settings → API → `service_role` secret, and the direct Postgres connection string (port 5432) from Project Settings → Database. Ask the user for these two secrets if you don't have them.

- [ ] **Step 2: Update `app/api/.env.example` and `app/api/.env`**

Replace the `## Auth ##` block in both files:
```
# ── Auth (Supabase) ──
SUPABASE_URL="https://yicblouwgguhmfvwqdhm.supabase.co"
SUPABASE_SERVICE_ROLE_KEY="change-me-service-role-key"
```
removing the old `JWT_ACCESS_SECRET`/`JWT_REFRESH_SECRET` lines. Also update the `DATABASE_URL` line/comment in both files — this project's dashboard surfaces pooler connections rather than a plain direct string, so use both a pooled `DATABASE_URL` (runtime, transaction mode, port 6543) and a `DIRECT_URL` (used only for `prisma migrate`, session mode, port 5432 — transaction-mode pgbouncer can't run DDL reliably):
```
# ── Database (Supabase Postgres via the shared pooler) ──
# Runtime queries go through the transaction-mode pooler (pgbouncer, 6543).
DATABASE_URL="postgresql://postgres.yicblouwgguhmfvwqdhm:[DB-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?pgbouncer=true"
# prisma migrate needs a non-pgbouncer connection — session-mode pooler (5432).
DIRECT_URL="postgresql://postgres.yicblouwgguhmfvwqdhm:[DB-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"
```
Percent-encode any special characters in the DB password when substituting it in (e.g. `@` → `%40`) — connection strings are URIs. `.env.example` keeps the `[DB-PASSWORD]`/`change-me-service-role-key` placeholders; `.env` gets the real secrets (ask the user for them, do not invent values).

- [ ] **Step 3: Update `app/packages/prisma/.env.example` and `app/packages/prisma/.env`**

Same `DATABASE_URL`/`DIRECT_URL` lines as Step 2 (comment already says "Keep in sync with ../../api/.env").

- [ ] **Step 3b: Add `directUrl` to `app/packages/prisma/schema.prisma`'s datasource block**

```prisma
datasource db {
  provider  = "postgresql"
  url       = env("DATABASE_URL")
  directUrl = env("DIRECT_URL")
}
```

- [ ] **Step 4: Create `app/web/.env.example` and `app/web/.env`**

```
# ── Supabase (public — safe to ship to the browser) ──
VITE_SUPABASE_URL="https://yicblouwgguhmfvwqdhm.supabase.co"
VITE_SUPABASE_ANON_KEY="change-me-anon-key"
```
`.env` gets the real anon key from Step 1.

- [ ] **Step 5: Add `@supabase/supabase-js` to `app/api/package.json`, `app/web/package.json`, `app/packages/prisma/package.json`**

In each `dependencies` block add:
```json
"@supabase/supabase-js": "^2.45.0",
```
In `app/api/package.json` `dependencies`, remove: `"@nestjs/jwt"`, `"@nestjs/passport"`, `"passport"`, `"passport-jwt"`, `"bcryptjs"`, `"cookie-parser"`. In `devDependencies`, remove: `"@types/bcryptjs"`, `"@types/cookie-parser"`, `"@types/passport-jwt"`.
In `app/packages/prisma/package.json` `devDependencies`, remove `"bcryptjs"` and `"@types/bcryptjs"`.

- [ ] **Step 6: Install**

Run: `npm install` (from `app/`)
Expected: lockfile updates, no errors; `@supabase/supabase-js` resolves in `web/node_modules`, `api/node_modules`, `packages/prisma/node_modules`.

- [ ] **Step 7: Commit**

```bash
git add api/package.json api/package-lock.json web/package.json web/package-lock.json \
        packages/prisma/package.json package-lock.json \
        api/.env.example packages/prisma/.env.example web/.env.example
git commit -m "chore: add supabase-js and Supabase env vars, drop JWT secrets"
```
(Do not `git add` the real `.env` files — they're gitignored already; verify with `git status` that only `.env.example` files are staged.)

---

## Task 2: Prisma schema + Postgres migration

**Files:**
- Modify: `app/packages/prisma/schema.prisma`
- Create: `app/packages/prisma/migrations/20260722080000_supabase_auth/migration.sql`

**Interfaces:**
- Produces: `User.id` is now `String @db.Uuid` (Supabase's `auth.users.id`), no `passwordHash`/`tokenVersion` fields, no `RefreshToken` model. `public.handle_new_user()` trigger auto-creates a `viewer`-role profile row on `auth.users` insert. Consumed by Task 3 (guard's Prisma lookup), Task 6 (seed.ts uuid ids), Task 7 (web store expects Supabase uuid as the user id).

- [ ] **Step 1: Edit `schema.prisma`'s `User` model**

Replace:
```prisma
model User {
  id           String   @id @default(cuid())
  email        String   @unique
  name         String
  passwordHash String
  initials     String
  avatarGrad   String   @default("var(--ac-grad)")
  title        String? // e.g. "Senior Analyst", "VP Sales & Ops"
  roleId       String
  role         Role     @relation(fields: [roleId], references: [id])
  tokenVersion Int      @default(0)
  isCore       Boolean  @default(false) // seed personas: cannot be deleted
  createdAt    DateTime @default(now())
  updatedAt    DateTime @updatedAt

  refreshTokens RefreshToken[]
  conversations Conversation[]
  documents     DataSource[]
  feedback      Feedback[]

  @@map("users")
}

model RefreshToken {
  id        String   @id @default(cuid())
  jti       String   @unique
  userId    String
  user      User     @relation(fields: [userId], references: [id], onDelete: Cascade)
  revoked   Boolean  @default(false)
  expiresAt DateTime
  createdAt DateTime @default(now())

  @@map("refresh_tokens")
}
```
with:
```prisma
// id is always a Supabase Auth user id (auth.users.id) — never generated
// locally. Assigned at signup (via the handle_new_user trigger) or by
// UsersService.create() after inviting the user through the Supabase
// Admin API.
model User {
  id         String   @id @db.Uuid
  email      String   @unique
  name       String
  initials   String
  avatarGrad String   @default("var(--ac-grad)")
  title      String? // e.g. "Senior Analyst", "VP Sales & Ops"
  roleId     String
  role       Role     @relation(fields: [roleId], references: [id])
  isCore     Boolean  @default(false) // seed personas: cannot be deleted
  createdAt  DateTime @default(now())
  updatedAt  DateTime @updatedAt

  conversations Conversation[]
  documents     DataSource[]
  feedback      Feedback[]

  @@map("users")
}
```
(the `RefreshToken` model is deleted entirely — Supabase Auth owns session/refresh lifecycle now).

- [ ] **Step 2: Update the three FK fields that reference `User.id`**

In `model DataSource`, change `uploadedById String` to `uploadedById String @db.Uuid`.
In `model Conversation`, change `userId String` to `userId String @db.Uuid`.
In `model Feedback`, change `userId String` to `userId String @db.Uuid`.

- [ ] **Step 3: Write the migration SQL**

Create `app/packages/prisma/migrations/20260722080000_supabase_auth/migration.sql`:
```sql
-- Drop legacy refresh-token bookkeeping (Supabase Auth owns session lifecycle now)
DROP TABLE "refresh_tokens";

-- Drop FK constraints that reference users.id so its type can change
ALTER TABLE "data_sources" DROP CONSTRAINT "data_sources_uploadedById_fkey";
ALTER TABLE "conversations" DROP CONSTRAINT "conversations_userId_fkey";
ALTER TABLE "feedback" DROP CONSTRAINT "feedback_userId_fkey";

-- users.id now comes from Supabase Auth (auth.users.id), not Prisma's cuid()
ALTER TABLE "users" ALTER COLUMN "id" TYPE UUID USING "id"::uuid;
ALTER TABLE "data_sources" ALTER COLUMN "uploadedById" TYPE UUID USING "uploadedById"::uuid;
ALTER TABLE "conversations" ALTER COLUMN "userId" TYPE UUID USING "userId"::uuid;
ALTER TABLE "feedback" ALTER COLUMN "userId" TYPE UUID USING "userId"::uuid;

-- Re-add the FK constraints
ALTER TABLE "data_sources" ADD CONSTRAINT "data_sources_uploadedById_fkey" FOREIGN KEY ("uploadedById") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "conversations" ADD CONSTRAINT "conversations_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "feedback" ADD CONSTRAINT "feedback_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- Drop local-credential columns (Supabase Auth owns passwords/sessions)
ALTER TABLE "users" DROP COLUMN "passwordHash";
ALTER TABLE "users" DROP COLUMN "tokenVersion";

-- Auto-provision a public.users profile row (default "viewer" role) whenever
-- someone signs up directly through supabase-js (self-serve register flow).
-- Requires the "viewer" role to already exist (seed.ts creates it) —
-- signups before the first seed run will fail with an FK violation.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  full_name text := COALESCE(NEW.raw_user_meta_data ->> 'name', split_part(NEW.email, '@', 1));
BEGIN
  INSERT INTO public.users (id, email, name, initials, "roleId")
  VALUES (NEW.id, NEW.email, full_name, upper(left(full_name, 1)), 'viewer')
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
```

- [ ] **Step 4: Apply the migration to `datacon-staging-ew` via the Supabase MCP tool**

Run:
```
mcp__supabase-2__apply_migration(
  project_id="yicblouwgguhmfvwqdhm",
  name="supabase_auth",
  query=<the full SQL from Step 3>
)
```
Expected: success. This applies against the real project without needing the Postgres password.

- [ ] **Step 5: Verify**

Run: `mcp__supabase-2__list_tables(project_id="yicblouwgguhmfvwqdhm", schemas=["public"], verbose=true)`
Expected: `users` table present with an `id` column of type `uuid`, no `passwordHash`/`tokenVersion` columns, no `refresh_tokens` table.

- [ ] **Step 6: Reconcile Prisma's own migration bookkeeping**

Once `DATABASE_URL` in `api/.env`/`packages/prisma/.env` has the real password (Task 1, Step 2), run (from `app/packages/prisma/`):
```
npx prisma migrate resolve --applied 20260722080000_supabase_auth
```
Expected: `Migration 20260722080000_supabase_auth marked as applied.` This tells Prisma's `_prisma_migrations` table the SQL was already run (via MCP in Step 4), so a later `prisma migrate deploy` elsewhere doesn't try to re-run it.

- [ ] **Step 7: Regenerate the Prisma client**

Run: `npm run prisma:generate` (from `app/`)
Expected: no errors; `@prisma/client`'s generated `User` type now has `id: string` (still a string in TS, just Postgres-typed as uuid) with no `passwordHash`/`tokenVersion` fields.

- [ ] **Step 8: Commit**

```bash
git add packages/prisma/schema.prisma packages/prisma/migrations/20260722080000_supabase_auth
git commit -m "feat: migrate users table to Supabase Auth uuid ids, drop refresh_tokens"
```

---

## Task 3: SupabaseAuthGuard

**Files:**
- Create: `app/api/src/auth/supabase-admin.client.ts`
- Create: `app/api/src/auth/guards/supabase-auth.guard.ts`
- Test: `app/api/src/auth/guards/supabase-auth.guard.spec.ts`

**Interfaces:**
- Consumes: `PrismaService` (from `../prisma/prisma.service`, `@Global()` — no extra module wiring needed, same as `PermissionsGuard`'s existing `Reflector` injection pattern).
- Produces: `getSupabaseAdminClient(): SupabaseClient` and `SupabaseAuthGuard implements CanActivate`, which sets `req.user: AuthenticatedUser` (`{ id: string; roleId: string; permissions: string[] }`, from `../token.types`). Consumed by Task 4 (every controller swaps `JwtAuthGuard` for this).

- [ ] **Step 1: Write the failing test**

Create `app/api/src/auth/guards/supabase-auth.guard.spec.ts`:
```ts
import { UnauthorizedException } from "@nestjs/common";
import type { ExecutionContext } from "@nestjs/common";
import { SupabaseAuthGuard } from "./supabase-auth.guard";
import * as supabaseAdminClient from "../supabase-admin.client";
import { PrismaService } from "../../prisma/prisma.service";

function contextWith(headers: Record<string, string>): ExecutionContext {
  return {
    switchToHttp: () => ({ getRequest: () => ({ headers }) }),
  } as unknown as ExecutionContext;
}

describe("SupabaseAuthGuard", () => {
  afterEach(() => jest.restoreAllMocks());

  it("throws Unauthorized when no bearer token is present", async () => {
    const guard = new SupabaseAuthGuard({} as PrismaService);
    await expect(guard.canActivate(contextWith({}))).rejects.toThrow(UnauthorizedException);
  });

  it("throws Unauthorized when getClaims rejects the token", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: { getClaims: jest.fn().mockResolvedValue({ data: null, error: new Error("bad token") }) },
    } as never);
    const guard = new SupabaseAuthGuard({} as PrismaService);
    await expect(guard.canActivate(contextWith({ authorization: "Bearer bad" }))).rejects.toThrow(UnauthorizedException);
  });

  it("throws Unauthorized when no local profile row exists for the verified user", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: { getClaims: jest.fn().mockResolvedValue({ data: { claims: { sub: "ghost-id" } }, error: null }) },
    } as never);
    const prisma = { user: { findUnique: jest.fn().mockResolvedValue(null) } } as unknown as PrismaService;
    const guard = new SupabaseAuthGuard(prisma);
    await expect(guard.canActivate(contextWith({ authorization: "Bearer good" }))).rejects.toThrow(UnauthorizedException);
  });

  it("attaches req.user with role permissions when the token and profile are valid", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: {
        getClaims: jest
          .fn()
          .mockResolvedValue({ data: { claims: { sub: "11111111-1111-1111-1111-111111111111" } }, error: null }),
      },
    } as never);
    const prisma = {
      user: {
        findUnique: jest.fn().mockResolvedValue({
          id: "11111111-1111-1111-1111-111111111111",
          roleId: "admin",
          role: { permissions: [{ permissionKey: "manage_users" }] },
        }),
      },
    } as unknown as PrismaService;
    const guard = new SupabaseAuthGuard(prisma);
    const req: { headers: Record<string, string>; user?: unknown } = { headers: { authorization: "Bearer good" } };
    const ctx = { switchToHttp: () => ({ getRequest: () => req }) } as unknown as ExecutionContext;

    const result = await guard.canActivate(ctx);

    expect(result).toBe(true);
    expect(req.user).toEqual({
      id: "11111111-1111-1111-1111-111111111111",
      roleId: "admin",
      permissions: ["manage_users"],
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test --workspace=api -- supabase-auth.guard.spec.ts`
Expected: FAIL — `Cannot find module './supabase-auth.guard'`.

- [ ] **Step 3: Create `app/api/src/auth/supabase-admin.client.ts`**

```ts
import { createClient, SupabaseClient } from "@supabase/supabase-js";

let cached: SupabaseClient | undefined;

/** Server-only Supabase client (service-role key). Used to verify bearer
 * tokens (getClaims) and for admin operations (inviting users). Never
 * import this from web/. */
export function getSupabaseAdminClient(): SupabaseClient {
  if (!cached) {
    const url = process.env.SUPABASE_URL;
    const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
    if (!url || !serviceRoleKey) {
      throw new Error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.");
    }
    cached = createClient(url, serviceRoleKey, {
      auth: { autoRefreshToken: false, persistSession: false },
    });
  }
  return cached;
}
```

- [ ] **Step 4: Create `app/api/src/auth/guards/supabase-auth.guard.ts`**

```ts
import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from "@nestjs/common";
import { PrismaService } from "../../prisma/prisma.service";
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
    const userId = data?.claims?.sub as string | undefined;
    if (error || !userId) throw new UnauthorizedException("Invalid or expired token.");

    const user = await this.prisma.user.findUnique({
      where: { id: userId },
      include: { role: { include: { permissions: true } } },
    });
    if (!user) throw new UnauthorizedException("No profile for this account.");

    const authedUser: AuthenticatedUser = {
      id: user.id,
      roleId: user.roleId,
      permissions: user.role.permissions.map((p) => p.permissionKey),
    };
    req.user = authedUser;
    return true;
  }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm run test --workspace=api -- supabase-auth.guard.spec.ts`
Expected: PASS — 4 tests green.

- [ ] **Step 6: Commit**

```bash
git add api/src/auth/supabase-admin.client.ts api/src/auth/guards/supabase-auth.guard.ts api/src/auth/guards/supabase-auth.guard.spec.ts
git commit -m "feat: add SupabaseAuthGuard verifying bearer tokens via getClaims"
```

---

## Task 4: Swap every controller from JwtAuthGuard to SupabaseAuthGuard; delete legacy JWT files

**Files:**
- Modify: `app/api/src/connectors/catalog.controller.ts`, `app/api/src/users/users.controller.ts`, `app/api/src/forecasts/forecasts.controller.ts`, `app/api/src/documents/documents.controller.ts`, `app/api/src/chat/chat.controller.ts`, `app/api/src/insights/insights.controller.ts`, `app/api/src/permissions/permissions.controller.ts`, `app/api/src/roles/roles.controller.ts`, `app/api/src/connectors/connectors.controller.ts`
- Modify: `app/api/src/auth/auth.module.ts`, `app/api/src/main.ts`, `app/api/src/auth/token.types.ts`
- Delete: `app/api/src/auth/strategies/jwt.strategy.ts`, `app/api/src/auth/strategies/jwt-refresh.strategy.ts`, `app/api/src/auth/guards/jwt-auth.guard.ts`, `app/api/src/auth/guards/jwt-refresh.guard.ts`

**Interfaces:**
- Consumes: `SupabaseAuthGuard` from Task 3.
- Produces: no controller references `JwtAuthGuard` anywhere; `AuthenticatedUser` (from `token.types.ts`) no longer has sibling `AccessTokenPayload`/`RefreshTokenPayload` types (removed, unused after Task 5).

- [ ] **Step 1: Replace the guard import + usage in each of the 9 controller files**

In each file below, replace the import line and the `@UseGuards(...)` line exactly as shown (nothing else in these files changes):

`app/api/src/connectors/catalog.controller.ts`:
```ts
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
// ...
@UseGuards(SupabaseAuthGuard)
```

`app/api/src/users/users.controller.ts`:
```ts
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
// ...
@UseGuards(SupabaseAuthGuard, PermissionsGuard)
```

`app/api/src/forecasts/forecasts.controller.ts`:
```ts
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
// ...
@UseGuards(SupabaseAuthGuard, PermissionsGuard)
```

`app/api/src/documents/documents.controller.ts`:
```ts
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
// ...
@UseGuards(SupabaseAuthGuard, PermissionsGuard)
```

`app/api/src/chat/chat.controller.ts`:
```ts
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
// ...
@UseGuards(SupabaseAuthGuard, PermissionsGuard)
```

`app/api/src/insights/insights.controller.ts`:
```ts
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
// ...
@UseGuards(SupabaseAuthGuard, PermissionsGuard)
```

`app/api/src/permissions/permissions.controller.ts`:
```ts
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { PermissionsGuard as PermissionsAuthGuard } from "../auth/guards/permissions.guard";
// ...
@UseGuards(SupabaseAuthGuard, PermissionsAuthGuard)
```

`app/api/src/roles/roles.controller.ts`:
```ts
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
// ...
@UseGuards(SupabaseAuthGuard, PermissionsGuard)
```

`app/api/src/connectors/connectors.controller.ts`:
```ts
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
// ...
@UseGuards(SupabaseAuthGuard, PermissionsGuard)
```

- [ ] **Step 2: Update `app/api/src/auth/token.types.ts`**

Replace the whole file with:
```ts
export interface AuthenticatedUser {
  id: string;
  roleId: string;
  permissions: string[];
}
```
(`AccessTokenPayload`/`RefreshTokenPayload` are deleted — nothing decodes a locally-signed JWT anymore.)

- [ ] **Step 3: Update `app/api/src/auth/auth.module.ts`**

Replace with:
```ts
import { Module } from "@nestjs/common";
import { AuthService } from "./auth.service";
import { AuthController } from "./auth.controller";

@Module({
  controllers: [AuthController],
  providers: [AuthService],
  exports: [AuthService],
})
export class AuthModule {}
```

- [ ] **Step 4: Update `app/api/src/main.ts`**

Remove the `cookie-parser` import and its `app.use(...)` call, and drop `credentials: true` from the CORS config (no cookies are sent cross-origin anymore — the bearer token is a header):
```ts
import "reflect-metadata";
import { NestFactory } from "@nestjs/core";
import { ValidationPipe } from "@nestjs/common";
import { AppModule } from "./app.module";

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.enableCors({
    origin: (process.env.CORS_ORIGINS ?? "http://localhost:5173").split(","),
  });
  app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
  app.setGlobalPrefix("api");
  const port = process.env.PORT ? Number(process.env.PORT) : 4000;
  await app.listen(port);
  // eslint-disable-next-line no-console
  console.log(`Datacon API listening on http://localhost:${port}/api`);
}
bootstrap();
```

- [ ] **Step 5: Delete the legacy JWT strategy/guard files**

```bash
rm api/src/auth/strategies/jwt.strategy.ts
rm api/src/auth/strategies/jwt-refresh.strategy.ts
rm api/src/auth/guards/jwt-auth.guard.ts
rm api/src/auth/guards/jwt-refresh.guard.ts
rmdir api/src/auth/strategies 2>/dev/null || true
```

- [ ] **Step 6: Build to verify no dangling references**

Run: `npm run build --workspace=api`
Expected: compiles with no errors (this will surface any missed `JwtAuthGuard`/`JwtRefreshGuard`/`AccessTokenPayload`/`RefreshTokenPayload` references — fix any that show up before moving on; Task 5 removes the remaining usages in `auth.controller.ts`/`auth.service.ts`, so a handful of errors there are expected and fixed in that task).

- [ ] **Step 7: Commit**

```bash
git add api/src/connectors/catalog.controller.ts api/src/users/users.controller.ts \
        api/src/forecasts/forecasts.controller.ts api/src/documents/documents.controller.ts \
        api/src/chat/chat.controller.ts api/src/insights/insights.controller.ts \
        api/src/permissions/permissions.controller.ts api/src/roles/roles.controller.ts \
        api/src/connectors/connectors.controller.ts api/src/auth/auth.module.ts \
        api/src/main.ts api/src/auth/token.types.ts
git rm api/src/auth/strategies/jwt.strategy.ts api/src/auth/strategies/jwt-refresh.strategy.ts \
       api/src/auth/guards/jwt-auth.guard.ts api/src/auth/guards/jwt-refresh.guard.ts
git commit -m "feat: swap JwtAuthGuard for SupabaseAuthGuard across all controllers"
```

---

## Task 5: Trim AuthController/AuthService to /me + /personas

**Files:**
- Modify: `app/api/src/auth/auth.controller.ts`, `app/api/src/auth/auth.service.ts`
- Delete: `app/api/src/auth/dto/login.dto.ts`, `app/api/src/auth/dto/register.dto.ts`

**Interfaces:**
- Produces: `AuthController` only exposes `GET /auth/me` (guarded) and `GET /auth/personas` (public). `AuthService` only exposes `personas()` and `me(userId)`.

- [ ] **Step 1: Replace `app/api/src/auth/auth.service.ts`**

```ts
import { Injectable } from "@nestjs/common";
import { PrismaService } from "../prisma/prisma.service";

@Injectable()
export class AuthService {
  constructor(private readonly prisma: PrismaService) {}

  private async userWithPermissions(userId: string) {
    const user = await this.prisma.user.findUniqueOrThrow({
      where: { id: userId },
      include: { role: { include: { permissions: true } } },
    });
    return {
      user,
      permissions: user.role.permissions.map((p) => p.permissionKey),
    };
  }

  /** Public quick-login roster shown on the login screen (demo personas only). */
  async personas() {
    const users = await this.prisma.user.findMany({
      where: { isCore: true },
      select: {
        id: true,
        name: true,
        title: true,
        initials: true,
        avatarGrad: true,
        roleId: true,
        role: { select: { name: true, colorHex: true, bgHex: true } },
      },
      orderBy: { createdAt: "asc" },
    });
    return users;
  }

  async me(userId: string) {
    const { user, permissions } = await this.userWithPermissions(userId);
    return {
      id: user.id,
      name: user.name,
      email: user.email,
      initials: user.initials,
      avatarGrad: user.avatarGrad,
      title: user.title,
      roleId: user.roleId,
      roleName: user.role.name,
      permissions,
    };
  }
}
```

- [ ] **Step 2: Replace `app/api/src/auth/auth.controller.ts`**

```ts
import { Controller, Get } from "@nestjs/common";
import { UseGuards } from "@nestjs/common";
import { AuthService } from "./auth.service";
import { SupabaseAuthGuard } from "./guards/supabase-auth.guard";
import { CurrentUser } from "./decorators/current-user.decorator";
import { AuthenticatedUser } from "./token.types";

@Controller("auth")
export class AuthController {
  constructor(private readonly auth: AuthService) {}

  @Get("personas")
  personas() {
    return this.auth.personas();
  }

  @UseGuards(SupabaseAuthGuard)
  @Get("me")
  async me(@CurrentUser() user: AuthenticatedUser) {
    return this.auth.me(user.id);
  }
}
```

- [ ] **Step 3: Delete the now-unused DTOs**

```bash
rm api/src/auth/dto/login.dto.ts
rm api/src/auth/dto/register.dto.ts
```

- [ ] **Step 4: Build to verify**

Run: `npm run build --workspace=api`
Expected: compiles cleanly — this resolves the expected errors from Task 4 Step 6.

- [ ] **Step 5: Commit**

```bash
git add api/src/auth/auth.controller.ts api/src/auth/auth.service.ts
git rm api/src/auth/dto/login.dto.ts api/src/auth/dto/register.dto.ts
git commit -m "feat: trim AuthController/AuthService to /me and /personas"
```

---

## Task 6: Admin user creation via Supabase invite

**Files:**
- Modify: `app/api/src/users/users.service.ts`

**Interfaces:**
- Consumes: `getSupabaseAdminClient()` from Task 3.
- Produces: `UsersService.create()` no longer generates a fake bcrypt password — it invites a real Supabase Auth user, then creates/updates the local profile row for the chosen role.

- [ ] **Step 1: Replace the `create()` method (and drop the `bcrypt` import) in `app/api/src/users/users.service.ts`**

Remove `import * as bcrypt from "bcryptjs";` and replace `create()`:
```ts
async create(dto: CreateUserDto) {
  const existing = await this.prisma.user.findUnique({ where: { email: dto.email } });
  if (existing) throw new ConflictException("An account with this email already exists.");
  const role = await this.prisma.role.findUnique({ where: { id: dto.roleId } });
  if (!role) throw new BadRequestException("Unknown role.");

  const { data, error } = await getSupabaseAdminClient().auth.admin.inviteUserByEmail(dto.email, {
    data: { name: dto.name },
  });
  if (error || !data?.user) {
    throw new BadRequestException(error?.message ?? "Could not invite this user.");
  }

  const count = await this.prisma.user.count();
  // handle_new_user already inserted a "viewer"-role row for this id — upsert
  // it here to apply the chosen role/title in the same request.
  const user = await this.prisma.user.upsert({
    where: { id: data.user.id },
    update: { name: dto.name, title: dto.title, roleId: dto.roleId },
    create: {
      id: data.user.id,
      name: dto.name,
      email: dto.email,
      title: dto.title,
      roleId: dto.roleId,
      initials: initialsFor(dto.name),
      avatarGrad: AVATAR_GRADIENTS[count % AVATAR_GRADIENTS.length],
      isCore: false,
    },
    select: this.select(),
  });
  return { ...user, canDelete: true, permissionCount: user.role.permissions.length };
}
```
Add the import at the top: `import { getSupabaseAdminClient } from "../auth/supabase-admin.client";`

- [ ] **Step 2: Build to verify**

Run: `npm run build --workspace=api`
Expected: compiles cleanly.

- [ ] **Step 3: Commit**

```bash
git add api/src/users/users.service.ts
git commit -m "feat: create admin-added users via Supabase invite instead of a fake password"
```

---

## Task 7: Seed script — real Supabase users for demo personas

**Files:**
- Modify: `app/packages/prisma/seed.ts`

**Interfaces:**
- Produces: the 4 demo personas exist as real Supabase Auth users (`SEED_PASSWORD = "Datacon123!"`, unchanged) with their local `users` row keyed by the Supabase-issued UUID instead of hardcoded slugs.

- [ ] **Step 1: Replace the imports and the `USERS`-seeding block in `app/packages/prisma/seed.ts`**

Remove `import * as bcrypt from "bcryptjs";` and add:
```ts
import { createClient } from "@supabase/supabase-js";

const supabaseAdmin = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!, {
  auth: { autoRefreshToken: false, persistSession: false },
});
```
Replace the `USERS` seeding block:
```ts
console.log("Seeding users...");
const personaIds: Record<string, string> = {};
for (const u of USERS) {
  const { data: existing } = await supabaseAdmin.auth.admin.listUsers();
  let authUser = existing?.users.find((au) => au.email === u.email);
  if (!authUser) {
    const { data, error } = await supabaseAdmin.auth.admin.createUser({
      email: u.email,
      password: SEED_PASSWORD,
      email_confirm: true,
      user_metadata: { name: u.name },
    });
    if (error || !data.user) throw new Error(`Could not create Supabase user ${u.email}: ${error?.message}`);
    authUser = data.user;
  }
  personaIds[u.id] = authUser.id;

  const { id: _slug, ...rest } = u;
  await prisma.user.upsert({
    where: { id: authUser.id },
    update: rest,
    create: { id: authUser.id, ...rest },
  });
}
```
Then, further down, replace the hardcoded `uploadedById: "sarah"` references in `DOCUMENTS` usage — change the seeding loop for documents to remap through `personaIds`:
```ts
console.log("Seeding data sources...");
for (const d of DOCUMENTS) {
  const { uploadedById, ...rest } = d;
  const data = { ...rest, uploadedById: personaIds[uploadedById] };
  await prisma.dataSource.upsert({ where: { id: d.id }, update: data, create: data });
}
```

- [ ] **Step 2: Add `@supabase/supabase-js` usage guard**

At the top of `main()`, keep the existing behavior of failing loudly if env vars are missing — `createClient` already throws synchronously if passed `undefined, undefined`, which is an acceptable failure mode for a seed script (no extra handling needed).

- [ ] **Step 3: Run the seed against Supabase**

Run: `npm run prisma:seed` (from `app/`, with `DATABASE_URL`/`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` set per Task 1)
Expected: `Done. Seed login password for all personas: Datacon123!` with no errors.

- [ ] **Step 4: Verify via Supabase MCP**

Run: `mcp__supabase-2__execute_sql(project_id="yicblouwgguhmfvwqdhm", query="select id, email, \"roleId\" from public.users order by \"createdAt\"")`
Expected: 4 rows (`sarah@acme.com`, `david@acme.com`, `tom@acme.com`, `maria@acme.com`) with uuid ids and correct `roleId`s.

- [ ] **Step 5: Commit**

```bash
git add packages/prisma/seed.ts
git commit -m "feat: seed demo personas as real Supabase Auth users"
```

---

## Task 8: Web app — supabase-js client, auth store, bearer interceptor

**Files:**
- Create: `app/web/src/lib/supabaseClient.ts`
- Modify: `app/web/src/stores/useAuthStore.ts`, `app/web/src/api/client.ts`, `app/web/src/lib/types.ts`, `app/web/src/routes/auth/AuthPage.tsx`
- Modify: `app/api/src/auth/auth.service.ts` (add `email` to the `personas()` select)

**Interfaces:**
- Produces: `supabase: SupabaseClient` (browser client, anon key). `useAuthStore`/`useAuth()` keep their existing public shape except `quickLogin` gains a second parameter: `quickLogin(personaId: string, email: string)` — the persona's email is already in hand on `AuthPage` (from `usePersonas()`), so `quickLogin` doesn't need to re-fetch it.

- [ ] **Step 1: Create `app/web/src/lib/supabaseClient.ts`**

```ts
import { createClient } from "@supabase/supabase-js";

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL as string,
  import.meta.env.VITE_SUPABASE_ANON_KEY as string,
);
```

- [ ] **Step 2: Replace `app/web/src/api/client.ts`**

```ts
import axios from "axios";
import { supabase } from "../lib/supabaseClient";

export const api = axios.create({
  baseURL: "/api",
});

api.interceptors.request.use(async (config) => {
  const { data } = await supabase.auth.getSession();
  if (data.session?.access_token) {
    config.headers.Authorization = `Bearer ${data.session.access_token}`;
  }
  return config;
});

export interface ApiErrorShape {
  message: string | string[];
  statusCode: number;
}

export function apiErrorMessage(err: unknown, fallback = "Something went wrong."): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as ApiErrorShape | undefined;
    if (data?.message) return Array.isArray(data.message) ? data.message.join(" ") : data.message;
  }
  return fallback;
}
```

- [ ] **Step 3: Replace `app/web/src/stores/useAuthStore.ts`**

```ts
import { create } from "zustand";
import { capsFromPermissions, type Capabilities } from "@datacon/shared-types";
import type { CurrentUser } from "../lib/types";
import { api } from "../api/client";
import { queryClient } from "../lib/queryClient";
import { supabase } from "../lib/supabaseClient";

const EMPTY_CAPS = capsFromPermissions([]);

interface AuthState {
  user: CurrentUser | undefined;
  caps: Capabilities;
  isLoading: boolean;
  isAuthenticated: boolean;
  fetchUser: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  quickLogin: (personaId: string, email: string) => Promise<void>;
  logout: () => Promise<void>;
}

const SEED_PASSWORD = "Datacon123!";

export const useAuthStore = create<AuthState>((set, get) => ({
  user: undefined,
  caps: EMPTY_CAPS,
  isLoading: true,
  isAuthenticated: false,
  fetchUser: async () => {
    try {
      const res = await api.get<CurrentUser>("/auth/me");
      set({
        user: res.data,
        caps: capsFromPermissions(res.data.permissions),
        isAuthenticated: true,
        isLoading: false,
      });
    } catch {
      set({
        user: undefined,
        caps: EMPTY_CAPS,
        isAuthenticated: false,
        isLoading: false,
      });
    }
  },
  login: async (email, password) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    await get().fetchUser();
  },
  register: async (name, email, password) => {
    const { error } = await supabase.auth.signUp({ email, password, options: { data: { name } } });
    if (error) throw error;
    await get().fetchUser();
  },
  quickLogin: async (_personaId, email) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password: SEED_PASSWORD });
    if (error) throw error;
    await get().fetchUser();
  },
  logout: async () => {
    await supabase.auth.signOut();
    set({
      user: undefined,
      caps: EMPTY_CAPS,
      isAuthenticated: false,
    });
    queryClient.clear();
  },
}));

supabase.auth.onAuthStateChange(() => {
  useAuthStore.getState().fetchUser();
});

export function useAuth() {
  const user = useAuthStore((state) => state.user);
  const caps = useAuthStore((state) => state.caps);
  const isLoading = useAuthStore((state) => state.isLoading);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const login = useAuthStore((state) => state.login);
  const register = useAuthStore((state) => state.register);
  const quickLogin = useAuthStore((state) => state.quickLogin);
  const logout = useAuthStore((state) => state.logout);

  return {
    user,
    caps,
    isLoading,
    isAuthenticated,
    login,
    register,
    quickLogin,
    logout,
  };
}
```
- [ ] **Step 4: Add `email` to `AuthService.personas()`'s select**

In `app/api/src/auth/auth.service.ts`, in `personas()`, add `email: true,` to the `select` object (alongside `id`, `name`, `title`, ...) — `quickLogin` needs the persona's email to sign in with.

- [ ] **Step 5: Add `email` to the `Persona` type and pass it through in `AuthPage.tsx`**

In `app/web/src/lib/types.ts`, add `email: string;` to the `Persona` interface:
```ts
export interface Persona {
  id: string;
  name: string;
  email: string;
  title: string | null;
  initials: string;
  avatarGrad: string;
  roleId: string;
  role: { name: string; colorHex: string | null; bgHex: string | null };
}
```
In `app/web/src/routes/auth/AuthPage.tsx`, update the quick-login button's `onClick`:
```tsx
onClick={() => quickLogin(p.id, p.email)}
```
(replacing the current `onClick={() => quickLogin(p.id)}`).

- [ ] **Step 6: Build to verify**

Run: `npm run build --workspace=web` and `npm run build --workspace=api`
Expected: both compile with no errors.

- [ ] **Step 7: Commit**

```bash
git add web/src/lib/supabaseClient.ts web/src/api/client.ts web/src/stores/useAuthStore.ts \
        web/src/lib/types.ts web/src/routes/auth/AuthPage.tsx api/src/auth/auth.service.ts
git commit -m "feat: authenticate the web app directly against Supabase via supabase-js"
```

---

## Task 9: Infra cleanup — docker-compose and README

**Files:**
- Modify: `app/docker-compose.yml`, `app/README.md`

**Interfaces:**
- None (documentation/infra only).

- [ ] **Step 1: Remove the `app_postgres` service and volume from `app/docker-compose.yml`**

Delete the `app_postgres:` service block (lines 8–20 in the current file) and its comment header, and remove `app_postgres_data:` from the `volumes:` section at the bottom. Update the file's top comment:
```yaml
version: "3.9"

# Local dev infrastructure. Supabase Postgres (datacon-staging-ew) is the
# app's own primary database in both dev and staging — the containers below
# are sample *external* data sources for the Postgres/MySQL/MongoDB
# connector engines, plus the ChromaDB vector store.
services:
  sample_postgres:
    ...
```
(keep `sample_postgres`, `sample_mysql`, `sample_mongo`, `chroma` and their volumes exactly as they are today).

- [ ] **Step 2: Update `app/README.md`'s "First-time setup" step 1**

Replace:
```
1. **Database**: either
   - create a [Supabase](https://supabase.com) project and copy its Postgres connection string into `DATABASE_URL`, **or**
   - run Postgres locally (`docker compose up -d app_postgres`, or a native `postgresql` install) and point `DATABASE_URL` at it.
```
with:
```
1. **Database**: create a [Supabase](https://supabase.com) project (or use the existing `datacon-staging-ew` project) and copy its direct Postgres connection string into `DATABASE_URL` — see `api/.env.example` for the exact format.
```

- [ ] **Step 3: Update the "Auth & RBAC" bullet under "What's implemented"**

Replace:
```
- **Auth & RBAC** — double-JWT cookie auth, custom roles/permissions, Users/Roles/Assign-roles/Permissions admin pages.
```
with:
```
- **Auth & RBAC** — Supabase Auth (bearer tokens, verified server-side via `getClaims`), custom roles/permissions, Users/Roles/Assign-roles/Permissions admin pages.
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml README.md
git commit -m "docs: update setup instructions for Supabase-only Postgres"
```

---

## Final verification (manual, via the `run` skill)

1. `npm run dev` (from `app/`) — boots api/ai/web together.
2. Register a brand-new user through the web UI → confirm (`mcp__supabase-2__execute_sql`) a `viewer`-role row now exists in `public.users`.
3. Quick-login as each of the 4 seeded personas.
4. As `viewer`, hit `PATCH /api/users/:id` (or the Users admin page) → expect 403. As `admin`, expect success.
5. Log out → confirm redirect to `/auth` and that a subsequent `GET /api/auth/me` without a session 401s.
6. Leave a tab open past the Supabase access-token expiry window; confirm `supabase-js`'s silent refresh keeps `isAuthenticated` true without user action.
