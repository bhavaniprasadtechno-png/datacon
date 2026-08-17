# 03 — Category-comparison tracer bullet: "show tickets by status"

**What to build:** Extends the pipeline from ticket 02 to a category-comparison question against the `tickets` dataset grouped by status. Adds grouped-aggregation/ranking math to the Analytics Engine and a `horizontal_bar` rule to the Presentation Planner, replacing the Descriptive analyst's old hardcoded bar-chart shortcut for this query shape. Adds `horizontal_bar` rendering on the frontend.

**Blocked by:** 02

**Status:** done

**Note:** the real `tickets` fixture schema has no `status` column
(`ticket_id, account, region, priority, category, opened_at`) — the
tracer-bullet scenario used "tickets by category" instead of "by status";
same category-comparison shape, no behavior difference.

- [x] Analytics Engine adds grouped-aggregation and ranking calculations needed for a category breakdown (e.g. ticket counts grouped by status). — `rank_categories` in `app/ai/app/pipeline/analytics_engine.py`.
- [x] Presentation Planner adds the `horizontal_bar` rule — selected for category-comparison/ranking results, especially with more than a few categories or longer labels — as part of the same registry introduced in ticket 02. — `category_ranking` + `plan_visualization` in `presentation_planner.py`.
- [x] The Descriptive analyst's existing categorical-detection logic is rerouted through the new Presentation Planner instead of its previous hardcoded bar-chart output. — `_category_breakdown` in `descriptive.py` calls `category_ranking`; no hardcoded bar-chart path exists post-ticket-02, so this is a clean addition rather than a reroute.
- [x] Frontend chart component adds `horizontal_bar` rendering via the existing Recharts dependency; the shared visualization type is widened to include `horizontal_bar`. — `AgentChart.tsx` (shared-types already had `horizontal_bar` in `VisualizationType` from ticket 02).
- [x] Asking "show tickets by category" in the running app renders a horizontal bar chart plus a ranking-style insight, not a generic bar chart. — verified live in the running app (relaunched dev stack + claude-in-chrome): asked "Show orders by deal size" against the real `sales_data_sample` CSV (no mocking — real LLM SQL generation → `SELECT DEALSIZE, COUNT(ORDERNUMBER) ... GROUP BY DEALSIZE` → DuckDB → pipeline). Rendered a horizontal bar chart (Medium 1384, Small 1282, Large 157), a grounded ranking insight ("Medium has the most ... (1384, 49.0%)."), and a collapsed underlying-records table. Also spot-checked an existing pre-refactor saved conversation still renders correctly through the adapter (bar chart + full table). No console errors.
- [x] Integration test: the descriptive analyst's structured-response entry point, tested for the tickets-by-category scenario via the same DuckDB-fixture + mocked-SQL-generation seam as ticket 02. — `test_descriptive_answers_a_category_breakdown_with_horizontal_bar_and_ranking_insight` in `test_agents.py`.
- [x] Unit tests: Presentation Planner's `horizontal_bar` selection rule as a pure function; Analytics Engine grouped-aggregation/ranking math. — `test_presentation_planner.py`, `test_analytics_engine.py`, `test_insight_engine.py`.
