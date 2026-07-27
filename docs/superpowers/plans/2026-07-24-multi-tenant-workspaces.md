# Multi-tenant Workspaces + Platform Admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retrofit real multi-tenancy onto Datacon — isolated workspaces (`Organization`), each with its own users/roles/connectors/documents/conversations, plus a `PlatformAdmin` identity outside every workspace that can create workspaces and manage their users.

**Architecture:** Every org-scoped table gains a required `orgId`. NestJS filters explicitly by `orgId` in every service (the primary gate); Postgres RLS policies enforce the same boundary as a backstop, which requires switching Prisma's runtime connection off the RLS-bypassing role and wrapping each request in a transaction that sets a session-local org marker via `set_config()`. Self-registration creates a brand-new workspace (no domain logic); joining an existing one is invite-only. Platform Admin lives in a separate table, reachable only for Users/Roles management in any workspace, never workspace business data.

**Tech Stack:** NestJS 10, Prisma 5 (Client Extensions), Postgres RLS (Supabase), React 19 + Zustand 5, Jest.

**Reference spec:** `docs/superpowers/specs/2026-07-24-multi-tenant-workspaces-design.md`

## Global Constraints

- One workspace per email, for life — `User.orgId` is a single required, immutable FK. No multi-workspace switching.
- No domain-based logic anywhere — every self-registration creates a brand-new `Organization`, regardless of email domain.
- `Permission` catalog stays global (unscoped); only `Role`/`RolePermission` are per-workspace.
- Platform Admin's reach into "any org" is Users/Roles only — RLS gives it zero bypass on `connectors`/`unified_datasets`/`data_sources`/`conversations`/`messages`/`feedback`.
- Platform Admin UI lives in the same web app under `/platform-admin/*`, not a separate deployment.
- The public quick-login roster (`GET /auth/personas`, `quickLogin()`) is removed entirely — it structurally conflicts with workspace isolation (see design doc addendum). Seed personas still sign in normally via email + `Datacon123!`.
- `handle_new_user`/`on_auth_user_created` (the Postgres trigger from the prior auth migration) is dropped — replaced by `POST /auth/complete-registration`.
- Do not commit any changes unless the user explicitly asks in that turn (per repo `CLAUDE.md`).
- `app/ai/**` is out of scope, same as the prior auth migration.

---

## Task 1: Prisma schema — `Organization`, `PlatformAdmin`, `orgId` everywhere

**Files:**
- Modify: `app/packages/prisma/schema.prisma`

**Interfaces:**
- Produces: `Organization` (id, name), `PlatformAdmin` (id = auth uid, email, no relation to `User`), and a required `orgId String` field + relation on `User`, `Role`, `Connector`, `UnifiedDataset`, `DataSource`, `Conversation`, `Message`, `Feedback`. Consumed by every task below.

- [ ] **Step 1: Add the `Organization` and `PlatformAdmin` models**

In `app/packages/prisma/schema.prisma`, add near the top of the `Auth / RBAC` section (before `model User`):

```prisma
model Organization {
  id        String   @id @default(cuid())
  name      String
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt

  users         User[]
  roles         Role[]
  connectors    Connector[]
  datasets      UnifiedDataset[]
  documents     DataSource[]
  conversations Conversation[]
  messages      Message[]
  feedback      Feedback[]

  @@map("organizations")
}

// Deliberately NOT related to `User`/`Organization` — a platform admin must
// never be able to show up in any workspace-scoped query. Provisioned
// directly (one-off script), never through self-registration.
model PlatformAdmin {
  id        String   @id @db.Uuid // = auth.users.id
  email     String   @unique
  createdAt DateTime @default(now())

  @@map("platform_admins")
}
```

- [ ] **Step 2: Add `orgId` to `User` and `Role`**

Replace the `User` model:

```prisma
model User {
  id         String   @id @db.Uuid
  orgId      String
  org        Organization @relation(fields: [orgId], references: [id])
  email      String   @unique
  name       String
  initials   String
  avatarGrad String   @default("var(--ac-grad)")
  title      String?
  roleId     String
  role       Role     @relation(fields: [roleId], references: [id])
  isCore     Boolean  @default(false)
  createdAt  DateTime @default(now())
  updatedAt  DateTime @updatedAt

  conversations Conversation[]
  documents     DataSource[]
  feedback      Feedback[]

  @@map("users")
}
```

Replace the `Role` model:

```prisma
model Role {
  id          String   @id @default(cuid())
  orgId       String
  org         Organization @relation(fields: [orgId], references: [id])
  name        String
  colorHex    String?
  bgHex       String?
  isSystem    Boolean  @default(false)
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt

  users       User[]
  permissions RolePermission[]

  @@map("roles")
}
```

`Permission`/`RolePermission` are unchanged (stay global / scoped transitively via `Role.orgId`).

- [ ] **Step 3: Add `orgId` to `Connector`, `UnifiedDataset`, `DataSource`, `Conversation`, `Message`, `Feedback`**

In each model below, add `orgId String` + `org Organization @relation(fields: [orgId], references: [id])` (place directly after the `id` field). Nothing else in these models changes:

```prisma
model Connector {
  id            String          @id @default(cuid())
  orgId         String
  org           Organization    @relation(fields: [orgId], references: [id])
  name          String
  engine        ConnectorEngine
  // ...rest unchanged...
}

model UnifiedDataset {
  id          String    @id @default(cuid())
  orgId       String
  org         Organization @relation(fields: [orgId], references: [id])
  connectorId String
  connector   Connector @relation(fields: [connectorId], references: [id], onDelete: Cascade)
  // ...rest unchanged...
}

model DataSource {
  id           String    @id @default(cuid())
  orgId        String
  org          Organization @relation(fields: [orgId], references: [id])
  title        String
  // ...rest unchanged...
}

model Conversation {
  id        String    @id @default(cuid())
  orgId     String
  org       Organization @relation(fields: [orgId], references: [id])
  userId    String    @db.Uuid
  user      User      @relation(fields: [userId], references: [id])
  // ...rest unchanged...
}

model Message {
  id             String       @id @default(cuid())
  orgId          String
  org            Organization @relation(fields: [orgId], references: [id])
  conversationId String
  conversation   Conversation @relation(fields: [conversationId], references: [id], onDelete: Cascade)
  // ...rest unchanged...
}

model Feedback {
  id        String   @id @default(cuid())
  orgId     String
  org       Organization @relation(fields: [orgId], references: [id])
  messageId String   @unique
  message   Message  @relation(fields: [messageId], references: [id], onDelete: Cascade)
  userId    String   @db.Uuid
  user      User     @relation(fields: [userId], references: [id])
  vote      Int
  createdAt DateTime @default(now())

  @@map("feedback")
}
```

- [ ] **Step 4: Commit**

```bash
git add packages/prisma/schema.prisma
git commit -m "feat: add Organization/PlatformAdmin models, orgId on every workspace-scoped table"
```

---

## Task 2: Migration — tables, columns, backfill, `app_user` role, RLS policies

**Files:**
- Create: `app/packages/prisma/migrations/20260724000000_multi_tenant_workspaces/migration.sql`

**Interfaces:**
- Consumes: schema from Task 1.
- Produces: `organizations`/`platform_admins` tables; `orgId` on every workspace-scoped table, backfilled to one `'acme-corp'` org; a non-RLS-bypassing `app_user` Postgres role; RLS policies enforcing org isolation (with a Platform-Admin bypass limited to `users`/`roles`/`role_permissions`/`organizations`); `handle_new_user`/`on_auth_user_created` dropped. Consumed by Task 16 (seed data must match the `'acme-corp'` id) and every service task below (RLS is now load-bearing once Task 3 switches `DATABASE_URL`).

- [ ] **Step 1: Write the migration SQL**

Create `app/packages/prisma/migrations/20260724000000_multi_tenant_workspaces/migration.sql`:

```sql
-- ── New tables ──
CREATE TABLE "organizations" (
  "id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "organizations_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "platform_admins" (
  "id" UUID NOT NULL,
  "email" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "platform_admins_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "platform_admins_email_key" ON "platform_admins"("email");

-- Single existing workspace: every row created before this migration belongs here.
INSERT INTO "organizations" ("id", "name", "updatedAt")
VALUES ('acme-corp', 'Acme Corp', now());

-- ── orgId: add nullable, backfill, then require ──
ALTER TABLE "users" ADD COLUMN "orgId" TEXT;
ALTER TABLE "roles" ADD COLUMN "orgId" TEXT;
ALTER TABLE "connectors" ADD COLUMN "orgId" TEXT;
ALTER TABLE "unified_datasets" ADD COLUMN "orgId" TEXT;
ALTER TABLE "data_sources" ADD COLUMN "orgId" TEXT;
ALTER TABLE "conversations" ADD COLUMN "orgId" TEXT;
ALTER TABLE "messages" ADD COLUMN "orgId" TEXT;
ALTER TABLE "feedback" ADD COLUMN "orgId" TEXT;

UPDATE "users" SET "orgId" = 'acme-corp';
UPDATE "roles" SET "orgId" = 'acme-corp';
UPDATE "connectors" SET "orgId" = 'acme-corp';
UPDATE "unified_datasets" SET "orgId" = 'acme-corp';
UPDATE "data_sources" SET "orgId" = 'acme-corp';
UPDATE "conversations" SET "orgId" = 'acme-corp';
UPDATE "messages" SET "orgId" = 'acme-corp';
UPDATE "feedback" SET "orgId" = 'acme-corp';

ALTER TABLE "users" ALTER COLUMN "orgId" SET NOT NULL;
ALTER TABLE "roles" ALTER COLUMN "orgId" SET NOT NULL;
ALTER TABLE "connectors" ALTER COLUMN "orgId" SET NOT NULL;
ALTER TABLE "unified_datasets" ALTER COLUMN "orgId" SET NOT NULL;
ALTER TABLE "data_sources" ALTER COLUMN "orgId" SET NOT NULL;
ALTER TABLE "conversations" ALTER COLUMN "orgId" SET NOT NULL;
ALTER TABLE "messages" ALTER COLUMN "orgId" SET NOT NULL;
ALTER TABLE "feedback" ALTER COLUMN "orgId" SET NOT NULL;

ALTER TABLE "users" ADD CONSTRAINT "users_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "roles" ADD CONSTRAINT "roles_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "connectors" ADD CONSTRAINT "connectors_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "unified_datasets" ADD CONSTRAINT "unified_datasets_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "data_sources" ADD CONSTRAINT "data_sources_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "conversations" ADD CONSTRAINT "conversations_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "messages" ADD CONSTRAINT "messages_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "feedback" ADD CONSTRAINT "feedback_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- ── Remove the old single-tenant auto-provisioning trigger ──
-- Self-registration now creates the Organization/Roles/User itself via
-- POST /auth/complete-registration (see Task 8) — a plpgsql trigger is the
-- wrong place for that much logic.
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP FUNCTION IF EXISTS public.handle_new_user();

-- ── Non-bypassing runtime role ──
-- The existing DATABASE_URL/DIRECT_URL role (`postgres`) owns every table
-- and therefore always bypasses RLS regardless of policies, by Postgres's
-- table-owner rule. Prisma's *runtime* connection (DATABASE_URL only — NOT
-- DIRECT_URL, which `prisma migrate` still uses via the owning role) must
-- switch to a non-owning role with no BYPASSRLS for RLS to mean anything.
CREATE ROLE app_user WITH LOGIN PASSWORD 'REPLACE_WITH_REAL_PASSWORD';
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;

-- ── RLS policies ──
-- permissions/platform_admins: global, not org data — permissive so the
-- non-bypassing app_user role can still read them at all (RLS was enabled
-- with zero policies for every public table by the prior auth migration,
-- which was a correct deny-all *until now* — these two tables need an
-- explicit allow, since they're not workspace-scoped).
CREATE POLICY permissions_readable ON public.permissions USING (true);
CREATE POLICY platform_admins_readable ON public.platform_admins USING (true);

-- organizations: a member can see their own org; Platform Admin (real or
-- bootstrapping a brand-new org via complete-registration) sees/creates any.
CREATE POLICY org_isolation ON public.organizations
  USING ("id" = current_setting('app.current_org_id', true)
         OR current_setting('app.is_platform_admin', true) = 'true');

-- users/roles: org-scoped, but Platform Admin bypasses (its one allowed
-- cross-org capability — see design doc Decision 5).
CREATE POLICY org_isolation ON public.users
  USING ("orgId" = current_setting('app.current_org_id', true)
         OR current_setting('app.is_platform_admin', true) = 'true');
CREATE POLICY org_isolation ON public.roles
  USING ("orgId" = current_setting('app.current_org_id', true)
         OR current_setting('app.is_platform_admin', true) = 'true');

-- role_permissions has no orgId of its own — join to its Role's orgId.
CREATE POLICY org_isolation ON public.role_permissions
  USING (EXISTS (
    SELECT 1 FROM roles r WHERE r.id = role_permissions."roleId"
      AND (r."orgId" = current_setting('app.current_org_id', true)
           OR current_setting('app.is_platform_admin', true) = 'true')
  ));

-- Business data: org-scoped, NO Platform Admin bypass — structurally
-- unreadable to Platform Admin even via a raw query (design Decision 5).
CREATE POLICY org_isolation ON public.connectors
  USING ("orgId" = current_setting('app.current_org_id', true));
CREATE POLICY org_isolation ON public.unified_datasets
  USING ("orgId" = current_setting('app.current_org_id', true));
CREATE POLICY org_isolation ON public.data_sources
  USING ("orgId" = current_setting('app.current_org_id', true));
CREATE POLICY org_isolation ON public.conversations
  USING ("orgId" = current_setting('app.current_org_id', true));
CREATE POLICY org_isolation ON public.messages
  USING ("orgId" = current_setting('app.current_org_id', true));
CREATE POLICY org_isolation ON public.feedback
  USING ("orgId" = current_setting('app.current_org_id', true));

ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.platform_admins ENABLE ROW LEVEL SECURITY;
```

- [ ] **Step 2: Set a real `app_user` password before applying**

Before running this migration, replace `'REPLACE_WITH_REAL_PASSWORD'` in the file with a freshly generated secret: `node -e "console.log(require('crypto').randomBytes(24).toString('base64url'))"`. Keep this value — Task 3 needs it in `DATABASE_URL`.

- [ ] **Step 3: Apply the migration to `datacon-staging-ew` via the Supabase MCP tool**

Run:
```
mcp__supabase-2__apply_migration(
  project_id="yicblouwgguhmfvwqdhm",
  name="multi_tenant_workspaces",
  query=<the full SQL from Step 1, with the real password substituted>
)
```
Expected: success.

- [ ] **Step 4: Verify**

Run: `mcp__supabase-2__list_tables(project_id="yicblouwgguhmfvwqdhm", schemas=["public"], verbose=true)`
Expected: `organizations` (1 row) and `platform_admins` (0 rows) present; `users`/`roles`/`connectors`/`unified_datasets`/`data_sources`/`conversations`/`messages`/`feedback` all have a non-null `orgId` column.

- [ ] **Step 5: Reconcile Prisma's migration bookkeeping**

Once `app/packages/prisma/.env`'s `DATABASE_URL`/`DIRECT_URL` still point at the privileged role (unchanged for now — Task 3 changes `DATABASE_URL` only, after this resolve), run from `app/packages/prisma/`:
```
npx prisma migrate resolve --applied 20260724000000_multi_tenant_workspaces
```
Expected: `Migration 20260724000000_multi_tenant_workspaces marked as applied.`

- [ ] **Step 6: Regenerate the Prisma client**

Run: `npm run prisma:generate` (from `app/`)
Expected: no errors; `Organization`/`PlatformAdmin` types exist on `@prisma/client`; `User`/`Role`/etc. have `orgId: string`.

- [ ] **Step 7: Commit**

```bash
git add packages/prisma/migrations/20260724000000_multi_tenant_workspaces
git commit -m "feat: add organizations/platform_admins tables, orgId everywhere, app_user RLS role"
```

---

## Task 3: Per-request org context — AsyncLocalStorage + Prisma scoped client

**Files:**
- Create: `app/api/src/prisma/org-context.storage.ts`
- Modify: `app/api/src/prisma/prisma.service.ts`
- Modify: `app/api/.env`, `app/api/.env.example`, `app/packages/prisma/.env`, `app/packages/prisma/.env.example`

**Interfaces:**
- Produces: `orgContextStorage: AsyncLocalStorage<OrgContext>` and `PrismaService.scoped` — a Prisma Client Extension that, for every query, reads the current `OrgContext` from `orgContextStorage` and runs the query inside a transaction that first sets the matching Postgres session variable via `set_config()`. Consumed by every service task below (Tasks 10–15) via `this.prisma.scoped.<model>` instead of `this.prisma.<model>`, and by Task 4 (the interceptor that populates the storage).

- [ ] **Step 1: Create `app/api/src/prisma/org-context.storage.ts`**

```ts
import { AsyncLocalStorage } from "node:async_hooks";

export interface OrgContext {
  orgId?: string;
  isPlatformAdmin?: boolean;
}

/** Populated per-request by OrgContextInterceptor (Task 4); read by
 * PrismaService.scoped's query extension (this file's sibling,
 * prisma.service.ts) to set the matching Postgres RLS session variable. */
export const orgContextStorage = new AsyncLocalStorage<OrgContext>();
```

- [ ] **Step 2: Replace `app/api/src/prisma/prisma.service.ts`**

```ts
import { Injectable, OnModuleDestroy, OnModuleInit } from "@nestjs/common";
import { PrismaClient } from "@datacon/prisma";
import { orgContextStorage } from "./org-context.storage";

function withOrgContext(client: PrismaClient) {
  return client.$extends({
    name: "org-context",
    query: {
      $allModels: {
        async $allOperations({ model, operation, args, query }) {
          const ctx = orgContextStorage.getStore();
          if (!ctx || (!ctx.orgId && !ctx.isPlatformAdmin)) return query(args);

          return client.$transaction(async (tx) => {
            if (ctx.isPlatformAdmin) {
              await tx.$executeRaw`SELECT set_config('app.is_platform_admin', 'true', true)`;
            } else {
              await tx.$executeRaw`SELECT set_config('app.current_org_id', ${ctx.orgId}, true)`;
            }
            return (tx as unknown as Record<string, Record<string, (a: unknown) => unknown>>)[model!][operation](args);
          });
        },
      },
    },
  });
}

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  /** Org-scoped client — every query runs with the current request's RLS
   * session variable set. Services must use `this.prisma.scoped.<model>`,
   * never `this.prisma.<model>` directly, for anything org-scoped. */
  readonly scoped = withOrgContext(this);

  async onModuleInit() {
    await this.$connect();
  }

  async onModuleDestroy() {
    await this.$disconnect();
  }
}
```

- [ ] **Step 3: Point `DATABASE_URL` at the new `app_user` role**

In `app/api/.env` and `app/api/.env.example`, change the `DATABASE_URL` line to use `app_user` (keep `DIRECT_URL` unchanged — it stays on the privileged role, since `prisma migrate` needs to own/alter tables):

```
# ── Database (Supabase Postgres via the shared pooler) ──
# Runtime queries go through app_user (non-RLS-bypassing) via the transaction-mode pooler.
DATABASE_URL="postgresql://app_user.yicblouwgguhmfvwqdhm:<APP_USER_PASSWORD>@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?pgbouncer=true"
# prisma migrate needs the privileged owning role (app_user has no DDL rights) — session-mode pooler (5432).
DIRECT_URL="postgresql://postgres.yicblouwgguhmfvwqdhm:[DB-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"
```
(`.env.example` keeps `<APP_USER_PASSWORD>` as a placeholder; `.env` gets the real password generated in Task 2 Step 2. **Important:** Supabase's shared pooler (Supavisor) requires the tenant identifier in the username — `app_user.<project-ref>`, not a bare `app_user` — or every connection fails with `FATAL: no tenant identifier provided`. This is easy to miss since `app_user` is a real, valid Postgres role name on its own; the `.project-ref` suffix is a Supavisor routing convention, not part of the role name itself. Verified live in Task 19: a bare `app_user` connection string fails to connect at all.)

Apply the same `DATABASE_URL` change to `app/packages/prisma/.env`/`.env.example` (comment already says "keep in sync with ../../api/.env") — but note `packages/prisma`'s scripts (`prisma:seed`, `prisma migrate`) need the **privileged** role to create the `PlatformAdmin` seed row and to run migrations, so for `packages/prisma/.env` specifically, keep `DATABASE_URL` on the privileged role too (only `api/.env`'s runtime `DATABASE_URL` switches to `app_user`). Add a one-line comment noting this divergence from the "keep in sync" convention.

- [ ] **Step 4: Rebuild and confirm the API still boots**

Run: `npm run build --workspace=api` (from `app/`)
Expected: compiles with no errors (this task only adds code; no service has switched to `.scoped` yet, so behavior is unchanged until Task 4's interceptor is registered and Tasks 10–15 switch their calls).

- [ ] **Step 5: Commit**

```bash
git add api/src/prisma/org-context.storage.ts api/src/prisma/prisma.service.ts \
        api/.env.example packages/prisma/.env.example
git commit -m "feat: add per-request org-context storage and PrismaService.scoped extension"
```

---

## Task 4: `OrgContextInterceptor` + `@Bootstrapping()` decorator

**Files:**
- Create: `app/api/src/prisma/org-context.interceptor.ts`
- Create: `app/api/src/auth/decorators/bootstrapping.decorator.ts`
- Modify: `app/api/src/app.module.ts`

**Interfaces:**
- Consumes: `orgContextStorage` (Task 3), `req.user`/`req.platformAdmin` (set by guards in Tasks 5–7).
- Produces: a globally-registered interceptor that populates `orgContextStorage` for the duration of each request. Routes marked `@Bootstrapping()` (only `POST /auth/complete-registration`, Task 8) get `{ isPlatformAdmin: true }` — the same DB-level RLS bypass a real Platform Admin gets, scoped to the one code path that creates brand-new `Organization`/`Role`/`User` rows before any `orgId` exists yet.

- [ ] **Step 1: Create the `@Bootstrapping()` decorator**

```ts
// app/api/src/auth/decorators/bootstrapping.decorator.ts
import { SetMetadata } from "@nestjs/common";

export const BOOTSTRAPPING_KEY = "isBootstrapping";
export const Bootstrapping = () => SetMetadata(BOOTSTRAPPING_KEY, true);
```

- [ ] **Step 2: Create `app/api/src/prisma/org-context.interceptor.ts`**

```ts
import { CallHandler, ExecutionContext, Injectable, NestInterceptor } from "@nestjs/common";
import { Reflector } from "@nestjs/core";
import { Observable } from "rxjs";
import { orgContextStorage } from "./org-context.storage";
import { BOOTSTRAPPING_KEY } from "../auth/decorators/bootstrapping.decorator";

@Injectable()
export class OrgContextInterceptor implements NestInterceptor {
  constructor(private readonly reflector: Reflector) {}

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const req = context.switchToHttp().getRequest();
    const isBootstrapping = this.reflector.getAllAndOverride<boolean>(BOOTSTRAPPING_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);

    const ctx = req.platformAdmin || isBootstrapping
      ? { isPlatformAdmin: true }
      : req.user
        ? { orgId: req.user.orgId }
        : {};

    return new Observable((subscriber) => {
      orgContextStorage.run(ctx, () => {
        next.handle().subscribe(subscriber);
      });
    });
  }
}
```

- [ ] **Step 3: Register it globally in `app/api/src/app.module.ts`**

```ts
import { Module } from "@nestjs/common";
import { APP_INTERCEPTOR } from "@nestjs/core";
import { ConfigModule } from "@nestjs/config";
import { PrismaModule } from "./prisma/prisma.module";
import { CommonModule } from "./common/common.module";
import { HealthController } from "./health/health.controller";
import { AuthModule } from "./auth/auth.module";
import { UsersModule } from "./users/users.module";
import { RolesModule } from "./roles/roles.module";
import { PermissionsModule } from "./permissions/permissions.module";
import { ConnectorsModule } from "./connectors/connectors.module";
import { DocumentsModule } from "./documents/documents.module";
import { MetricsModule } from "./metrics/metrics.module";
import { ChatModule } from "./chat/chat.module";
import { ForecastsModule } from "./forecasts/forecasts.module";
import { InsightsModule } from "./insights/insights.module";
import { PlatformAdminModule } from "./platform-admin/platform-admin.module";
import { OrgContextInterceptor } from "./prisma/org-context.interceptor";

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    PrismaModule,
    CommonModule,
    AuthModule,
    UsersModule,
    RolesModule,
    PermissionsModule,
    ConnectorsModule,
    DocumentsModule,
    MetricsModule,
    ChatModule,
    ForecastsModule,
    InsightsModule,
    PlatformAdminModule,
  ],
  controllers: [HealthController],
  providers: [{ provide: APP_INTERCEPTOR, useClass: OrgContextInterceptor }],
})
export class AppModule {}
```

(`PlatformAdminModule` doesn't exist yet — created in Task 9. Import will error until then; that's expected and resolved by Task 9.)

- [ ] **Step 4: Commit**

```bash
git add api/src/prisma/org-context.interceptor.ts api/src/auth/decorators/bootstrapping.decorator.ts api/src/app.module.ts
git commit -m "feat: add OrgContextInterceptor populating per-request RLS session context"
```

---

## Task 5: `SupabaseAuthGuard` — attach `orgId`

**Files:**
- Modify: `app/api/src/auth/token.types.ts`
- Modify: `app/api/src/auth/guards/supabase-auth.guard.ts`
- Modify: `app/api/src/auth/guards/supabase-auth.guard.spec.ts`

**Interfaces:**
- Produces: `AuthenticatedUser` gains `orgId: string`. No other behavior changes — a Platform Admin has no `users` row, so the existing "No profile for this account" 401 already excludes them correctly; no new branching needed here.

- [ ] **Step 1: Update `app/api/src/auth/token.types.ts`**

```ts
export interface AuthenticatedUser {
  id: string;
  orgId: string;
  roleId: string;
  permissions: string[];
}
```

- [ ] **Step 2: Update the failing test first**

In `app/api/src/auth/guards/supabase-auth.guard.spec.ts`, update the last test's mock and expectation:

```ts
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
          orgId: "acme-corp",
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
      orgId: "acme-corp",
      roleId: "admin",
      permissions: ["manage_users"],
    });
  });
```

- [ ] **Step 3: Run test to verify it fails**

Run: `npm run test --workspace=api -- supabase-auth.guard.spec.ts`
Expected: FAIL — `req.user` is missing `orgId`.

- [ ] **Step 4: Update `app/api/src/auth/guards/supabase-auth.guard.ts`**

```ts
    const authedUser: AuthenticatedUser = {
      id: user.id,
      orgId: user.orgId,
      roleId: user.roleId,
      permissions: user.role.permissions.map((p) => p.permissionKey),
    };
```
(only this block changes; the rest of the file is unchanged.)

- [ ] **Step 5: Run test to verify it passes**

Run: `npm run test --workspace=api -- supabase-auth.guard.spec.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/src/auth/token.types.ts api/src/auth/guards/supabase-auth.guard.ts api/src/auth/guards/supabase-auth.guard.spec.ts
git commit -m "feat: attach orgId to AuthenticatedUser"
```

---

## Task 6: `SupabaseTokenGuard` (token-only, no profile lookup)

**Files:**
- Create: `app/api/src/auth/guards/supabase-token.guard.ts`
- Test: `app/api/src/auth/guards/supabase-token.guard.spec.ts`

**Interfaces:**
- Produces: `SupabaseTokenGuard implements CanActivate`, attaches `req.supabaseUserId: string` on success, 401s otherwise. Consumed by Task 8 (`GET /auth/me`, `POST /auth/complete-registration`).

- [ ] **Step 1: Write the failing test**

```ts
// app/api/src/auth/guards/supabase-token.guard.spec.ts
import { UnauthorizedException } from "@nestjs/common";
import type { ExecutionContext } from "@nestjs/common";
import { SupabaseTokenGuard } from "./supabase-token.guard";
import * as supabaseAdminClient from "../supabase-admin.client";

function contextWith(headers: Record<string, string>, req: Record<string, unknown> = {}): ExecutionContext {
  const reqObj = { headers, ...req };
  return { switchToHttp: () => ({ getRequest: () => reqObj }) } as unknown as ExecutionContext;
}

describe("SupabaseTokenGuard", () => {
  afterEach(() => jest.restoreAllMocks());

  it("throws Unauthorized when no bearer token is present", async () => {
    const guard = new SupabaseTokenGuard();
    await expect(guard.canActivate(contextWith({}))).rejects.toThrow(UnauthorizedException);
  });

  it("throws Unauthorized when getClaims rejects the token", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: { getClaims: jest.fn().mockResolvedValue({ data: null, error: new Error("bad token") }) },
    } as never);
    const guard = new SupabaseTokenGuard();
    await expect(guard.canActivate(contextWith({ authorization: "Bearer bad" }))).rejects.toThrow(UnauthorizedException);
  });

  it("attaches req.supabaseUserId when the token is valid", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: {
        getClaims: jest
          .fn()
          .mockResolvedValue({ data: { claims: { sub: "11111111-1111-1111-1111-111111111111" } }, error: null }),
      },
    } as never);
    const guard = new SupabaseTokenGuard();
    const req: { headers: Record<string, string>; supabaseUserId?: string } = { headers: { authorization: "Bearer good" } };
    const ctx = { switchToHttp: () => ({ getRequest: () => req }) } as unknown as ExecutionContext;

    const result = await guard.canActivate(ctx);

    expect(result).toBe(true);
    expect(req.supabaseUserId).toBe("11111111-1111-1111-1111-111111111111");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test --workspace=api -- supabase-token.guard.spec.ts`
Expected: FAIL — `Cannot find module './supabase-token.guard'`.

- [ ] **Step 3: Create `app/api/src/auth/guards/supabase-token.guard.ts`**

```ts
import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from "@nestjs/common";
import { getSupabaseAdminClient } from "../supabase-admin.client";

function bearerToken(req: { headers?: Record<string, unknown> }): string | undefined {
  const header = req.headers?.["authorization"];
  return typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : undefined;
}

/** Verifies the bearer token only — no local-profile lookup. Used by routes
 * that must work for a Supabase-authenticated identity with no `users` or
 * `platform_admins` row yet (GET /auth/me, POST /auth/complete-registration). */
@Injectable()
export class SupabaseTokenGuard implements CanActivate {
  async canActivate(context: ExecutionContext): Promise<boolean> {
    const req = context.switchToHttp().getRequest();
    const token = bearerToken(req);
    if (!token) throw new UnauthorizedException("Missing bearer token.");

    const { data, error } = await getSupabaseAdminClient().auth.getClaims(token);
    const userId = data?.claims?.sub as string | undefined;
    if (error || !userId) throw new UnauthorizedException("Invalid or expired token.");

    req.supabaseUserId = userId;
    return true;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test --workspace=api -- supabase-token.guard.spec.ts`
Expected: PASS — 3 tests green.

- [ ] **Step 5: Commit**

```bash
git add api/src/auth/guards/supabase-token.guard.ts api/src/auth/guards/supabase-token.guard.spec.ts
git commit -m "feat: add SupabaseTokenGuard for pre-profile authenticated routes"
```

---

## Task 7: `PlatformAdminGuard`

**Files:**
- Create: `app/api/src/auth/guards/platform-admin.guard.ts`
- Test: `app/api/src/auth/guards/platform-admin.guard.spec.ts`

**Interfaces:**
- Consumes: `PrismaService` (plain, unscoped — this guard runs *before* any org context exists, so it must query `platform_admins` directly, not via `.scoped`; the table's permissive RLS policy from Task 2 allows this regardless).
- Produces: attaches `req.platformAdmin = { id, email }` on success, 403s otherwise. Consumed by Task 9 (`PlatformAdminModule`).

- [ ] **Step 1: Write the failing test**

```ts
// app/api/src/auth/guards/platform-admin.guard.spec.ts
import { ForbiddenException, UnauthorizedException } from "@nestjs/common";
import type { ExecutionContext } from "@nestjs/common";
import { PlatformAdminGuard } from "./platform-admin.guard";
import * as supabaseAdminClient from "../supabase-admin.client";
import { PrismaService } from "../../prisma/prisma.service";

function contextWith(headers: Record<string, string>): ExecutionContext {
  const req: { headers: Record<string, string>; platformAdmin?: unknown } = { headers };
  return { switchToHttp: () => ({ getRequest: () => req }) } as unknown as ExecutionContext;
}

describe("PlatformAdminGuard", () => {
  afterEach(() => jest.restoreAllMocks());

  it("throws Unauthorized when no bearer token is present", async () => {
    const guard = new PlatformAdminGuard({} as PrismaService);
    await expect(guard.canActivate(contextWith({}))).rejects.toThrow(UnauthorizedException);
  });

  it("throws Forbidden when the verified user has no PlatformAdmin row", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: {
        getClaims: jest
          .fn()
          .mockResolvedValue({ data: { claims: { sub: "11111111-1111-1111-1111-111111111111" } }, error: null }),
      },
    } as never);
    const prisma = { platformAdmin: { findUnique: jest.fn().mockResolvedValue(null) } } as unknown as PrismaService;
    const guard = new PlatformAdminGuard(prisma);
    await expect(guard.canActivate(contextWith({ authorization: "Bearer good" }))).rejects.toThrow(ForbiddenException);
  });

  it("attaches req.platformAdmin when a PlatformAdmin row exists", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: {
        getClaims: jest
          .fn()
          .mockResolvedValue({ data: { claims: { sub: "11111111-1111-1111-1111-111111111111" } }, error: null }),
      },
    } as never);
    const prisma = {
      platformAdmin: {
        findUnique: jest.fn().mockResolvedValue({ id: "11111111-1111-1111-1111-111111111111", email: "pa@datacon.internal" }),
      },
    } as unknown as PrismaService;
    const guard = new PlatformAdminGuard(prisma);
    const req: { headers: Record<string, string>; platformAdmin?: unknown } = { headers: { authorization: "Bearer good" } };
    const ctx = { switchToHttp: () => ({ getRequest: () => req }) } as unknown as ExecutionContext;

    const result = await guard.canActivate(ctx);

    expect(result).toBe(true);
    expect(req.platformAdmin).toEqual({ id: "11111111-1111-1111-1111-111111111111", email: "pa@datacon.internal" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test --workspace=api -- platform-admin.guard.spec.ts`
Expected: FAIL — `Cannot find module './platform-admin.guard'`.

- [ ] **Step 3: Create `app/api/src/auth/guards/platform-admin.guard.ts`**

```ts
import { CanActivate, ExecutionContext, ForbiddenException, Injectable, UnauthorizedException } from "@nestjs/common";
import { PrismaService } from "../../prisma/prisma.service";
import { getSupabaseAdminClient } from "../supabase-admin.client";

function bearerToken(req: { headers?: Record<string, unknown> }): string | undefined {
  const header = req.headers?.["authorization"];
  return typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : undefined;
}

@Injectable()
export class PlatformAdminGuard implements CanActivate {
  constructor(private readonly prisma: PrismaService) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const req = context.switchToHttp().getRequest();
    const token = bearerToken(req);
    if (!token) throw new UnauthorizedException("Missing bearer token.");

    const { data, error } = await getSupabaseAdminClient().auth.getClaims(token);
    const userId = data?.claims?.sub as string | undefined;
    if (error || !userId) throw new UnauthorizedException("Invalid or expired token.");

    const admin = await this.prisma.platformAdmin.findUnique({ where: { id: userId } });
    if (!admin) throw new ForbiddenException("Platform Admin access required.");

    req.platformAdmin = { id: admin.id, email: admin.email };
    return true;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test --workspace=api -- platform-admin.guard.spec.ts`
Expected: PASS — 3 tests green.

- [ ] **Step 5: Commit**

```bash
git add api/src/auth/guards/platform-admin.guard.ts api/src/auth/guards/platform-admin.guard.spec.ts
git commit -m "feat: add PlatformAdminGuard"
```

---

## Task 8: `/auth/me` (kind discriminator) + `/auth/complete-registration`; remove quick-login

**Files:**
- Modify: `app/api/src/auth/auth.controller.ts`
- Modify: `app/api/src/auth/auth.service.ts`
- Test: `app/api/src/auth/auth.service.spec.ts`

**Interfaces:**
- Produces: `GET /auth/me` returns `{ kind: "platform_admin", id, email } | { kind: "org_member", id, orgId, name, email, initials, avatarGrad, title, roleId, roleName, permissions }`. `POST /auth/complete-registration { name, orgName }` creates a new `Organization` + 3 `Role`s + the calling `User` as its Admin, idempotent on the caller's Supabase id. `GET /auth/personas` and `AuthService.personas()` are removed.

- [ ] **Step 1: Write the failing test for `completeRegistration`**

Create `app/api/src/auth/auth.service.spec.ts`:

```ts
import { Test } from "@nestjs/testing";
import { AuthService } from "./auth.service";
import { PrismaService } from "../prisma/prisma.service";

describe("AuthService.completeRegistration", () => {
  it("is idempotent — returns the existing profile if one already exists", async () => {
    const prisma = {
      scoped: {
        user: {
          findUnique: jest.fn().mockResolvedValue({ id: "u1", orgId: "org1" }),
        },
      },
    } as unknown as PrismaService;
    const module = await Test.createTestingModule({
      providers: [AuthService, { provide: PrismaService, useValue: prisma }],
    }).compile();
    const service = module.get(AuthService);

    const result = await service.completeRegistration("u1", "Jordan Lee", "Jordan's Workspace");

    expect(result).toEqual({ id: "u1", orgId: "org1" });
    expect((prisma as any).scoped.user.findUnique).toHaveBeenCalledWith({ where: { id: "u1" } });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test --workspace=api -- auth.service.spec.ts`
Expected: FAIL — `completeRegistration` doesn't exist on `AuthService`.

- [ ] **Step 3: Replace `app/api/src/auth/auth.service.ts`**

```ts
import { Injectable } from "@nestjs/common";
import { PrismaService } from "../prisma/prisma.service";

const DEFAULT_PERMISSIONS_BY_ROLE: Record<string, string[]> = {
  viewer: ["view_dashboards", "ask_agents"],
  analyst: ["view_dashboards", "ask_agents", "export_data", "upload_docs", "manage_connectors"],
  admin: [
    "view_dashboards",
    "ask_agents",
    "export_data",
    "upload_docs",
    "manage_connectors",
    "manage_users",
    "manage_roles",
  ],
};

function initialsFor(name: string): string {
  const initials = name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
  return initials || "U";
}

@Injectable()
export class AuthService {
  constructor(private readonly prisma: PrismaService) {}

  private async userWithPermissions(userId: string) {
    // .scoped, not plain — see the class-level note below on why every
    // method here needs the is_platform_admin RLS bypass.
    const user = await this.prisma.scoped.user.findUniqueOrThrow({
      where: { id: userId },
      include: { role: { include: { permissions: true } } },
    });
    return { user, permissions: user.role.permissions.map((p) => p.permissionKey) };
  }

  /** GET /auth/me and POST /auth/complete-registration both run with
   * `@Bootstrapping()` on their controller routes (Task 4's
   * OrgContextInterceptor sets `app.is_platform_admin` for those routes),
   * which is what lets these two methods' `.scoped` queries see the
   * calling user's own row before any `app.current_org_id` is known —
   * exactly the same RLS bypass a real Platform Admin gets on
   * `users`/`roles`/`role_permissions`/`organizations` (Task 2), just
   * scoped in practice by every query below being hardcoded to the
   * caller's own verified `supabaseUserId`, never a listing. Plain
   * (non-`.scoped`) `this.prisma` calls would silently return zero rows
   * here, since no session var would ever be set for them. */

  /** GET /auth/me — checks PlatformAdmin first (disjoint identity space from
   * `users`), then falls back to the org-member profile. */
  async me(supabaseUserId: string) {
    const platformAdmin = await this.prisma.scoped.platformAdmin.findUnique({ where: { id: supabaseUserId } });
    if (platformAdmin) {
      return { kind: "platform_admin" as const, id: platformAdmin.id, email: platformAdmin.email };
    }

    const { user, permissions } = await this.userWithPermissions(supabaseUserId);
    return {
      kind: "org_member" as const,
      id: user.id,
      orgId: user.orgId,
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

  /** POST /auth/complete-registration — the self-registration bootstrap: a
   * brand-new Organization, its 3 default Roles + permissions, and the
   * calling Supabase user as that org's Admin. Idempotent on supabaseUserId
   * so a retry after a partial failure is safe (design doc "Error handling"). */
  async completeRegistration(supabaseUserId: string, name: string, orgName: string) {
    const existing = await this.prisma.scoped.user.findUnique({ where: { id: supabaseUserId } });
    if (existing) return existing;

    return this.prisma.scoped.$transaction(async (tx) => {
      const org = await tx.organization.create({ data: { name: orgName } });

      const roles: Record<string, { id: string }> = {};
      for (const [roleId, permissions] of Object.entries(DEFAULT_PERMISSIONS_BY_ROLE)) {
        const role = await tx.role.create({
          data: {
            orgId: org.id,
            name: roleId.charAt(0).toUpperCase() + roleId.slice(1),
            isSystem: true,
            permissions: { create: permissions.map((key) => ({ permissionKey: key })) },
          },
        });
        roles[roleId] = role;
      }

      return tx.user.create({
        data: {
          id: supabaseUserId,
          orgId: org.id,
          roleId: roles.admin.id,
          name,
          email: (await tx.$queryRaw<{ email: string }[]>`SELECT email FROM auth.users WHERE id = ${supabaseUserId}::uuid`)[0]?.email ?? "",
          initials: initialsFor(name),
          isCore: false,
        },
      });
    });
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test --workspace=api -- auth.service.spec.ts`
Expected: PASS.

- [ ] **Step 5: Replace `app/api/src/auth/auth.controller.ts`**

```ts
import { Body, Controller, Get, Post, Req, UseGuards } from "@nestjs/common";
import { SupabaseTokenGuard } from "./guards/supabase-token.guard";
import { Bootstrapping } from "./decorators/bootstrapping.decorator";
import { AuthService } from "./auth.service";
import { CompleteRegistrationDto } from "./dto/complete-registration.dto";

@Controller("auth")
export class AuthController {
  constructor(private readonly auth: AuthService) {}

  @UseGuards(SupabaseTokenGuard)
  @Bootstrapping()
  @Get("me")
  async me(@Req() req: { supabaseUserId: string }) {
    return this.auth.me(req.supabaseUserId);
  }

  @UseGuards(SupabaseTokenGuard)
  @Bootstrapping()
  @Post("complete-registration")
  async completeRegistration(@Req() req: { supabaseUserId: string }, @Body() dto: CompleteRegistrationDto) {
    return this.auth.completeRegistration(req.supabaseUserId, dto.name, dto.orgName);
  }
}
```

- [ ] **Step 6: Create the DTO**

```ts
// app/api/src/auth/dto/complete-registration.dto.ts
import { IsString, MinLength } from "class-validator";

export class CompleteRegistrationDto {
  @IsString()
  @MinLength(1)
  name!: string;

  @IsString()
  @MinLength(1)
  orgName!: string;
}
```

- [ ] **Step 7: Build to verify**

Run: `npm run build --workspace=api`
Expected: compiles cleanly.

- [ ] **Step 8: Commit**

```bash
git add api/src/auth/auth.controller.ts api/src/auth/auth.service.ts api/src/auth/auth.service.spec.ts api/src/auth/dto/complete-registration.dto.ts
git commit -m "feat: add /auth/complete-registration bootstrap flow, kind discriminator on /auth/me, remove personas"
```

---

## Task 9: `PlatformAdminModule` — create orgs, manage users in any org

**Files:**
- Create: `app/api/src/platform-admin/platform-admin.module.ts`
- Create: `app/api/src/platform-admin/platform-admin.controller.ts`
- Create: `app/api/src/platform-admin/platform-admin.service.ts`
- Create: `app/api/src/platform-admin/dto/create-organization.dto.ts`

**Interfaces:**
- Consumes: `PlatformAdminGuard` (Task 7), `getSupabaseAdminClient` (existing, from `../auth/supabase-admin.client`).
- Produces: `POST /platform-admin/organizations`, `GET/POST/PATCH /platform-admin/organizations/:orgId/users`. Note: this module's service uses the **plain** `PrismaService` (not `.scoped`) for the org-creation step, since `OrgContextInterceptor` already sets `app.is_platform_admin` for every request through `PlatformAdminGuard` — using `.scoped` here is what makes the cross-org RLS bypass actually take effect for these specific routes.

- [ ] **Step 1: Create the DTO**

```ts
// app/api/src/platform-admin/dto/create-organization.dto.ts
import { IsEmail, IsString, MinLength } from "class-validator";

export class CreateOrganizationDto {
  @IsString()
  @MinLength(1)
  name!: string;

  @IsEmail()
  adminEmail!: string;

  @IsString()
  @MinLength(1)
  adminName!: string;
}
```

- [ ] **Step 2: Create `app/api/src/platform-admin/platform-admin.service.ts`**

```ts
import { BadRequestException, Injectable } from "@nestjs/common";
import { PrismaService } from "../prisma/prisma.service";
import { getSupabaseAdminClient } from "../auth/supabase-admin.client";
import { CreateOrganizationDto } from "./dto/create-organization.dto";

const DEFAULT_PERMISSIONS_BY_ROLE: Record<string, string[]> = {
  viewer: ["view_dashboards", "ask_agents"],
  analyst: ["view_dashboards", "ask_agents", "export_data", "upload_docs", "manage_connectors"],
  admin: [
    "view_dashboards",
    "ask_agents",
    "export_data",
    "upload_docs",
    "manage_connectors",
    "manage_users",
    "manage_roles",
  ],
};

function initialsFor(name: string): string {
  const initials = name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("");
  return initials || "U";
}

@Injectable()
export class PlatformAdminService {
  // Uses `.scoped` throughout: PlatformAdminGuard + OrgContextInterceptor
  // together set `app.is_platform_admin`, which is what the RLS bypass on
  // organizations/users/roles/role_permissions checks (Task 2).
  constructor(private readonly prisma: PrismaService) {}

  async listOrganizations() {
    return this.prisma.scoped.organization.findMany({ orderBy: { createdAt: "asc" } });
  }

  async createOrganization(dto: CreateOrganizationDto) {
    const { data, error } = await getSupabaseAdminClient().auth.admin.inviteUserByEmail(dto.adminEmail, {
      data: { name: dto.adminName },
    });
    if (error || !data?.user) {
      throw new BadRequestException(error?.message ?? "Could not invite this organization's first admin.");
    }

    return this.prisma.scoped.$transaction(async (tx) => {
      const org = await tx.organization.create({ data: { name: dto.name } });

      let adminRoleId = "";
      for (const [roleId, permissions] of Object.entries(DEFAULT_PERMISSIONS_BY_ROLE)) {
        const role = await tx.role.create({
          data: {
            orgId: org.id,
            name: roleId.charAt(0).toUpperCase() + roleId.slice(1),
            isSystem: true,
            permissions: { create: permissions.map((key) => ({ permissionKey: key })) },
          },
        });
        if (roleId === "admin") adminRoleId = role.id;
      }

      await tx.user.create({
        data: {
          id: data.user.id,
          orgId: org.id,
          roleId: adminRoleId,
          name: dto.adminName,
          email: dto.adminEmail,
          initials: initialsFor(dto.adminName),
          isCore: false,
        },
      });

      return org;
    });
  }

  async listUsers(orgId: string) {
    return this.prisma.scoped.user.findMany({
      where: { orgId },
      select: { id: true, name: true, email: true, roleId: true, role: { select: { name: true } } },
      orderBy: { createdAt: "asc" },
    });
  }
}
```

- [ ] **Step 3: Create `app/api/src/platform-admin/platform-admin.controller.ts`**

```ts
import { Body, Controller, Get, Param, Post, UseGuards } from "@nestjs/common";
import { PlatformAdminGuard } from "../auth/guards/platform-admin.guard";
import { PlatformAdminService } from "./platform-admin.service";
import { CreateOrganizationDto } from "./dto/create-organization.dto";

@UseGuards(PlatformAdminGuard)
@Controller("platform-admin/organizations")
export class PlatformAdminController {
  constructor(private readonly platformAdmin: PlatformAdminService) {}

  @Get()
  list() {
    return this.platformAdmin.listOrganizations();
  }

  @Post()
  create(@Body() dto: CreateOrganizationDto) {
    return this.platformAdmin.createOrganization(dto);
  }

  @Get(":orgId/users")
  listUsers(@Param("orgId") orgId: string) {
    return this.platformAdmin.listUsers(orgId);
  }
}
```

- [ ] **Step 4: Create `app/api/src/platform-admin/platform-admin.module.ts`**

```ts
import { Module } from "@nestjs/common";
import { PlatformAdminController } from "./platform-admin.controller";
import { PlatformAdminService } from "./platform-admin.service";

@Module({
  controllers: [PlatformAdminController],
  providers: [PlatformAdminService],
})
export class PlatformAdminModule {}
```

- [ ] **Step 5: Build to verify**

Run: `npm run build --workspace=api`
Expected: compiles cleanly (this resolves the `PlatformAdminModule` import added to `app.module.ts` in Task 4).

- [ ] **Step 6: Commit**

```bash
git add api/src/platform-admin
git commit -m "feat: add PlatformAdminModule — create organizations, list org users"
```

---

## Task 10: `UsersService`/`UsersController` — org scoping + cross-org role guard

**Files:**
- Modify: `app/api/src/users/users.service.ts`

**Interfaces:**
- Produces: every method takes/uses `orgId`; `create()` rejects a `roleId` that doesn't belong to the caller's org before inviting.

- [ ] **Step 1: Replace `app/api/src/users/users.service.ts`**

```ts
import { BadRequestException, ConflictException, ForbiddenException, Injectable, NotFoundException } from "@nestjs/common";
import { PrismaService } from "../prisma/prisma.service";
import { getSupabaseAdminClient } from "../auth/supabase-admin.client";
import { CreateUserDto } from "./dto/create-user.dto";
import { UpdateUserDto } from "./dto/update-user.dto";

const AVATAR_GRADIENTS = [
  "var(--ac-grad)",
  "linear-gradient(135deg,#ff8a5c,#ff5c7a)",
  "linear-gradient(135deg,#1fb6a6,#13a06b)",
  "linear-gradient(135deg,#5b8def,#3f6fd6)",
  "linear-gradient(135deg,#f2a65a,#e2603f)",
];

function initialsFor(name: string): string {
  const initials = name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("");
  return initials || "U";
}

@Injectable()
export class UsersService {
  constructor(private readonly prisma: PrismaService) {}

  private select() {
    return {
      id: true,
      name: true,
      email: true,
      initials: true,
      avatarGrad: true,
      title: true,
      isCore: true,
      createdAt: true,
      roleId: true,
      role: { select: { id: true, name: true, colorHex: true, bgHex: true, permissions: { select: { permissionKey: true } } } },
    } as const;
  }

  async list(orgId: string) {
    const users = await this.prisma.scoped.user.findMany({ where: { orgId }, select: this.select(), orderBy: { createdAt: "asc" } });
    return users.map((u) => ({ ...u, canDelete: !u.isCore, permissionCount: u.role.permissions.length }));
  }

  async create(orgId: string, dto: CreateUserDto) {
    const existing = await this.prisma.scoped.user.findUnique({ where: { email: dto.email } });
    if (existing) throw new ConflictException("An account with this email already exists.");
    const role = await this.prisma.scoped.role.findUnique({ where: { id: dto.roleId } });
    if (!role || role.orgId !== orgId) throw new BadRequestException("Unknown role.");

    const { data, error } = await getSupabaseAdminClient().auth.admin.inviteUserByEmail(dto.email, {
      data: { name: dto.name },
    });
    if (error || !data?.user) {
      throw new BadRequestException(error?.message ?? "Could not invite this user.");
    }

    const count = await this.prisma.scoped.user.count({ where: { orgId } });
    const user = await this.prisma.scoped.user.upsert({
      where: { id: data.user.id },
      update: { name: dto.name, title: dto.title, roleId: dto.roleId },
      create: {
        id: data.user.id,
        orgId,
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

  async update(orgId: string, id: string, dto: UpdateUserDto) {
    const user = await this.prisma.scoped.user.findUnique({ where: { id } });
    if (!user || user.orgId !== orgId) throw new NotFoundException("User not found.");
    if (dto.roleId) {
      const role = await this.prisma.scoped.role.findUnique({ where: { id: dto.roleId } });
      if (!role || role.orgId !== orgId) throw new BadRequestException("Unknown role.");
    }
    const updated = await this.prisma.scoped.user.update({
      where: { id },
      data: { name: dto.name, email: dto.email, roleId: dto.roleId },
      select: this.select(),
    });
    return { ...updated, canDelete: !updated.isCore, permissionCount: updated.role.permissions.length };
  }

  async remove(orgId: string, id: string) {
    const user = await this.prisma.scoped.user.findUnique({ where: { id } });
    if (!user || user.orgId !== orgId) throw new NotFoundException("User not found.");
    if (user.isCore) throw new ForbiddenException("This is a core demo account and can't be removed.");
    await this.prisma.scoped.user.delete({ where: { id } });
    return { ok: true };
  }

  async assignRole(orgId: string, id: string, roleId: string) {
    const role = await this.prisma.scoped.role.findUnique({ where: { id: roleId } });
    if (!role || role.orgId !== orgId) throw new BadRequestException("Unknown role.");
    const updated = await this.prisma.scoped.user.update({
      where: { id },
      data: { roleId },
      select: this.select(),
    });
    return { ...updated, canDelete: !updated.isCore, permissionCount: updated.role.permissions.length };
  }
}
```

- [ ] **Step 2: Pass `orgId` from the controller**

In `app/api/src/users/users.controller.ts`, add `@CurrentUser() user: AuthenticatedUser` to every method and pass `user.orgId` as the first argument to each service call (import `CurrentUser` from `"../auth/decorators/current-user.decorator"` and `AuthenticatedUser` from `"../auth/token.types"`):

```ts
import { Body, Controller, Delete, Get, Param, Patch, Post, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { CurrentUser } from "../auth/decorators/current-user.decorator";
import { AuthenticatedUser } from "../auth/token.types";
import { UsersService } from "./users.service";
import { CreateUserDto } from "./dto/create-user.dto";
import { UpdateUserDto } from "./dto/update-user.dto";
import { AssignRoleDto } from "./dto/assign-role.dto";

@UseGuards(SupabaseAuthGuard, PermissionsGuard)
@Controller("users")
export class UsersController {
  constructor(private readonly users: UsersService) {}

  @RequirePermissions("manage_users")
  @Get()
  list(@CurrentUser() user: AuthenticatedUser) {
    return this.users.list(user.orgId);
  }

  @RequirePermissions("manage_users")
  @Post()
  create(@CurrentUser() user: AuthenticatedUser, @Body() dto: CreateUserDto) {
    return this.users.create(user.orgId, dto);
  }

  @RequirePermissions("manage_users")
  @Patch(":id")
  update(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string, @Body() dto: UpdateUserDto) {
    return this.users.update(user.orgId, id, dto);
  }

  @RequirePermissions("manage_users")
  @Delete(":id")
  remove(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string) {
    return this.users.remove(user.orgId, id);
  }

  @RequirePermissions("manage_users")
  @Patch(":id/assign-role")
  assignRole(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string, @Body() dto: AssignRoleDto) {
    return this.users.assignRole(user.orgId, id, dto.roleId);
  }
}
```

- [ ] **Step 3: Build to verify**

Run: `npm run build --workspace=api`
Expected: compiles cleanly.

- [ ] **Step 4: Commit**

```bash
git add api/src/users/users.service.ts api/src/users/users.controller.ts
git commit -m "feat: scope UsersService by orgId, reject cross-org role assignment"
```

---

## Task 11: `RolesService` — org scoping

**Files:**
- Modify: `app/api/src/roles/roles.service.ts`
- Modify: `app/api/src/roles/roles.controller.ts`

**Interfaces:**
- Produces: every method scoped by `orgId`, following the exact pattern from Task 10.

- [ ] **Step 1: Replace `app/api/src/roles/roles.service.ts`**

```ts
import { BadRequestException, ConflictException, ForbiddenException, Injectable, NotFoundException } from "@nestjs/common";
import { PrismaService } from "../prisma/prisma.service";
import { CreateRoleDto } from "./dto/create-role.dto";
import { UpdateRoleDto } from "./dto/update-role.dto";

function deriveBg(colorHex: string): string | null {
  if (/^#([0-9a-f]{6})$/i.test(colorHex)) return `${colorHex}1f`;
  return null;
}

@Injectable()
export class RolesService {
  constructor(private readonly prisma: PrismaService) {}

  private include() {
    return {
      permissions: { select: { permissionKey: true } },
      _count: { select: { users: true } },
    } as const;
  }

  private shape(role: any) {
    return {
      id: role.id,
      name: role.name,
      colorHex: role.colorHex,
      bgHex: role.bgHex,
      isSystem: role.isSystem,
      permissions: role.permissions.map((p: any) => p.permissionKey),
      userCount: role._count.users,
    };
  }

  async list(orgId: string) {
    const roles = await this.prisma.scoped.role.findMany({ where: { orgId }, include: this.include(), orderBy: { createdAt: "asc" } });
    return roles.map((r) => this.shape(r));
  }

  async create(orgId: string, dto: CreateRoleDto) {
    const role = await this.prisma.scoped.role.create({
      data: {
        orgId,
        name: dto.name,
        colorHex: dto.colorHex,
        bgHex: deriveBg(dto.colorHex),
        isSystem: false,
        permissions: { create: dto.permissions.map((key) => ({ permissionKey: key })) },
      },
      include: this.include(),
    });
    return this.shape(role);
  }

  async update(orgId: string, id: string, dto: UpdateRoleDto) {
    const role = await this.prisma.scoped.role.findUnique({ where: { id } });
    if (!role || role.orgId !== orgId) throw new NotFoundException("Role not found.");

    if (dto.permissions) {
      await this.prisma.scoped.rolePermission.deleteMany({ where: { roleId: id } });
      await this.prisma.scoped.rolePermission.createMany({
        data: dto.permissions.map((key) => ({ roleId: id, permissionKey: key })),
      });
    }

    const updated = await this.prisma.scoped.role.update({
      where: { id },
      data: {
        name: dto.name,
        colorHex: dto.colorHex,
        bgHex: dto.colorHex ? deriveBg(dto.colorHex) : undefined,
      },
      include: this.include(),
    });
    return this.shape(updated);
  }

  async remove(orgId: string, id: string) {
    const role = await this.prisma.scoped.role.findUnique({ where: { id }, include: this.include() });
    if (!role || role.orgId !== orgId) throw new NotFoundException("Role not found.");
    if (role.isSystem) throw new ForbiddenException("System roles can't be deleted.");
    if (role._count.users > 0) {
      throw new ConflictException(`${role.name} is assigned to ${role._count.users} user(s). Reassign them first.`);
    }
    await this.prisma.scoped.role.delete({ where: { id } });
    return { ok: true };
  }

  async applyPermissionsMatrix(orgId: string, matrix: Record<string, string[]>) {
    const roleIds = Object.keys(matrix);
    const existing = await this.prisma.scoped.role.findMany({ where: { id: { in: roleIds }, orgId } });
    if (existing.length !== roleIds.length) {
      throw new BadRequestException("One or more roles in the matrix were not found.");
    }
    await this.prisma.scoped.$transaction(
      roleIds.flatMap((roleId) => [
        this.prisma.scoped.rolePermission.deleteMany({ where: { roleId } }),
        this.prisma.scoped.rolePermission.createMany({
          data: matrix[roleId].map((key) => ({ roleId, permissionKey: key })),
        }),
      ]),
    );
    return this.list(orgId);
  }
}
```

- [ ] **Step 2: Update `app/api/src/roles/roles.controller.ts`** to pass `user.orgId` (same pattern as Task 10 Step 2):

```ts
import { Body, Controller, Delete, Get, Param, Patch, Post, Put, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { RequireAnyPermission } from "../auth/decorators/require-any-permission.decorator";
import { CurrentUser } from "../auth/decorators/current-user.decorator";
import { AuthenticatedUser } from "../auth/token.types";
import { RolesService } from "./roles.service";
import { CreateRoleDto } from "./dto/create-role.dto";
import { UpdateRoleDto } from "./dto/update-role.dto";
import { ApplyPermissionsMatrixDto } from "./dto/apply-permissions-matrix.dto";

@UseGuards(SupabaseAuthGuard, PermissionsGuard)
@Controller("roles")
export class RolesController {
  constructor(private readonly roles: RolesService) {}

  @RequireAnyPermission("manage_users", "manage_roles")
  @Get()
  list(@CurrentUser() user: AuthenticatedUser) {
    return this.roles.list(user.orgId);
  }

  @RequirePermissions("manage_roles")
  @Post()
  create(@CurrentUser() user: AuthenticatedUser, @Body() dto: CreateRoleDto) {
    return this.roles.create(user.orgId, dto);
  }

  @RequirePermissions("manage_roles")
  @Patch(":id")
  update(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string, @Body() dto: UpdateRoleDto) {
    return this.roles.update(user.orgId, id, dto);
  }

  @RequirePermissions("manage_roles")
  @Delete(":id")
  remove(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string) {
    return this.roles.remove(user.orgId, id);
  }

  @RequirePermissions("manage_roles")
  @Put("permissions-matrix")
  applyMatrix(@CurrentUser() user: AuthenticatedUser, @Body() dto: ApplyPermissionsMatrixDto) {
    return this.roles.applyPermissionsMatrix(user.orgId, dto.matrix);
  }
}
```

- [ ] **Step 3: Build to verify**

Run: `npm run build --workspace=api`
Expected: compiles cleanly.

- [ ] **Step 4: Commit**

```bash
git add api/src/roles/roles.service.ts api/src/roles/roles.controller.ts
git commit -m "feat: scope RolesService by orgId"
```

---

## Task 12: `ConnectorsService` — org scoping

**Files:**
- Modify: `app/api/src/connectors/connectors.service.ts`
- Modify: `app/api/src/connectors/connectors.controller.ts`
- Modify: `app/api/src/connectors/catalog.controller.ts`

**Interfaces:**
- Produces: `list`/`create`/`remove`/`syncNow`/`catalog`/`tablePreview` all take `orgId` and use `this.prisma.scoped`.

- [ ] **Step 1: In `app/api/src/connectors/connectors.service.ts`**, change every `this.prisma.` to `this.prisma.scoped.`, and thread `orgId` through:

```ts
  async list(orgId: string) {
    const rows = await this.prisma.scoped.connector.findMany({
      where: { orgId },
      include: { _count: { select: { datasets: true } } },
      orderBy: { createdAt: "asc" },
    });
    return rows.map((r) => this.shape(r));
  }

  async create(orgId: string, dto: SaveConnectorDto) {
    this.validateFields(dto.engine, dto.fields);
    const { config, plainSecrets } = this.splitFields(dto.engine, dto.fields);
    const secrets = this.encryptSecrets(plainSecrets);

    const row = await this.prisma.scoped.connector.create({
      data: {
        orgId,
        name: dto.name?.trim() || `${dto.engine} connector`,
        engine: toEngineEnum(dto.engine),
        config,
        secrets,
        syncInterval: dto.syncInterval || "Manual only",
        status: "SYNCING",
      },
    });

    await this.runSync(row.id, dto.engine, config, plainSecrets);
    return this.findOneShaped(row.id);
  }

  async remove(orgId: string, id: string) {
    const row = await this.prisma.scoped.connector.findUnique({ where: { id } });
    if (!row || row.orgId !== orgId) throw new NotFoundException("Connector not found.");
    await this.prisma.scoped.connector.delete({ where: { id } });
    return { ok: true };
  }

  async syncNow(orgId: string, id: string) {
    const row = await this.prisma.scoped.connector.findUnique({ where: { id } });
    if (!row || row.orgId !== orgId) throw new NotFoundException("Connector not found.");
    await this.prisma.scoped.connector.update({ where: { id }, data: { status: "SYNCING" } });
    const engineId = toEngineId(row.engine);
    const plainSecrets = this.decryptSecrets(row.secrets as Record<string, string>);
    await this.runSync(id, engineId, row.config as Record<string, string>, plainSecrets);
    return this.findOneShaped(id);
  }
```

`runSync` and `findOneShaped` stay unaffected in signature (called after an org-membership check already happened) but must swap their internal `this.prisma.` for `this.prisma.scoped.`:

```ts
  private async runSync(id: string, engineId: ConnectorEngineId, config: Record<string, string>, secrets: Record<string, string>) {
    try {
      const res = await this.ai.client.post("/internal/connectors/sync", { engine: engineId, config, secrets, connectorId: id });
      const data = res.data as { ok: boolean; message: string; datasets: { name: string; columns: string[]; rowCount: number; sampleRows: string[][] }[] };

      if (!data.ok) {
        await this.prisma.scoped.connector.update({
          where: { id },
          data: { status: "ERROR", lastTestOk: false, lastTestMsg: data.message, lastTestAt: new Date() },
        });
        return;
      }

      const connector = await this.prisma.scoped.connector.findUniqueOrThrow({ where: { id } });
      await this.prisma.scoped.$transaction([
        this.prisma.scoped.unifiedDataset.deleteMany({ where: { connectorId: id } }),
        ...data.datasets.map((d) =>
          this.prisma.scoped.unifiedDataset.create({
            data: {
              orgId: connector.orgId,
              connectorId: id,
              name: d.name,
              columns: d.columns,
              rowCount: d.rowCount,
              sampleRows: d.sampleRows,
              status: "synced",
              syncedAt: new Date(),
            },
          }),
        ),
        this.prisma.scoped.connector.update({
          where: { id },
          data: { status: "SYNCED", lastSyncedAt: new Date(), lastTestOk: true, lastTestMsg: data.message, lastTestAt: new Date() },
        }),
      ]);
    } catch (e: any) {
      await this.prisma.scoped.connector.update({
        where: { id },
        data: { status: "ERROR", lastTestOk: false, lastTestMsg: e?.message ?? "Sync failed.", lastTestAt: new Date() },
      });
    }
  }

  private async findOneShaped(id: string) {
    const row = await this.prisma.scoped.connector.findUniqueOrThrow({ where: { id }, include: { _count: { select: { datasets: true } } } });
    return this.shape(row);
  }

  async catalog(orgId: string) {
    const rows = await this.prisma.scoped.unifiedDataset.findMany({
      where: { orgId },
      include: { connector: { select: { name: true, engine: true } } },
      orderBy: { name: "asc" },
    });
    return rows.map((r) => ({
      id: r.id,
      name: r.name,
      connectorId: r.connectorId,
      connectorName: r.connector.name,
      connectorEngine: toEngineId(r.connector.engine),
      columns: r.columns as string[],
      rowCount: r.rowCount,
      status: r.status,
      syncedAt: r.syncedAt,
    }));
  }

  async tablePreview(orgId: string, id: string) {
    const row = await this.prisma.scoped.unifiedDataset.findUnique({ where: { id }, include: { connector: { select: { name: true } } } });
    if (!row || row.orgId !== orgId) throw new NotFoundException("Table not found.");
    return {
      id: row.id,
      name: row.name,
      connectorName: row.connector.name,
      columns: row.columns as string[],
      rowCount: row.rowCount,
      sampleRows: (row.sampleRows as string[][]) ?? [],
      status: row.status,
    };
  }
```

(`testDraft` is unchanged — it never touches Postgres, only the AI service.)

- [ ] **Step 2: Replace `app/api/src/connectors/connectors.controller.ts`**

```ts
import { Body, Controller, Delete, Get, Param, Post, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { CurrentUser } from "../auth/decorators/current-user.decorator";
import { AuthenticatedUser } from "../auth/token.types";
import { ConnectorsService } from "./connectors.service";
import { SaveConnectorDto } from "./dto/save-connector.dto";

@UseGuards(SupabaseAuthGuard, PermissionsGuard)
@Controller("connectors")
export class ConnectorsController {
  constructor(private readonly connectors: ConnectorsService) {}

  @Get()
  list(@CurrentUser() user: AuthenticatedUser) {
    return this.connectors.list(user.orgId);
  }

  @RequirePermissions("manage_connectors")
  @Post("test-draft")
  testDraft(@Body() dto: SaveConnectorDto) {
    return this.connectors.testDraft(dto);
  }

  @RequirePermissions("manage_connectors")
  @Post()
  create(@CurrentUser() user: AuthenticatedUser, @Body() dto: SaveConnectorDto) {
    return this.connectors.create(user.orgId, dto);
  }

  @RequirePermissions("manage_connectors")
  @Post(":id/sync")
  sync(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string) {
    return this.connectors.syncNow(user.orgId, id);
  }

  @RequirePermissions("manage_connectors")
  @Delete(":id")
  remove(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string) {
    return this.connectors.remove(user.orgId, id);
  }
}
```

- [ ] **Step 3: Replace `app/api/src/connectors/catalog.controller.ts`**

```ts
import { Controller, Get, Param, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { CurrentUser } from "../auth/decorators/current-user.decorator";
import { AuthenticatedUser } from "../auth/token.types";
import { ConnectorsService } from "./connectors.service";

@UseGuards(SupabaseAuthGuard)
@Controller("catalog")
export class CatalogController {
  constructor(private readonly connectors: ConnectorsService) {}

  @Get()
  list(@CurrentUser() user: AuthenticatedUser) {
    return this.connectors.catalog(user.orgId);
  }

  @Get(":id")
  preview(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string) {
    return this.connectors.tablePreview(user.orgId, id);
  }
}
```

- [ ] **Step 4: Build to verify**

Run: `npm run build --workspace=api`
Expected: compiles cleanly.

- [ ] **Step 5: Commit**

```bash
git add api/src/connectors
git commit -m "feat: scope ConnectorsService by orgId"
```

---

## Task 13: `DocumentsService` — org scoping

**Files:**
- Modify: `app/api/src/documents/documents.service.ts`
- Modify: `app/api/src/documents/documents.controller.ts`

**Interfaces:**
- Produces: `list`/`preview`/`remove`/`upload` all take `orgId`, use `this.prisma.scoped`.

- [ ] **Step 1: Update `app/api/src/documents/documents.service.ts`** — change every `this.prisma.` to `this.prisma.scoped.` and thread `orgId`:

```ts
  async list(orgId: string) {
    const rows = await this.prisma.scoped.dataSource.findMany({
      where: { orgId },
      include: { uploadedBy: { select: { email: true } } },
      orderBy: { createdAt: "desc" },
    });
    return rows.map((r) => this.shape(r));
  }

  async preview(orgId: string, id: string) {
    const row = await this.prisma.scoped.dataSource.findUnique({ where: { id } });
    if (!row || row.orgId !== orgId) throw new NotFoundException("Data source not found.");
    if (!row.columns || !row.sampleRows) {
      throw new NotFoundException("No table preview available for this file — try re-uploading it.");
    }
    return { id: row.id, title: row.title, filename: row.filename, columns: row.columns as string[], rowCount: row.rowCount, sampleRows: row.sampleRows as string[][] };
  }

  async remove(orgId: string, id: string) {
    const row = await this.prisma.scoped.dataSource.findUnique({ where: { id } });
    if (!row || row.orgId !== orgId) throw new NotFoundException("Data source not found.");
    try {
      await this.ai.client.delete(`/internal/documents/${id}`);
    } catch (e: any) {
      this.logger.warn(`Failed to remove ${id} from the vector index (deleting the record anyway): ${e?.message ?? e}`);
    }
    await this.prisma.scoped.dataSource.delete({ where: { id } });
    return { ok: true };
  }

  async upload(orgId: string, file: Express.Multer.File, uploadedById: string) {
    // ...unchanged validation logic (file type/size checks)...
    const row = await this.prisma.scoped.dataSource.create({
      data: { orgId, title, filename: file.originalname, type: docType, status: docType === "CSV" ? "INDEXING" : "CHUNKING", sizeBytes: file.size, uploadedById },
    });
    // ...unchanged ingestion call...
    // both `this.prisma.dataSource.update(...)` calls further down (success and
    // catch-block paths) become `this.prisma.scoped.dataSource.update(...)`.
  }
```

Read the current file (already shown earlier in this session) and apply this same `.prisma.` → `.prisma.scoped.` swap plus the `orgId`/ownership-check additions to the two `update()` calls inside `upload()`'s try/catch, keeping every other line (logging, error messages, file validation) verbatim.

- [ ] **Step 2: Replace `app/api/src/documents/documents.controller.ts`**

```ts
import { Controller, Delete, Get, Param, Post, UploadedFile, UseGuards, UseInterceptors } from "@nestjs/common";
import { FileInterceptor } from "@nestjs/platform-express";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { CurrentUser } from "../auth/decorators/current-user.decorator";
import { AuthenticatedUser } from "../auth/token.types";
import { DocumentsService } from "./documents.service";

@UseGuards(SupabaseAuthGuard, PermissionsGuard)
@Controller("documents")
export class DocumentsController {
  constructor(private readonly documents: DocumentsService) {}

  @Get()
  list(@CurrentUser() user: AuthenticatedUser) {
    return this.documents.list(user.orgId);
  }

  @Get(":id/preview")
  preview(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string) {
    return this.documents.preview(user.orgId, id);
  }

  @RequirePermissions("upload_docs")
  @Post()
  @UseInterceptors(FileInterceptor("file", { limits: { fileSize: 25 * 1024 * 1024 } }))
  upload(@UploadedFile() file: Express.Multer.File, @CurrentUser() user: AuthenticatedUser) {
    return this.documents.upload(user.orgId, file, user.id);
  }

  @RequirePermissions("upload_docs")
  @Delete(":id")
  remove(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string) {
    return this.documents.remove(user.orgId, id);
  }
}
```

- [ ] **Step 3: Build to verify**

Run: `npm run build --workspace=api`
Expected: compiles cleanly.

- [ ] **Step 4: Commit**

```bash
git add api/src/documents
git commit -m "feat: scope DocumentsService by orgId"
```

---

## Task 14: `ChatService` — org scoping

**Files:**
- Modify: `app/api/src/chat/chat.service.ts`
- Modify: `app/api/src/chat/chat.controller.ts`

**Interfaces:**
- Produces: every method takes `orgId` in addition to `userId`; `Conversation`/`Message`/`Feedback` creates now set `orgId`.

- [ ] **Step 1: Replace `app/api/src/chat/chat.service.ts`**

```ts
import { Injectable, NotFoundException } from "@nestjs/common";
import { Intent } from "@datacon/prisma";
import { PrismaService } from "../prisma/prisma.service";

const INTENT_MAP: Record<string, Intent> = {
  descriptive: "DESCRIPTIVE",
  diagnostic: "DIAGNOSTIC",
  predictive: "PREDICTIVE",
  prescriptive: "PRESCRIPTIVE",
};

@Injectable()
export class ChatService {
  constructor(private readonly prisma: PrismaService) {}

  async getOrCreateConversation(orgId: string, userId: string, conversationId?: string) {
    if (conversationId) {
      const existing = await this.prisma.scoped.conversation.findFirst({ where: { id: conversationId, orgId, userId } });
      if (!existing) throw new NotFoundException("Conversation not found.");
      return existing;
    }
    const latest = await this.prisma.scoped.conversation.findFirst({ where: { orgId, userId }, orderBy: { updatedAt: "desc" } });
    if (latest) return latest;
    return this.prisma.scoped.conversation.create({ data: { orgId, userId, title: "New chat" } });
  }

  async createConversation(orgId: string, userId: string) {
    return this.prisma.scoped.conversation.create({ data: { orgId, userId, title: "New chat" } });
  }

  async listConversations(orgId: string, userId: string, search?: string) {
    const term = search?.trim();
    const where = term
      ? {
          orgId,
          userId,
          messages: { some: {} },
          OR: [
            { title: { contains: term, mode: "insensitive" as const } },
            { messages: { some: { text: { contains: term, mode: "insensitive" as const } } } },
          ],
        }
      : { orgId, userId, messages: { some: {} } };
    const conversations = await this.prisma.scoped.conversation.findMany({
      where,
      orderBy: { updatedAt: "desc" },
      include: { messages: { orderBy: { createdAt: "desc" }, take: 1, select: { text: true } } },
    });
    return conversations.map((c) => ({ id: c.id, title: c.title ?? "New chat", updatedAt: c.updatedAt, preview: c.messages[0]?.text ?? null }));
  }

  async deleteConversation(orgId: string, userId: string, conversationId: string) {
    const existing = await this.prisma.scoped.conversation.findFirst({ where: { id: conversationId, orgId, userId } });
    if (!existing) throw new NotFoundException("Conversation not found.");
    await this.prisma.scoped.conversation.delete({ where: { id: conversationId } });
  }

  async listMessages(orgId: string, userId: string, conversationId?: string) {
    const conversation = await this.getOrCreateConversation(orgId, userId, conversationId);
    const messages = await this.prisma.scoped.message.findMany({
      where: { conversationId: conversation.id },
      orderBy: { createdAt: "asc" },
      include: { feedback: true },
    });
    return {
      conversationId: conversation.id,
      messages: messages.map((m) => ({ id: m.id, role: m.role, intent: m.intent?.toLowerCase() ?? null, text: m.text, payload: m.payload, vote: m.feedback?.vote ?? 0, createdAt: m.createdAt })),
    };
  }

  async appendUserMessage(orgId: string, conversationId: string, text: string) {
    const message = await this.prisma.scoped.message.create({ data: { orgId, conversationId, role: "user", text } });
    const messageCount = await this.prisma.scoped.message.count({ where: { conversationId } });
    await this.prisma.scoped.conversation.update({
      where: { id: conversationId },
      data: { updatedAt: new Date(), ...(messageCount === 1 ? { title: text.slice(0, 60) } : {}) },
    });
    return message;
  }

  async appendAgentMessage(orgId: string, conversationId: string, intent: string, text: string, payload: unknown) {
    const message = await this.prisma.scoped.message.create({
      data: { orgId, conversationId, role: "agent", intent: INTENT_MAP[intent], text, payload: payload as any },
    });
    await this.prisma.scoped.conversation.update({ where: { id: conversationId }, data: { updatedAt: new Date() } });
    return message;
  }

  async setFeedback(orgId: string, messageId: string, userId: string, vote: -1 | 0 | 1) {
    const message = await this.prisma.scoped.message.findUnique({ where: { id: messageId } });
    if (!message || message.orgId !== orgId) throw new NotFoundException("Message not found.");
    if (vote === 0) {
      await this.prisma.scoped.feedback.deleteMany({ where: { messageId } });
      return { vote: 0 };
    }
    await this.prisma.scoped.feedback.upsert({
      where: { messageId },
      update: { vote, userId },
      create: { orgId, messageId, userId, vote },
    });
    return { vote };
  }
}
```

- [ ] **Step 2: Update `app/api/src/chat/chat.controller.ts`** — every handler already receives `@CurrentUser() user: AuthenticatedUser`; thread `user.orgId` as the new first argument into each `this.chat.*` call:

```ts
  @Get("conversations")
  async conversations(@Query("search") search: string | undefined, @CurrentUser() user: AuthenticatedUser) {
    return this.chat.listConversations(user.orgId, user.id, search);
  }

  @Post("conversations")
  async createConversation(@CurrentUser() user: AuthenticatedUser) {
    return this.chat.createConversation(user.orgId, user.id);
  }

  @Delete("conversations/:id")
  async deleteConversation(@Param("id") id: string, @CurrentUser() user: AuthenticatedUser) {
    await this.chat.deleteConversation(user.orgId, user.id, id);
    return { ok: true };
  }

  @Get("messages")
  async messages(@Query("conversationId") conversationId: string | undefined, @CurrentUser() user: AuthenticatedUser) {
    return this.chat.listMessages(user.orgId, user.id, conversationId);
  }
```

Inside `stream()`, update the two calls that create/append conversation data:

```ts
    const conversation = await this.chat.getOrCreateConversation(user.orgId, user.id, dto.conversationId);
    this.logger.log(`[Chat] Using Conversation ID: ${conversation.id}. Appending user message: "${dto.message}"`);
    await this.chat.appendUserMessage(user.orgId, conversation.id, dto.message);
```

and, in the `upstream.data.on("end", ...)` handler:

```ts
      for (const result of results) {
        if (result.text) {
          this.logger.log(`[Chat] [Conversation ${conversation.id}] Saving response for agent '${result.intent}' to Postgres...`);
          await this.chat.appendAgentMessage(user.orgId, conversation.id, result.intent, result.text, result.payload);
        }
      }
```

Finally, the feedback handler:

```ts
  @Patch("messages/:id/feedback")
  async feedback(@Param("id") id: string, @Body() dto: FeedbackDto, @CurrentUser() user: AuthenticatedUser) {
    return this.chat.setFeedback(user.orgId, id, user.id, dto.vote);
  }
```

- [ ] **Step 3: Build to verify**

Run: `npm run build --workspace=api`
Expected: compiles cleanly.

- [ ] **Step 4: Commit**

```bash
git add api/src/chat
git commit -m "feat: scope ChatService by orgId"
```

---

## Task 15: `MetricsService` — org scoping for `ticketTableRowCount`

**Files:**
- Modify: `app/api/src/metrics/metrics.service.ts`
- Modify: `app/api/src/insights/insights.service.ts`
- Modify: `app/api/src/forecasts/forecasts.controller.ts`

**Interfaces:**
- Produces: `MetricsService.ticketTableRowCount(orgId)` — the only method here touching org-scoped Postgres data (`UnifiedDataset`). Everything else in `MetricsService`/`InsightsService`/`ForecastsController` queries the external AI service (which queries the *sample* connector databases, not this app's own multi-tenant Postgres), so it needs no `orgId` threading.

- [ ] **Step 1: Update `app/api/src/metrics/metrics.service.ts`**

```ts
  async ticketTableRowCount(orgId: string): Promise<number> {
    const row = await this.prisma.scoped.unifiedDataset.findFirst({ where: { orgId, name: "tickets" } });
    return row?.rowCount ?? 0;
  }
```
(only this method changes; every other method in the file is unaffected since they call the AI service, not Postgres.)

- [ ] **Step 2: Update `app/api/src/insights/insights.service.ts`**

Change `InsightsService.get()`'s signature and its one call site:

```ts
  async get(orgId: string) {
    const [revenueHistory, regionRevenue, ticketDaily, churnSnapshot, ticketTableRowCount] = await Promise.all([
      this.metrics.revenueHistory(),
      this.metrics.regionRevenue(),
      this.metrics.ticketDaily(),
      this.metrics.churnSnapshot(),
      this.metrics.ticketTableRowCount(orgId),
    ]);
    // ...rest of the method body is unchanged...
```

Replace `app/api/src/insights/insights.controller.ts`:

```ts
import { Controller, Get, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { CurrentUser } from "../auth/decorators/current-user.decorator";
import { AuthenticatedUser } from "../auth/token.types";
import { InsightsService } from "./insights.service";

@UseGuards(SupabaseAuthGuard, PermissionsGuard)
@Controller("insights")
export class InsightsController {
  constructor(private readonly insights: InsightsService) {}

  @RequirePermissions("view_dashboards")
  @Get()
  get(@CurrentUser() user: AuthenticatedUser) {
    return this.insights.get(user.orgId);
  }
}
```

- [ ] **Step 3: Update `app/api/src/forecasts/forecasts.controller.ts`**

This controller doesn't call `ticketTableRowCount` — no change needed here after all; skip this file. (Verified by reading it in this session: `ForecastsController.get()` only calls `this.metrics.revenueHistory()`/`this.metrics.regionRevenue()`, both AI-service-backed, no org-scoped Postgres read.)

- [ ] **Step 4: Build to verify**

Run: `npm run build --workspace=api`
Expected: compiles cleanly.

- [ ] **Step 5: Commit**

```bash
git add api/src/metrics/metrics.service.ts api/src/insights
git commit -m "feat: scope MetricsService.ticketTableRowCount by orgId"
```

---

## Task 16: Seed — Acme Corp org + Platform Admin

**Files:**
- Modify: `app/packages/prisma/seed.ts`

**Interfaces:**
- Produces: an `Organization` upsert for `'acme-corp'` (matching the migration's backfilled id from Task 2), a `PlatformAdmin` row + matching Supabase Auth user.

- [ ] **Step 1: Add an `Organization` upsert near the top of `main()`, and scope the existing seed data**

In `app/packages/prisma/seed.ts`, right after `dotenv.config(...)`, add the org id constant:

```ts
const ORG_ID = "acme-corp";
```

At the very start of `main()` (before "Seeding permissions..."), add:

```ts
  console.log("Seeding organization...");
  await prisma.organization.upsert({
    where: { id: ORG_ID },
    update: { name: "Acme Corp" },
    create: { id: ORG_ID, name: "Acme Corp" },
  });
```

Add `orgId: ORG_ID` to every `prisma.role.upsert(...)`'s `create`/`update` data, every `prisma.user.upsert(...)`'s `create` data, every `prisma.connector.upsert(...)`'s `create`/`update` data (via `...c` spreads — add `orgId: ORG_ID` alongside `secrets: {}`), every `prisma.unifiedDataset.create/update(...)`'s data (via `...t` spreads — add `orgId: ORG_ID`), and every `prisma.dataSource.upsert(...)`'s data (the `data` object built from `...rest, uploadedById: personaIds[uploadedById]` — add `orgId: ORG_ID` there too).

- [ ] **Step 2: Seed the Platform Admin**

After the "Seeding users..." block (which creates the 4 Acme Corp personas), add:

```ts
  console.log("Seeding platform admin...");
  const { data: existingPlatformAdmins } = await supabaseAdmin.auth.admin.listUsers();
  let platformAdminAuthUser = existingPlatformAdmins?.users.find((au) => au.email === "platform-admin@datacon.internal");
  if (!platformAdminAuthUser) {
    const { data, error } = await supabaseAdmin.auth.admin.createUser({
      email: "platform-admin@datacon.internal",
      password: SEED_PASSWORD,
      email_confirm: true,
    });
    if (error || !data.user) throw new Error(`Could not create platform admin auth user: ${error?.message}`);
    platformAdminAuthUser = data.user;
  }
  await prisma.platformAdmin.upsert({
    where: { id: platformAdminAuthUser.id },
    update: {},
    create: { id: platformAdminAuthUser.id, email: "platform-admin@datacon.internal" },
  });
```

- [ ] **Step 3: Run the seed against Supabase**

Run: `npm run prisma:seed` (from `app/`)
Expected: `Done. Seed login password for all personas: Datacon123!` with no errors.

- [ ] **Step 4: Verify via Supabase MCP**

Run: `mcp__supabase-2__execute_sql(project_id="yicblouwgguhmfvwqdhm", query="select id, name from public.organizations")`
Expected: one row, `('acme-corp', 'Acme Corp')`.

Run: `mcp__supabase-2__execute_sql(project_id="yicblouwgguhmfvwqdhm", query="select id, email from public.platform_admins")`
Expected: one row for `platform-admin@datacon.internal`.

- [ ] **Step 5: Commit**

```bash
git add packages/prisma/seed.ts
git commit -m "feat: seed Acme Corp organization and platform admin account"
```

---

## Task 17: Web — remove quick-login, add Workspace name to registration

**Files:**
- Modify: `app/web/src/routes/auth/AuthPage.tsx`
- Modify: `app/web/src/stores/useAuthStore.ts`
- Modify: `app/web/src/api/auth.ts`
- Modify: `app/web/src/lib/types.ts`

**Interfaces:**
- Produces: `useAuth().register(name, email, password, orgName)` now also calls the new `completeRegistration` endpoint; `usePersonas`/`quickLogin`/`Persona` type are removed; `CurrentUser` gains a `kind` discriminator.

- [ ] **Step 1: Update `app/web/src/lib/types.ts`** — remove the `Persona` interface entirely, and change `CurrentUser`:

```ts
export type CurrentUser =
  | { kind: "platform_admin"; id: string; email: string }
  | {
      kind: "org_member";
      id: string;
      orgId: string;
      name: string;
      email: string;
      initials: string;
      avatarGrad: string;
      title: string | null;
      roleId: string;
      roleName: string;
      permissions: PermissionKey[];
    };
```

- [ ] **Step 2: Replace `app/web/src/api/auth.ts`** (remove `usePersonas`, add `completeRegistration`):

```ts
import { useMutation } from "@tanstack/react-query";
import { api } from "./client";

export function useCompleteRegistration() {
  return useMutation({
    mutationFn: async (dto: { name: string; orgName: string }) => (await api.post("/auth/complete-registration", dto)).data,
  });
}
```

- [ ] **Step 3: Replace `app/web/src/stores/useAuthStore.ts`** — remove `quickLogin`, add `completeRegistration` to `register()`, adjust `fetchUser()` for the `kind` discriminator:

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
  register: (name: string, email: string, password: string, orgName: string) => Promise<void>;
  logout: () => Promise<void>;
}

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
        caps: res.data.kind === "org_member" ? capsFromPermissions(res.data.permissions) : EMPTY_CAPS,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch {
      set({ user: undefined, caps: EMPTY_CAPS, isAuthenticated: false, isLoading: false });
    }
  },
  login: async (email, password) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    await get().fetchUser();
  },
  register: async (name, email, password, orgName) => {
    const { error } = await supabase.auth.signUp({ email, password, options: { data: { name } } });
    if (error) throw error;
    await api.post("/auth/complete-registration", { name, orgName });
    await get().fetchUser();
  },
  logout: async () => {
    await supabase.auth.signOut();
    set({ user: undefined, caps: EMPTY_CAPS, isAuthenticated: false });
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
  const logout = useAuthStore((state) => state.logout);

  return { user, caps, isLoading, isAuthenticated, login, register, logout };
}
```

(`quickLogin` and the `supabase.auth.admin`-adjacent `SEED_PASSWORD` constant are removed — quick-login no longer exists per the Global Constraints.)

- [ ] **Step 4: Update `app/web/src/routes/auth/AuthPage.tsx`** — add a "Workspace name" field to register mode, remove the persona roster section:

Add state: `const [orgName, setOrgName] = useState("");` alongside the existing `name`/`email`/`password` state.

In the `submit` handler, change the register branch:
```tsx
      if (mode === "login") await login(email, password);
      else await register(name, email, password, orgName);
```

Add a field right after the "Full name" field (inside the `mode === "register"` block):
```tsx
            {mode === "register" && (
              <Field label="Workspace name">
                <input value={orgName} onChange={(e) => setOrgName(e.target.value)} placeholder="Acme Corp" style={inputStyle} />
              </Field>
            )}
```

Remove: the `usePersonas` import and call, the entire "OR JUMP IN AS" divider block and the `personas?.map(...)` button list, and the `quickLogin` destructure from `useAuth()`.

- [ ] **Step 5: Build to verify**

Run: `npm run build --workspace=web` (from `app/`)
Expected: compiles cleanly.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/types.ts web/src/api/auth.ts web/src/stores/useAuthStore.ts web/src/routes/auth/AuthPage.tsx
git commit -m "feat: add Workspace name to registration, remove public quick-login roster"
```

---

## Task 18: Web — Platform Admin routes

**Files:**
- Create: `app/web/src/api/platformAdmin.ts`
- Create: `app/web/src/routes/platform-admin/OrganizationsPage.tsx`
- Create: `app/web/src/routes/platform-admin/OrgUsersPage.tsx`
- Modify: `app/web/src/App.tsx`

**Interfaces:**
- Produces: `/platform-admin` (list + create orgs) and `/platform-admin/organizations/:orgId/users` (list that org's users), gated on `user.kind === "platform_admin"`.

- [ ] **Step 1: Create `app/web/src/api/platformAdmin.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

interface Organization {
  id: string;
  name: string;
  createdAt: string;
}

interface OrgUser {
  id: string;
  name: string;
  email: string;
  roleId: string;
  role: { name: string };
}

export function useOrganizations() {
  return useQuery({
    queryKey: ["platform-admin", "organizations"],
    queryFn: async () => (await api.get<Organization[]>("/platform-admin/organizations")).data,
  });
}

export function useCreateOrganization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (dto: { name: string; adminEmail: string; adminName: string }) =>
      (await api.post<Organization>("/platform-admin/organizations", dto)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["platform-admin", "organizations"] }),
  });
}

export function useOrgUsers(orgId: string | undefined) {
  return useQuery({
    queryKey: ["platform-admin", "organizations", orgId, "users"],
    queryFn: async () => (await api.get<OrgUser[]>(`/platform-admin/organizations/${orgId}/users`)).data,
    enabled: !!orgId,
  });
}
```

- [ ] **Step 2: Create `app/web/src/routes/platform-admin/OrganizationsPage.tsx`**

```tsx
import { useState } from "react";
import { Link } from "react-router-dom";
import { useCreateOrganization, useOrganizations } from "../../api/platformAdmin";
import { PageHeader } from "../settings/UsersPage";
import { Button } from "../../components/ui/Button";
import { Modal, ModalHeader } from "../../components/ui/Modal";
import { FieldRow, inputStyle } from "../settings/UsersPage";
import { useToast } from "../../stores/useToastStore";
import { apiErrorMessage } from "../../api/client";

export function OrganizationsPage() {
  const { data: orgs, isLoading } = useOrganizations();
  const createOrg = useCreateOrganization();
  const { addToast } = useToast();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [adminName, setAdminName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");

  const submit = async () => {
    try {
      await createOrg.mutateAsync({ name, adminName, adminEmail });
      addToast({ icon: "✅", accent: "#0f8a5c", title: "Workspace created", desc: `${name} is ready — invite sent to ${adminEmail}` });
      setCreating(false);
      setName("");
      setAdminName("");
      setAdminEmail("");
    } catch (err) {
      addToast({ icon: "⚠️", accent: "#e2603f", title: "Couldn't create workspace", desc: apiErrorMessage(err) });
    }
  };

  return (
    <div style={{ padding: 32, maxWidth: 1080, margin: "0 auto" }}>
      <PageHeader title="Workspaces" sub="Create and manage every organization on the platform" action={<Button variant="primary" onClick={() => setCreating(true)}>+ Create workspace</Button>} />
      <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #e9eaf2", overflow: "hidden" }}>
        {isLoading && <div style={{ padding: 20, color: "#9499ad" }}>Loading…</div>}
        {orgs?.map((o) => (
          <Link key={o.id} to={`/platform-admin/organizations/${o.id}/users`} style={{ display: "flex", justifyContent: "space-between", padding: "14px 18px", borderBottom: "1px solid #f5f6fb" }}>
            <span style={{ fontWeight: 700, fontSize: 13.5 }}>{o.name}</span>
            <span style={{ color: "var(--ac)", fontWeight: 700, fontSize: 12.5 }}>Manage users →</span>
          </Link>
        ))}
      </div>

      <Modal open={creating} onClose={() => setCreating(false)}>
        <ModalHeader title="Create workspace" onClose={() => setCreating(false)} />
        <FieldRow label="WORKSPACE NAME">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Globex Inc" style={inputStyle} />
        </FieldRow>
        <FieldRow label="FIRST ADMIN — FULL NAME">
          <input value={adminName} onChange={(e) => setAdminName(e.target.value)} placeholder="Jordan Lee" style={inputStyle} />
        </FieldRow>
        <FieldRow label="FIRST ADMIN — EMAIL">
          <input value={adminEmail} onChange={(e) => setAdminEmail(e.target.value)} placeholder="jordan@globex.com" style={inputStyle} />
        </FieldRow>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 18 }}>
          <Button variant="secondary" onClick={() => setCreating(false)}>Cancel</Button>
          <Button variant="primary" disabled={!name.trim() || !adminName.trim() || !adminEmail.trim()} onClick={submit}>Create</Button>
        </div>
      </Modal>
    </div>
  );
}
```

(This reuses `PageHeader`/`FieldRow`/`inputStyle` already exported from `UsersPage.tsx` — no new shared component needed.)

- [ ] **Step 3: Create `app/web/src/routes/platform-admin/OrgUsersPage.tsx`**

```tsx
import { useParams } from "react-router-dom";
import { useOrgUsers } from "../../api/platformAdmin";
import { PageHeader } from "../settings/UsersPage";
import { RoleBadge } from "../../components/ui/RoleBadge";

export function OrgUsersPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { data: users, isLoading } = useOrgUsers(orgId);

  return (
    <div style={{ padding: 32, maxWidth: 1080, margin: "0 auto" }}>
      <PageHeader title="Workspace users" sub="Users in this organization" />
      <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #e9eaf2", overflow: "hidden" }}>
        {isLoading && <div style={{ padding: 20, color: "#9499ad" }}>Loading…</div>}
        {users?.map((u) => (
          <div key={u.id} style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr", padding: "12px 18px", borderBottom: "1px solid #f5f6fb", alignItems: "center" }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700 }}>{u.name}</div>
              <div style={{ fontSize: 11.5, color: "#9499ad" }}>{u.email}</div>
            </div>
            <RoleBadge name={u.role.name} color={null} bg={null} />
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Update `app/web/src/App.tsx`** — add the Platform Admin route tree and route post-login by `user.kind`:

```tsx
import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { useAuth } from "./stores/useAuthStore";
import { AppShell } from "./components/shell/AppShell";
import { RequireAdmin } from "./components/shell/RequireAdmin";
import { AuthPage } from "./routes/auth/AuthPage";
import { UsersPage } from "./routes/settings/UsersPage";
import { RolesPage } from "./routes/settings/RolesPage";
import { AssignRolesPage } from "./routes/settings/AssignRolesPage";
import { PermissionsPage } from "./routes/settings/PermissionsPage";
import { ConnectorsPage } from "./routes/connectors/ConnectorsPage";
import { DataSourcesPage } from "./routes/data-sources/DataSourcesPage";
import { ChatPage } from "./routes/chat/ChatPage";
import { ChatHistoryPage } from "./routes/chat/ChatHistoryPage";
import { InsightsPage } from "./routes/insights/InsightsPage";
import { ThemesPage } from "./routes/themes/ThemesPage";
import { OrganizationsPage } from "./routes/platform-admin/OrganizationsPage";
import { OrgUsersPage } from "./routes/platform-admin/OrgUsersPage";
import { queryClient } from "./lib/queryClient";
import { useAuthStore } from "./stores/useAuthStore";
import { useThemeStore } from "./stores/useThemeStore";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return null;
  if (!isAuthenticated) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function RequirePlatformAdmin({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  if (isLoading) return null;
  if (user?.kind !== "platform_admin") return <Navigate to="/" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<AuthPage />} />
      <Route
        path="/platform-admin"
        element={
          <RequirePlatformAdmin>
            <OrganizationsPage />
          </RequirePlatformAdmin>
        }
      />
      <Route
        path="/platform-admin/organizations/:orgId/users"
        element={
          <RequirePlatformAdmin>
            <OrgUsersPage />
          </RequirePlatformAdmin>
        }
      />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/chat/history" element={<ChatHistoryPage />} />
        <Route path="/insights" element={<InsightsPage />} />
        <Route path="/connectors" element={<ConnectorsPage />} />
        <Route path="/data-sources" element={<DataSourcesPage />} />
        <Route path="/themes" element={<ThemesPage />} />
        <Route path="/settings/users" element={<RequireAdmin><UsersPage /></RequireAdmin>} />
        <Route path="/settings/roles" element={<RequireAdmin><RolesPage /></RequireAdmin>} />
        <Route path="/settings/assign" element={<RequireAdmin><AssignRolesPage /></RequireAdmin>} />
        <Route path="/settings/permissions" element={<RequireAdmin><PermissionsPage /></RequireAdmin>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  useEffect(() => {
    useAuthStore.getState().fetchUser();
    useThemeStore.getState().initialize();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

Also update `AuthPage.tsx`'s post-login redirect (`useEffect(() => { if (isAuthenticated) navigate("/chat", ...) }, ...)`) to branch on `user?.kind`:

```tsx
  const { login, register, isAuthenticated, user } = useAuth();
  // ...
  useEffect(() => {
    if (isAuthenticated) navigate(user?.kind === "platform_admin" ? "/platform-admin" : "/chat", { replace: true });
  }, [isAuthenticated, user, navigate]);
```

- [ ] **Step 5: Build to verify**

Run: `npm run build --workspace=web` (from `app/`)
Expected: compiles cleanly.

- [ ] **Step 6: Commit**

```bash
git add web/src/api/platformAdmin.ts web/src/routes/platform-admin web/src/App.tsx web/src/routes/auth/AuthPage.tsx
git commit -m "feat: add Platform Admin console (list/create workspaces, view org users)"
```

---

## Task 19: End-to-end verification (manual, via the `run` skill)

1. `npm run dev` (from `app/`) — boots api/ai/web together.
2. Register a brand-new user (any email, e.g. a personal gmail address) with a chosen Workspace name → confirm via `mcp__supabase-2__execute_sql` that a new `organizations` row and a matching `users` row (roleId = that org's Admin role) now exist.
3. Register a second brand-new user with a *different* Workspace name → confirm (`select orgId from public.users where email = '...'`) it landed in a **different** `orgId` than the first — two self-registrations never collide, regardless of email domain.
4. As the first workspace's Admin, invite a third user via the Users admin page → confirm the new user's `orgId` matches the inviting Admin's `orgId`, not the other workspace's.
5. Cross-workspace isolation: as workspace A's Admin, hit `GET /connectors`/`GET /data-sources`/`GET /chat/conversations` → confirm zero rows from workspace B ever appear, and vice versa.
6. Sign in as `platform-admin@datacon.internal` (`Datacon123!`) → confirm redirect to `/platform-admin`, the Organizations list shows every workspace created above, and `/platform-admin/organizations/:orgId/users` shows the correct roster per workspace.
7. As the Platform Admin, attempt a direct query (`mcp__supabase-2__execute_sql`, simulating what an `app_user`-authenticated raw query would see) against `data_sources`/`connectors`/`conversations` while `SET LOCAL app.is_platform_admin = 'true'` is active and `app.current_org_id` is unset → expect **zero rows**, confirming the RLS bypass truly doesn't extend to business data.
8. Cross-org role-id guessing: as workspace A's Admin, attempt `PATCH /users/:id/assign-role` with a `roleId` copied from workspace B → expect a 400 `"Unknown role."` rejection.
9. Confirm the quick-login roster is gone from `/auth` (no "OR JUMP IN AS" section), and `GET /auth/personas` no longer exists (404).
10. Log out from an org member session → confirm redirect to `/auth` and `GET /auth/me` 401s without a session, matching prior behavior.
