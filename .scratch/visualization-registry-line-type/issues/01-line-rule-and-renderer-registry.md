# 01 — Visualization Registry: extensible Planner + renderer architecture, with `line` as the first type

**What to build:** Establish the extensible visualization architecture this whole series depends on — not just "add a line chart." On the backend, the Presentation Planner keeps owning visualization-type selection, expressed as a semantic contract (`type` + `dimension`/`measure`/`data` — never raw chart-library configuration like axis or series objects). On the frontend, replace `AgentChart.tsx`'s hardcoded `if/else` chain with a `type → renderer` lookup, so that adding the next chart type (bar, horizontal_bar, pie, donut, scatter, area, heatmap, funnel, etc., in future tickets) is a new Planner rule plus a new registry entry — never a change to the agent pipeline, `chat_router`, or any other renderer.

`line` is the first concrete rule and renderer built on this architecture: selected when a result has a single time-ordered dimension and a single measure. This is what the Diagnostic and Predictive migration tickets both consume for their trend/forecast visuals — build the architecture once here so neither duplicates it.

**Blocked by:** None — can start immediately. (Independent of `01 — Prefactor: payloadAdapter...`; different files, different concern — the two can proceed in parallel.)

**Status:** done

- [x] Presentation Planner selects `line` when a `NormalizedResult` has exactly one time-ordered (date) dimension and exactly one measure, with more than one row.
- [x] The `line` rule falls through to the existing kpi/none checks when the shape doesn't fit — same rule-chain-as-fallback pattern `horizontal_bar` already uses; no separate suitability-validation subsystem is introduced.
- [x] The `Visualization` contract gains optional `dimension` and `measure` fields, populated by the new rule; existing types (kpi, none, horizontal_bar, table) leave them unset.
- [x] The semantic contract stays semantic: the backend emits `{type, dimension, measure, data}` for `line` — no axis/series/tooltip-shaped configuration anywhere in the payload.
- [x] `AgentChart.tsx`'s chart-type branching is replaced by a `type → renderer` lookup table (`CHART_RENDERERS`, a plain `Record`, no plugin system, no dynamic registration).
- [x] Today's still-unmigrated Predictive agent's existing `line` chart (old payload shape, with its confidence band) renders visually unchanged through the new renderer registry — verified live: chart title, 95% CI badge, band, and the PROJECTED/95% CI/GROWTH stat row all render identically.
- [x] `bar` and `horizontal_bar` rendering are also visually unchanged through the new registry (typecheck + lint clean, no logic change to either renderer beyond extraction into named functions).
- [x] A `line` visualization's data points support optional `lower`/`upper` keys per point as a data-level convention, not a new contract field (unchanged — `renderLine` already reads them ad hoc from `chart.data`).
- [x] The Presentation Planner's `line` rule is unit-tested as a pure function against synthetic `NormalizedResult` inputs — 3 new tests in `test_presentation_planner.py`, plus 2 new contract tests for the `dimension`/`measure` fields.
- [x] No new chart type beyond `line` is implemented in this ticket.

**Also, incidentally:** promoted `analytics_engine._column_index` to a public `column_index`, since `presentation_planner.py`'s new `line` rule is now a second real consumer — same "second caller earns the shared helper" precedent used elsewhere in this pipeline. Full backend suite: 147 passed (3 pre-existing, unrelated `test_generator.py` failures). Frontend: `payloadAdapter.test.ts` + new checks all green, `tsc --noEmit` clean, `oxlint` clean (pre-existing unrelated warnings only).
