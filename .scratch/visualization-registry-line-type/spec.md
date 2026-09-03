# Visualization Registry — Extensible Planner + Renderer Architecture

Status: ready-for-agent

## Problem Statement

The Presentation Planner only knows two shapes today: headline KPI numbers, and a single-category comparison (`horizontal_bar`). Anything whose answer is inherently a trend over time — day-by-day event counts, a monthly revenue forecast — has no Planner rule to select from, so those answers either get no chart or fall back to ad hoc per-agent chart-building outside the pipeline. Separately, the frontend still decides how to render a chart via a hardcoded `if/else` chain keyed on chart type, rather than a lookup-based registry, so every new chart type means another branch added to a growing conditional instead of one new registry entry — and nothing stops a future chart type from being described as raw chart-library configuration rather than semantic data.

## Solution

Establish the extensible registry architecture on both sides of the contract — not just add one chart type. On the backend, the Presentation Planner keeps owning visualization-type selection through a semantic contract (a chart type plus the dimension/measure/data driving it — never raw chart-library configuration such as axis or series config). On the frontend, a `type → renderer` lookup replaces `AgentChart.tsx`'s hardcoded conditional, so the concrete Recharts configuration is assembled entirely inside each renderer, never handed down from the backend or the LLM. Neither side requires touching the agent pipeline to add the next type — a new type is a new Planner rule plus a new registry entry, nothing else.

`line` is the first concrete rule and renderer built on top of this architecture, added via the same rule-chain-as-fallback pattern `horizontal_bar` already uses (a rule's own condition determines fitness; an unsuitable shape falls through to the next rule, no separate suitability-validation pass). The `Visualization` contract gains two new optional fields, `dimension` and `measure`, recording which columns drove the selection — the semantic shape this whole architecture exists to keep, not a first step toward raw configuration. Today's working Predictive chart (pre-migration, old payload shape) must render unchanged through the new frontend registry — this is a structural refactor of *how* rendering is dispatched, not a rewrite of *what* renders.

This is deliberately scoped to exactly one new visualization type. It's the shared piece two separate, already-planned agent migrations (Diagnostic, Predictive) both need — building it once here avoids either migration duplicating the same Planner rule, and avoids committing to the full multi-type visualization registry surface ahead of real callers for anything beyond `line`.

## User Stories

1. As a user asking a question whose answer is inherently a trend over time (day-by-day counts, monthly revenue), I want a line chart rather than no chart or a mismatched chart type, so that the shape of the change is visible at a glance.
2. As a user, I want a forecast's confidence band (lower/upper bounds) to render on the same line chart the trend itself uses, so that visual treatment stays consistent whether or not the trend carries uncertainty.
3. As a user, I want chart-type selection to remain the Presentation Planner's job, not something an individual agent decides for itself, so that every future trend-shaped answer gets the same treatment.
4. As a backend engineer, I want a `line` Planner rule that only fires for a genuinely clean single-dimension, time-ordered, single-measure shape, and falls through safely otherwise, so that no misleading chart is ever rendered.
5. As a backend engineer, I want the `Visualization` contract to optionally record which column was the dimension and which was the measure, so that debugging a selection doesn't require re-deriving the Planner's reasoning by hand.
6. As a frontend engineer, I want a centralized `type → renderer` lookup for chart types, so that adding the next visualization type is one registry entry, not another branch in a growing conditional.
7. As a frontend engineer, I want the existing `bar` and `horizontal_bar` rendering behavior to be pixel-for-pixel unchanged after the registry refactor, so this is a safe restructuring, not a rewrite.
8. As a QA engineer, I want the `line` rule unit-tested as a pure function against synthetic `NormalizedResult` inputs, consistent with how the `horizontal_bar` rule is already tested.
9. As a product owner, I want this delivery scoped to exactly the `line` type plus the registry refactor it justifies — not the full visualization-type surface from the broader visualization-architecture brief this spec is drawn from — so each addition stays provably driven by a real scenario instead of speculative surface area.

## Implementation Decisions

- **Presentation Planner** gains a `line` rule: selected when a `NormalizedResult` has exactly one time-ordered (date) dimension and exactly one measure, with more than one row. It falls through to the existing kpi/none rules when the shape doesn't fit — the same pattern `horizontal_bar`'s shape check already uses. No separate suitability-validation or fallback-chain subsystem is introduced; a rule's own condition *is* the suitability check, and "fallback" is simply the next rule in the existing chain.
- **`Visualization` contract**: two new optional fields, `dimension` and `measure` — the column names that drove the selection. Populated only by the new `line` rule for now; existing types (`kpi`, `none`, `horizontal_bar`, `table`) leave them unset.
- **Confidence-interval band data**: a `line` visualization's data points may optionally carry `lower`/`upper` keys per point (matching the shape a forecast-producing agent already needs). This is a data-level convention, not a contract field — the Planner rule only decides *whether* `line` applies to the base trend; whichever agent has band data attaches it when building the chart's data points.
- **Frontend renderer registry**: `AgentChart.tsx`'s current `if (chart.type === "bar") ... else ...` branching becomes a plain object lookup mapping visualization type to a renderer function/component — no plugin system, no dynamic registration, matching the lightweight enum-keyed-object pattern already used elsewhere in this codebase (e.g. the `METRIC_FORMAT`/`INSIGHT_STYLE` maps in `AgentVisualization.tsx`). Adding a future type (bar, horizontal_bar, pie, donut, scatter, etc.) is a new Planner rule plus a new registry entry — neither requires touching `chat_router`, the agent modules, or any other renderer's code.
- **Semantic contract, never raw chart configuration**: the backend (and, by construction, the LLM — which never sees or produces visualization data at all, only prose) emits `{type, dimension, measure, data}` — never axis, series, tooltip, or any other chart-library-shaped configuration. The frontend renderer alone owns turning that semantic shape into actual Recharts props. This is why `dimension`/`measure` are named after what they *mean*, not how they'll be plotted — the same contract shape works whether a future renderer puts the measure on the x-axis, the y-axis, or a radius.
- **Charting library**: Recharts, already installed, already renders `line` (including band data, used today by Predictive's pre-migration chart) — no library change, no formal evaluation needed since the in-scope surface (just `line`, for this delivery) is already fully covered.
- No suitability-validation subsystem, no fallback-chain mechanism, and no observability/reason metadata are added anywhere in this delivery — each was considered and explicitly deferred (see Out of Scope).

## Testing Decisions

- Tests assert on external behavior — which visualization type and data a given `NormalizedResult` produces — not on internal call sequencing.
- **Presentation Planner**: the `line` rule tested as a pure function, fed synthetic `NormalizedResult` inputs — a clean date+measure series (should select `line`), a series with an extra dimension column (should NOT select `line`), and a single-row series (should fall through to `kpi`). Same seam and style as the existing `horizontal_bar` rule's tests.
- **Frontend**: no new automated tests (none exist for this area, consistent with prior deliveries in this series). The registry refactor is verified by confirming `bar`/`horizontal_bar` rendering is visually unchanged, plus a manual check once a real `line`-producing agent exists (in the Diagnostic/Predictive migration deliveries).
- This spec does not add an agent that produces `line` end-to-end — that verification belongs to the Diagnostic and Predictive migration deliveries, which are this rule's real callers.

## Out of Scope

- Any visualization type beyond `line` (pie, donut, scatter, stacked_bar, grouped_bar, area, heatmap, treemap, funnel, gauge, radar, waterfall, etc.) — each deferred until a real scenario needs it, per this pipeline's established incremental pattern (`kpi`/`none` → `horizontal_bar` → `line`, each added with a real caller already in hand).
- A general suitability-validation subsystem or fallback-chain mechanism in the Validator — the existing rule-chain-as-fallback pattern already satisfies this need.
- Observability/debug metadata (planner reason, rejected candidates, cardinality) on the wire contract — any future debugging need is a backend log line, not a response field, since no debug UI exists to consume one.
- An AI evaluation/regression dataset or harness — none exists in this repo today; standing one up is a separate initiative.
- A charting-library migration or formal Recharts-vs-ECharts evaluation — Recharts already covers everything in this delivery's scope.
- Any change to the Diagnostic or Predictive agents themselves — this spec only builds the shared Planner rule and contract/frontend support those agents' own migration deliveries will consume.

## Further Notes

- This spec exists because the Diagnostic and Predictive agent migrations (see `.scratch/diagnostic-agent-pipeline-migration/` and `.scratch/predictive-agent-pipeline-migration/`) both need a `line` visualization type from the shared Presentation Planner. Building it once here, rather than letting either migration build its own copy, preserves the pipeline's intent-agnostic design principle already established for `horizontal_bar`.
- This is a deliberately narrow first delivery drawn from a much larger "Visualization Architecture" brief (a full backend+frontend registry across ~20 chart types, a richer semantic contract with encoding/ranking/formatting fields, suitability validation with fallback chains, observability metadata, and an evaluation dataset). The full registry remains a target design, not committed scope — each further type gets added the same way `line` was: on demand, with a real caller, one ticket at a time.
