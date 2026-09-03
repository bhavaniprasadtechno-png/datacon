# 01 — Prefactor: payloadAdapter preserves citations/correlation on structured-shape payloads

**What to build:** `payloadAdapter.ts`'s structured-shape branch currently hardcodes `citations: [], actions: [], correlation: null` whenever a payload is detected as the new `StructuredResponse` shape. That's correct for Descriptive today (its payload is ever fully old-shape or fully new-shape, never both), but it's wrong for the two migrations this prefactor unblocks: Diagnostic's computed-spike case and Prescriptive's recommendation case both need to emit a real `StructuredResponse` (metrics/insights/visualizations/tables) *and* the flat escape-hatch `citations`/`correlation` fields on the same payload. Without this fix, citation chips and correlation tags would silently disappear for both agents the moment they ship.

Fix the adapter to read `citations`/`correlation` off the raw payload whenever present, regardless of whether the rest of the payload is old-shape or new-shape. This is a narrow, targeted fix to this one blind spot — not a general refactor of the adapter.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `adaptPayload` reads `citations` off the raw payload and includes them in the adapted result even when the payload is otherwise detected as `StructuredResponse`-shaped (has `summary` + `metrics`/`visualizations`/`tables`).
- [x] `adaptPayload` reads `correlation` off the raw payload the same way.
- [x] Any other explicitly-documented legacy/escape-hatch field on the old `AgentPayload` shape (currently: `citations`, `actions`, `correlation`) is preserved the same way when present alongside a structured-shape payload — `actions` now falls back to the raw payload's value too, not just `citations`/`correlation`.
- [x] Existing behavior is unchanged for: pure old-shape payloads (pre-refactor persisted messages, not-yet-migrated agents), and pure new-shape payloads with no escape-hatch fields at all (today's Descriptive messages) — covered by the second test case.
- [x] A focused unit test calls `adaptPayload` directly with a synthetic payload object that has both `summary`/`metrics` (structured) and `citations`/`correlation` (escape-hatch) set, and asserts all of them come through in the adapted result — first automated test for this module (`payloadAdapter.test.ts`); Vitest added as the test runner (zero-config against the existing `vite.config.ts`, no test infra existed anywhere in `app/web` before this).
- [x] No other change to `payloadAdapter.ts`, `AgentVisualization.tsx`, or `AgentChart.tsx` in this ticket — scoped strictly to the citations/correlation/actions blind spot.
