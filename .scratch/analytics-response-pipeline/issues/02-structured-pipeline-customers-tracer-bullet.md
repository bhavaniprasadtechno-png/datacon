# 02 — Structured response pipeline + "give me customers" tracer bullet

**What to build:** The full new pipeline — Result Normalizer, Analytics Engine, Validator, Insight Engine, and Presentation Planner (kpi/none/table rules) — wired end-to-end behind the Descriptive analyst for a plain aggregate/summary question against the `customers` dataset. This introduces the new Pydantic response contract, the matching shared frontend type, and a single backward-compat adapter that normalizes both pre-refactor persisted payloads and the four not-yet-migrated analysts' live payloads into that same shape. `chat_router` routes the `descriptive` intent through the new pipeline; the other four intents are untouched. SSE gains an `error` event. The frontend renders the full structured response for this scenario.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Result Normalizer converts a query-engine result into dataset name, row count, columns, classified dimensions/measures, typed values (categorical/numeric/date/percentage/currency, null-aware), and preserved source metadata for later evidence use.
- [ ] Analytics Engine deterministically computes totals/counts/percentages for the customers scenario — no LLM involvement in any numeric fact.
- [ ] Validator checks query success, metric arithmetic, insight evidence, and visualization/table field validity before a response is returned; a failing component is dropped or regenerated rather than discarding the whole response.
- [ ] Insight Engine produces insight statements grounded in Analytics Engine metrics only, each carrying at least one evidence reference to a real metric ID; no insight is emitted without evidence.
- [ ] Presentation Planner implements the `kpi`, `none` (chart-suppression), and `table` (relevant-column subset, default-collapsed) rules, and never selects a chart solely because rows were returned.
- [ ] New Pydantic response contract (summary/metrics/insights/visualizations/tables/sources) is used for the descriptive intent's structured response.
- [ ] Confidence is computed from query success + Validator outcome (high/medium/low per the spec's rules), never asserted directly by the LLM.
- [ ] Shared frontend type is extended to carry metrics/insights/visualizations/tables/sources.
- [ ] One backward-compat adapter normalizes both pre-refactor persisted payloads and live old-shape payloads (from the four not-yet-migrated analysts) into the new structured shape; the frontend renderer has a single render path driven by the adapted shape.
- [ ] SSE: `agent_delta` continues streaming summary prose unchanged; `agent_done.payload` for the descriptive intent carries the new structured contract; a new `error` event is emitted on pipeline failure (previously missing at the FastAPI layer).
- [ ] The LLM prompt for summary/insight prose is constrained to computed metrics and insight facts only, never raw query rows.
- [ ] Validator spot-checks that numbers in the streamed prose match the computed metrics; a mismatch affects confidence rather than blocking the (already-streamed) response.
- [ ] Frontend renders Summary, Metrics (KPI cards), Insights, a collapsed Table behind a "view underlying records" disclosure with relevant columns only, and Sources for the customers scenario.
- [ ] Asking "give me customers" in the running app produces the target UX end-to-end.
- [ ] An existing pre-refactor saved conversation and dashboard still render correctly through the adapter.
- [ ] Integration test: the descriptive analyst's structured-response entry point, tested via real DuckDB fixtures (`snapshot_store.load_dataset`) with `generator.generate_sql` mocked, covering the customers scenario and an insufficient-data case (no fabricated chart or insight).
- [ ] Unit tests: Presentation Planner's kpi/none/table rules as pure functions against synthetic `NormalizedResult` inputs; Analytics Engine percentage/aggregation arithmetic; Normalizer dimension/measure and null/date/percentage classification.
