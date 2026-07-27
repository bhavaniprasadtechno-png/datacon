# Platform Admin: Suspend/Activate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a platform admin suspend/activate an entire workspace (on `OrganizationsPage`) or an individual user within a workspace (on `OrgUsersPage`), with real login-blocking enforcement — not just a UI flag.

**Architecture:** One shared `AccountStatus` enum (`ACTIVE` | `SUSPENDED`) added to both `Organization` and `User` via one additive migration. Two new `PATCH` endpoints on the existing `PlatformAdminController`. Enforcement lives in the two places that already load a user's full row on every request/login — `SupabaseAuthGuard` and `AuthService.me()` — both gain the same one-line check (`user.status === "SUSPENDED" || user.org.status === "SUSPENDED"` → 403), no new guard or module. Frontend gains a small shared `StatusBadge`, two new mutation hooks, and inline suspend/activate buttons on the two existing pages, reusing the app's existing `useConfirm()` dialog and `Button`/toast patterns — no new component library.

**Tech Stack:** NestJS + Prisma (`api/`), React + `@tanstack/react-query` + inline-style CSS-variable system (`web/`). No Tailwind/shadcn here — this is `OrganizationsPage`/`OrgUsersPage`, which stayed on the existing visual system per [[2026-07-24-platform-admin-dashboard-design]] (the Tailwind/shadcn shell only covers `PlatformAdminShell`/`PlatformOverviewPage`/`ComingSoonPage`).

## Global Constraints

- Suspending a workspace or a user must reject their next API call — not just show a badge. See spec's "Auth enforcement" section.
- `Organization.status` and `User.status` are independent fields — suspending a workspace does NOT write to every `User` row in it. Effective enforcement is `user.status === SUSPENDED || user.org.status === SUSPENDED`, computed at request time.
- No audit log, no email/notification, no bulk suspend, no real-time session kill for an already-open tab (a suspended user's current tab keeps working until its next API call reaches `SupabaseAuthGuard`) — all explicitly out of scope per the spec.
- Platform admin accounts (`PlatformAdmin` model/`PlatformAdminGuard`) are untouched — no status concept added there.
- Reference spec: `docs/superpowers/specs/2026-07-27-platform-admin-suspend-activate-design.md`.

---

### Task 1: Prisma schema — `AccountStatus` enum + `status` on `Organization`/`User`

**Files:**
- Modify: `packages/prisma/schema.prisma`
- Modify: `packages/prisma/index.ts`
- Create: `packages/prisma/migrations/20260727000000_account_status/migration.sql`

**Interfaces:**
- Produces: `AccountStatus` — a Prisma enum (`ACTIVE` | `SUSPENDED`) in `schema.prisma`, and a mirrored runtime const + type `AccountStatus` exported from `@datacon/prisma` (same pattern as the existing `DocStatus`/`ConnectorStatus` exports in that file). `Organization.status` and `User.status` both default to `ACTIVE`.
- Consumed by: Task 2 (backend service/DTO import `AccountStatus` from `@datacon/prisma`), Task 3 (guard/service check `=== "SUSPENDED"`), Task 4 (frontend types use the literal union `"ACTIVE" | "SUSPENDED"`).

- [ ] **Step 1: Add the enum and the two fields to `schema.prisma`**

Replace the `Organization` model:

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
```

with:

```prisma
enum AccountStatus {
  ACTIVE
  SUSPENDED
}

model Organization {
  id        String        @id @default(cuid())
  name      String
  status    AccountStatus @default(ACTIVE)
  createdAt DateTime      @default(now())
  updatedAt DateTime      @updatedAt

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
```

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

with:

```prisma
model User {
  id         String        @id @db.Uuid
  orgId      String
  org        Organization  @relation(fields: [orgId], references: [id])
  email      String        @unique
  name       String
  initials   String
  avatarGrad String        @default("var(--ac-grad)")
  title      String? // e.g. "Senior Analyst", "VP Sales & Ops"
  roleId     String
  role       Role          @relation(fields: [roleId], references: [id])
  isCore     Boolean       @default(false) // seed personas: cannot be deleted
  status     AccountStatus @default(ACTIVE)
  createdAt  DateTime      @default(now())
  updatedAt  DateTime      @updatedAt

  conversations Conversation[]
  documents     DataSource[]
  feedback      Feedback[]

  @@map("users")
}
```

- [ ] **Step 2: Write the migration SQL**

Create `packages/prisma/migrations/20260727000000_account_status/migration.sql`:

```sql
CREATE TYPE "AccountStatus" AS ENUM ('ACTIVE', 'SUSPENDED');

ALTER TABLE "organizations" ADD COLUMN "status" "AccountStatus" NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE "users" ADD COLUMN "status" "AccountStatus" NOT NULL DEFAULT 'ACTIVE';
```

- [ ] **Step 3: Mirror the enum in `packages/prisma/index.ts`**

At the end of `packages/prisma/index.ts`, following the exact pattern the file already uses for `DocStatus`/`ConnectorStatus`, add:

```ts
export const AccountStatus = {
  ACTIVE: "ACTIVE",
  SUSPENDED: "SUSPENDED",
} as const;

export type AccountStatus = (typeof AccountStatus)[keyof typeof AccountStatus];
```

- [ ] **Step 4: Apply the migration and rebuild the package**

Apply `migrations/20260727000000_account_status/migration.sql` to the project's Supabase database using whichever mechanism is connected in this session — the same choice the prior `20260724000000_multi_tenant_workspaces` migration used (see `docs/superpowers/plans/2026-07-24-multi-tenant-workspaces.md`, Task 2 Steps 3–5): a Supabase MCP `apply_migration` tool if one is authenticated for this project, otherwise:

```bash
cd packages/prisma
npx prisma db execute --file migrations/20260727000000_account_status/migration.sql --schema schema.prisma
npx prisma migrate resolve --applied 20260727000000_account_status
npx prisma generate
npm run build
```

(`prisma generate` regenerates the `@prisma/client` types the schema change needs; `npm run build` recompiles `packages/prisma/index.ts`'s new `AccountStatus` export into `dist/`, which `api/` imports as `@datacon/prisma`.)

- [ ] **Step 5: Verify**

Run: `cd api && npx tsc --noEmit`
Expected: clean (nothing references `AccountStatus` yet — this just confirms the schema/package change didn't break anything downstream).

- [ ] **Step 6: Commit**

```bash
git add packages/prisma/schema.prisma packages/prisma/index.ts packages/prisma/migrations/20260727000000_account_status
git commit -m "feat: add AccountStatus enum to Organization and User"
```

---

### Task 2: Backend — status endpoints on `PlatformAdminController`

**Files:**
- Create: `api/src/platform-admin/dto/update-status.dto.ts`
- Modify: `api/src/platform-admin/platform-admin.service.ts`
- Modify: `api/src/platform-admin/platform-admin.controller.ts`

**Interfaces:**
- Consumes: `AccountStatus` from `@datacon/prisma` (Task 1).
- Produces: `PlatformAdminService.setOrganizationStatus(orgId: string, status: AccountStatus)`, `PlatformAdminService.setUserStatus(userId: string, status: AccountStatus)`. `PATCH /platform-admin/organizations/:orgId/status` and `PATCH /platform-admin/organizations/:orgId/users/:userId/status`, both body `{ status: "ACTIVE" | "SUSPENDED" }`.
- Consumed by: Task 4 (frontend hooks call these two routes).

- [ ] **Step 1: Add the DTO**

Create `api/src/platform-admin/dto/update-status.dto.ts`:

```ts
import { IsEnum } from "class-validator";
import { AccountStatus } from "@datacon/prisma";

export class UpdateStatusDto {
  @IsEnum(AccountStatus)
  status!: AccountStatus;
}
```

- [ ] **Step 2: Add the two service methods and expose `status` on `listUsers`**

In `api/src/platform-admin/platform-admin.service.ts`, add the import at the top:

```ts
import { AccountStatus } from "@datacon/prisma";
```

`listOrganizations()` needs no change — it uses `include` (not `select`), so Prisma already returns every scalar column, including the new `status`, automatically.

Replace `listUsers`:

```ts
  async listUsers(orgId: string) {
    return this.prisma.scoped.user.findMany({
      where: { orgId },
      select: {
        id: true,
        name: true,
        email: true,
        roleId: true,
        initials: true,
        avatarGrad: true,
        role: { select: { name: true } },
      },
      orderBy: { createdAt: "asc" },
    });
  }
```

with:

```ts
  async listUsers(orgId: string) {
    return this.prisma.scoped.user.findMany({
      where: { orgId },
      select: {
        id: true,
        name: true,
        email: true,
        roleId: true,
        initials: true,
        avatarGrad: true,
        status: true,
        role: { select: { name: true } },
      },
      orderBy: { createdAt: "asc" },
    });
  }
```

Then add two new methods at the end of the class, right after `listUsers`:

```ts

  async setOrganizationStatus(orgId: string, status: AccountStatus) {
    return this.prisma.scoped.organization.update({ where: { id: orgId }, data: { status } });
  }

  async setUserStatus(userId: string, status: AccountStatus) {
    return this.prisma.scoped.user.update({ where: { id: userId }, data: { status } });
  }
```

- [ ] **Step 3: Add the two routes**

In `api/src/platform-admin/platform-admin.controller.ts`, replace:

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

with:

```ts
import { Body, Controller, Get, Param, Patch, Post, UseGuards } from "@nestjs/common";
import { PlatformAdminGuard } from "../auth/guards/platform-admin.guard";
import { PlatformAdminService } from "./platform-admin.service";
import { CreateOrganizationDto } from "./dto/create-organization.dto";
import { UpdateStatusDto } from "./dto/update-status.dto";

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

  @Patch(":orgId/status")
  setOrganizationStatus(@Param("orgId") orgId: string, @Body() dto: UpdateStatusDto) {
    return this.platformAdmin.setOrganizationStatus(orgId, dto.status);
  }

  @Get(":orgId/users")
  listUsers(@Param("orgId") orgId: string) {
    return this.platformAdmin.listUsers(orgId);
  }

  @Patch(":orgId/users/:userId/status")
  setUserStatus(@Param("userId") userId: string, @Body() dto: UpdateStatusDto) {
    return this.platformAdmin.setUserStatus(userId, dto.status);
  }
}
```

- [ ] **Step 4: Typecheck**

Run: `cd api && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 5: Verify with a manual API check (no unit test — see rationale)**

These are additive `select`/DTO-validated pass-through changes with no branching logic — same rationale as the original dashboard-redesign plan's Task 1 (`docs/superpowers/plans/2026-07-24-platform-admin-dashboard.md`). Verify directly instead:

Run: `cd api && npm run start:dev`

As a platform admin:
```
PATCH /platform-admin/organizations/:orgId/status    body: { "status": "SUSPENDED" }
PATCH /platform-admin/organizations/:orgId/users/:userId/status    body: { "status": "SUSPENDED" }
GET /platform-admin/organizations/:orgId/users
```
Expected: both PATCH calls return the updated row with `"status": "SUSPENDED"`; the GET response's items include a `status` field.

- [ ] **Step 6: Commit**

```bash
git add api/src/platform-admin/dto/update-status.dto.ts api/src/platform-admin/platform-admin.service.ts api/src/platform-admin/platform-admin.controller.ts
git commit -m "feat: add suspend/activate endpoints for workspaces and users"
```

---

### Task 3: Auth enforcement — `SupabaseAuthGuard` + `AuthService.me()`

**Files:**
- Modify: `api/src/auth/guards/supabase-auth.guard.ts`
- Modify: `api/src/auth/guards/supabase-auth.guard.spec.ts`
- Modify: `api/src/auth/auth.service.ts`
- Modify: `api/src/auth/auth.service.spec.ts`

**Interfaces:**
- Consumes: `AccountStatus` values (Task 1) on the `user`/`user.org` rows both call sites already load.
- Produces: `SupabaseAuthGuard.canActivate` and `AuthService.me()` both now throw `ForbiddenException("This account has been suspended.")` for a suspended user or a user in a suspended org, instead of proceeding.

This is the one piece of real branching logic in this plan — write the tests first.

- [ ] **Step 1: Write the failing guard tests**

In `api/src/auth/guards/supabase-auth.guard.spec.ts`, add `ForbiddenException` to the import on line 1:

```ts
import { ForbiddenException, UnauthorizedException } from "@nestjs/common";
```

Update the existing green-path test's mock user (in the `"attaches req.user..."` test) to include the new fields, so it stays realistic:

Replace:

```ts
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
```

with:

```ts
    const prisma = {
      user: {
        findUnique: jest.fn().mockResolvedValue({
          id: "11111111-1111-1111-1111-111111111111",
          orgId: "acme-corp",
          roleId: "admin",
          status: "ACTIVE",
          org: { status: "ACTIVE" },
          role: { permissions: [{ permissionKey: "manage_users" }] },
        }),
      },
    } as unknown as PrismaService;
```

Then add two new tests at the end of the `describe` block, right before the final closing `});`:

```ts

  it("throws Forbidden when the user's own status is SUSPENDED", async () => {
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
          status: "SUSPENDED",
          org: { status: "ACTIVE" },
          role: { permissions: [] },
        }),
      },
    } as unknown as PrismaService;
    const guard = new SupabaseAuthGuard(prisma);
    await expect(guard.canActivate(contextWith({ authorization: "Bearer good" }))).rejects.toThrow(ForbiddenException);
  });

  it("throws Forbidden when the user's organization is SUSPENDED, even if the user themself is ACTIVE", async () => {
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
          status: "ACTIVE",
          org: { status: "SUSPENDED" },
          role: { permissions: [] },
        }),
      },
    } as unknown as PrismaService;
    const guard = new SupabaseAuthGuard(prisma);
    await expect(guard.canActivate(contextWith({ authorization: "Bearer good" }))).rejects.toThrow(ForbiddenException);
  });
```

- [ ] **Step 2: Run the guard tests and confirm the two new ones fail**

Run: `cd api && npx jest supabase-auth.guard.spec.ts`
Expected: the two new tests FAIL (guard doesn't check `status` yet — it currently returns `true` for any row it finds), the other tests still PASS.

- [ ] **Step 3: Implement the guard check**

In `api/src/auth/guards/supabase-auth.guard.ts`, replace:

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
      orgId: user.orgId,
      roleId: user.roleId,
      permissions: user.role.permissions.map((p) => p.permissionKey),
    };
    req.user = authedUser;
    return true;
  }
}
```

with:

```ts
import { CanActivate, ExecutionContext, ForbiddenException, Injectable, UnauthorizedException } from "@nestjs/common";
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
      include: { role: { include: { permissions: true } }, org: { select: { status: true } } },
    });
    if (!user) throw new UnauthorizedException("No profile for this account.");
    if (user.status === "SUSPENDED" || user.org.status === "SUSPENDED") {
      throw new ForbiddenException("This account has been suspended.");
    }

    const authedUser: AuthenticatedUser = {
      id: user.id,
      orgId: user.orgId,
      roleId: user.roleId,
      permissions: user.role.permissions.map((p) => p.permissionKey),
    };
    req.user = authedUser;
    return true;
  }
}
```

- [ ] **Step 4: Run the guard tests and confirm all pass**

Run: `cd api && npx jest supabase-auth.guard.spec.ts`
Expected: all tests PASS.

- [ ] **Step 5: Write the failing `AuthService.me()` tests**

In `api/src/auth/auth.service.spec.ts`, replace the full file:

```ts
import { ForbiddenException } from "@nestjs/common";
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

describe("AuthService.me", () => {
  function servicWith(userRow: Record<string, unknown>) {
    const prisma = {
      scoped: {
        platformAdmin: { findUnique: jest.fn().mockResolvedValue(null) },
        user: { findUniqueOrThrow: jest.fn().mockResolvedValue(userRow) },
      },
    } as unknown as PrismaService;
    return { prisma };
  }

  it("throws Forbidden when the user's own status is SUSPENDED", async () => {
    const { prisma } = servicWith({
      id: "u1",
      orgId: "org1",
      status: "SUSPENDED",
      org: { status: "ACTIVE" },
      role: { name: "Admin", permissions: [] },
    });
    const module = await Test.createTestingModule({
      providers: [AuthService, { provide: PrismaService, useValue: prisma }],
    }).compile();
    const service = module.get(AuthService);

    await expect(service.me("u1")).rejects.toThrow(ForbiddenException);
  });

  it("throws Forbidden when the user's organization is SUSPENDED, even if the user themself is ACTIVE", async () => {
    const { prisma } = servicWith({
      id: "u1",
      orgId: "org1",
      status: "ACTIVE",
      org: { status: "SUSPENDED" },
      role: { name: "Admin", permissions: [] },
    });
    const module = await Test.createTestingModule({
      providers: [AuthService, { provide: PrismaService, useValue: prisma }],
    }).compile();
    const service = module.get(AuthService);

    await expect(service.me("u1")).rejects.toThrow(ForbiddenException);
  });

  it("returns the org-member profile for an ACTIVE user in an ACTIVE org", async () => {
    const { prisma } = servicWith({
      id: "u1",
      orgId: "org1",
      name: "Jordan Lee",
      email: "jordan@acme.com",
      initials: "JL",
      avatarGrad: "var(--ac-grad)",
      title: null,
      roleId: "admin",
      status: "ACTIVE",
      org: { status: "ACTIVE" },
      role: { name: "Admin", permissions: [] },
    });
    const module = await Test.createTestingModule({
      providers: [AuthService, { provide: PrismaService, useValue: prisma }],
    }).compile();
    const service = module.get(AuthService);

    const result = await service.me("u1");

    expect(result).toMatchObject({ kind: "org_member", id: "u1", roleName: "Admin" });
  });
});
```

- [ ] **Step 6: Run the `AuthService` tests and confirm the two new ones fail**

Run: `cd api && npx jest auth.service.spec.ts`
Expected: the two `Forbidden` tests FAIL (`userWithPermissions` doesn't check `status` yet), the idempotency test and the third new test still PASS (or also fail on the `org` field being unread — either way, not yet throwing Forbidden).

- [ ] **Step 7: Implement the `AuthService.me()` check**

In `api/src/auth/auth.service.ts`, replace the import line:

```ts
import { Injectable } from "@nestjs/common";
```

with:

```ts
import { ForbiddenException, Injectable } from "@nestjs/common";
```

Replace `userWithPermissions`:

```ts
  private async userWithPermissions(userId: string) {
    // .scoped, not plain — see the class-level note below on why every
    // method here needs the is_platform_admin RLS bypass.
    const user = await this.prisma.scoped.user.findUniqueOrThrow({
      where: { id: userId },
      include: { role: { include: { permissions: true } } },
    });
    return { user, permissions: user.role.permissions.map((p) => p.permissionKey) };
  }
```

with:

```ts
  private async userWithPermissions(userId: string) {
    // .scoped, not plain — see the class-level note below on why every
    // method here needs the is_platform_admin RLS bypass.
    const user = await this.prisma.scoped.user.findUniqueOrThrow({
      where: { id: userId },
      include: { role: { include: { permissions: true } }, org: { select: { status: true } } },
    });
    if (user.status === "SUSPENDED" || user.org.status === "SUSPENDED") {
      throw new ForbiddenException("This account has been suspended.");
    }
    return { user, permissions: user.role.permissions.map((p) => p.permissionKey) };
  }
```

- [ ] **Step 8: Run the `AuthService` tests and confirm all pass**

Run: `cd api && npx jest auth.service.spec.ts`
Expected: all tests PASS.

- [ ] **Step 9: Run the full API test suite**

Run: `cd api && npm test`
Expected: all tests PASS (this also catches any other spec relying on the old `user.findUnique`/`userWithPermissions` shape).

- [ ] **Step 10: Typecheck**

Run: `cd api && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 11: Commit**

```bash
git add api/src/auth/guards/supabase-auth.guard.ts api/src/auth/guards/supabase-auth.guard.spec.ts api/src/auth/auth.service.ts api/src/auth/auth.service.spec.ts
git commit -m "feat: block suspended users and suspended-org members at auth"
```

---

### Task 4: Frontend — types and mutation hooks

**Files:**
- Modify: `web/src/api/platformAdmin.ts` (full file, 43 lines)

**Interfaces:**
- Produces: `Organization.status: "ACTIVE" | "SUSPENDED"`, `OrgUser.status: "ACTIVE" | "SUSPENDED"`, `useSetOrganizationStatus()`, `useSetUserStatus()`.
- Consumed by: Task 6 (`OrganizationsPage`), Task 7 (`OrgUsersPage`), Task 8 (`PlatformOverviewPage`).

- [ ] **Step 1: Replace the file**

Replace the full contents of `web/src/api/platformAdmin.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export type AccountStatus = "ACTIVE" | "SUSPENDED";

export interface Organization {
  id: string;
  name: string;
  createdAt: string;
  status: AccountStatus;
  _count: { users: number };
}

export interface OrgUser {
  id: string;
  name: string;
  email: string;
  roleId: string;
  initials: string;
  avatarGrad: string;
  status: AccountStatus;
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

export function useSetOrganizationStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ orgId, status }: { orgId: string; status: AccountStatus }) =>
      (await api.patch<Organization>(`/platform-admin/organizations/${orgId}/status`, { status })).data,
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

export function useSetUserStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ orgId, userId, status }: { orgId: string; userId: string; status: AccountStatus }) =>
      (await api.patch<OrgUser>(`/platform-admin/organizations/${orgId}/users/${userId}/status`, { status })).data,
    onSuccess: (_data, vars) =>
      qc.invalidateQueries({ queryKey: ["platform-admin", "organizations", vars.orgId, "users"] }),
  });
}
```

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: clean (nothing consumes `status`/the new hooks yet, so no new errors — Tasks 6-8 wire them up).

- [ ] **Step 3: Commit**

```bash
git add web/src/api/platformAdmin.ts
git commit -m "feat: add status types and suspend/activate hooks to platformAdmin API client"
```

---

### Task 5: `StatusBadge` — shared status pill

**Files:**
- Create: `web/src/components/ui/StatusBadge.tsx`

**Interfaces:**
- Consumes: `AccountStatus` from `web/src/api/platformAdmin.ts` (Task 4).
- Produces: `StatusBadge({ status }: { status: AccountStatus })`.
- Consumed by: Task 6 (`OrganizationsPage`), Task 7 (`OrgUsersPage`).

- [ ] **Step 1: Create the component**

Create `web/src/components/ui/StatusBadge.tsx`:

```tsx
import type { AccountStatus } from "../../api/platformAdmin";

export function StatusBadge({ status }: { status: AccountStatus }) {
  const active = status === "ACTIVE";
  return (
    <span
      style={{
        font: "600 10px 'IBM Plex Mono',monospace",
        padding: "3px 9px",
        borderRadius: 20,
        color: active ? "#0f8a5c" : "#c0405a",
        background: active ? "#e6f6ee" : "#fbe8ea",
        whiteSpace: "nowrap",
      }}
    >
      {active ? "ACTIVE" : "SUSPENDED"}
    </span>
  );
}
```

(Mirrors `RoleBadge.tsx`'s exact shape — pill, uppercase, `IBM Plex Mono` — with fixed colors instead of `RoleBadge`'s per-role `color`/`bg` props, since there are only ever two states.)

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/ui/StatusBadge.tsx
git commit -m "feat: add StatusBadge component"
```

---

### Task 6: `OrganizationsPage` — workspace suspend/activate

**Files:**
- Modify: `web/src/routes/platform-admin/OrganizationsPage.tsx` (full file, 141 lines)

**Interfaces:**
- Consumes: `useSetOrganizationStatus`, `Organization` type (Task 4); `StatusBadge` (Task 5); `useConfirm` from `web/src/stores/useConfirmStore.ts` (existing, signature `confirm(spec: { title: string; body: string; label: string; tone: "primary" | "danger" }) => Promise<boolean>`).

- [ ] **Step 1: Add the new imports**

Replace the import block at the top of `web/src/routes/platform-admin/OrganizationsPage.tsx`:

```tsx
import { useState } from "react";
import { Link } from "react-router-dom";
import { useCreateOrganization, useOrganizations } from "../../api/platformAdmin";
import { PageHeader, FieldRow, inputStyle } from "../settings/UsersPage";
import { Button } from "../../components/ui/Button";
import { Modal, ModalHeader } from "../../components/ui/Modal";
import { useToast } from "../../stores/useToastStore";
import { apiErrorMessage } from "../../api/client";
```

with:

```tsx
import { useState } from "react";
import { Link } from "react-router-dom";
import { useCreateOrganization, useOrganizations, useSetOrganizationStatus, type Organization } from "../../api/platformAdmin";
import { PageHeader, FieldRow, inputStyle } from "../settings/UsersPage";
import { Button } from "../../components/ui/Button";
import { Modal, ModalHeader } from "../../components/ui/Modal";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { useToast } from "../../stores/useToastStore";
import { useConfirm } from "../../stores/useConfirmStore";
import { apiErrorMessage } from "../../api/client";
```

- [ ] **Step 2: Add the confirm/mutate hook and the toggle handler**

Inside `OrganizationsPage`, replace:

```tsx
  const { data: orgs, isLoading } = useOrganizations();
  const createOrg = useCreateOrganization();
  const { addToast } = useToast();
```

with:

```tsx
  const { data: orgs, isLoading } = useOrganizations();
  const createOrg = useCreateOrganization();
  const setOrgStatus = useSetOrganizationStatus();
  const { addToast } = useToast();
  const confirm = useConfirm();
```

Add this new function right after the existing `submit` function (after its closing `};`):

```tsx

  const toggleOrgStatus = async (e: React.MouseEvent, o: Organization) => {
    e.preventDefault();
    e.stopPropagation();
    const suspending = o.status === "ACTIVE";
    if (suspending) {
      const ok = await confirm({
        title: `Suspend ${o.name}?`,
        body: "All users in this workspace will be immediately blocked from signing in.",
        label: "Suspend workspace",
        tone: "danger",
      });
      if (!ok) return;
    }
    try {
      await setOrgStatus.mutateAsync({ orgId: o.id, status: suspending ? "SUSPENDED" : "ACTIVE" });
      addToast({
        icon: suspending ? "⛔" : "✅",
        accent: suspending ? "#c0405a" : "#0f8a5c",
        title: suspending ? "Workspace suspended" : "Workspace activated",
        desc: o.name,
      });
    } catch (err) {
      addToast({ icon: "⚠️", accent: "#e2603f", title: "Couldn't update workspace", desc: apiErrorMessage(err) });
    }
  };
```

- [ ] **Step 3: Render the badge and button in each row**

Replace:

```tsx
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 13.5 }}>{o.name}</div>
              <div style={{ fontSize: 11.5, color: "#9499ad" }}>
                {o._count.users} {o._count.users === 1 ? "user" : "users"} · Created{" "}
                {new Date(o.createdAt).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
              </div>
            </div>
            <span style={{ color: "var(--ac)", fontWeight: 700, fontSize: 12.5, flexShrink: 0 }}>Manage users →</span>
```

with:

```tsx
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 13.5 }}>{o.name}</div>
              <div style={{ fontSize: 11.5, color: "#9499ad" }}>
                {o._count.users} {o._count.users === 1 ? "user" : "users"} · Created{" "}
                {new Date(o.createdAt).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
              </div>
            </div>
            <StatusBadge status={o.status} />
            <Button
              variant={o.status === "ACTIVE" ? "danger" : "secondary"}
              onClick={(e) => toggleOrgStatus(e, o)}
              style={{ padding: "4px 10px", fontSize: 11.5, flexShrink: 0 }}
            >
              {o.status === "ACTIVE" ? "Suspend" : "Activate"}
            </Button>
            <span style={{ color: "var(--ac)", fontWeight: 700, fontSize: 12.5, flexShrink: 0 }}>Manage users →</span>
```

- [ ] **Step 4: Typecheck and manually verify**

Run: `cd web && npx tsc --noEmit`
Expected: clean.

Then, as a platform admin on `/platform-admin/organizations`: click "Suspend" on a workspace → confirm dialog appears → confirm → badge flips to "Suspended", button flips to "Activate" (secondary style), row still navigates to that workspace's users on a click elsewhere in the row. Click "Activate" → no confirm dialog, badge flips back immediately. Confirm clicking Suspend/Activate never navigates to the users page.

- [ ] **Step 5: Commit**

```bash
git add web/src/routes/platform-admin/OrganizationsPage.tsx
git commit -m "feat: add workspace suspend/activate to OrganizationsPage"
```

---

### Task 7: `OrgUsersPage` — user suspend/activate

**Files:**
- Modify: `web/src/routes/platform-admin/OrgUsersPage.tsx` (full file, 45 lines)

**Interfaces:**
- Consumes: `useSetUserStatus`, `OrgUser` type (Task 4); `StatusBadge` (Task 5); `useConfirm` (existing); `useToast`/`apiErrorMessage` (existing, same as Task 6).

- [ ] **Step 1: Rewrite the page**

Replace the full contents of `web/src/routes/platform-admin/OrgUsersPage.tsx`:

```tsx
import { Link, useParams } from "react-router-dom";
import { useOrganizations, useOrgUsers, useSetUserStatus, type OrgUser } from "../../api/platformAdmin";
import { PageHeader } from "../settings/UsersPage";
import { RoleBadge } from "../../components/ui/RoleBadge";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { Button } from "../../components/ui/Button";
import { Avatar } from "../../components/shell/Sidebar";
import { useToast } from "../../stores/useToastStore";
import { useConfirm } from "../../stores/useConfirmStore";
import { apiErrorMessage } from "../../api/client";

export function OrgUsersPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { data: users, isLoading } = useOrgUsers(orgId);
  const { data: orgs } = useOrganizations();
  const org = orgs?.find((o) => o.id === orgId);
  const setUserStatus = useSetUserStatus();
  const { addToast } = useToast();
  const confirm = useConfirm();

  const toggleUserStatus = async (u: OrgUser) => {
    const suspending = u.status === "ACTIVE";
    if (suspending) {
      const ok = await confirm({
        title: `Suspend ${u.name}?`,
        body: "They will be immediately blocked from signing in.",
        label: "Suspend user",
        tone: "danger",
      });
      if (!ok) return;
    }
    try {
      await setUserStatus.mutateAsync({ orgId: orgId!, userId: u.id, status: suspending ? "SUSPENDED" : "ACTIVE" });
      addToast({
        icon: suspending ? "⛔" : "✅",
        accent: suspending ? "#c0405a" : "#0f8a5c",
        title: suspending ? "User suspended" : "User activated",
        desc: u.name,
      });
    } catch (err) {
      addToast({ icon: "⚠️", accent: "#e2603f", title: "Couldn't update user", desc: apiErrorMessage(err) });
    }
  };

  return (
    <div style={{ padding: 32, maxWidth: 1080, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "#9499ad", marginBottom: 14 }}>
        <Link to="/platform-admin/organizations" style={{ color: "#9499ad" }}>
          ← Workspaces
        </Link>
        {org && (
          <>
            <span>/</span>
            <span style={{ color: "var(--ac-fg)", fontWeight: 600 }}>{org.name}</span>
          </>
        )}
      </div>
      <PageHeader
        title={org ? org.name : "Workspace users"}
        sub={`${users?.length ?? 0} ${users?.length === 1 ? "user" : "users"} in this organization`}
      />
      <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #e9eaf2", overflow: "hidden" }}>
        {isLoading && <div style={{ padding: 20, color: "#9499ad" }}>Loading…</div>}
        {users?.map((u) => (
          <div key={u.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 18px", minHeight: 56, borderBottom: "1px solid #f5f6fb" }}>
            <Avatar grad={u.avatarGrad} initials={u.initials} size={34} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>{u.name}</div>
              <div style={{ fontSize: 11.5, color: "#9499ad" }}>{u.email}</div>
            </div>
            <StatusBadge status={u.status} />
            <Button
              variant={u.status === "ACTIVE" ? "danger" : "secondary"}
              onClick={() => toggleUserStatus(u)}
              style={{ padding: "4px 10px", fontSize: 11.5, flexShrink: 0 }}
            >
              {u.status === "ACTIVE" ? "Suspend" : "Activate"}
            </Button>
            <RoleBadge name={u.role.name} color={null} bg={null} />
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck and manually verify**

Run: `cd web && npx tsc --noEmit`
Expected: clean.

Then, as a platform admin, open a workspace's users. Expected:
- Each row shows a status badge + Suspend/Activate button, next to the existing role badge.
- Clicking Suspend prompts a confirm dialog; confirming flips the badge and button; canceling leaves it unchanged.
- Clicking Activate on a suspended user updates immediately, no dialog.
- Log in (in a second browser/incognito) as a user you just suspended — confirm they're rejected (see Task 3's enforcement; `/auth/me` now 403s for them, so they land back on the login page).

- [ ] **Step 3: Commit**

```bash
git add web/src/routes/platform-admin/OrgUsersPage.tsx
git commit -m "feat: add user suspend/activate to OrgUsersPage"
```

---

### Task 8: `PlatformOverviewPage` — "Active Organizations" counts only active orgs

**Files:**
- Modify: `web/src/routes/platform-admin/PlatformOverviewPage.tsx:21-30` (the `PlatformOverviewPage` function body)

**Interfaces:**
- Consumes: `Organization.status` (Task 4).

- [ ] **Step 1: Filter the count**

Replace:

```tsx
export function PlatformOverviewPage() {
  const { data: orgs } = useOrganizations();

  const now = new Date();
  const newThisMonth = (orgs ?? []).filter((o) => {
    const d = new Date(o.createdAt);
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
  }).length;
  const totalUsers = (orgs ?? []).reduce((sum, o) => sum + o._count.users, 0);
  const planTotal = MOCK_PLANS.reduce((sum, p) => sum + p.price * p.orgCount, 0);
```

with:

```tsx
export function PlatformOverviewPage() {
  const { data: orgs } = useOrganizations();

  const now = new Date();
  const newThisMonth = (orgs ?? []).filter((o) => {
    const d = new Date(o.createdAt);
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
  }).length;
  const activeOrgCount = (orgs ?? []).filter((o) => o.status === "ACTIVE").length;
  const totalUsers = (orgs ?? []).reduce((sum, o) => sum + o._count.users, 0);
  const planTotal = MOCK_PLANS.reduce((sum, p) => sum + p.price * p.orgCount, 0);
```

Then replace the KPI card that uses `orgs?.length`:

```tsx
        <KpiCard label="ACTIVE ORGANIZATIONS" value={String(orgs?.length ?? 0)} trend={`↑ ${newThisMonth} new this month`} />
```

with:

```tsx
        <KpiCard label="ACTIVE ORGANIZATIONS" value={String(activeOrgCount)} trend={`↑ ${newThisMonth} new this month`} />
```

- [ ] **Step 2: Typecheck and manually verify**

Run: `cd web && npx tsc --noEmit`
Expected: clean.

Then, on `/platform-admin/dashboard`: suspend a workspace (via `/platform-admin/organizations`), navigate back to the Dashboard, confirm "Active Organizations" drops by one. Activate it again, confirm the count returns.

- [ ] **Step 3: Commit**

```bash
git add web/src/routes/platform-admin/PlatformOverviewPage.tsx
git commit -m "feat: exclude suspended workspaces from the Active Organizations KPI"
```

---

## Self-Review Notes

- **Spec coverage:** Data model (Task 1), backend endpoints (Task 2), auth enforcement at both `SupabaseAuthGuard` and `AuthService.me()` (Task 3), frontend types/hooks (Task 4), shared badge (Task 5), `OrganizationsPage` UI (Task 6), `OrgUsersPage` UI (Task 7), Dashboard KPI (Task 8) — every spec section has a task. Out-of-scope items (audit log, email, bulk actions, real-time session kill, platform-admin status) are intentionally not tasked.
- **Placeholder scan:** No TBD/TODO; every step has literal code or an exact command.
- **Type consistency:** `AccountStatus` (Task 1's Prisma enum, mirrored in `packages/prisma/index.ts`) is imported by name in Task 2's DTO/service. The frontend never imports that Prisma-side type — Task 4 independently defines the literal union `AccountStatus = "ACTIVE" | "SUSPENDED"` in `platformAdmin.ts`, matching the wire values exactly (both sides use the same uppercase strings, so JSON round-trips without translation). `useSetOrganizationStatus({ orgId, status })` and `useSetUserStatus({ orgId, userId, status })` (Task 4) are called with matching argument shapes in Task 6/7. `StatusBadge({ status: AccountStatus })` (Task 5) is used identically in Task 6 (`o.status`) and Task 7 (`u.status`).
- **Task 2 correction while writing:** originally planned to also modify `listOrganizations()`, but since it already uses `include` (not an exhaustive `select`), Prisma returns the new `status` column automatically — no code change needed there, only `listUsers()` needed its `select` extended. Reflected directly in Task 2's steps.
