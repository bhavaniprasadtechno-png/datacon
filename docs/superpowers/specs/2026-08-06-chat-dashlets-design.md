# Chat → dashboard dashlets

## Context

The design mockup (`Datacon.dc.html`, screens `chat-save-modal.png`, `chat-to-dashboard.png`, `dash-list.png`, `dash-detail.png`/`dash-detail2.png`) adds a way to save any visual chat answer as a "dashlet" onto a personal dashboard, surfaced under Insights. Verified live in the mockup:

- Every agent chat message with visual content gets an **"Add to dashboard"** button in the footer row (next to Helpful/thumbs-down).
- Clicking it opens a **"Save as dashboard"** modal: toggle between **New dashboard** (name input) and **Existing dashboard** (list of the user's dashboards, each showing its dashlet count). One **Save** button either way. A toast confirms ("Dashboard created" / dashlet added).
- The Insights page gains an **"Overview" / "My dashboards · N"** tab toggle next to the existing KPI/forecast content.
- The dashboards tab, empty, shows: icon + "No dashboards yet" + "Ask Datacon a question in chat, then hit 'Add to dashboard' on any insight to start building one." + a "Go to chat →" button.
- Non-empty, it's a card grid: dashboard name + dashlet count per card.
- Opening a card shows a **"← All dashboards"** breadcrumb, the dashboard name, and a grid of dashlet cards. Each dashlet card has a title (the original question), a text snippet, the chart, and a "×" to remove it from the dashboard.

## Decisions from brainstorming

1. **Dashlet content**: full `AgentPayload` (chart + table + citations + actions), not chart-only — reuse `AgentVisualization` as-is for rendering.
2. **Data freshness**: live. A dashlet stores the original natural-language question + intent + model, and viewing a dashboard replays that question through the AI service's existing deterministic per-intent `prepare()` functions (`app/ai/app/agents/{descriptive,diagnostic,predictive,prescriptive}.py`). These already re-run the SQL/data fetch fresh on every call and require **no LLM cost** — prose generation is a separate stage those functions don't invoke. So "live" is free to implement: no query-lineage storage, no repeated LLM calls, just replay the question.
3. **CRUD scope**: create dashboard, add dashlet (new or existing dashboard), remove dashlet — matching exactly what the mockup demonstrates. No dashboard rename/delete in this pass.

## Data model

Two new tables, following the existing `Organization`-scoped pattern used throughout `schema.prisma`. No changes to `Conversation`/`Message`.

```prisma
model Dashboard {
  id        String   @id @default(cuid())
  orgId     String
  org       Organization @relation(fields: [orgId], references: [id])
  userId    String   @db.Uuid          // owner — "My dashboards" is per-user, not org-shared
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
  title       String    // frozen: the question that produced this answer
  text        String    // frozen: the agent's answer text, for context
  intent      Intent    // DESCRIPTIVE | DIAGNOSTIC | PREDICTIVE | PRESCRIPTIVE (reuses existing enum)
  question    String    // original NL question — replayed live on every dashboard view
  model       String?   // LLM model id used for the original answer, replayed for consistency
  payload     Json      // last-known-good AgentPayload — fallback if live refresh fails
  createdAt   DateTime  @default(now())          // also drives display order — no reordering in this pass

  @@map("dashlets")
}
```

Add `dashboards Dashboard[]` and `dashlets Dashlet[]` back-relations to `Organization`, and `dashboards Dashboard[]` to `User`.

`Intent` excludes `general` deliberately — general-agent answers carry no chart/table/actions (see gating rule below), so they're never dashlet-able.

## AI service change

One new endpoint in `app/ai/app/internal/chat_router.py`, reusing the existing `_ANALYSTS` dispatch table already defined in that file:

```python
class AnswerPayload(BaseModel):
    question: str
    intent: str
    model: str | None = None

@router.post("/answer")
async def answer(payload: AnswerPayload):
    prep = await _ANALYSTS[payload.intent](payload.question, payload.model)
    return {"payload": prep.payload}
```

No new agent logic — `descriptive.prepare` / `diagnostic.prepare` / `predictive.prepare` / `prescriptive.prepare` already compute their payload from a live data fetch, independent of the LLM prose stage.

## API (NestJS)

New `app/api/src/dashboards/` module (mirrors `insights/`), gated by the existing `view_dashboards` permission — no new permission needed.

- `GET /dashboards` — current user's dashboards with dashlet counts (list view).
- `POST /dashboards/save` — body `{ dashboardId?, name?, title, text, intent, question, model, payload }`. Creates a new dashboard when `dashboardId` is omitted (requires `name`); otherwise appends a dashlet to the given dashboard. One endpoint for both modal paths since it's a single Save action either way.
- `GET /dashboards/:id` — detail. For each dashlet, call the AI service's `POST /internal/chat/answer` with `{question, intent, model}` in parallel (`Promise.allSettled`). On success, return the live payload; on failure, return the stored `payload` with `stale: true`.
- `DELETE /dashboards/:id/dashlets/:dashletId` — remove a dashlet.

All queries scoped by `orgId` (existing `OrgContextInterceptor`/RLS) **and** `userId = current user` — dashboards are private to their owner, matching "My dashboards."

## Frontend

- **`ChatPage.tsx`**: add an "Add to dashboard" button to the existing footer row (next to Helpful/thumbs-down), visible only when `m.payload` has a `chart`, `table`, or `actions` key — nothing to save for a plain-text/general answer. The originating question is the text of the nearest preceding user message in `messages`, already in local state — no new field needed on `ChatMessage`.
- **New `SaveDashboardModal`**: New/Existing dashboard toggle, name input, dashboard picker list (name + dashlet count), Cancel/Save — matches the mockup. On success, toast + close.
- **`InsightsPage.tsx`**: add the "Overview" / "My dashboards · N" tab toggle, driven by a `?tab=dashboards` query param (linkable, back-button-friendly). Dashboards tab renders the empty state or a card grid (`useDashboards()`).
- **New `DashboardDetailPage`** at `/insights/dashboards/:id`: "← All dashboards" breadcrumb, dashboard name, grid of dashlet cards. Each card renders through the **existing** `AgentVisualization` component, given a synthetic `{ payload }` — reusing the same chart/table/citations/actions rendering chat already has, not a new renderer — plus a "×" (calls the delete endpoint, optimistic removal).

## Error handling

If the AI service's live-refresh call fails for a dashlet (connector down, underlying data deleted, AI service unavailable), the dashboard detail response falls back to that dashlet's stored `payload` and marks it `stale: true`; the card renders normally with a small "showing last known data" indicator instead of breaking.

## Testing

- `dashboards.service.ts`: unit tests for save-new vs. save-existing dashboard branching, and that list/detail queries are scoped to the requesting user (not just org).
- One test for the live-refresh-fails-falls-back-to-cached-payload path in the detail endpoint.
- AI service: a thin test for the new `/internal/chat/answer` endpoint asserting it dispatches to the correct `_ANALYSTS` entry and returns only `payload` (no LLM call).

## Out of scope

- Dashboard rename/delete, dashlet reordering/drag-drop.
- Org-shared/team dashboards (this is "My dashboards" — per-user only).
- Any change to `Conversation`/`Message` schema — the question text needed for replay is read from existing chat state, not persisted onto `Message`.
