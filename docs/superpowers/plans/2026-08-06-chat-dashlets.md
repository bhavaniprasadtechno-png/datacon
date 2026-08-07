# Chat → Dashboard Dashlets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user save any chart/table/action-bearing chat answer as a "dashlet" onto a personal dashboard, browsable from Insights → "My dashboards".

**Architecture:** Two new Prisma tables (`Dashboard`, `Dashlet`) hold the *reference* to a chat question, not a frozen picture. A new AI-service endpoint (`POST /internal/chat/answer`) replays that question through the existing deterministic per-intent `prepare()` functions on every dashboard view — no LLM cost, genuinely live data. A new NestJS `dashboards` module exposes list/save/detail/delete-dashlet, gated by the existing `view_dashboards` permission and scoped to `orgId` + the owning `userId`. On the frontend, `ChatPage` gets an "Add to dashboard" button that opens a save modal (reusing the existing `Modal` component); `InsightsPage` gets an "Overview"/"My dashboards" tab toggle; a new `DashboardDetailPage` renders each dashlet by reusing the existing `AgentVisualization` chart/table/citations/actions renderer.

**Tech Stack:** NestJS + Prisma + PostgreSQL (existing) — `app/api/`. FastAPI (existing) — `app/ai/`. React + React Router + TanStack Query (existing) — `app/web/`. Jest (`app/api/`) and pytest (`app/ai/`) for tests — both already configured, no new test infra needed. No frontend test framework exists in this repo today, so frontend tasks end with a manual dev-server verification step, matching existing practice.

## Global Constraints

- Every Prisma query in the API touching org data MUST go through `this.prisma.scoped.<model>`, never the bare client — see `app/api/src/prisma/prisma.service.ts`.
- Dashboards are private per-user ("My dashboards"): every dashboard/dashlet query must filter by `userId` in addition to `orgId` — RLS only enforces `orgId`, not `userId` (same split as `Conversation`/`Message`).
- Reuse the existing `view_dashboards` permission — do not add a new permission.
- Reuse the existing `Intent` Prisma enum (`DESCRIPTIVE | DIAGNOSTIC | PREDICTIVE | PRESCRIPTIVE`) — do not add a new enum. It is NOT mirrored anywhere else (unlike `ConnectorEngine`), so no `app/packages/prisma/index.ts` change is needed.
- No changes to `Conversation`/`Message` schema — the question text needed for replay is read from existing chat UI state, not persisted server-side onto `Message`.
- Follow the spec at `docs/superpowers/specs/2026-08-06-chat-dashlets-design.md` for all behavior not otherwise specified here.

---

### Task 1: Prisma schema — `Dashboard` and `Dashlet` models + migration

**Files:**
- Modify: `app/packages/prisma/schema.prisma` (Organization model ~line 19-36, User model ~line 53-74, end of Chat section ~line 252)
- Create: `app/packages/prisma/migrations/20260806120000_chat_dashlets/migration.sql`

**Interfaces:**
- Produces: Prisma models `Dashboard { id, orgId, userId, name, createdAt, updatedAt, dashlets }` and `Dashlet { id, orgId, dashboardId, title, text, intent: Intent, question, model, payload: Json, createdAt }`, available as `this.prisma.scoped.dashboard` / `this.prisma.scoped.dashlet` after `prisma generate`. Task 3 depends on these exact field names.

- [ ] **Step 1: Add the two models to the schema**

In `app/packages/prisma/schema.prisma`, add this new section right after the `Feedback` model (end of the `// ───────────────────────────── Chat ─────────────────────────────` section, after line 266's closing `}`):

```prisma
// ───────────────────────────── Dashboards ─────────────────────────────

model Dashboard {
  id        String   @id @default(cuid())
  orgId     String
  org       Organization @relation(fields: [orgId], references: [id])
  userId    String   @db.Uuid
  user      User     @relation(fields: [userId], references: [id])
  name      String
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
  dashlets  Dashlet[]

  @@map("dashboards")
}

model Dashlet {
  id          String    @id @default(cuid())
  orgId       String
  org         Organization @relation(fields: [orgId], references: [id])
  dashboardId String
  dashboard   Dashboard @relation(fields: [dashboardId], references: [id], onDelete: Cascade)
  title       String
  text        String
  intent      Intent
  question    String
  model       String?
  payload     Json
  createdAt   DateTime  @default(now())

  @@map("dashlets")
}
```

- [ ] **Step 2: Add back-relations to `Organization` and `User`**

In `app/packages/prisma/schema.prisma`, in the `Organization` model, replace:

```prisma
  conversations Conversation[]
  messages      Message[]
  feedback      Feedback[]

  @@map("organizations")
```

with:

```prisma
  conversations Conversation[]
  messages      Message[]
  feedback      Feedback[]
  dashboards    Dashboard[]
  dashlets      Dashlet[]

  @@map("organizations")
```

In the `User` model, replace:

```prisma
  conversations Conversation[]
  documents     DataSource[]
  feedback      Feedback[]

  @@map("users")
```

with:

```prisma
  conversations Conversation[]
  documents     DataSource[]
  feedback      Feedback[]
  dashboards    Dashboard[]

  @@map("users")
```

- [ ] **Step 3: Validate and regenerate the Prisma client**

Run: `npm run generate --workspace=packages/prisma`
Expected: completes with no errors; the generated client now has `dashboard`/`dashlet` model delegates.

- [ ] **Step 4: Write the migration**

Create `app/packages/prisma/migrations/20260806120000_chat_dashlets/migration.sql`:

```sql
-- Dashboards: per-user saved collections of chat insights ("dashlets").
-- Live data — a dashlet stores the original question, not a frozen result;
-- app/ai's /internal/chat/answer replays it on every dashboard view.
CREATE TABLE "dashboards" (
  "id"        TEXT NOT NULL,
  "orgId"     TEXT NOT NULL,
  "userId"    UUID NOT NULL,
  "name"      TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "dashboards_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "dashlets" (
  "id"          TEXT NOT NULL,
  "orgId"       TEXT NOT NULL,
  "dashboardId" TEXT NOT NULL,
  "title"       TEXT NOT NULL,
  "text"        TEXT NOT NULL,
  "intent"      "Intent" NOT NULL,
  "question"    TEXT NOT NULL,
  "model"       TEXT,
  "payload"     JSONB NOT NULL,
  "createdAt"   TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "dashlets_pkey" PRIMARY KEY ("id")
);

ALTER TABLE "dashboards" ADD CONSTRAINT "dashboards_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "dashboards" ADD CONSTRAINT "dashboards_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "dashlets" ADD CONSTRAINT "dashlets_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "dashlets" ADD CONSTRAINT "dashlets_dashboardId_fkey" FOREIGN KEY ("dashboardId") REFERENCES "dashboards"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- RLS: org-scoped, same shape as every other business-data table (see
-- 20260724000000_multi_tenant_workspaces/migration.sql). Per-user ownership
-- within an org (dashboards are private, not org-shared) is enforced at the
-- application layer in DashboardsService, exactly like Conversation/Message's
-- userId scoping.
--
-- No explicit GRANT is needed for app_user here: the multi-tenant migration
-- already set `ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT,
-- INSERT, UPDATE, DELETE ON TABLES TO app_user`, which covers tables created
-- afterwards, including these two.
CREATE POLICY org_isolation ON public.dashboards
  USING ("orgId" = current_setting('app.current_org_id', true));
CREATE POLICY org_isolation ON public.dashlets
  USING ("orgId" = current_setting('app.current_org_id', true));

ALTER TABLE public.dashboards ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dashlets ENABLE ROW LEVEL SECURITY;
```

- [ ] **Step 5: Build the prisma package**

Run: `npm run build --workspace=packages/prisma`
Expected: builds with no TypeScript errors.

- [ ] **Step 6: Apply the migration to your local dev database (if available)**

Run: `npm run prisma:migrate --workspace=packages/prisma` (requires a running local Postgres matching `DATABASE_URL`; skip if none is available in this environment — the migration file is still correct and will be picked up by `prisma migrate deploy` in the real deploy pipeline)
Expected: `Your database is now in sync with your schema.` and the new migration is recorded in `_prisma_migrations`.

- [ ] **Step 7: Commit**

```bash
git add app/packages/prisma/schema.prisma app/packages/prisma/migrations/20260806120000_chat_dashlets
git commit -m "feat(prisma): add Dashboard and Dashlet models"
```

---

### Task 2: AI service — `POST /internal/chat/answer`

**Files:**
- Modify: `app/ai/app/internal/chat_router.py`
- Modify: `app/ai/tests/internal/test_chat_router.py`

**Interfaces:**
- Consumes: `_ANALYSTS: dict[str, Callable]` already defined at the top of `chat_router.py` (keys: `"descriptive"`, `"diagnostic"`, `"predictive"`, `"prescriptive"`, `"general"`), each `prepare(question: str, model: str | None) -> AgentPrep`.
- Produces: `POST /internal/chat/answer` accepting `{question: str, intent: str, model?: str}`, returning `{"payload": <dict>}` on success, `400` on an unknown intent. Task 3's `DashboardsService.detail()` calls this exact endpoint/shape.

- [ ] **Step 1: Write the failing tests**

In `app/ai/tests/internal/test_chat_router.py`, add at the end of the file:

```python
def test_answer_returns_the_analysts_payload_for_a_known_intent(client):
    res = client.post(
        "/internal/chat/answer",
        json={"question": "what are total leads", "intent": "descriptive"},
        headers=_auth_headers(),
    )
    assert res.status_code == 200
    assert res.json() == {"payload": {"confidence": "low"}}


def test_answer_rejects_an_unknown_intent(client):
    res = client.post(
        "/internal/chat/answer",
        json={"question": "what are total leads", "intent": "bogus"},
        headers=_auth_headers(),
    )
    assert res.status_code == 400
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd app/ai && python -m pytest tests/internal/test_chat_router.py -v -k test_answer`
Expected: both FAIL with `404 Not Found` (route doesn't exist yet).

- [ ] **Step 3: Implement the endpoint**

In `app/ai/app/internal/chat_router.py`, change the import line:

```python
from fastapi import APIRouter, Depends
```

to:

```python
from fastapi import APIRouter, Depends, HTTPException
```

Then add, right after the `ChatPayload` class definition:

```python
class AnswerPayload(BaseModel):
    question: str
    intent: str
    model: str | None = None
```

Then add this new route, right after the `get_models` endpoint (before `@router.post("/stream")`):

```python
@router.post("/answer")
async def answer(payload: AnswerPayload):
    """Replays a question through its analyst's deterministic prepare()
    step only — no LLM call — so dashboard dashlets can refresh live data
    on every view without repeated LLM cost."""
    analyst = _ANALYSTS.get(payload.intent)
    if analyst is None:
        raise HTTPException(status_code=400, detail=f"Unknown intent '{payload.intent}'.")
    prep = await analyst(payload.question, payload.model)
    return {"payload": prep.payload}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd app/ai && python -m pytest tests/internal/test_chat_router.py -v`
Expected: all PASS (including the pre-existing `test_stream_*` tests — no regression).

- [ ] **Step 5: Commit**

```bash
git add app/ai/app/internal/chat_router.py app/ai/tests/internal/test_chat_router.py
git commit -m "feat(ai): add /internal/chat/answer for live dashlet refresh"
```

---

### Task 3: API — `DashboardsService`

**Files:**
- Create: `app/api/src/dashboards/dto/save-dashlet.dto.ts`
- Create: `app/api/src/dashboards/dashboards.service.ts`
- Create: `app/api/src/dashboards/dashboards.service.spec.ts`

**Interfaces:**
- Consumes: `PrismaService.scoped.dashboard` / `.dashlet` (Task 1), `AiClientService.client` (existing, `app/api/src/common/ai-client.service.ts`).
- Produces: `DashboardsService.list(orgId, userId) -> {id, name, dashletCount, updatedAt}[]`; `.save(orgId, userId, dto: SaveDashletDto) -> DashboardDetail`; `.detail(orgId, userId, id) -> {id, name, dashlets: {id, title, text, intent, payload, stale}[]}`; `.removeDashlet(orgId, userId, dashboardId, dashletId) -> {ok: true}`. Task 4's controller calls these four methods with these exact signatures.

- [ ] **Step 1: Write the DTO**

Create `app/api/src/dashboards/dto/save-dashlet.dto.ts`:

```typescript
import { IsIn, IsObject, IsOptional, IsString, MinLength } from "class-validator";

const DASHLET_INTENTS = ["descriptive", "diagnostic", "predictive", "prescriptive"] as const;
export type DashletIntent = (typeof DASHLET_INTENTS)[number];

export class SaveDashletDto {
  @IsOptional()
  @IsString()
  dashboardId?: string;

  @IsOptional()
  @IsString()
  @MinLength(1)
  name?: string;

  @IsString()
  @MinLength(1)
  title!: string;

  @IsString()
  text!: string;

  @IsIn(DASHLET_INTENTS)
  intent!: DashletIntent;

  @IsString()
  @MinLength(1)
  question!: string;

  @IsOptional()
  @IsString()
  model?: string;

  @IsObject()
  payload!: Record<string, unknown>;
}
```

- [ ] **Step 2: Write the failing tests**

Create `app/api/src/dashboards/dashboards.service.spec.ts`:

```typescript
import { BadRequestException, NotFoundException } from "@nestjs/common";
import { Test } from "@nestjs/testing";
import { DashboardsService } from "./dashboards.service";
import { PrismaService } from "../prisma/prisma.service";
import { AiClientService } from "../common/ai-client.service";

describe("DashboardsService", () => {
  let service: DashboardsService;
  let dashboard: { findMany: jest.Mock; findUnique: jest.Mock; findUniqueOrThrow: jest.Mock; create: jest.Mock };
  let dashlet: { create: jest.Mock; delete: jest.Mock };
  let aiPost: jest.Mock;

  beforeEach(async () => {
    dashboard = { findMany: jest.fn(), findUnique: jest.fn(), findUniqueOrThrow: jest.fn(), create: jest.fn() };
    dashlet = { create: jest.fn(), delete: jest.fn() };
    aiPost = jest.fn();
    const moduleRef = await Test.createTestingModule({
      providers: [
        DashboardsService,
        { provide: PrismaService, useValue: { scoped: { dashboard, dashlet } } },
        { provide: AiClientService, useValue: { client: { post: aiPost } } },
      ],
    }).compile();
    service = moduleRef.get(DashboardsService);
  });

  it("creates a new dashboard when dashboardId is omitted", async () => {
    dashboard.create.mockResolvedValue({ id: "d1" });
    dashlet.create.mockResolvedValue({ id: "dl1" });
    dashboard.findUnique.mockResolvedValue({ id: "d1", orgId: "org1", userId: "user1" });
    dashboard.findUniqueOrThrow.mockResolvedValue({ id: "d1", name: "Revenue Watch", dashlets: [] });

    const result = await service.save("org1", "user1", {
      name: "Revenue Watch",
      title: "Revenue by region",
      text: "Here is what I found.",
      intent: "descriptive",
      question: "revenue by region last quarter",
      payload: { chart: { type: "bar", title: "t", data: [] } },
    } as any);

    expect(dashboard.create).toHaveBeenCalledWith({ data: { orgId: "org1", userId: "user1", name: "Revenue Watch" } });
    expect(dashlet.create).toHaveBeenCalledWith({
      data: expect.objectContaining({ orgId: "org1", dashboardId: "d1", intent: "DESCRIPTIVE", question: "revenue by region last quarter" }),
    });
    expect(result.id).toBe("d1");
  });

  it("rejects a new-dashboard save with no name", async () => {
    await expect(
      service.save("org1", "user1", { title: "t", text: "t", intent: "descriptive", question: "q", payload: {} } as any),
    ).rejects.toThrow(BadRequestException);
    expect(dashboard.create).not.toHaveBeenCalled();
  });

  it("appends to an existing dashboard owned by the requesting user", async () => {
    dashboard.findUnique.mockResolvedValue({ id: "d1", orgId: "org1", userId: "user1" });
    dashlet.create.mockResolvedValue({ id: "dl1" });
    dashboard.findUniqueOrThrow.mockResolvedValue({ id: "d1", name: "Revenue Watch", dashlets: [] });

    await service.save("org1", "user1", {
      dashboardId: "d1",
      title: "t",
      text: "t",
      intent: "predictive",
      question: "forecast revenue",
      payload: {},
    } as any);

    expect(dashboard.create).not.toHaveBeenCalled();
    expect(dashlet.create).toHaveBeenCalledWith({ data: expect.objectContaining({ dashboardId: "d1", intent: "PREDICTIVE" }) });
  });

  it("rejects appending to a dashboard owned by a different user", async () => {
    dashboard.findUnique.mockResolvedValue({ id: "d1", orgId: "org1", userId: "someone-else" });

    await expect(
      service.save("org1", "user1", { dashboardId: "d1", title: "t", text: "t", intent: "descriptive", question: "q", payload: {} } as any),
    ).rejects.toThrow(NotFoundException);
    expect(dashlet.create).not.toHaveBeenCalled();
  });

  it("returns live payloads for each dashlet on detail, refreshed from the AI service", async () => {
    dashboard.findUnique.mockResolvedValue({ id: "d1", orgId: "org1", userId: "user1" });
    dashboard.findUniqueOrThrow.mockResolvedValue({
      id: "d1",
      name: "Revenue Watch",
      dashlets: [{ id: "dl1", title: "Revenue by region", text: "t", intent: "DESCRIPTIVE", question: "revenue by region", model: null, payload: { confidence: "low" } }],
    });
    aiPost.mockResolvedValue({ data: { payload: { confidence: "high", table: { columns: ["a"], rows: [[1]] } } } });

    const result = await service.detail("org1", "user1", "d1");

    expect(aiPost).toHaveBeenCalledWith("/internal/chat/answer", { question: "revenue by region", intent: "descriptive", model: null });
    expect(result.dashlets[0]).toEqual({
      id: "dl1",
      title: "Revenue by region",
      text: "t",
      intent: "descriptive",
      payload: { confidence: "high", table: { columns: ["a"], rows: [[1]] } },
      stale: false,
    });
  });

  it("falls back to the cached payload and marks it stale when the AI service call fails", async () => {
    dashboard.findUnique.mockResolvedValue({ id: "d1", orgId: "org1", userId: "user1" });
    dashboard.findUniqueOrThrow.mockResolvedValue({
      id: "d1",
      name: "Revenue Watch",
      dashlets: [{ id: "dl1", title: "Revenue by region", text: "t", intent: "DESCRIPTIVE", question: "revenue by region", model: null, payload: { confidence: "low" } }],
    });
    aiPost.mockRejectedValue(new Error("AI service down"));

    const result = await service.detail("org1", "user1", "d1");

    expect(result.dashlets[0]).toEqual({
      id: "dl1",
      title: "Revenue by region",
      text: "t",
      intent: "descriptive",
      payload: { confidence: "low" },
      stale: true,
    });
  });

  it("rejects detail/removeDashlet for a dashboard not owned by the requesting user", async () => {
    dashboard.findUnique.mockResolvedValue(null);
    await expect(service.detail("org1", "user1", "missing")).rejects.toThrow(NotFoundException);
    await expect(service.removeDashlet("org1", "user1", "missing", "dl1")).rejects.toThrow(NotFoundException);
    expect(dashlet.delete).not.toHaveBeenCalled();
  });

  it("removes a dashlet from an owned dashboard", async () => {
    dashboard.findUnique.mockResolvedValue({ id: "d1", orgId: "org1", userId: "user1" });
    dashlet.delete.mockResolvedValue({ id: "dl1" });

    const result = await service.removeDashlet("org1", "user1", "d1", "dl1");

    expect(dashlet.delete).toHaveBeenCalledWith({ where: { id: "dl1" } });
    expect(result).toEqual({ ok: true });
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd app/api && npx jest dashboards.service.spec.ts`
Expected: FAIL — `Cannot find module './dashboards.service'`.

- [ ] **Step 4: Implement the service**

Create `app/api/src/dashboards/dashboards.service.ts`:

```typescript
import { BadRequestException, Injectable, NotFoundException } from "@nestjs/common";
import { Intent } from "@datacon/prisma";
import { PrismaService } from "../prisma/prisma.service";
import { AiClientService } from "../common/ai-client.service";
import { SaveDashletDto } from "./dto/save-dashlet.dto";

const INTENT_MAP: Record<string, Intent> = {
  descriptive: "DESCRIPTIVE",
  diagnostic: "DIAGNOSTIC",
  predictive: "PREDICTIVE",
  prescriptive: "PRESCRIPTIVE",
};

@Injectable()
export class DashboardsService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly ai: AiClientService,
  ) {}

  async list(orgId: string, userId: string) {
    const rows = await this.prisma.scoped.dashboard.findMany({
      where: { orgId, userId },
      include: { _count: { select: { dashlets: true } } },
      orderBy: { createdAt: "desc" },
    });
    return rows.map((r: any) => ({ id: r.id, name: r.name, dashletCount: r._count.dashlets, updatedAt: r.updatedAt }));
  }

  async save(orgId: string, userId: string, dto: SaveDashletDto) {
    let dashboardId: string;
    if (dto.dashboardId) {
      const owned = await this.assertOwnedDashboard(orgId, userId, dto.dashboardId);
      dashboardId = owned.id;
    } else {
      if (!dto.name?.trim()) throw new BadRequestException("Dashboard name is required.");
      const created = await this.prisma.scoped.dashboard.create({ data: { orgId, userId, name: dto.name.trim() } });
      dashboardId = created.id;
    }

    await this.prisma.scoped.dashlet.create({
      data: {
        orgId,
        dashboardId,
        title: dto.title,
        text: dto.text,
        intent: INTENT_MAP[dto.intent],
        question: dto.question,
        model: dto.model ?? null,
        payload: dto.payload as any,
      },
    });

    return this.detail(orgId, userId, dashboardId);
  }

  private async assertOwnedDashboard(orgId: string, userId: string, id: string) {
    const row = await this.prisma.scoped.dashboard.findUnique({ where: { id } });
    if (!row || row.orgId !== orgId || row.userId !== userId) throw new NotFoundException("Dashboard not found.");
    return row;
  }

  async detail(orgId: string, userId: string, id: string) {
    await this.assertOwnedDashboard(orgId, userId, id);
    const dashboard = await this.prisma.scoped.dashboard.findUniqueOrThrow({
      where: { id },
      include: { dashlets: { orderBy: { createdAt: "asc" } } },
    });

    const dashlets = await Promise.all(
      dashboard.dashlets.map(async (d: any) => {
        const intent = (d.intent as string).toLowerCase();
        try {
          const res = await this.ai.client.post("/internal/chat/answer", { question: d.question, intent, model: d.model });
          return { id: d.id, title: d.title, text: d.text, intent, payload: res.data.payload, stale: false };
        } catch {
          return { id: d.id, title: d.title, text: d.text, intent, payload: d.payload, stale: true };
        }
      }),
    );

    return { id: dashboard.id, name: dashboard.name, dashlets };
  }

  async removeDashlet(orgId: string, userId: string, dashboardId: string, dashletId: string) {
    await this.assertOwnedDashboard(orgId, userId, dashboardId);
    await this.prisma.scoped.dashlet.delete({ where: { id: dashletId } });
    return { ok: true };
  }
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd app/api && npx jest dashboards.service.spec.ts`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/src/dashboards/dto/save-dashlet.dto.ts app/api/src/dashboards/dashboards.service.ts app/api/src/dashboards/dashboards.service.spec.ts
git commit -m "feat(api): add DashboardsService with live dashlet refresh"
```

---

### Task 4: API — `DashboardsController` + module wiring

**Files:**
- Create: `app/api/src/dashboards/dashboards.controller.ts`
- Create: `app/api/src/dashboards/dashboards.module.ts`
- Modify: `app/api/src/app.module.ts:16,35`

**Interfaces:**
- Consumes: `DashboardsService` (Task 3), `SupabaseAuthGuard`/`PermissionsGuard`/`RequirePermissions`/`CurrentUser`/`AuthenticatedUser` (existing, `app/api/src/auth/*`).
- Produces: routes `GET /dashboards`, `POST /dashboards/save`, `GET /dashboards/:id`, `DELETE /dashboards/:id/dashlets/:dashletId`, all requiring the `view_dashboards` permission. Task 5's frontend hooks call these exact paths.

- [ ] **Step 1: Write the controller**

Create `app/api/src/dashboards/dashboards.controller.ts`:

```typescript
import { Body, Controller, Delete, Get, Param, Post, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { CurrentUser } from "../auth/decorators/current-user.decorator";
import { AuthenticatedUser } from "../auth/token.types";
import { DashboardsService } from "./dashboards.service";
import { SaveDashletDto } from "./dto/save-dashlet.dto";

@UseGuards(SupabaseAuthGuard, PermissionsGuard)
@RequirePermissions("view_dashboards")
@Controller("dashboards")
export class DashboardsController {
  constructor(private readonly dashboards: DashboardsService) {}

  @Get()
  list(@CurrentUser() user: AuthenticatedUser) {
    return this.dashboards.list(user.orgId, user.id);
  }

  @Post("save")
  save(@CurrentUser() user: AuthenticatedUser, @Body() dto: SaveDashletDto) {
    return this.dashboards.save(user.orgId, user.id, dto);
  }

  @Get(":id")
  detail(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string) {
    return this.dashboards.detail(user.orgId, user.id, id);
  }

  @Delete(":id/dashlets/:dashletId")
  removeDashlet(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string, @Param("dashletId") dashletId: string) {
    return this.dashboards.removeDashlet(user.orgId, user.id, id, dashletId);
  }
}
```

- [ ] **Step 2: Write the module**

Create `app/api/src/dashboards/dashboards.module.ts`:

```typescript
import { Module } from "@nestjs/common";
import { DashboardsService } from "./dashboards.service";
import { DashboardsController } from "./dashboards.controller";

@Module({
  providers: [DashboardsService],
  controllers: [DashboardsController],
})
export class DashboardsModule {}
```

- [ ] **Step 3: Wire the module into the app**

In `app/api/src/app.module.ts`, add the import after line 16 (`import { InsightsModule } from "./insights/insights.module";`):

```typescript
import { DashboardsModule } from "./dashboards/dashboards.module";
```

Then add `DashboardsModule,` to the `imports` array right after `InsightsModule,` (line 35).

- [ ] **Step 4: Verify the app builds**

Run: `cd app/api && npm run build`
Expected: builds with no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add app/api/src/dashboards/dashboards.controller.ts app/api/src/dashboards/dashboards.module.ts app/api/src/app.module.ts
git commit -m "feat(api): expose dashboards endpoints"
```

---

### Task 5: Web — dashboards API hooks

**Files:**
- Create: `app/web/src/api/dashboards.ts`

**Interfaces:**
- Consumes: `api` (existing axios instance, `app/web/src/api/client.ts`), `ChatIntent`/`ChatPayload` (existing, `app/web/src/lib/types.ts`).
- Produces: `DashletIntent` type, `DashboardSummary`, `DashletView`, `DashboardDetail` interfaces, and hooks `useDashboards()`, `useDashboard(id)`, `useSaveDashboard()`, `useDeleteDashlet()`. Tasks 6 and 8 import these by these exact names.

- [ ] **Step 1: Write the hooks file**

Create `app/web/src/api/dashboards.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { ChatIntent } from "@datacon/shared-types";
import type { ChatPayload } from "../lib/types";

export type DashletIntent = Exclude<ChatIntent, "general">;

export interface DashboardSummary {
  id: string;
  name: string;
  dashletCount: number;
  updatedAt: string;
}

export interface DashletView {
  id: string;
  title: string;
  text: string;
  intent: ChatIntent;
  payload: ChatPayload;
  stale: boolean;
}

export interface DashboardDetail {
  id: string;
  name: string;
  dashlets: DashletView[];
}

export interface SaveDashletInput {
  dashboardId?: string;
  name?: string;
  title: string;
  text: string;
  intent: DashletIntent;
  question: string;
  model?: string | null;
  payload: ChatPayload;
}

export function useDashboards() {
  return useQuery({
    queryKey: ["dashboards"],
    queryFn: async () => (await api.get<DashboardSummary[]>("/dashboards")).data,
  });
}

export function useDashboard(id: string) {
  return useQuery({
    queryKey: ["dashboard", id],
    queryFn: async () => (await api.get<DashboardDetail>(`/dashboards/${id}`)).data,
    enabled: !!id,
  });
}

export function useSaveDashboard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: SaveDashletInput) => (await api.post<DashboardDetail>("/dashboards/save", input)).data,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["dashboards"] });
      qc.invalidateQueries({ queryKey: ["dashboard", data.id] });
    },
  });
}

export function useDeleteDashlet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ dashboardId, dashletId }: { dashboardId: string; dashletId: string }) =>
      api.delete(`/dashboards/${dashboardId}/dashlets/${dashletId}`),
    onSuccess: (_data, { dashboardId }) => {
      qc.invalidateQueries({ queryKey: ["dashboard", dashboardId] });
      qc.invalidateQueries({ queryKey: ["dashboards"] });
    },
  });
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd app/web && npx tsc --noEmit`
Expected: no new errors from `src/api/dashboards.ts`.

- [ ] **Step 3: Commit**

```bash
git add app/web/src/api/dashboards.ts
git commit -m "feat(web): add dashboards API hooks"
```

---

### Task 6: Web — "Add to dashboard" button + `SaveDashboardModal`

**Files:**
- Create: `app/web/src/routes/chat/SaveDashboardModal.tsx`
- Modify: `app/web/src/routes/chat/ChatPage.tsx`

**Interfaces:**
- Consumes: `Modal`/`ModalHeader`/`ModalFooter` (existing, `app/web/src/components/ui/Modal.tsx`), `useDashboards`/`useSaveDashboard`/`DashletIntent` (Task 5), `useToast` (existing), `apiErrorMessage` (existing, `app/web/src/api/client.ts`).
- Produces: `SaveDashboardModal({ open, onClose, title, text, intent, model, payload })`. Task 8 does not depend on this — it's chat-only.

- [ ] **Step 1: Write the modal**

Create `app/web/src/routes/chat/SaveDashboardModal.tsx`:

```tsx
import { useEffect, useState } from "react";
import { LayoutDashboard } from "lucide-react";
import { Modal, ModalHeader, ModalFooter } from "../../components/ui/Modal";
import { useToast } from "../../stores/useToastStore";
import { apiErrorMessage } from "../../api/client";
import { useDashboards, useSaveDashboard, type DashletIntent } from "../../api/dashboards";
import type { ChatPayload } from "../../lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  text: string;
  intent: DashletIntent;
  model: string | null;
  payload: ChatPayload;
}

export function SaveDashboardModal({ open, onClose, title, text, intent, model, payload }: Props) {
  const { data: dashboards = [] } = useDashboards();
  const saveDashboard = useSaveDashboard();
  const { addToast } = useToast();
  const [mode, setMode] = useState<"new" | "existing">("new");
  const [name, setName] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setMode("new");
    setName("");
    setSelectedId(dashboards[0]?.id ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const canSave = mode === "new" ? name.trim().length > 0 : !!selectedId;

  const save = async () => {
    try {
      const targetName = mode === "existing" ? dashboards.find((d) => d.id === selectedId)?.name : name.trim();
      await saveDashboard.mutateAsync({
        dashboardId: mode === "existing" ? selectedId! : undefined,
        name: mode === "new" ? name.trim() : undefined,
        title,
        text,
        intent,
        question: title,
        model: model ?? undefined,
        payload,
      });
      addToast({
        icon: <LayoutDashboard size={16} />,
        accent: "var(--ac)",
        title: mode === "new" ? "Dashboard created" : "Added to dashboard",
        desc: `${targetName ?? "Your dashboard"} now includes this insight as a dashlet.`,
      });
      onClose();
    } catch (err) {
      addToast({ icon: <LayoutDashboard size={16} />, accent: "#e2603f", title: "Couldn't save", desc: apiErrorMessage(err) });
    }
  };

  return (
    <Modal open={open} onClose={onClose} width={460}>
      <ModalHeader title="Save as dashboard" onClose={onClose} />
      <div style={{ fontSize: 12.5, color: "var(--ac-muted)", marginTop: -8, marginBottom: 16 }}>Add "{title}" as a dashlet</div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 16 }}>
        <button
          onClick={() => setMode("new")}
          style={{
            padding: "10px 0",
            borderRadius: "var(--radius-sm)",
            border: `1px solid ${mode === "new" ? "var(--ac)" : "var(--ac-border)"}`,
            background: mode === "new" ? "var(--ac-soft)" : "#fff",
            color: mode === "new" ? "var(--ac-deep)" : "var(--ac-fg)",
            fontSize: 13,
            fontWeight: 700,
          }}
        >
          New dashboard
        </button>
        <button
          onClick={() => dashboards.length > 0 && setMode("existing")}
          disabled={dashboards.length === 0}
          style={{
            padding: "10px 0",
            borderRadius: "var(--radius-sm)",
            border: `1px solid ${mode === "existing" ? "var(--ac)" : "var(--ac-border)"}`,
            background: mode === "existing" ? "var(--ac-soft)" : "#fff",
            color: mode === "existing" ? "var(--ac-deep)" : "var(--ac-fg)",
            fontSize: 13,
            fontWeight: 700,
            opacity: dashboards.length === 0 ? 0.5 : 1,
          }}
        >
          Existing dashboard
        </button>
      </div>

      {mode === "new" ? (
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 11.5, fontWeight: 700, color: "var(--ac-muted)", marginBottom: 6 }}>Dashboard name</div>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Quick Commerce Growth"
            style={{ width: "100%", border: "1px solid var(--ac-border)", borderRadius: "var(--radius-sm)", padding: "10px 12px", fontSize: 13.5 }}
          />
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20, maxHeight: 220, overflowY: "auto" }}>
          {dashboards.map((d) => (
            <button
              key={d.id}
              onClick={() => setSelectedId(d.id)}
              style={{
                display: "flex",
                justifyContent: "space-between",
                textAlign: "left",
                padding: "10px 12px",
                borderRadius: "var(--radius-sm)",
                border: `1px solid ${selectedId === d.id ? "var(--ac)" : "var(--ac-border)"}`,
                background: selectedId === d.id ? "var(--ac-soft)" : "#fff",
                fontSize: 13,
                fontWeight: 700,
                color: selectedId === d.id ? "var(--ac-deep)" : "var(--ac-fg)",
              }}
            >
              <span>{d.name}</span>
              <span style={{ fontWeight: 500, color: "var(--ac-muted)" }}>{d.dashletCount} dashlets</span>
            </button>
          ))}
        </div>
      )}

      <ModalFooter>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <button onClick={onClose} style={{ padding: "10px 0", borderRadius: "var(--radius-sm)", border: "1px solid var(--ac-border)", background: "#fff", fontSize: 13.5, fontWeight: 700 }}>
            Cancel
          </button>
          <button
            onClick={save}
            disabled={!canSave || saveDashboard.isPending}
            style={{
              padding: "10px 0",
              borderRadius: "var(--radius-sm)",
              border: "none",
              background: "var(--ac)",
              color: "#fff",
              fontSize: 13.5,
              fontWeight: 700,
              opacity: !canSave || saveDashboard.isPending ? 0.6 : 1,
            }}
          >
            Save
          </button>
        </div>
      </ModalFooter>
    </Modal>
  );
}
```

- [ ] **Step 2: Wire the button into `ChatPage.tsx`**

In `app/web/src/routes/chat/ChatPage.tsx`, add to the imports (after the existing `import { AgentVisualization } from "./AgentVisualization";` on line 7):

```typescript
import { SaveDashboardModal } from "./SaveDashboardModal";
import type { DashletIntent } from "../../api/dashboards";
```

Add `LayoutDashboard` to the lucide-react import list (line 10-19):

```typescript
import {
  Sparkles,
  ArrowUp,
  ThumbsUp,
  ThumbsDown,
  AlertCircle,
  FileText,
  Compass,
  LineChart,
  Play,
  LayoutDashboard,
} from "lucide-react";
```

Add this helper function right after the `CONFIDENCE_COLOR` const (after line 33, before `export function ChatPage()`):

```typescript
/** The question that produced a given agent message: the nearest preceding
 * user message in the flat message list — one question can fan out to
 * several agent messages (one per intent), all sharing the same origin. */
function findQuestionFor(messages: ChatMessage[], agentId: string): string {
  const idx = messages.findIndex((m) => m.id === agentId);
  for (let i = idx - 1; i >= 0; i--) {
    if (messages[i].role === "user") return messages[i].text;
  }
  return "";
}
```

Add new state right after `const [openCitation, setOpenCitation] = useState<Citation | null>(null);` (line 54):

```typescript
  const [dashboardTarget, setDashboardTarget] = useState<{ title: string; text: string; intent: DashletIntent; model: string; payload: ChatPayload } | null>(null);
```

In the footer-row block (lines 253-271), replace:

```tsx
                    {!m.streaming && m.text && (
                      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--ac-border)" }}>
                        <button
                          onClick={() => vote(m.id, 1)}
                          style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11.5, fontWeight: 700, padding: "4px 9px", borderRadius: "var(--radius-sm)", color: m.vote === 1 ? "#0f8a5c" : "var(--ac-muted)", background: m.vote === 1 ? "#e6f7ef" : "transparent" }}
                        >
                          <ThumbsUp size={12} /> Helpful
                        </button>
                        <button
                          onClick={() => vote(m.id, -1)}
                          style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11.5, fontWeight: 700, padding: "4px 9px", borderRadius: "var(--radius-sm)", color: m.vote === -1 ? "#c0392b" : "var(--ac-muted)", background: m.vote === -1 ? "#fdeee9" : "transparent" }}
                        >
                          <ThumbsDown size={12} />
                        </button>
                        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--ac-muted)" }}>
                          {m.vote === 1 ? "Thanks — feeds insight accuracy" : m.vote === -1 ? "Noted — we'll improve routing" : "Was this helpful?"}
                        </span>
                      </div>
                    )}
```

with:

```tsx
                    {!m.streaming && m.text && (
                      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--ac-border)" }}>
                        <button
                          onClick={() => vote(m.id, 1)}
                          style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11.5, fontWeight: 700, padding: "4px 9px", borderRadius: "var(--radius-sm)", color: m.vote === 1 ? "#0f8a5c" : "var(--ac-muted)", background: m.vote === 1 ? "#e6f7ef" : "transparent" }}
                        >
                          <ThumbsUp size={12} /> Helpful
                        </button>
                        <button
                          onClick={() => vote(m.id, -1)}
                          style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11.5, fontWeight: 700, padding: "4px 9px", borderRadius: "var(--radius-sm)", color: m.vote === -1 ? "#c0392b" : "var(--ac-muted)", background: m.vote === -1 ? "#fdeee9" : "transparent" }}
                        >
                          <ThumbsDown size={12} />
                        </button>
                        {m.payload && (m.payload.chart || m.payload.table || (m.payload.actions && m.payload.actions.length > 0)) && (
                          <button
                            onClick={() =>
                              setDashboardTarget({
                                title: findQuestionFor(messages, m.id) || m.text.slice(0, 80),
                                text: m.text,
                                intent: (m.intent as DashletIntent) ?? "descriptive",
                                model,
                                payload: m.payload!,
                              })
                            }
                            style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11.5, fontWeight: 700, padding: "4px 9px", borderRadius: "var(--radius-sm)", color: "var(--ac-deep)", background: "var(--ac-soft)" }}
                          >
                            <LayoutDashboard size={12} /> Add to dashboard
                          </button>
                        )}
                        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--ac-muted)" }}>
                          {m.vote === 1 ? "Thanks — feeds insight accuracy" : m.vote === -1 ? "Noted — we'll improve routing" : "Was this helpful?"}
                        </span>
                      </div>
                    )}
```

Finally, right before the component's closing `</div>` (the last line, 367, just after the citation drawer block that ends at line 366), add:

```tsx
        {dashboardTarget && (
          <SaveDashboardModal
            open={true}
            onClose={() => setDashboardTarget(null)}
            title={dashboardTarget.title}
            text={dashboardTarget.text}
            intent={dashboardTarget.intent}
            model={dashboardTarget.model}
            payload={dashboardTarget.payload}
          />
        )}
```

- [ ] **Step 3: Verify it compiles**

Run: `cd app/web && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 4: Manual verification**

Start the app (see the `run` skill / project dev-server instructions). In Chat, ask a question that returns a chart (e.g. "revenue by region last quarter"). Confirm an "Add to dashboard" button appears next to Helpful/thumbs-down, opens the modal, and "New dashboard" → typing a name → Save shows a "Dashboard created" toast. Confirm a plain-text/general answer (no chart/table/actions) does NOT show the button.

- [ ] **Step 5: Commit**

```bash
git add app/web/src/routes/chat/SaveDashboardModal.tsx app/web/src/routes/chat/ChatPage.tsx
git commit -m "feat(web): add 'Add to dashboard' flow to chat"
```

---

### Task 7: Web — Insights "Overview" / "My dashboards" tabs

**Files:**
- Create: `app/web/src/routes/insights/DashboardsList.tsx`
- Modify: `app/web/src/routes/insights/InsightsPage.tsx`

**Interfaces:**
- Consumes: `useDashboards` (Task 5).
- Produces: `DashboardsList()` — empty state + card grid, navigates to `/insights/dashboards/:id` on card click (route added in Task 8).

- [ ] **Step 1: Write the dashboards list/empty-state component**

Create `app/web/src/routes/insights/DashboardsList.tsx`:

```tsx
import { useNavigate } from "react-router-dom";
import { LayoutDashboard } from "lucide-react";
import { useDashboards } from "../../api/dashboards";

export function DashboardsList() {
  const { data: dashboards = [], isLoading } = useDashboards();
  const navigate = useNavigate();

  if (isLoading) return null;

  if (dashboards.length === 0) {
    return (
      <div style={{ background: "#fff", border: "1px dashed var(--ac-border)", borderRadius: 16, padding: 48, textAlign: "center" }}>
        <div style={{ width: 44, height: 44, borderRadius: "var(--radius-lg)", background: "var(--ac-soft)", color: "var(--ac)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 14px" }}>
          <LayoutDashboard size={22} />
        </div>
        <div style={{ fontSize: 15, fontWeight: 800, marginBottom: 6 }}>No dashboards yet</div>
        <div style={{ fontSize: 12.5, color: "var(--ac-muted)", maxWidth: 360, margin: "0 auto 18px" }}>
          Ask Datacon a question in chat, then hit "Add to dashboard" on any insight to start building one.
        </div>
        <button
          onClick={() => navigate("/chat")}
          style={{ background: "var(--ac)", color: "#fff", fontWeight: 700, fontSize: 13, padding: "9px 18px", borderRadius: "var(--radius-sm)" }}
        >
          Go to chat →
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 14 }}>
      {dashboards.map((d) => (
        <button
          key={d.id}
          onClick={() => navigate(`/insights/dashboards/${d.id}`)}
          style={{ textAlign: "left", background: "#fff", border: "1px solid var(--ac-border)", borderRadius: 16, padding: 18 }}
        >
          <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 2, background: "var(--ac)", marginBottom: 10 }} />
          <div style={{ fontSize: 14.5, fontWeight: 800 }}>{d.name}</div>
          <div style={{ fontSize: 12, color: "var(--ac-muted)", marginTop: 4 }}>{d.dashletCount} dashlet{d.dashletCount === 1 ? "" : "s"}</div>
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Add the tab toggle to `InsightsPage.tsx`**

In `app/web/src/routes/insights/InsightsPage.tsx`, replace the import line:

```typescript
import { useNavigate } from "react-router-dom";
```

with:

```typescript
import { useNavigate, useSearchParams } from "react-router-dom";
```

Add two new imports right after `import { Skeleton, KpiCardSkeleton, ChartCardSkeleton } from "../../components/ui/Skeleton";`:

```typescript
import { useDashboards } from "../../api/dashboards";
import { DashboardsList } from "./DashboardsList";
```

Inside `InsightsPage()`, right after `const navigate = useNavigate();` (line 16), add:

```typescript
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") === "dashboards" ? "dashboards" : "overview";
  const { data: dashboards } = useDashboards();
```

Replace the header block's closing and the start of the KPI grid — i.e. replace:

```tsx
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 14, marginBottom: 20 }}>
```

(this is the `</div>` that closes the `todayLabel`/greeting/live-syncs header row, immediately followed by the KPI grid) with:

```tsx
      </div>

      <div style={{ display: "flex", gap: 4, marginBottom: 20, borderBottom: "1px solid var(--ac-border)" }}>
        <button
          onClick={() => setSearchParams({}, { replace: true })}
          style={{ padding: "10px 14px", fontSize: 13, fontWeight: 700, color: tab === "overview" ? "var(--ac-deep)" : "var(--ac-muted)", borderBottom: tab === "overview" ? "2px solid var(--ac)" : "2px solid transparent" }}
        >
          Overview
        </button>
        <button
          onClick={() => setSearchParams({ tab: "dashboards" }, { replace: true })}
          style={{ padding: "10px 14px", fontSize: 13, fontWeight: 700, color: tab === "dashboards" ? "var(--ac-deep)" : "var(--ac-muted)", borderBottom: tab === "dashboards" ? "2px solid var(--ac)" : "2px solid transparent" }}
        >
          My dashboards · {dashboards?.length ?? 0}
        </button>
      </div>

      {tab === "dashboards" ? (
        <DashboardsList />
      ) : (
        <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 14, marginBottom: 20 }}>
```

Then, right before the component's final closing `</div>` and `);` (originally lines 154-155 — the `</div>` closing the outer `padding: 32` wrapper, immediately after the Ask-Datacon button's closing `</button>`), close the new fragment: replace:

```tsx
      </button>
    </div>
  );
}
```

with:

```tsx
      </button>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify it compiles**

Run: `cd app/web && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 4: Manual verification**

Start the app, navigate to Insights. Confirm "Overview"/"My dashboards · 0" tabs render, "My dashboards" shows the empty state with a working "Go to chat →" button, and after saving a dashlet from Task 6 the count updates and a card appears.

- [ ] **Step 5: Commit**

```bash
git add app/web/src/routes/insights/DashboardsList.tsx app/web/src/routes/insights/InsightsPage.tsx
git commit -m "feat(web): add My dashboards tab to Insights"
```

---

### Task 8: Web — `CitationDrawer` extraction + `DashboardDetailPage`

**Files:**
- Create: `app/web/src/components/common/CitationDrawer.tsx`
- Modify: `app/web/src/routes/chat/ChatPage.tsx`
- Create: `app/web/src/routes/insights/DashboardDetailPage.tsx`
- Modify: `app/web/src/App.tsx`

**Interfaces:**
- Consumes: `Citation` type (existing, `@datacon/shared-types`), `AgentVisualization` (existing, `app/web/src/routes/chat/AgentVisualization.tsx`), `useDashboard`/`useDeleteDashlet` (Task 5).
- Produces: `CitationDrawer({ citation, onClose })`, used by both `ChatPage` and the new `DashboardDetailPage`. Route `/insights/dashboards/:id`.

- [ ] **Step 1: Extract the citation drawer**

Create `app/web/src/components/common/CitationDrawer.tsx`:

```tsx
import type { Citation } from "@datacon/shared-types";

export function CitationDrawer({ citation, onClose }: { citation: Citation | null; onClose: () => void }) {
  if (!citation) return null;
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 40, background: "rgba(0,0,0,0.3)" }}>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ position: "absolute", right: 0, top: 0, height: "100%", width: "min(480px, 100%)", background: "#fff", borderLeft: "1px solid var(--ac-border)", padding: 24, overflowY: "auto" }}
      >
        <div style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--ac-muted)" }}>SOURCE CITATION</div>
        <div style={{ fontSize: 19, fontWeight: 800, marginTop: 8 }}>{citation.documentTitle}</div>
        <div style={{ font: "500 11px 'IBM Plex Mono',monospace", color: "var(--ac-muted)", marginTop: 4 }}>
          {citation.filename} · chunk {citation.chunkIndex}
        </div>
        <div style={{ fontSize: 13, lineHeight: 1.6, color: "var(--ac-fg)", marginTop: 16, background: "var(--ac-bg-muted)", border: "1px solid var(--ac-border)", borderRadius: "var(--radius-sm)", padding: 14, whiteSpace: "pre-wrap" }}>
          {citation.snippet}
        </div>
        <button onClick={onClose} style={{ marginTop: 20, padding: "8px 14px", borderRadius: "var(--radius-sm)", background: "var(--ac-bg-muted)", border: "1px solid var(--ac-border)", fontSize: 12.5, fontWeight: 600 }}>
          Close
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Use it from `ChatPage.tsx`**

In `app/web/src/routes/chat/ChatPage.tsx`, add the import (alongside the other new imports from Task 6):

```typescript
import { CitationDrawer } from "../../components/common/CitationDrawer";
```

Replace the entire inline citation drawer block (the `{openCitation && ( ... )}` block, originally lines 331-366) with:

```tsx
        <CitationDrawer citation={openCitation} onClose={() => setOpenCitation(null)} />
```

- [ ] **Step 3: Verify no regression**

Run: `cd app/web && npx tsc --noEmit`
Expected: no new errors. Manually: in Chat, ask a question grounded in an uploaded Data Source so a citation chip appears; click it; confirm the same side drawer opens/closes as before.

- [ ] **Step 4: Write `DashboardDetailPage`**

Create `app/web/src/routes/insights/DashboardDetailPage.tsx`:

```tsx
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { X } from "lucide-react";
import type { Citation } from "@datacon/shared-types";
import { useDashboard, useDeleteDashlet } from "../../api/dashboards";
import { AgentVisualization } from "../chat/AgentVisualization";
import { CitationDrawer } from "../../components/common/CitationDrawer";
import type { ChatMessage } from "../../lib/types";

export function DashboardDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { data, isLoading } = useDashboard(id);
  const deleteDashlet = useDeleteDashlet();
  const [openCitation, setOpenCitation] = useState<Citation | null>(null);

  return (
    <div style={{ padding: 32, maxWidth: 1180, margin: "0 auto" }}>
      <button onClick={() => navigate("/insights?tab=dashboards")} style={{ fontSize: 12.5, fontWeight: 700, color: "var(--ac-muted)", marginBottom: 12 }}>
        ← All dashboards
      </button>
      <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 20 }}>{data?.name ?? (isLoading ? "" : "Dashboard")}</h1>

      {!isLoading && data && data.dashlets.length === 0 && <div style={{ color: "var(--ac-muted)", fontSize: 13.5 }}>No dashlets yet.</div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 16 }}>
        {data?.dashlets.map((d) => {
          const message: ChatMessage = { id: d.id, role: "agent", intent: d.intent, text: d.text, payload: d.payload, vote: 0 };
          return (
            <div key={d.id} style={{ background: "#fff", border: "1px solid var(--ac-border)", borderRadius: "var(--radius-lg)", padding: 18 }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{d.title}</div>
                  <div style={{ fontSize: 12, color: "var(--ac-muted)", marginTop: 2 }}>{d.text}</div>
                </div>
                <button
                  onClick={() => deleteDashlet.mutate({ dashboardId: id, dashletId: d.id })}
                  style={{ color: "var(--ac-muted)", flexShrink: 0 }}
                  aria-label="Remove dashlet"
                >
                  <X size={16} />
                </button>
              </div>
              {d.stale && (
                <div style={{ fontSize: 10.5, fontWeight: 700, color: "#a3730c", background: "#fdf3e3", display: "inline-block", padding: "2px 8px", borderRadius: 20, marginTop: 8 }}>
                  Showing last known data
                </div>
              )}
              <AgentVisualization message={message} onOpenCitation={setOpenCitation} />
            </div>
          );
        })}
      </div>

      <CitationDrawer citation={openCitation} onClose={() => setOpenCitation(null)} />
    </div>
  );
}
```

- [ ] **Step 5: Register the route**

In `app/web/src/App.tsx`, add the import after `import { InsightsPage } from "./routes/insights/InsightsPage";`:

```typescript
import { DashboardDetailPage } from "./routes/insights/DashboardDetailPage";
```

Add the route right after the `/insights` route (`<Route path="/insights" element={<ErrorBoundary><InsightsPage /></ErrorBoundary>} />`):

```tsx
        <Route path="/insights/dashboards/:id" element={<ErrorBoundary><DashboardDetailPage /></ErrorBoundary>} />
```

- [ ] **Step 6: Verify it compiles**

Run: `cd app/web && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 7: Manual end-to-end verification**

Start the app. From Chat, save a chart-bearing answer to a new dashboard. Go to Insights → My dashboards, click the card. Confirm: breadcrumb navigates back to the dashboards tab, the dashlet renders its chart via the same visualization as chat, a citation (if present) opens the same side drawer, and the "×" removes the dashlet (card disappears, count updates). Disconnect/stop the AI service and reload the dashboard to confirm the stale-fallback "Showing last known data" badge appears instead of a broken card.

- [ ] **Step 8: Commit**

```bash
git add app/web/src/components/common/CitationDrawer.tsx app/web/src/routes/chat/ChatPage.tsx app/web/src/routes/insights/DashboardDetailPage.tsx app/web/src/App.tsx
git commit -m "feat(web): add dashboard detail page reusing chat's visualization"
```

---

## Self-Review Notes

- **Spec coverage:** data model (Task 1), AI live-refresh endpoint (Task 2), API save/list/detail/delete (Tasks 3-4), chat button + modal (Task 6), Insights tabs + empty state + list (Task 7), dashboard detail + stale fallback (Task 8), web hooks tying it together (Task 5) — every spec section has a task.
- **Type consistency checked:** `DashletIntent` (Task 3's DTO, Task 5's hook file, Task 6's button) all use the same four lowercase strings; `DashboardsService.detail()`'s returned shape (`{id, title, text, intent, payload, stale}`) matches `DashletView` in Task 5 exactly, which `DashboardDetailPage` (Task 8) consumes unchanged.
- **No placeholders:** every step has literal, complete code — nothing marked TBD or "similar to above."
