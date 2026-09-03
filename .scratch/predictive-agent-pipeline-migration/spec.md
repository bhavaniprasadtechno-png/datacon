# Predictive Agent Pipeline Migration — Forecast with Structured Facts

Status: ready-for-agent

## Problem Statement

The Predictive analyst ("forecast revenue") still bypasses the structured analytics pipeline. Its forecast figures (projected value, confidence interval, growth %, model fit) are only ever expressed as interpolated prose and an ad hoc `chart`/`table` payload built by hand, not as validated, deterministic facts. The chart and table it builds are entirely bespoke to this one agent, duplicating shape and dataset-naming logic that the migrated agents already have solved versions of. As a result, a forecast answer doesn't get the same grounded-metrics guarantee, presentation hierarchy, or backward-compatible rendering that Descriptive and (once built) Diagnostic already provide.

## Solution

Migrate the Predictive analyst onto the same structured pipeline as Descriptive and Diagnostic: Result Normalizer → Analytics Engine → Validator → Insight Engine → Presentation Planner → `StructuredResponse`. This is a single-agent, tracer-bullet delivery in the same incremental series (Descriptive, then Diagnostic, then this one) — not a combined migration.

Predictive's forecast figures (projected, CI low/high, growth %) become headline KPI metrics. The historical-plus-forecast trend becomes a `line` visualization (consuming the `line` Planner rule built in the Visualization Registry delivery), with the forecast's confidence band attached as `lower`/`upper` data on the final point — the same band shape Predictive's pre-migration chart already produced, so the frontend needs no new rendering work. Predictive keeps computing its own forecast-fit confidence directly from the model's MAPE (today's `<15% high / <30% medium / else low` logic, unchanged), placing it directly into the structured response's confidence field, rather than routing it through the Validator's generic issue-based computation — the same precedent already set for Diagnostic's citation-groundedness confidence. Predictive has no RAG/citation behavior, so no escape-hatch fields are needed on its payload at all; its migration is a clean, fully-structured response with no mixed shape.

The dataset-name-inference and row-sanitization helpers that Descriptive built (and Diagnostic also needs) are extracted into a shared location, since Predictive is the second consumer that needs the same behavior — following the same "second caller earns the shared abstraction" principle already applied elsewhere in this pipeline.

## User Stories

**As a person asking the assistant "forecast X" questions:**

1. As a user, I want the forecast's headline figures (projected value, confidence interval, growth %) shown as KPI metrics, so that I get the answer immediately without parsing prose.
2. As a user, I want the historical series and the forecast to render as one continuous line chart with the confidence band visible, so that I can see both the trend and its uncertainty at a glance.
3. As a user, I want the underlying period-by-period figures available behind a "view underlying records" disclosure, so that the response stays readable, consistent with other analytics answers.
4. As a user, I want the response's confidence to reflect the actual model fit (MAPE), not an arbitrary guess, so that I know how much to trust a given forecast.
5. As a user asking for a forecast when there isn't enough history, I want a clear explanation of the limitation, not a fabricated projection or invented chart.
6. As a user with existing saved conversations and dashboards involving forecast answers, I want them to keep rendering correctly after this migration ships.
7. As a user, I want the assistant's prose to keep streaming in live as it's generated, so the experience feels the same as it does today.

**As an engineer building and maintaining this system:**

8. As a backend engineer, I want Predictive's forecast figures computed exactly as they are today (same Holt-Winters model, same horizon, same MAPE-based confidence thresholds) — this migration restructures where the numbers land, not how they're calculated.
9. As a backend engineer, I want the forecast's chart to be produced via the shared `line` Presentation Planner rule, not bespoke chart-building code local to this agent, so chart-type decisions stay centralized.
10. As a backend engineer, I want the dataset-name-inference and row-sanitization helpers shared between Descriptive, Diagnostic, and Predictive rather than duplicated a third time.
11. As a backend engineer, I want Predictive's table to reflect only the real queried historical rows (no synthetic forecast row spliced in), since the forecast value already appears on the chart and as a KPI metric — the table should never contain a number the query itself didn't return.
12. As a backend engineer, I want Predictive's own confidence computation kept separate from the Validator's generic issue-based confidence, consistent with the precedent already set for Diagnostic's domain-specific confidence — model-fit quality is a judgment the shared Validator has no way to make generically.
13. As a QA engineer, I want the Predictive analyst's structured-response entry point testable against real DuckDB fixtures with only SQL generation mocked, consistent with the existing seam for Descriptive and Diagnostic.

## Implementation Decisions

**Delivery scope**

- Only the Predictive analyst is migrated in this delivery, using the `line` Presentation Planner rule already built in the Visualization Registry delivery (`.scratch/visualization-registry-line-type/`) — this spec does not build that rule itself.
- `chat_router`'s per-intent dispatch requires no changes, same as every prior migration in this series — it already calls every intent's `prepare()` uniformly.

**Forecast computation**

- The forecast computation itself (Holt-Winters model, 6-month horizon, MAPE-based confidence thresholds) is unchanged from today. This delivery restructures the output shape, not the forecasting logic.

**Metrics**

- Projected value, CI low, CI high, and growth % become headline `Metric`/KPI cards, mirroring the hierarchy already established for Descriptive and Diagnostic ("what's the answer" belongs above the fold).
- MAPE (model fit error) does not become a separate KPI metric — it's a model-diagnostic number, not a business figure, and it's already reflected in the response's confidence level rather than needing its own card.

**Visualization**

- The historical series plus the forecast point become one `line` visualization via the shared Planner rule. The forecast's confidence band (`lower`/`upper`) is attached to the final data point exactly as today's pre-migration chart already does — no change to that band-anchoring behavior, only to where the chart gets built (via the Planner rule and shared contract, not agent-local code).

**Table**

- The table reflects only the real historical rows returned by the query (`period`, `revenue`), built via the standard `plan_table` on the `NormalizedResult`. The synthetic "forecast" row today's pre-migration table appends is dropped — the forecast is already visible as a KPI metric and on the chart, and the table should never contain a value the query itself didn't return, consistent with this pipeline's "never invent a number" principle.

**Confidence**

- Predictive keeps computing its own confidence directly from MAPE (`<15% high / <30% medium / else low`, unchanged) and places it directly into the structured response's summary confidence field, rather than routing it through the Validator's generic issue-based computation — same precedent as Diagnostic's citation-groundedness confidence.
- The true-empty-state response (insufficient revenue history) returns a real `StructuredResponse` with `confidence: low` and empty metrics/insights, mirroring Descriptive's and Diagnostic's no-data precedent.

**Citations and the escape hatch**

- Predictive does not perform any RAG/document lookups and has no citation or correlation behavior today. Its migrated payload is a clean, fully-structured `StructuredResponse` with no escape-hatch fields at all — unlike Diagnostic, there is no mixed-shape payload concern here.

**Shared helpers**

- The dataset-name-inference (`FROM`-clause parsing, connector-prefix stripping) and row-sanitization helpers currently local to the Descriptive agent module are extracted into a shared location within the pipeline package, since Predictive is now a second real consumer needing the same behavior. This extraction is deliberately minimal: only the specific functions Predictive actually calls move, not a general-purpose utility layer built ahead of a third consumer. No behavior change to the helpers themselves — this is a relocation driven by reuse, not a redesign. Descriptive's existing behavior and tests must be unaffected by the move. Since dataset-name inference has real edge-case behavior (quoted vs. unquoted identifiers, the connector-prefix strip, hyphenated names — already the subject of a prior bug fix in this pipeline), its existing test coverage moves with it rather than being dropped.

## Testing Decisions

- Tests assert on external behavior — the shape and values of the structured response, which visualization/metrics/confidence resulted — not on internal call sequencing.
- **Primary integration seam**: the Predictive analyst's structured-response entry point (`prepare()`), tested against real DuckDB fixtures loaded via `snapshot_store.load_dataset`, with `generator.generate_sql` mocked — the same seam and mocking boundary already used for Descriptive and Diagnostic. Assertions cover: a successful forecast with high confidence (low MAPE), a successful forecast with lower confidence (higher MAPE), and a true-empty-state (insufficient history) scenario.
- **Focused unit tests**: none new at the Presentation Planner or Analytics Engine layer are needed for this delivery — the `line` rule is already unit-tested in the Visualization Registry delivery, and no new Analytics Engine math is introduced here (the forecast math itself is unchanged, pre-existing, already covered by the `app/ai/app/forecasting` module's own tests).
- Frontend: no new automated tests (none exist for this area). Verified manually in the running app — a fresh forecast message with a real line-plus-band chart, and confirmation that an existing pre-migration forecast message still renders correctly through the adapter.

## Out of Scope

- Any change to the forecasting math itself (model choice, horizon, MAPE thresholds) — this is a structural migration only.
- Migrating General onto the new pipeline — not part of this series.
- Folding model-fit confidence into the shared Validator's issue vocabulary — confidence stays agent-computed for this concern, same as Diagnostic.
- Any visualization type beyond `line` — not needed by this agent's current behavior.
- Any change to `chat_router`'s routing logic — none is needed.
- Any change to authentication, RBAC, or connector credential handling.

## Further Notes

- This is the third delivery in the incremental per-agent migration series that began with Descriptive (`.scratch/analytics-response-pipeline/`) and continued with Diagnostic (`.scratch/diagnostic-agent-pipeline-migration/`). Prescriptive is the fourth and final agent in this series (`.scratch/prescriptive-agent-pipeline-migration/`), which — unlike this delivery — does require a contract extension (a new `Action` type), since recommendation data doesn't fit losslessly into the existing `Metric`/`Insight` shapes.
- Depends on the Visualization Registry delivery (`.scratch/visualization-registry-line-type/`) for the `line` Presentation Planner rule and the `dimension`/`measure` contract fields it relies on.
