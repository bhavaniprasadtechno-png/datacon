# Chat agent response — round 2 parity gaps (recommendation cards, CI band, distribution chart)

Follow-up to `2026-07-15-chat-agent-payload-parity-design.md` and
`2026-07-16-query-result-sanitization-design.md`. Those specs brought every
agent's payload up to "insight + table + chart + citations + confidence" and
fixed the descriptive table's raw-value display bugs found while
live-testing a real "give leads" question. This spec closes three gaps found
comparing the result against the reference implementation at
`C:\Users\pc\Desktop\datavue` in more depth:

1. **Prescriptive recommendations** render as a bare grid (title/impact/
   effort/owner) — the payload-parity spec explicitly left `actions`
   "unchanged," so this is a clean extension, not a reversal.
2. **Predictive chart** has no visual confidence-interval band — the
   payload-parity spec explicitly chose not to draw one, "without adding
   formatted-string fields back onto the payload." This spec doesn't add any
   payload fields (`lower`/`upper` are already plain numbers on
   `chart.data`); it only changes how that already-present data renders. It
   supersedes that one specific rendering choice, not the payload shape the
   prior spec deliberately preserved.
3. **Descriptive auto-chart** only fires when the whole query result is
   exactly 2 columns, 2–20 rows (`_looks_categorical`). It can't add a
   secondary "count by category" distribution chart next to a wider
   raw-records table — e.g. a Leads table with Name/Email/Company/Status/
   Source columns, where a status-distribution bar chart should sit
   alongside the raw table, as datavue's reference does.

## Gap ① — Prescriptive recommendation cards

**Shared types** (`app/packages/shared-types/src/chat.ts`) — `PrescriptiveAction` gains three fields:

```ts
export interface PrescriptiveAction {
  title: string;
  impact: string;
  effort: "Low" | "Medium" | "High";
  owner: string;
  rationale: string;
  expectedImpact: string;
  citationIds?: number[];
}
```

**Backend** (`app/ai/app/agents/prescriptive.py`) — the 3 hardcoded action
templates each gain a `rationale` and `expectedImpact` string, templated from
the same real numbers already computed (`churn_pct`, `at_risk_accounts`,
`target`) — no LLM authorship, consistent with this codebase's deterministic-
payload principle:

- **Save-offer action**: rationale explains these accounts show renewal-risk
  signals in the churn data; `expectedImpact` states the ~0.4pp reduction
  against the `at_risk_accounts` count.
- **Billing-fix action**: rationale ties billing errors to support-ticket
  volume as a churn driver; `expectedImpact` states the ~0.2pp reduction.
- **Usage-alert action**: rationale frames low seat utilization as a leading
  non-renewal indicator; `expectedImpact` states the ~0.1pp reduction.

Citation assignment moves from one shared `chroma_query` call for the whole
payload to one topic-scoped query per action (e.g. the billing action
queries `"billing error incident"`, the usage action queries `"usage
adoption seat utilization"`). Hits are deduplicated across actions by
`(filename, chunkIndex)` into a single running `citations` list with stable
sequential ids; each action's `citationIds` references only the ids from its
own query. `payload["citations"]` remains the deduped union, as today, so
the citation drawer keeps working unmodified.

**Frontend** (`app/web/src/routes/chat/AgentVisualization.tsx`) — `ActionsTable`
(plain grid) is replaced by a `RecommendationCard` list modeled on datavue's
`RecommendationsBlock`: a numbered circle badge, title, color-coded effort
badge, owner tag, rationale line, expected-impact line, and `CitationChip`s
(reusing the existing chip component) resolved from `citationIds` against
`payload.citations`. Same visual language (borders, radii, type scale) as
the rest of `AgentVisualization.tsx` — no new design system introduced.

## Gap ② — Predictive confidence-interval band

No payload/shared-types change. `app/web/src/routes/chat/AgentChart.tsx` already
computes `hasForecast` (true when the last chart point carries `lower`/
`upper`) for the stat-tile row below the chart. When `chart.type === "line"`
and `hasForecast` is true, the chart itself switches from `LineChart` to
`ComposedChart` with two additional layers before the existing `Line`,
matching datavue's `ChartBlock` technique:

- `<Area dataKey="lower" stroke="none" fill="var(--ac)" fillOpacity={0} legendType="none" />` — invisible, anchors the band's floor.
- `<Area dataKey="upper" stroke="none" fill="var(--ac)" fillOpacity={0.12} legendType="none" />` — the visible translucent band from the floor up to `upper`.

Historical points don't carry `lower`/`upper`, so recharts treats those keys
as gaps and the band only shades the forecast segment. The stat-tile row
(`PROJECTED`/`95% CI`/`GROWTH`) is unchanged — the chart adds a visual
signal, it doesn't replace the numbers. When `hasForecast` is false (a plain
line chart with no forecast point), rendering is unchanged (`LineChart`, no
`Area`s). Bar charts are untouched entirely.

## Gap ③ — Descriptive distribution chart from a wide table

**New executor helper** (`app/ai/app/query_engine/executor.py`) — `grouped_count(base_sql: str, column: str) -> QueryAnswer`:
strips a trailing `;` from `base_sql` and executes

```sql
SELECT "{column}" AS label, COUNT(*) AS value
FROM ({base_sql}) AS _dc_dist
GROUP BY "{column}"
ORDER BY value DESC
LIMIT 20
```

through the same `_execute_with_timeout` / `_is_safe_select` path
`answer_question` already uses. No LLM call — this reuses the exact SQL
`answer_question` already generated and validated for the original
question (available as `QueryAnswer.sql`), guaranteeing the distribution is
computed over the same underlying table/filter, not a re-interpreted one.

**Column-picker heuristic** (new function in `app/ai/app/agents/descriptive.py`,
e.g. `_pick_distribution_column(columns, rows)`) — scans the **full**
fetched result (`result.columns`/`result.rows`, up to the executor's
existing `ROW_LIMIT` of 500 — not just the 20 rows shown in the table) for
the first column where:

- every non-null value is a string,
- the column name doesn't match an id/email/name/url/phone/date-shaped
  denylist (`id`, `email`, `name`, `url`, `phone`, `date`, `created`,
  `updated`, `title`, `description` — case-insensitive substring match),
- the number of distinct values is between 2 and 8 inclusive.

The qualifying column with the fewest distinct values wins, ties broken by
the order `result.columns` returned them in — deterministic, no ambiguity to
resolve. (This was refined from an initial "first qualifying column wins"
rule after live verification found it picked a less-meaningful column when
multiple columns qualified.)

**Wiring into `descriptive.prepare()`** — only attempted when
`_looks_categorical` is `False` (that path already produces its own chart
for the pure-2-column case; the two chart sources never conflict) and a
candidate column is found. On success:

```python
payload["chart"] = {
    "type": "bar",
    "title": f"{column} distribution",
    "data": [{"label": row[0], "value": row[1]} for row in grouped.rows],
}
```

sitting alongside the existing raw `payload["table"]` — reproducing the
"leads table + status bar chart" shape shown in the reference.

**Failure handling** — the grouped-count call is best-effort, wrapped in
`try/except`: any failure (column-quoting edge case, timeout, connector
quirk) is logged and `chart` is simply omitted; the raw table is still
returned. A broken distribution chart must never break the primary answer.

## Error handling (cross-cutting)

Same principle as the prior two specs: every new computation here
(rationale/impact templating, the column-picker heuristic, the
grouped-count query) runs in Python before the LLM call, so a failure only
ever affects that one optional field, never the base `text`/`table`/
`confidence` the user already gets. `grouped_count` is the only new I/O call
in this batch and is explicitly try/excepted at its call site in
`descriptive.py`.

## Testing

Backend (`app/ai/tests`, pytest, TDD as in prior specs — write these first):

- `test_agents.py`: prescriptive actions carry `rationale`/`expectedImpact`/
  `citationIds`, with citation ids deduplicated and stable across actions
  that share a source; descriptive result gets a `chart` when a qualifying
  low-cardinality column exists alongside a wide table, and no `chart` when
  no column qualifies or the grouped-count query raises.
- `test_executor.py`: new `grouped_count` cases — wraps arbitrary SQL
  correctly, quotes the column name, returns `ok=False` (not a raised
  exception) on failure.
- New unit tests for `_pick_distribution_column`: denylist names excluded,
  cardinality bounds (reject 1, reject 9+, accept 2 and 8), an all-null
  column excluded, an all-unique string column excluded (cardinality above
  the bound), first-qualifying-column-wins when multiple candidates exist.

Frontend: no test runner exists in `app/web` (confirmed in the prior spec,
still true). `RecommendationCard` and the `AgentChart` CI band are verified
manually — drive one prescriptive question and one predictive question
through chat, confirm the recommendation cards show rationale/impact/
citations and the forecast chart shows a shaded band, same live-verification
approach used in the prior two specs.
