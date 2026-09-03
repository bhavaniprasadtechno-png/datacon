# Diagnostic Agent Pipeline Migration — Trend Detection with Grounded Insight

Status: ready-for-agent

## Problem Statement

The Diagnostic analyst ("why did X spike?") still bypasses the structured analytics pipeline built for the Descriptive analyst. It computes a spike-vs-baseline comparison with inline arithmetic, shows a raw table of counts with no chart even though the data is an inherent day-by-day trend, and its confidence label isn't grounded in any shared validation logic. It also duplicates a citation/RAG-fallback pattern that's already been solved once, in a subtly different shape. As a result, Diagnostic answers read less like a considered analytics product than Descriptive's now do, and the deterministic-facts guarantee (no LLM-invented numbers) that the rest of the pipeline provides doesn't yet cover this agent.

## Solution

Migrate the Diagnostic analyst onto the same structured pipeline Descriptive already uses: Result Normalizer → Analytics Engine → Validator → Insight Engine → Presentation Planner → `StructuredResponse`. This is a single-agent, tracer-bullet delivery — the second in an incremental series that started with Descriptive (analytics-response-pipeline, tickets 02–03) — not a combined migration of all remaining agents.

Diagnostic's spike-detection query is rebuilt to capture an explicit date/day column (today it only infers day order from row position) and a shared `percent_change`-style calculation is added to the Analytics Engine so the spike-vs-baseline math is no longer bespoke inline arithmetic. The day-by-day counts get a real trend visualization — today there is none, only a table — via a new `line` rule added to the Presentation Planner. Diagnostic's headline figures (today's count, baseline average, % change) become KPI metrics and a grounded, evidence-carrying insight, following the same primary/secondary presentation hierarchy already established for Descriptive (chart + KPIs primary, table collapsed behind a disclosure).

Diagnostic's RAG-grounded citation/correlation behavior — which has no equivalent in the current `StructuredResponse` contract — is preserved via the same flat-field escape-hatch pattern already shipped for Descriptive's document-QA fallback, rather than forcing a lossy fit into the structured contract or blocking this delivery on a contract extension. Because Diagnostic's computed-spike case needs *both* the new structured fields and the old flat citation/correlation fields on one payload (unlike Descriptive, which is ever fully one shape or the other), the frontend payload adapter is extended to preserve `citations`/`correlation` on an otherwise-structured payload instead of silently dropping them.

## User Stories

**As a person asking the assistant "why did X spike?" questions:**

1. As a user, I want to see a trend chart of the day-by-day counts, not just a raw table, so that I can see the shape of the spike at a glance.
2. As a user, I want the spike's headline figures (today's count, baseline average, % change) shown as KPI metrics, so that I get the "how much, compared to what" answer immediately.
3. As a user, I want the full day-by-day table hidden by default behind a "view underlying records" disclosure, so that the response stays readable, consistent with how other analytics answers already behave.
4. As a user, I want the spike insight grounded in the actual computed baseline/spike numbers, so that I can trust the stated percentage instead of wondering if the assistant is guessing.
5. As a user, I want the trend chart's x-axis to show real dates, not an implicit day-1-through-8 ordering, so that I know exactly which days the data covers.
6. As a user, I want to keep seeing which document a spike correlates with (citation chips, a correlation tag) exactly as I do today, so that this migration doesn't regress functionality I already rely on.
7. As a user asking a diagnostic question the data can't actually answer (no day-by-day data connected), I want a clear explanation of the limitation, not a fabricated chart or invented insight.
8. As a user, I want the response's confidence to reflect whether a supporting citation was actually found, not an arbitrary LLM guess.
9. As a user with existing saved conversations and dashboards involving diagnostic answers, I want them to keep rendering correctly after this change ships.
10. As a user, I want the assistant's prose to keep streaming in live as it's generated, so that the experience feels the same as it does today, not slower.

**As an engineer building and maintaining this system:**

11. As a backend engineer, I want Diagnostic's spike-vs-baseline percentage computed by a shared, reusable Analytics Engine function rather than bespoke inline arithmetic, so that the same growth/change math is available to future agents (e.g. Predictive) without duplication.
12. As a backend engineer, I want the day-by-day count query to select an explicit date/day column, so that Diagnostic's row data carries real date labels instead of relying on row position.
13. As a backend engineer, I want the Presentation Planner's chart-selection logic extended with a `line` rule for a single time-ordered measure, so that chart-type decisions stay centralized in the Planner rather than scattered per-agent.
14. As a backend engineer, I want Diagnostic's insight grounded via the same evidence-reference mechanism as Descriptive's insights, so that the Validator's evidence check applies uniformly.
15. As a backend engineer, I want Diagnostic to keep computing its own domain-specific confidence (citation-groundedness) directly, the same way Predictive is expected to keep computing its own forecast-fit confidence, rather than teaching the shared Validator agent-specific judgment calls it has no way to make generically.
16. As a backend engineer, I want Diagnostic's true-empty-state and citation-fallback-state responses to follow the same shape split Descriptive already uses (`StructuredResponse` for true-empty, old flat shape for citation-fallback), so the two agents behave consistently.
17. As a frontend engineer, I want the payload adapter to stop unconditionally discarding `citations`/`correlation` on a structured-shaped payload, so that an agent whose payload mixes both the new structured fields and the old escape-hatch fields renders correctly.
18. As a QA engineer, I want the pipeline's structured-response entry point for Diagnostic testable against real DuckDB fixtures with only SQL generation mocked, consistent with the existing seam for Descriptive.
19. As a QA engineer, I want the Analytics Engine's new `percent_change` function unit-testable as a pure function, independent of the database (the `line` rule itself is unit-tested in the Visualization Registry delivery this ticket consumes).

## Implementation Decisions

**Delivery scope**

- Only the Diagnostic analyst is migrated in this delivery. Predictive and Prescriptive keep their current direct-query + `compose_stream` behavior unchanged, and are each planned as their own follow-up grilling/spec/tickets round — they raise distinct open questions (a forecast-quality confidence formula for Predictive; a new `Action`/recommendation contract type for Prescriptive) not resolved here.
- `chat_router`'s per-intent dispatch requires no changes: it already calls every intent's `prepare()` uniformly and treats the returned payload as opaque. This migration is entirely internal to the Diagnostic agent module plus the shared pipeline modules — no routing-layer change.

**Diagnostic's query and data shape**

- The day-by-day count query is rebuilt to select an explicit date/day column alongside the count, rather than relying on row position as an implicit day index.
- The optional region/category grouping in today's query is dropped for this delivery — the trend becomes a single overall daily-count series. A region/category label may still appear in insight prose text when the underlying data happens to carry one, but it does not become a chart dimension (no multi-series chart). Multi-series trend charts are treated as unproven scope, to be added only if a concrete scenario needs one.
- The last row (by date, once explicit) remains "the spike"; all prior rows remain "the baseline," same as today's logic.

**Analytics Engine**

- A new `percent_change`-style function is added, computing the percentage change of a value against the average of a preceding baseline set. This generalizes Diagnostic's spike-vs-baseline arithmetic (today implemented inline) into shared, reusable math, following the same pattern as the existing grouped-aggregation/ranking function added for the category-comparison delivery. No other Analytics Engine changes are needed for this delivery.

**Presentation Planner**

- Diagnostic's day-by-day trend consumes the `line` visualization rule (single time-ordered dimension, single measure) built by the separate Visualization Registry delivery (`.scratch/visualization-registry-line-type/`) — that rule, its `dimension`/`measure` contract fields, and the frontend renderer-registry refactor are built there, not in this ticket. This ticket depends on that delivery rather than duplicating it; Predictive's later migration reuses the same rule for its forecast chart.
- Diagnostic's response follows the same primary/secondary hierarchy as Descriptive: the KPI metrics and the trend chart are primary; the day-by-day table is collapsed behind a "view underlying records" disclosure.

**Insight Engine**

- A new insight is produced for the spike, grounded in evidence references to the spike-count and baseline-average metric IDs (mirroring how existing insights reference metric IDs).
- The insight's type is direction-agnostic — always the "attention" type regardless of whether the change is an increase or decrease. Diagnostic has no reliable way to know whether a rise or fall in an arbitrary connected dataset is good or bad news (unlike Descriptive's boolean-split insights, where the "positive" case is unambiguous), so no positive/negative value judgment is made on the direction itself.

**Confidence**

- Diagnostic keeps computing its own confidence directly from whether a supporting citation was found (mirroring today's `"high" if citations else "medium"` logic) and places it directly into the structured response's summary confidence field, rather than routing it through the shared Validator's generic issue-based confidence computation. The Validator's issue vocabulary stays limited to structural checks (insight evidence, table columns, visualization shape); citation-groundedness is a domain judgment specific to RAG-grounded agents, not a structural validation concern.
- The true-empty-state response (no spike data, no citations found) computes confidence the standard way: `low`, via a real `StructuredResponse` with empty metrics/insights — same as Descriptive's no-data case.

**Citations, correlation, and the escape hatch**

- Diagnostic's RAG-grounded citation list and correlation string continue to be represented as flat fields (`citations`, `correlation`) outside the `StructuredResponse` contract — the same escape-hatch pattern already shipped for Descriptive's document-QA fallback. No contract extension for rich citation metadata is made in this delivery.
- Unlike Descriptive (where a message is ever fully old-shape or fully new-shape), Diagnostic's computed-spike case emits both: a real `StructuredResponse` (metrics, insight, visualization, table) *and* the flat `citations`/`correlation` fields, merged onto the same payload object.
- Diagnostic's fallback paths mirror Descriptive's exact shape split: a true-empty state (no spike data, no citations) returns a real `StructuredResponse` with low confidence; a citations-found-but-no-spike-data state returns the old flat shape entirely (matching Descriptive's `_citation_fallback` precedent).

**Frontend**

- The payload adapter's structured-shape branch is changed to read `citations`/`correlation` off the raw payload when present, instead of unconditionally hardcoding them empty/null. This is required for Diagnostic's mixed-shape payload (structured fields + escape-hatch fields together) to render correctly, and has no effect on Descriptive's existing payloads (which never carry both shapes at once).
- The frontend chart component renders the new `line` visualization type using its existing line-chart rendering path (already used for Predictive's forecast chart) — no new chart-rendering code needed, since Diagnostic's trend has no confidence-interval band data.

## Testing Decisions

- Tests assert on external behavior — the shape and values of the structured response, which visualization/insight/confidence got produced — not on internal call sequencing between pipeline stages, consistent with the existing testing philosophy for this pipeline.
- **Primary integration seam**: the Diagnostic analyst's structured-response entry point (`prepare()`), tested against real DuckDB fixtures loaded via `snapshot_store.load_dataset`, with `generator.generate_sql` mocked — the same seam and mocking boundary already used for Descriptive. All deterministic layers (Normalizer, Analytics Engine, Validator, Insight Engine, Presentation Planner) run for real inside this seam. Assertions cover: a computed-spike scenario with citations found, a computed-spike scenario with no citations found, a true-empty-state scenario, and a citations-found-but-no-spike-data scenario.
- **Focused unit tests** on top of that seam: the Analytics Engine's new `percent_change` function, direct unit tests against representative inputs (including a zero-baseline edge case). The `line` rule it feeds is already unit-tested in the Visualization Registry delivery.
- Frontend: no new automated tests (none exist for this area, consistent with the prior delivery). The scenario is verified manually in the running app, covering a fresh diagnostic message with a real trend chart and citation chips, and confirming an existing pre-migration diagnostic message still renders correctly.

## Out of Scope

- Migrating Predictive, Prescriptive, or General onto the new pipeline — each is its own future delivery with its own open questions.
- Extending the `StructuredResponse` contract with a native citations field or an `Action`/recommendation model — deferred until Prescriptive's migration, where the need is real rather than anticipated.
- Multi-series (per-region) trend charts — Diagnostic's region/category grouping is dropped to a single overall series for this delivery.
- Folding citation-groundedness into the shared Validator's issue vocabulary — confidence stays agent-computed for this concern.
- Real anomaly-detection statistics (z-scores, thresholding) for what counts as "a spike" — the last-row-vs-baseline-average heuristic is unchanged from today.
- Any change to `chat_router`'s routing logic — none is needed.
- Any change to authentication, RBAC, or connector credential handling.

## Further Notes

- This is the second delivery in an incremental series that began with the Descriptive analyst (see `.scratch/analytics-response-pipeline/`), continuing with Predictive (`.scratch/predictive-agent-pipeline-migration/`) and Prescriptive (`.scratch/prescriptive-agent-pipeline-migration/`), both now spec'd. This ticket depends on the Visualization Registry delivery (`.scratch/visualization-registry-line-type/`) for its `line` rule.
- The real seeded domain tables relevant here are the same as noted in the prior spec (`tickets`, `product_events`, etc., plus dynamic per-connector tables) — exact column names for the rebuilt date-aware query are confirmed during implementation, not fixed here.
