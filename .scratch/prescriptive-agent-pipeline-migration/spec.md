# Prescriptive Agent Pipeline Migration — Grounded Recommendations with a New Action Contract

Status: ready-for-agent

## Problem Statement

The Prescriptive analyst ("what should we do about churn?") still bypasses the structured analytics pipeline. Its headline figures (current churn rate, at-risk account count, target churn rate) never surface as explicit numbers — they're only interpolated into three hardcoded recommendation templates. Its confidence is a coarse "high if the query succeeded, else low," never factoring in whether a recommendation actually has supporting evidence. The module also contains two functions, `_build_actions` and `_offline_actions`, that take a data shape (`facts.get("churn")`, `facts.get("tickets")`, `facts.get("regions")`) nothing in `prepare()` actually builds — dead code left over from an earlier design. Finally, recommendation data (effort, owner, expected impact, supporting citations) has no home in the existing `StructuredResponse` contract at all.

## Solution

Migrate the Prescriptive analyst onto the same structured pipeline as Descriptive, Diagnostic, and Predictive: Result Normalizer → Analytics Engine → Validator → Insight Engine → Presentation Planner → `StructuredResponse`. This is the fourth and final delivery in this incremental per-agent migration series.

Prescriptive is the one agent in this series where the `StructuredResponse` contract itself gets extended: a new `Action` type (title, rationale, effort, owner, expected impact, and optional citation references) is added, since recommendation data doesn't fit losslessly into the existing `Metric` or `Insight` shapes the way every other migrated agent's output has. The `Action` objects are the authoritative record of what's being recommended — computed deterministically before the LLM ever runs, the same "facts first, prose second" discipline already established for every other migrated agent. The LLM's summary prose composes a user-readable explanation from those validated `Action` facts; it never invents a recommendation, a number, or a citation of its own. Churn figures (current rate, at-risk accounts, target rate) become headline KPI metrics. The response gets an explicit `none` visualization via the Presentation Planner — a deliberate decision that no chart adds value here, not an omission. Confidence now accounts for whether the RAG lookups actually found supporting citations for the recommended actions, rather than being a flat "high" whenever the churn query succeeds. Citations themselves stay on the flat escape-hatch pattern already shipped for Descriptive's document-QA fallback and planned for Diagnostic — referenced by the new `Action.citationIds`, unchanged from today's mechanism. The two dead functions are removed (confirmed zero callers — see Implementation Decisions). The three recommendation templates and their always-emitted (non-conditional) selection logic are otherwise unchanged — this is a structural migration, not a rework of which recommendations get made or when.

## User Stories

**As a person asking the assistant "what should we do about X?" questions:**

1. As a user, I want the churn figures behind a recommendation (current rate, at-risk accounts, target rate) shown as KPI metrics, so that I understand what's being acted on before reading the recommendations themselves.
2. As a user, I want each recommendation to show its title, rationale, effort level, owner, and expected impact in a consistent, structured shape, so that recommendations read as a considered plan, not free text.
3. As a user, I want to keep seeing which document a recommendation's rationale is grounded in (citation chips), exactly as I do today, so this migration doesn't regress functionality I already rely on.
4. As a user, I want the response's confidence to reflect whether the recommendations actually have supporting evidence, not just whether the churn query succeeded, so I know how much to trust a given plan.
5. As a user asking for recommendations when there's no churn data connected, I want a clear explanation of the limitation, not fabricated advice.
6. As a user, I want no chart shown when a chart wouldn't add anything to a list of recommendations, so the response stays focused on the actions themselves.
7. As a user with existing saved conversations and dashboards involving recommendations, I want them to keep rendering correctly after this migration ships.
8. As a user, I want the assistant's prose to keep streaming in live as it's generated, so the experience feels the same as it does today.

**As an engineer building and maintaining this system:**

9. As a backend engineer, I want a new `Action` contract type (title, rationale, effort, owner, expected impact, optional citation references) added to `StructuredResponse`, since this is the one migrated agent whose output genuinely doesn't fit the existing `Metric`/`Insight` shapes.
10. As a backend engineer, I want the two dead functions (`_build_actions`, `_offline_actions`) removed as part of this migration, since they're unreachable code operating on a data shape `prepare()` never builds.
11. As a backend engineer, I want today's always-emit-3-recommendations behavior preserved exactly as-is — making recommendations genuinely conditional on which underlying data conditions are met is a real but separate improvement, not part of this structural migration.
12. As a backend engineer, I want the unused `impact` field (defined on the old `PrescriptiveAction` type but never rendered) dropped from the new `Action` contract, rather than carried forward out of inertia.
13. As a backend engineer, I want recommendation priority to stay implicit in list order, since nothing today (including the dead `_build_actions` function) consumes an explicit priority number.
14. As a backend engineer, I want `Action.citationIds` to keep referencing the same flat escape-hatch `citations` list Diagnostic uses, so citation handling works identically across every agent that needs it.
15. As a backend engineer, I want confidence to account for citation-groundedness (whether RAG lookups actually found supporting evidence for the recommended actions), computed directly by this agent rather than through the Validator's generic issue-based logic — same precedent already set for Diagnostic and Predictive's domain-specific confidence.
16. As a backend engineer, I want the response's visualization to be an explicit `none` selected by the Presentation Planner (a real rule outcome), not simply the absence of visualization handling.
17. As a backend engineer, I want the `Action` objects to be computed and validated before the LLM ever runs, so the LLM's summary prose is composing an explanation from settled facts, never inventing or altering a recommendation.
18. As a QA engineer, I want the Prescriptive analyst's structured-response entry point testable against real DuckDB fixtures with only SQL generation mocked, consistent with the existing seam for every other agent in this series.

## Implementation Decisions

**Delivery scope**

- This is the fourth and final agent migration in the incremental series (Descriptive → Diagnostic → Predictive → Prescriptive). `chat_router`'s per-intent dispatch requires no changes, same as every prior migration.
- Action-generation logic itself is unchanged: the three recommendation templates are still always emitted (with interpolated numbers) whenever the churn query succeeds, never conditional on whether ticket/region data actually supports each one. Making this genuinely data-driven (reviving something closer to the dead `_build_actions`'s conditional approach) is a real, separate future improvement, not part of this structural migration — it would also require gathering ticket/region facts `prepare()` doesn't currently query at all.

**Dead code**

- `_build_actions` and `_offline_actions` are removed — confirmed zero callers (a repo-wide search finds neither referenced outside their own definitions; `prepare()` never calls them). Both operate on a `facts` dict shape (`facts.get("churn")`, `facts.get("tickets")`, `facts.get("regions")`) that nothing in the current agent builds. This is the same class of finding as the original pipeline delivery's ticket-01 dead-code retirement. This removal is scoped strictly to these two confirmed-dead functions — no other cleanup in this module rides along with it.

**Contract extension: `Action`**

- A new `Action` type is added to the `StructuredResponse` contract: `title`, `rationale`, `effort` (Low/Medium/High), `owner`, `expectedImpact`, and an optional `citationIds` list. This is the only contract extension in this entire four-agent series — every other agent's output fit the existing `Metric`/`Insight`/`Visualization`/`Table`/`Source` shapes; Prescriptive's doesn't.
- The `impact` field from today's pre-migration `PrescriptiveAction` type (e.g. `"-0.4pp"`) is dropped — it's defined today but never rendered by the frontend (only `expectedImpact`, the prose version, is shown). An unused field carried into a brand-new contract on day one is dead weight from the start.
- No explicit `priority` field is added — array order alone encodes priority today, and nothing (not even the dead `_build_actions` function) ever consumed an explicit number.
- `Action.citationIds` continues referencing entries in the flat escape-hatch `citations` list, unchanged in mechanism from today and from Diagnostic's equivalent usage.

**Metrics**

- Current churn rate, at-risk account count, and target churn rate become headline `Metric`/KPI cards, mirroring the hierarchy already established across this series.

**Visualization**

- The Presentation Planner returns an explicit `none` visualization for Prescriptive's shape (metrics plus a list of actions, no chart-worthy data) — reusing the Planner's existing `none` rule (already selected today when there are no metrics to chart around), not a special case bypassing the Planner.

**Confidence**

- Confidence now factors in citation-groundedness: whether the RAG lookups backing the recommended actions actually found supporting citations, not just whether the churn query itself succeeded. Computed directly by this agent and placed into the structured response's confidence field, the same precedent as Diagnostic's and Predictive's domain-specific confidence — the shared Validator's issue vocabulary stays limited to structural checks (insight evidence, table columns, visualization shape), not citation-groundedness judgments specific to RAG-backed agents.
- The true-empty-state response (no churn data connected) returns a real `StructuredResponse` with `confidence: low` and empty metrics/insights/actions, mirroring the no-data precedent established by every prior agent in this series.

**Citations and the escape hatch**

- Citations continue as flat escape-hatch fields (`citations`) outside the `StructuredResponse` contract proper, referenced by `Action.citationIds` — the same pattern already shipped for Descriptive's document-QA fallback and planned for Diagnostic. No change to the citation-lookup or cross-action dedup logic itself.

## Testing Decisions

- Tests assert on external behavior — the shape and values of the structured response, which actions/metrics/confidence resulted — not on internal call sequencing.
- **Primary integration seam**: the Prescriptive analyst's structured-response entry point (`prepare()`), tested against real DuckDB fixtures loaded via `snapshot_store.load_dataset`, with `generator.generate_sql` mocked — the same seam already used across this series. Assertions cover: a successful recommendation scenario with citations found for at least one action, a successful scenario with no citations found for any action (lower confidence), and a true-empty-state (no churn data) scenario.
- **Focused unit tests**: the new `Action` contract model's validation/serialization (mirroring how `Metric`/`Insight`/`Table` are already unit-tested in `test_contracts.py`).
- Frontend: no new automated tests (none exist for this area). Verified manually in the running app — a fresh recommendation message rendering through the new `Action`-typed structured payload with citation chips intact, and confirmation that an existing pre-migration recommendation message still renders correctly through the adapter.

## Out of Scope

- Making recommendations genuinely conditional on underlying data (reviving `_build_actions`'s conditional logic, gathering ticket/region facts) — a real, separate future improvement.
- Migrating General onto the new pipeline — not part of this series.
- Any visualization type for Prescriptive beyond the explicit `none` selection.
- Folding citation-groundedness into the shared Validator's issue vocabulary — confidence stays agent-computed for this concern.
- Any change to `chat_router`'s routing logic — none is needed.
- Any change to authentication, RBAC, or connector credential handling.

## Further Notes

- This is the fourth and final delivery in the incremental per-agent migration series: Descriptive (`.scratch/analytics-response-pipeline/`) → Diagnostic (`.scratch/diagnostic-agent-pipeline-migration/`) → Predictive (`.scratch/predictive-agent-pipeline-migration/`) → this one. Once this ships, every specialized agent (Descriptive, Diagnostic, Predictive, Prescriptive) emits the shared `StructuredResponse` contract; only General remains on the pre-pipeline path, unchanged by design.
- The `Action` contract type introduced here is the first and only contract extension across the whole series — everything else (citations, correlation) stayed on the flat escape-hatch pattern by deliberate choice, reserved for data that's genuinely structural and reusable rather than agent-specific.
