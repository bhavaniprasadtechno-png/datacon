# Analytics Response Pipeline — Structured, Grounded, Presentation-Aware Chat Responses

Status: ready-for-agent

## Problem Statement

When a user asks the chat assistant an analytics question (e.g. "give me customers" or "show tickets by status"), the response feels like "chat with SQL" rather than an analytics product:

- Raw database rows and every returned column get dumped straight into the response, even when the user just wanted a summary.
- Charts are picked by a narrow, hardcoded heuristic that defaults to a bar chart almost regardless of what the data actually looks like — category breakdowns, percentages, and rankings all get the same treatment.
- There's no separation between "what the data says" (facts) and "what it means" (insight) — the LLM is left to narrate raw rows directly, so numeric claims aren't guaranteed to be correct.
- The four-stage Retriever → Validator → Responder pipeline that was designed for this system was never actually wired into the live `/stream` execution path — each specialized agent independently queries the database and streams its own LLM answer, bypassing validation entirely.
- The frontend receives an unstructured, ad hoc payload per agent (a grab-bag of `chart`/`table`/`citations`/`actions`/`correlation` fields with no enforced contract on the backend side), so it can't reliably decide what to show versus hide.

## Solution

Wire a real pipeline behind the Descriptive analyst — the one responsible for "what happened" questions, including both of this delivery's tracer-bullet scenarios — so that a question flows through: Retriever → Query Engine → Result Normalizer → Analytics Engine → Validator → Insight Engine → Presentation Planner → a validated structured response → SSE → the React renderer.

Deterministic code (not the LLM) computes every numeric fact — totals, percentages, groupings. A Presentation Planner then decides, from a controlled visualization registry, what the user actually needs to see: a KPI, a chart (and which kind), a table (and which columns), or nothing — never a chart just because rows came back, and never a raw dump of every column by default. The LLM's job narrows to phrasing the summary prose and insight wording from facts it's handed, not inventing them.

The other four specialized agents (Diagnostic, Predictive, Prescriptive, General) are unchanged in this delivery — they keep querying directly and streaming their own answer as they do today. The new pipeline stages are built as intent-agnostic components specifically so a later delivery can migrate them without rework.

## User Stories

**As a person asking the assistant analytics questions:**

1. As a user, I want a plain-language summary of my data instead of a raw table dump, so that I can understand the answer without parsing rows myself.
2. As a user asking a simple aggregate question ("give me customers"), I want to see KPI-style metrics (totals, counts), so that I get the headline numbers immediately.
3. As a user, I want the full underlying table hidden by default and available behind a "view underlying records" disclosure, so that the response stays readable.
4. As a user who does ask to see records ("show all customer details"), I want a table of the relevant columns only — not every database column (internal IDs, embeddings, raw JSON) — so that the table stays useful.
5. As a user, I want the insights in the response to be grounded in the actual computed numbers, so that I can trust them instead of wondering if the assistant is guessing.
6. As a user asking a category-comparison question ("show tickets by status"), I want a horizontal bar or ranking rather than a generic bar chart with no regard for the data shape, so that the comparison is easy to read, especially with longer category labels.
7. As a user, I want the assistant to skip the chart entirely when a visualization wouldn't add anything (e.g. a single scalar answer), so that I'm not shown a chart just because rows came back.
8. As a user asking a percentage/part-to-whole question, I want a compact KPI or donut instead of a giant table, so that the proportion is immediately clear.
9. As a user asking how something changed over time, I want a trend visualization and a trend-focused insight, so that the direction and magnitude are clear at a glance.
10. As a user asking a "which X is best/worst" ranking question, I want a ranked comparison with the relevant metric, not raw unranked rows.
11. As a user, I want to see where an answer's numbers came from ("based on 42 records from customers"), so that I can judge how much to trust it.
12. As a user, I want the confidence shown on a response to reflect whether the query and validation actually succeeded, not an arbitrary LLM guess.
13. As a user asking a question the data can't actually answer, I want a clear explanation of the limitation, not a fabricated chart or invented insight.
14. As a user, I want the assistant's prose to keep streaming in live as it's generated, so that the experience feels the same as it does today, not slower.
15. As a user with existing saved conversations and dashboards, I want them to keep rendering correctly after this change ships, so that nothing I've already saved breaks or looks wrong.
16. As a user, I want charts, KPIs, and tables to be presented in a clear primary/secondary hierarchy (summary and KPIs first, details collapsed), so that the response reads as a considered analytics answer, not a data dump.

**As an engineer building and maintaining this system:**

17. As a backend engineer, I want a single validated response contract (Pydantic) used by the Descriptive analyst, so that the response shape can't silently drift out from under the frontend.
18. As a backend engineer, I want every numeric fact (totals, percentages, growth, rankings) computed in deterministic code, so that arithmetic is never left to the LLM.
19. As a backend engineer, I want the LLM prompt for the summary/insight prose constrained to the pre-computed metrics and insight facts only (never raw rows), so that it cannot state a number that wasn't actually calculated.
20. As a backend engineer, I want a Validator stage that checks SQL success, metric arithmetic, insight evidence, and visualization field existence before a response is returned, so that a broken component gets caught, not shipped.
21. As a backend engineer, I want the currently-dead Retriever/Validator/Responder agent components either repurposed into the new pipeline's roles or removed, so there's no unreferenced pipeline code sitting next to the real one.
22. As a backend engineer, I want the Presentation Planner to be a distinct, independently testable component rather than logic scattered inside each analyst, so that chart/table decisions live in one place.
23. As a backend engineer, I want the visualization registry to cover the full conceptual set of chart types (even ones the frontend can't render yet), so that later chart-type additions are a frontend-only change, not a re-plumbing of the planner.
24. As a frontend engineer, I want the shared response type extended (metrics/insights/visualizations/tables/sources) to match the new backend contract, so that rendering logic can trust the shape it receives for messages built on the new pipeline.
25. As a frontend engineer, I want a safe fallback for a visualization type the chart component doesn't yet implement, so an unrecognized type degrades gracefully (e.g. to a table or nothing) instead of crashing or rendering blank.
26. As a frontend engineer, I want one adapter function that normalizes both pre-refactor persisted payloads and not-yet-migrated agents' live payloads into the shape the renderer expects, so I don't need two render code paths.
27. As a QA engineer, I want the pipeline's structured-response entry point testable against real DuckDB fixtures with only SQL generation mocked, so tests don't need network access to the LLM provider.
28. As a QA engineer, I want the Presentation Planner's chart-selection rules unit-testable as pure functions independent of the database, so each registry branch can be verified directly.
29. As a QA engineer, I want key Analytics Engine and Result Normalizer invariants unit-tested in isolation (e.g. percentage/aggregation correctness, dimension/measure classification), so regressions in those layers are caught without re-running full end-to-end scenarios.
30. As an operator, I want a real `error` SSE event (currently missing at the FastAPI layer), so that a pipeline failure surfaces as a clear state in the UI instead of a silently stalled stream.
31. As a product owner, I want this delivery scoped to two tracer-bullet scenarios under the Descriptive analyst, so we validate the new architecture end-to-end before generalizing it to every specialized agent and every visualization type.

## Implementation Decisions

**Pipeline scope for this delivery**

- Only the **Descriptive** analyst is migrated onto the new pipeline. Diagnostic, Predictive, Prescriptive, and General keep their current behavior (direct query + `compose_stream`) unchanged.
- The two tracer-bullet scenarios this delivery proves end-to-end: (a) a plain aggregate/summary question against the `customers` dataset (KPI metrics, grounded insights, no forced chart, table collapsed behind a disclosure), and (b) a category-comparison question against the `tickets` dataset grouped by status (horizontal-bar/ranking visualization, comparison insight).
- New pipeline stages are written as intent-agnostic components (not Descriptive-specific), so a follow-up delivery can route the other four analysts through the same stages without rework.
- `chat_router`'s per-intent dispatch branches: the `descriptive` intent is routed through the new pipeline entry point; the other four intents keep calling their existing `prepare()` + `compose_stream()` path exactly as today.

**Result Normalizer**

- New component converting an arbitrary query-engine result (columns + rows) into a consistent internal representation: dataset name, row count, columns, classified dimensions vs. measures, typed values (categorical / numeric / date / percentage / currency / null-aware), and preserved source metadata (which dataset/table, which SQL ran) for later evidence/citation use.
- Column classification (dimension vs. measure, and inferred value type) is done deterministically from the query result's column types and cardinality — no LLM involvement.

**Analytics Engine**

- A shared, deterministic calculation layer computing: totals, counts, percentages, averages, min/max, growth/change, rankings, grouped aggregations, and conversion-rate-style ratios, operating on a `NormalizedResult`.
- The existing but currently-unused analytics calculation functions (metric math for revenue/region/ticket/churn stats) are evaluated for reuse: any that fit the new `NormalizedResult`-based input are adapted in place; the rest (built against the old, no-longer-supplied context blob) are removed rather than left alongside the new implementation.
- Module boundaries stay minimal for this delivery — one cohesive analytics module rather than pre-splitting into seven separate sub-engine files; split further only if a single file becomes unwieldy.
- No LLM calls anywhere in this layer.

**Validator**

- Repurposes the existing (currently dead) Validator component's role, rewritten against the new pipeline's data shapes. Checks, before a response is returned:
  - Data: the query succeeded, the result is structurally valid.
  - Metrics: arithmetic/percentages match what the Analytics Engine computed from the source rows.
  - Insights: every insight carries at least one evidence reference to a real metric ID; no insight without evidence is emitted.
  - Visualization: referenced fields exist in the normalized result, and the chosen type doesn't apply to unrelated dimensions.
  - Table: every emitted column exists in the source result; no column outside an explicit allowlist is exposed by default.
- On a validation failure, the specific failing component (a bad insight, an invalid visualization) is dropped or regenerated — the whole response isn't discarded unless the underlying data itself is invalid.

**Insight Engine**

- Produces grounded, human-readable insight statements from the Analytics Engine's computed metrics — not from raw rows. Each insight carries a type (e.g. positive / attention / neutral) and one or more evidence references (metric IDs) that the Validator checks against.
- Insight statement generation for this delivery is rule/template-driven from the computed metrics (e.g., a low-count category trips an "attention" insight); the summary's natural-language prose is composed separately by the LLM (see below), constrained to the same computed facts.

**Presentation Planner**

- Decides, from a controlled visualization registry, what gets shown: which metrics are primary vs. secondary, whether a chart is warranted at all, which chart type if so, whether a table is warranted, which columns if so, and whether the table starts collapsed.
- The registry is defined conceptually across the full set described in the source brief (kpi, line, area, bar, horizontal_bar, stacked_bar, grouped_bar, donut, pie, funnel, scatter, histogram, heatmap, table, ranking, timeline, map, none), so the planner can select a type the frontend doesn't yet render.
- For this delivery, the two tracer-bullet scenarios only require these rules to be implemented: prefer `kpi` for a single-scalar or small fixed set of headline numbers; prefer `none` when a chart adds nothing beyond the KPI(s) already shown; prefer `horizontal_bar` for a category comparison/ranking, especially with more than a few categories or longer labels; prefer `table` only when the user's question is itself asking for record-level detail, restricted to a relevant-column subset. Rules for the remaining registry entries (line, donut, funnel, scatter, histogram, heatmap, map, etc.) are documented as the target design but not implemented until a scenario needs them.
- Never selects a chart solely because rows were returned; never falls back to bar as a universal default.

**Structured response contract**

- New Pydantic model on the backend (mirroring the source brief's shape): a summary (text + confidence), a metrics list (id/label/value/format), an insights list (type/text/evidence references to metric IDs), a visualizations list (each with a registry type plus the data needed to render it), a tables list (columns/rows, pre-filtered to relevant columns), and a sources list (dataset/query/row-count evidence).
- The shared frontend type is extended to match this contract (metrics/insights/visualizations/tables/sources), replacing the current single `chart`/`table`/`citations`/`actions`/`correlation` grab-bag for messages built on the new pipeline.
- Confidence is computed, not asserted by the LLM: `high` when the query succeeded, the Validator raised no issues, and the result is non-empty; `medium` when the Validator flagged a minor, non-blocking issue (e.g. partial null coverage); `low` when the query failed, returned nothing, or the Validator flagged a blocking issue. (The prediction-uncertainty variant of this formula, called for in the source brief, is out of scope until Predictive is migrated.)

**Backward compatibility**

- One adapter function normalizes a payload into the new structured shape regardless of source: payloads persisted before this change, and live payloads from the four not-yet-migrated analysts during the transition window. It detects shape by presence of the new fields (`metrics`/`visualizations`) versus the old ones (`chart`/`table`/`citations`) and maps old → new (e.g. an old `chart`/`table` become single-element `visualizations`/`tables` entries; `citations` become `sources`). No database migration of historical rows.
- The frontend renderer has one render path, driven entirely by the adapted structured shape.

**SSE**

- Event names are unchanged from today (`agents`, `agent_start`, `agent_delta`, `agent_done`, `done`): `agent_delta` keeps streaming the summary prose token-by-token as it does today; `agent_done.payload` for the `descriptive` intent now carries the new structured contract (run through the backward-compat adapter, so the frontend has one shape to handle regardless of which intent produced it).
- One new event type is added: `error`, emitted when the pipeline fails in a way that can't produce a usable response, currently missing at the FastAPI layer entirely.
- No chain-of-thought or internal reasoning is streamed — only the same user-safe summary text as today, plus the structured facts.
- Granular progress events (`query_started`, `analysis_started`, etc.) from the source brief are not implemented in this delivery.

**LLM usage**

- The summary/insight prose keeps streaming live from the configured provider (Together for dev/testing), exactly as today's UX.
- The prompt for that prose is constrained to the Analytics Engine's computed metrics and the Insight Engine's grounded insight statements — never raw query rows — so it cannot state a number that wasn't actually computed.
- The Validator spot-checks that numbers appearing in the streamed prose match the computed metrics; a mismatch is treated as a validation issue affecting confidence, not a hard failure of the stream (the prose has already been shown to the user by the time validation runs, since it streams live).

## Testing Decisions

- Tests assert on external behavior — the shape and values of the structured response object, and which visualization/table/insight got selected — not on internal call sequencing between pipeline stages.
- **Primary integration seam**: the per-intent "build structured response" entry point (the Descriptive analyst's successor to today's `prepare()`), tested against real DuckDB fixtures loaded the same way `tests/agents/test_agents.py` already does (`snapshot_store.load_dataset`), with `generator.generate_sql` mocked exactly as today. All deterministic layers (Normalizer, Analytics Engine, Validator, Insight Engine, Presentation Planner) run for real inside this seam — none of them individually mocked. Assertions cover both tracer-bullet scenarios (customers summary, tickets-by-status comparison) plus at least one insufficient-data case (no fabricated chart or insight).
- **Focused unit tests** on top of that seam, not duplicating full scenarios:
  - Presentation Planner chart-selection rules as pure functions — one test per implemented rule (kpi-for-scalar, none-when-chart-adds-nothing, horizontal_bar-for-category-comparison, table-only-on-explicit-detail-request), fed synthetic `NormalizedResult` inputs rather than going through SQL/DuckDB.
  - Key Analytics Engine invariants (percentage/aggregation arithmetic correctness) and Result Normalizer invariants (dimension vs. measure classification, null/date/percentage typing) as direct unit tests against representative inputs.
- Explicitly not covered in this delivery: SSE wire-format/event-sequencing tests, and the LLM-streamed prose content — both stay manually verified (per the existing coverage gap around `compose_stream`, unchanged by this work).
- Frontend: no new automated tests (none exist to extend); the two tracer-bullet scenarios are verified manually in the running app per the `run` skill, covering both a fresh new-pipeline message and an existing pre-refactor saved conversation/dashboard rendering correctly through the adapter.

## Out of Scope

- Migrating Diagnostic, Predictive, Prescriptive, or General onto the new pipeline (their current direct-query + `compose_stream` behavior is unchanged).
- Implementing the full 16-entry visualization registry — only `kpi`, `horizontal_bar`, `table`, and `none` are built; the rest are named in the registry design but not implemented.
- Granular SSE progress events (`query_started`, `analysis_started`, etc.) — only the existing event names plus one new `error` event.
- Any frontend automated test harness — none exists today, and adding one is a separate concern from this delivery.
- A database migration/backfill of historical payload rows — the read-time adapter handles old shapes instead.
- The prediction-uncertainty variant of the confidence formula (only the deterministic-query variant is implemented, since Predictive isn't touched).
- Any change to authentication, RBAC, or connector credential handling.
- The remaining source-brief acceptance criteria not covered by the two tracer-bullet scenarios (funnel/scatter/histogram/heatmap/map selection, full column-selection heuristics beyond the two scenarios' datasets, etc.).

## Further Notes

- The real seeded domain is `orders`, `customers`, `tickets`, `revenue_daily`, `product_events`, `churn_scores` (plus dynamic per-connector tables synced at runtime) — not "leads," which was illustrative in the source brief. Exact column names on `customers` and `tickets` are confirmed during ticket implementation, not fixed in this spec.
- The existing (currently dead) Retriever/Validator/Responder/context-filter/live-query/connector-query components are evaluated file-by-file during implementation: each is either repurposed into a new pipeline role (Retriever, Validator) or removed if nothing in the new design calls it (anything whose only caller was the dead Retriever). This disposition is an implementation-time decision within the ticket breakdown, not fixed here.
- Follow-up deliveries (not part of this spec): migrate the remaining four analysts onto the shared pipeline stages; expand the visualization registry's implemented set; add the granular SSE progress event taxonomy; revisit whether a real payload backfill is worth it once the adapter has been in place for a while.
