# Chat agent payload parity with datavue

Follow-up to `2026-07-14-free-form-chat-grounding-design.md`, and to the
temperature/timeout fixes made in the same debugging session as this spec.
That work made chat answers *deterministic* and *fast-failing*; this spec
makes them *visually complete* — bringing datacon's chat responses up to the
level of detail shown in the reference implementation at
`C:\Users\pc\Desktop\datavue` (insight text + query table + chart +
citations + confidence, per answer) without adopting datavue's
LLM-authored-JSON-envelope architecture, which datacon deliberately avoided
in favor of deterministic Python-computed payloads.

## Problem

Each of the four chat agents (`descriptive`, `diagnostic`, `predictive`,
`prescriptive`) is hardcoded to one visual in `AgentVisualization.tsx`,
branched on `message.intent`:

- `descriptive` → a bare table, no chart, even when the result is a small
  categorical comparison that would read better as a bar chart.
- `diagnostic` → citations only. The day-by-day counts behind "region rose
  40% vs baseline" are computed in `diagnostic.py` but never shown — the user
  has to take the prose's word for it.
- `predictive` → a line chart of history only. The forecast's own confidence
  interval (`ci_low`/`ci_high`, already computed) never reaches the chart.
- `prescriptive` → an actions table only, no citations even when supporting
  documents exist.

None of the four carry a confidence signal, so a low-confidence answer (no
data connected, no citation found, high forecast error) looks identical to a
high-confidence one.

## Goal

Every agent's payload can carry any combination of: a data table, a chart,
citations, a recommendations list, and a confidence level — computed
deterministically in Python from real facts (unchanged architectural
principle), not authored by the LLM. The frontend renders whichever of
these fields are present, rather than branching on which intent produced
them.

## Shared types

`app/packages/shared-types/src/chat.ts`'s four separate payload interfaces
(`DescriptivePayload`, `DiagnosticPayload`, `PredictivePayload`,
`PrescriptivePayload`) are replaced with one:

```ts
export type Confidence = "high" | "medium" | "low";

export interface AgentTable {
  columns: string[];
  rows: (string | number | boolean | null)[][];
}

export interface ChartPoint {
  label: string;
  value: number;
  lower?: number;
  upper?: number;
}

export interface AgentChart {
  type: "bar" | "line";
  title: string;
  data: ChartPoint[];
}

export interface Citation {
  id: number;
  documentTitle: string;
  filename: string;
  chunkIndex: number;
  snippet: string;
}

export interface PrescriptiveAction {
  title: string;
  impact: string;
  effort: string;
  owner: string;
}

export interface AgentPayload {
  confidence: Confidence;
  table?: AgentTable;
  chart?: AgentChart;
  citations?: Citation[];
  actions?: PrescriptiveAction[];
  correlation?: string;
}

export type ChatPayload = AgentPayload;
```

This is a breaking type change, but `ChatPayload` has no consumers outside
this app's own backend/frontend — no compatibility shim needed.
`app/web/src/lib/types.ts`'s `ChatMessage.payload: ChatPayload | null`
is unchanged in shape, just references the new type.

`chat_router.py` needs no changes: it already forwards `prep.payload`
untouched in the `agent_done` SSE frame (`{"intent", "text", "payload"}`).

## Confidence rules

Deterministic, computed in Python alongside the rest of each agent's
`payload`, no LLM involvement:

- **descriptive**: `"high"` if the query returned rows, `"low"` if the query
  failed or came back empty.
- **diagnostic**: `"high"` if a citation was found and correlates with the
  spike, `"medium"` if a spike was detected but no citation, `"low"` if no
  day-by-day data is connected.
- **predictive**: from the existing MAPE — `"high"` if MAPE < 15%, `"medium"`
  if < 30%, `"low"` otherwise. Mirrors datavue's "flag uncertainty when
  r_squared is low" rule, adapted to the fit metric this codebase already
  computes (MAPE, not r_squared).
- **prescriptive**: `"high"` if churn data is connected, `"low"` if not.

## Per-agent payload changes

All four `prepare()` functions keep their existing computations; only what
goes into `payload` changes.

**`descriptive.py`**
- `table`: unchanged, the existing `{columns, rows}`.
- `chart`: added only when the result "looks categorical" — exactly 2
  columns, the second fully numeric, row count between 2 and 20 inclusive.
  Then `{type: "bar", title: f"{columns[1]} by {columns[0]}", data: [{label:
  str(row[0]), value: float(row[1])} for row in rows]}`. Omitted otherwise.
- `confidence`: per the rule above.

**`diagnostic.py`**
- `table`: the `daily` list it already computes (region/count pairs behind
  the spike), as `{columns: ["region", "count"], rows: [[d["region"],
  d["count"]] for d in daily]}`.
- `citations` / `correlation`: unchanged.
- `confidence`: per the rule above.

**`predictive.py`**
- `table`: history rows as `{columns: ["period", "revenue"], rows:
  [[f"p{i}", v] for i, v in enumerate(series)]}` plus one appended
  `["forecast", forecast["projected"]]` row.
- `chart`: history points unchanged (`{label: f"p{i}", value: v}`), plus one
  appended point `{label: "forecast", value: forecast["projected"], lower:
  forecast["ci_low"], upper: forecast["ci_high"]}`. This shows the CI band on
  the chart without changing the forecasting math itself — Holt-Winters
  computes a single end-of-horizon point + CI today, not a per-month path, and
  extending it to a full path is out of scope here (it's a forecasting-module
  change, not a display-format change).
- `confidence`: per the rule above.

**`prescriptive.py`**
- `citations`: new. Reuses the same `chroma_query` call pattern
  `diagnostic.py` already uses: `chroma_query(question or "churn retention
  billing incident", n_results=2)` — the fallback string only applies when
  `question` is empty, exactly mirroring diagnostic's own `chroma_query(question
  or "billing incident ticket spike EMEA", n_results=2)` call. Same citation
  shape as diagnostic. Omitted (key absent) if no hits.
- `actions`: unchanged.
- `confidence`: per the rule above.

All four "no data connected" early-return branches simplify to
`payload={"confidence": "low"}` — no more empty-placeholder fields like
`{"citations": [], "correlation": None}`. The frontend checks "is this field
present," not "is this field non-empty."

## Frontend rendering

`AgentVisualization.tsx` drops all `message.intent === X` branching in favor
of straight-line composition by field presence:

```tsx
{payload.correlation && <CorrelationTag text={payload.correlation} />}
{payload.chart && <AgentChart chart={payload.chart} />}
{payload.table && <DataTable table={payload.table} />}
{payload.citations && <Citations items={payload.citations} onOpen={onOpenCitation} />}
{payload.actions && <ActionsTable items={payload.actions} />}
```

`DataTable`, `Citations`, and `ActionsTable` are the existing
descriptive/diagnostic/prescriptive JSX blocks, extracted into standalone
components (no behavior change, just de-duplicated from the intent
branches). `confidence` is not rendered here at all — see the UX parity
section below for why it moved to `ChatPage.tsx`'s message header instead of
a body badge.

`AgentChart` is new, built on `recharts` (already a `package.json`
dependency, currently unused anywhere in the app) rather than the hand-rolled
`<svg><polyline>` the predictive chart uses today. `type: "bar"` renders as
recharts' `BarChart`; `type: "line"` as `LineChart`. The forecast point's
`lower`/`upper` aren't drawn as an on-chart CI band — the existing
PROJECTED/95% CI/GROWTH stat row (already in today's predictive card, just
below the chart) is derived straight from the last two `chart.data` points
instead, matching current visual fidelity without adding formatted-string
fields back onto the payload.

## UX parity: badge icons, header confidence, citation drawer

Beyond the payload/rendering work above, three interaction details from
datavue's chat are ported to close the experience gap, on top of
`ChatPage.tsx`'s existing per-agent card layout (which already matches
datavue's one-card-per-agent structure):

- **Icon per intent badge**: `ChatPage.tsx`'s per-message intent badge
  (currently just colored text) gains an icon, reusing the same
  `FileText`/`Compass`/`LineChart`/`Play` icons already used for the
  empty-state suggestion cards in this file — one icon per intent, used
  consistently everywhere in this app, rather than importing datavue's
  different icon set (`ChartBar`/`MagnifyingGlass`/`TrendUp`/`Target`).
- **Confidence moves to the card header**: a plain colored text label
  (`"High confidence"` / `"Medium confidence"` / `"Low confidence"`,
  green/amber/gray) right-aligned in the same header row as the intent
  badge, shown once streaming finishes and a payload exists — matching
  datavue's `Confidence: {level}` header placement. This replaces the
  `ConfidenceBadge`-in-body approach floated earlier in this spec.
- **Citations become chips + a slide-in drawer**: `Citations` in
  `AgentVisualization.tsx` renders a row of small clickable chips
  (`[1] Document Title…`) instead of always-expanded blocks. Clicking one
  calls `onOpenCitation(citation)`, a new prop threaded
  `ChatPage.tsx` → `AgentVisualization` → `Citations` → `CitationChip`.
  `ChatPage.tsx` lifts `openCitation: Citation | null` state and renders a
  fixed right-side drawer (overlay + panel) showing the full document title,
  filename, chunk index, and snippet. Applies uniformly to both diagnostic's
  and prescriptive's citations — both already share the same `Citation[]`
  shape, so no special-casing needed.

This touches `ChatPage.tsx` in addition to `AgentVisualization.tsx` — the
intent-badge icons and confidence header text render there directly, and it
owns the new `openCitation` drawer state.

## Error handling

No new error surface: `payload` is built from real computed facts *before*
the LLM call in every agent (already true today), so a failed or slow LLM
call — now bounded by the `timeout=20` fix made earlier in this session —
only ever affects `text`, never `table`/`chart`/`confidence`. The frontend
needs only the usual empty-data guards (e.g. avoid divide-by-zero when all
chart values are equal, matching the existing `(max - min || 1)` pattern).

## Testing

- `app/ai/tests/agents/test_agents.py` (existing): add assertions for the new
  `table`/`chart`/`citations`/`confidence` fields per agent, and for the
  simplified `{"confidence": "low"}` no-data branches.
- `app/ai/tests/internal/test_chat_router.py` (existing): confirm the SSE
  `agent_done` frame still carries `payload` untouched.
- No frontend test runner exists in `app/web` today. `AgentVisualization`
  and `ChatPage` changes are verified manually: run the app and drive one
  question per intent (descriptive/diagnostic/predictive/prescriptive)
  through chat, confirming each renders its full available section set, the
  intent badge shows its icon, confidence text appears in the header once
  streaming finishes, and clicking a citation chip opens the drawer with the
  correct document/snippet — the same live-verification approach used
  earlier in this session.
