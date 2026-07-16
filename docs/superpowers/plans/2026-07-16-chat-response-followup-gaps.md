# Chat Response Follow-up Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three remaining gaps between datacon's chat response and the `C:\Users\pc\Desktop\datavue` reference: prescriptive recommendation cards gain rationale/expected-impact/per-item citations, the predictive chart gains a visible confidence-interval band, and the descriptive agent can add a category-distribution chart alongside a wider raw-records table.

**Architecture:** Backend enrichment stays deterministic and Python-computed (unchanged project principle) — no new LLM calls anywhere in this plan. `prescriptive.py`'s 3 action templates gain code-computed rationale/expected-impact strings and per-action topic-scoped citation lookups. A new `executor.grouped_count()` reuses the already-validated SQL from the original question (no second LLM round trip) to compute a category distribution. The frontend renders the richer payload: `AgentChart.tsx` adds a shaded `recharts` `Area` band for forecast points, `AgentVisualization.tsx` replaces the bare `ActionsTable` grid with `RecommendationCards`.

**Tech Stack:** FastAPI + Python (agents, executor), React + TypeScript + `recharts` (already a dependency).

## Global Constraints

- Per this session's explicit instruction, **no git operations** in this plan — no `git add`, no `git commit`. Each task ends with tests passing in the working tree; the user manages git themselves.
- `confidence`/payload fields remain deterministic, Python-computed — never LLM-authored, consistent with `2026-07-15-chat-agent-payload-parity-design.md`.
- No automated frontend test runner exists in `app/web` (still true, per the prior two plans). Frontend tasks are verified with `npx tsc -b --force` from `app/web` plus one manual end-to-end pass in the final task.
- Python test command (run from `app/ai`): `"./.venv/Scripts/python.exe" -m pytest <path> -v`
- New identifier-exclusion note: real identifier columns (`_id`, `*_id`, `*Id`, `*ID`) are already stripped upstream by `executor._filter_sensitive_columns` before any agent sees them — so the new distribution-column heuristic in Task 4 deliberately does **not** include bare `"id"` in its own denylist (it would false-positive on ordinary words like "Provider" or "Video").

---

### Task 1: Shared types — `PrescriptiveAction` gains rationale/expectedImpact/citationIds

**Files:**
- Modify: `app/packages/shared-types/src/chat.ts:31-36`
- Test: `npx tsc -b --force` from `app/web`

**Interfaces:**
- Produces: `PrescriptiveAction` with three new fields (`rationale: string`, `expectedImpact: string`, `citationIds?: number[]`), exported from `@datacon/shared-types`, unchanged otherwise.
- Consumed by: Task 2 (Python builds dicts matching this shape — no static cross-language check, but Task 2's pytest assertions pin the exact dict shape) and Task 6 (`AgentVisualization.tsx`'s new `RecommendationCards`).

This is a type-only addition of required fields to an interface nothing in the frontend currently constructs object literals against (`PrescriptiveAction` values only ever arrive over the wire and get read, not built, client-side) — so unlike the shared-types change in the prior payload-parity plan, this step causes **no** temporary compile error anywhere.

- [ ] **Step 1: Confirm current typecheck is clean (baseline)**

Run: `cd app/web && npx tsc -b --force`
Expected: no output (exits 0).

- [ ] **Step 2: Replace `app/packages/shared-types/src/chat.ts` lines 31-36**

Replace:
```ts
export interface PrescriptiveAction {
  title: string;
  impact: string;
  effort: "Low" | "Medium" | "High";
  owner: string;
}
```
with:
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

- [ ] **Step 3: Run typecheck, confirm it's still clean**

Run: `cd app/web && npx tsc -b --force`
Expected: no output (exits 0) — no consuming code needs updating for this step alone.

---

### Task 2: `prescriptive.py` — templated rationale/expectedImpact + per-action topic-scoped citations

**Files:**
- Modify: `app/ai/app/agents/prescriptive.py` (full file, currently 73 lines)
- Test: `app/ai/tests/agents/test_agents.py` (prescriptive tests, lines 117-146)

**Interfaces:**
- Consumes: unchanged (`answer_question`, `column_index`, `chroma_query`).
- Produces: `AgentPrep.payload["actions"]` items shaped `{"title", "impact", "effort", "owner", "rationale", "expectedImpact", "citationIds"?: [int, ...]}`. `payload["citations"]` remains the deduped union across all actions' queries (unchanged shape/key from the prior plan), omitted when no action found any hit.

- [ ] **Step 1: Replace the two existing prescriptive tests**

Replace:
```python
@pytest.mark.asyncio
async def test_prescriptive_builds_actions_from_a_real_free_form_query():
    snapshot_store.load_dataset("churn", pd.DataFrame({"churn_pct": [3.1], "prev_churn_pct": [3.5], "at_risk_accounts": [12]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT churn_pct, prev_churn_pct, at_risk_accounts FROM churn")), \
         patch.object(prescriptive, "chroma_query", return_value=[]):
        prep = await prescriptive.prepare("how do we reduce churn?")
    assert len(prep.payload["actions"]) == 3
    assert "12 at-risk" in prep.payload["actions"][0]["title"]
    assert prep.payload["confidence"] == "high"
    assert "citations" not in prep.payload
    assert "3.1" in prep.offline_text


@pytest.mark.asyncio
async def test_prescriptive_includes_citations_when_a_supporting_document_is_found():
    snapshot_store.load_dataset("churn", pd.DataFrame({"churn_pct": [3.1], "prev_churn_pct": [3.5], "at_risk_accounts": [12]}))
    hit = {"metadata": {"title": "Billing Postmortem", "filename": "billing.pdf", "chunk_index": 1}, "snippet": "billing errors caused churn", "distance": 0.2}
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT churn_pct, prev_churn_pct, at_risk_accounts FROM churn")), \
         patch.object(prescriptive, "chroma_query", return_value=[hit]):
        prep = await prescriptive.prepare("how do we reduce churn?")
    assert prep.payload["citations"] == [
        {"id": 1, "documentTitle": "Billing Postmortem", "filename": "billing.pdf", "chunkIndex": 1, "snippet": "billing errors caused churn"}
    ]
```
with:
```python
@pytest.mark.asyncio
async def test_prescriptive_builds_actions_from_a_real_free_form_query():
    snapshot_store.load_dataset("churn", pd.DataFrame({"churn_pct": [3.1], "prev_churn_pct": [3.5], "at_risk_accounts": [12]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT churn_pct, prev_churn_pct, at_risk_accounts FROM churn")), \
         patch.object(prescriptive, "chroma_query", return_value=[]):
        prep = await prescriptive.prepare("how do we reduce churn?")
    assert len(prep.payload["actions"]) == 3
    assert "12 at-risk" in prep.payload["actions"][0]["title"]
    assert prep.payload["confidence"] == "high"
    assert "citations" not in prep.payload
    assert "3.1" in prep.offline_text
    for action in prep.payload["actions"]:
        assert action["rationale"]
        assert action["expectedImpact"]
        assert "citationIds" not in action


@pytest.mark.asyncio
async def test_prescriptive_assigns_topic_scoped_citations_per_action():
    snapshot_store.load_dataset("churn", pd.DataFrame({"churn_pct": [3.1], "prev_churn_pct": [3.5], "at_risk_accounts": [12]}))
    billing_hit = {"metadata": {"title": "Billing Postmortem", "filename": "billing.pdf", "chunk_index": 1}, "snippet": "billing errors caused churn", "distance": 0.2}

    def fake_chroma_query(topic, n_results=2):
        if "billing" in topic:
            return [billing_hit]
        return []

    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT churn_pct, prev_churn_pct, at_risk_accounts FROM churn")), \
         patch.object(prescriptive, "chroma_query", side_effect=fake_chroma_query):
        prep = await prescriptive.prepare("how do we reduce churn?")

    actions = prep.payload["actions"]
    assert "citationIds" not in actions[0]
    assert actions[1]["citationIds"] == [1]
    assert "citationIds" not in actions[2]
    assert prep.payload["citations"] == [
        {"id": 1, "documentTitle": "Billing Postmortem", "filename": "billing.pdf", "chunkIndex": 1, "snippet": "billing errors caused churn"}
    ]
```

- [ ] **Step 2: Run tests, confirm they fail against current code**

Run (from `app/ai`): `"./.venv/Scripts/python.exe" -m pytest tests/agents/test_agents.py -k prescriptive -v`
Expected: FAIL — `test_prescriptive_builds_actions_from_a_real_free_form_query` fails on the new `rationale`/`expectedImpact` assertions (`KeyError`); `test_prescriptive_assigns_topic_scoped_citations_per_action` fails because `chroma_query` is currently called once for the whole payload, not once per action topic, so `actions[1]["citationIds"]` doesn't exist.

- [ ] **Step 3: Replace `app/ai/app/agents/prescriptive.py` in full**

```python
from app.agents.types import AgentPrep
from app.query_engine.executor import answer_question
from app.query_engine.extract import column_index
from app.rag.chroma_store import query as chroma_query

SYSTEM = (
    "You are Datacon's prescriptive analytics agent. Given real churn/at-risk-account "
    "figures, write one tight opening sentence introducing a short action list to reduce "
    "churn. Do not invent numbers beyond what's provided."
)

NO_DATA_TEXT = (
    "No churn data is connected yet. Connect a data source with churn/at-risk account "
    "figures to enable recommendations."
)

_CHURN_QUESTION = (
    "The single most recent churn rate percentage, the previous period's churn rate "
    "percentage, and the number of at-risk accounts."
)


def _action_templates(at_risk_accounts: int, target: float) -> list[dict]:
    return [
        {
            "title": f"Launch save-offer for {at_risk_accounts} at-risk enterprise accounts",
            "impact": "-0.4pp",
            "effort": "Low",
            "owner": "Success",
            "rationale": "These accounts show renewal-risk signals in the churn data; proactive outreach historically recovers a portion before cancellation.",
            "expectedImpact": f"Projected to reduce churn by ~0.4pp, protecting an estimated {at_risk_accounts} accounts this quarter.",
            "_topic": "at-risk account renewal retention outreach",
        },
        {
            "title": "Fix billing errors flagged in support documentation",
            "impact": "-0.2pp",
            "effort": "Medium",
            "owner": "Engineering",
            "rationale": "Billing errors are a recurring theme in support tickets and a known churn driver when customers feel over-charged or under-served.",
            "expectedImpact": f"Projected to reduce churn by ~0.2pp toward {target:.1f}% by removing a top complaint-driven cancellation trigger.",
            "_topic": "billing error incident",
        },
        {
            "title": "Add usage-drop alerts for accounts under 40% active seats",
            "impact": "-0.1pp",
            "effort": "Low",
            "owner": "Product",
            "rationale": "Low seat utilization is a leading indicator of non-renewal; early alerts let Customer Success intervene before the renewal decision is made.",
            "expectedImpact": "Projected to reduce churn by ~0.1pp via earlier intervention on declining-usage accounts.",
            "_topic": "usage adoption seat utilization",
        },
    ]


async def prepare(question: str, model: str | None = None) -> AgentPrep:
    result = await answer_question(_CHURN_QUESTION, model)
    churn_idx = column_index(result.columns, "churnpct", "churn_pct", "churn") if result.ok else -1

    if not result.ok or churn_idx < 0 or not result.rows:
        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\nNo churn data is connected.",
            offline_text=NO_DATA_TEXT,
            payload={"confidence": "low"},
        )

    at_risk_idx = column_index(result.columns, "atrisk", "at_risk", "risk")
    row = result.rows[0]
    churn_pct = float(row[churn_idx])
    at_risk_accounts = int(row[at_risk_idx]) if at_risk_idx >= 0 else 0

    target = max(churn_pct - 0.7, 0.0)
    templates = _action_templates(at_risk_accounts, target)

    offline_text = f"Three actions are projected to bring churn from {churn_pct:.1f}% toward {target:.1f}% this quarter:"

    prompt = (
        f"Question: {question}\n\nComputed facts:\n- Current churn: {churn_pct:.1f}%\n"
        f"- At-risk accounts: {at_risk_accounts}\n- Target churn: {target:.1f}%\n"
        f"- Planned actions: {[t['title'] for t in templates]}"
    )

    citations: list[dict] = []
    seen: dict[tuple[str, int], int] = {}
    actions: list[dict] = []
    for t in templates:
        hits = chroma_query(t["_topic"], n_results=2)
        action_citation_ids: list[int] = []
        for h in hits:
            key = (h["metadata"].get("filename", ""), h["metadata"].get("chunk_index", 0))
            if key not in seen:
                seen[key] = len(citations) + 1
                citations.append({
                    "id": seen[key],
                    "documentTitle": h["metadata"].get("title", h["metadata"].get("filename", "Untitled")),
                    "filename": h["metadata"].get("filename", ""),
                    "chunkIndex": h["metadata"].get("chunk_index", 0),
                    "snippet": h["snippet"][:220],
                })
            action_citation_ids.append(seen[key])
        action = {k: v for k, v in t.items() if k != "_topic"}
        if action_citation_ids:
            action["citationIds"] = action_citation_ids
        actions.append(action)

    payload = {"confidence": "high", "actions": actions}
    if citations:
        payload["citations"] = citations

    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload=payload)
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `"./.venv/Scripts/python.exe" -m pytest tests/agents/test_agents.py -k prescriptive -v`
Expected: 2 passed.

---

### Task 3: `executor.py` — `grouped_count()` helper (no new LLM call)

**Files:**
- Modify: `app/ai/app/query_engine/executor.py` (append after `answer_question`, currently ends at line 105)
- Test: `app/ai/tests/query_engine/test_executor.py` (append new cases after line 133)

**Interfaces:**
- Consumes: the module's existing private `_execute_with_timeout`, `_is_safe_select`, `logger`.
- Produces: `grouped_count(base_sql: str, column: str) -> QueryAnswer` — same `QueryAnswer` dataclass `answer_question` returns. Consumed by Task 4 (`descriptive.py`).

- [ ] **Step 1: Write the failing tests**

Append to `app/ai/tests/query_engine/test_executor.py`:

```python
@pytest.mark.asyncio
async def test_grouped_count_wraps_and_executes_the_given_sql():
    snapshot_store.load_dataset("leads", pd.DataFrame({"status": ["Won", "Won", "New"]}))
    result = await executor.grouped_count("SELECT status FROM leads", "status")
    assert result.ok is True
    assert result.columns == ["label", "value"]
    assert sorted(result.rows) == sorted([["Won", 2], ["New", 1]])


@pytest.mark.asyncio
async def test_grouped_count_strips_a_trailing_semicolon_before_wrapping():
    snapshot_store.load_dataset("leads", pd.DataFrame({"status": ["Won"]}))
    result = await executor.grouped_count("SELECT status FROM leads;", "status")
    assert result.ok is True
    assert result.rows == [["Won", 1]]


@pytest.mark.asyncio
async def test_grouped_count_returns_not_ok_on_a_column_the_inner_query_does_not_have():
    snapshot_store.load_dataset("leads", pd.DataFrame({"status": ["Won"]}))
    result = await executor.grouped_count("SELECT status FROM leads", "does_not_exist")
    assert result.ok is False
```

- [ ] **Step 2: Run tests, confirm they fail**

Run (from `app/ai`): `"./.venv/Scripts/python.exe" -m pytest tests/query_engine/test_executor.py -k grouped_count -v`
Expected: FAIL — `AttributeError: module 'app.query_engine.executor' has no attribute 'grouped_count'` on all three.

- [ ] **Step 3: Append `grouped_count` to `app/ai/app/query_engine/executor.py`**

Add at the end of the file (after the existing `answer_question` function's closing `return QueryAnswer(ok=False, columns=[], rows=[], sql=sql, message="Query failed.")`):

```python


async def grouped_count(base_sql: str, column: str) -> QueryAnswer:
    """Wraps an already-validated SELECT (the exact SQL answer_question just
    ran, available as QueryAnswer.sql) as a GROUP BY/COUNT subquery — no LLM
    call, guaranteed to run against the exact same rows the original query
    produced."""
    inner = base_sql.strip().rstrip(";")
    wrapped = (
        f'SELECT "{column}" AS label, COUNT(*) AS value\n'
        f"FROM ({inner}) AS _dc_dist\n"
        f'GROUP BY "{column}"\n'
        "ORDER BY value DESC\n"
        "LIMIT 20"
    )
    if not _is_safe_select(wrapped):
        return QueryAnswer(ok=False, columns=[], rows=[], sql=wrapped, message="Generated query was rejected (not a read-only SELECT).")
    try:
        columns, rows = await _execute_with_timeout(wrapped)
        return QueryAnswer(ok=True, columns=columns, rows=rows, sql=wrapped, message="ok")
    except Exception as e:
        logger.warning("[Executor] grouped_count query failed: %s", e)
        return QueryAnswer(ok=False, columns=[], rows=[], sql=wrapped, message=f"Grouped count query failed: {e}")
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `"./.venv/Scripts/python.exe" -m pytest tests/query_engine/test_executor.py -k grouped_count -v`
Expected: 3 passed.

- [ ] **Step 5: Run the full executor test suite**

Run: `"./.venv/Scripts/python.exe" -m pytest tests/query_engine/test_executor.py -v`
Expected: 15 passed (12 existing + 3 new).

---

### Task 4: `descriptive.py` — distribution-column heuristic wired to `grouped_count`

**Files:**
- Modify: `app/ai/app/agents/descriptive.py` (full file, currently 49 lines)
- Test: `app/ai/tests/agents/test_agents.py` (descriptive tests, lines 15-46)

**Interfaces:**
- Consumes: `app.query_engine.executor.answer_question` (unchanged) and `app.query_engine.executor.grouped_count` (new, Task 3).
- Produces: `_pick_distribution_column(columns: list[str], rows: list[list]) -> str | None` (private, no other consumers). `AgentPrep.payload` gains an additional path to a `"chart"` key (same `{"type": "bar", "title": str, "data": [...]}` shape as the existing categorical path) when `_looks_categorical` is `False` and a qualifying column is found.

- [ ] **Step 1: Add three new descriptive tests**

Append to `app/ai/tests/agents/test_agents.py`, immediately after the existing `test_descriptive_adds_a_bar_chart_when_the_result_is_a_small_categorical_comparison` test:

```python
@pytest.mark.asyncio
async def test_descriptive_adds_a_distribution_chart_for_a_low_cardinality_column_in_a_wider_table():
    snapshot_store.load_dataset(
        "leads",
        pd.DataFrame({
            "name": ["Ashwarya Aggarwal", "Deepinder", "Rivisha Tenter", "Jane"],
            "email": ["sherry@x.com", "deep@x.com", "sherry2@x.com", "jane@example.com"],
            "status": ["Won", "Won", "Won", "New"],
        }),
    )
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT name, email, status FROM leads")):
        prep = await descriptive.prepare("give leads")
    assert prep.payload["table"]["columns"] == ["name", "email", "status"]
    assert prep.payload["chart"] == {
        "type": "bar",
        "title": "status distribution",
        "data": [
            {"label": "Won", "value": 3.0},
            {"label": "New", "value": 1.0},
        ],
    }


@pytest.mark.asyncio
async def test_descriptive_omits_chart_when_no_column_qualifies():
    snapshot_store.load_dataset(
        "leads",
        pd.DataFrame({"name": ["Ashwarya", "Deepinder"], "email": ["a@x.com", "b@x.com"]}),
    )
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT name, email FROM leads")):
        prep = await descriptive.prepare("give leads")
    assert "chart" not in prep.payload


@pytest.mark.asyncio
async def test_descriptive_omits_chart_when_the_grouped_count_query_fails():
    snapshot_store.load_dataset(
        "leads",
        pd.DataFrame({"name": ["A", "B"], "status": ["Won", "New"]}),
    )
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT name, status FROM leads")), \
         patch.object(descriptive, "grouped_count", new=AsyncMock(side_effect=RuntimeError("boom"))):
        prep = await descriptive.prepare("give leads")
    assert prep.payload["table"]["columns"] == ["name", "status"]
    assert "chart" not in prep.payload
```

- [ ] **Step 2: Run tests, confirm they fail**

Run (from `app/ai`): `"./.venv/Scripts/python.exe" -m pytest tests/agents/test_agents.py -k "distribution_chart or omits_chart" -v`
Expected: FAIL — `test_descriptive_adds_a_distribution_chart...` fails with `KeyError: 'chart'`; `test_descriptive_omits_chart_when_the_grouped_count_query_fails` fails with `AttributeError: module 'app.agents.descriptive' has no attribute 'grouped_count'` (not yet imported). `test_descriptive_omits_chart_when_no_column_qualifies` already passes against current code (no regression risk there, just confirms the negative case up front).

- [ ] **Step 3: Replace `app/ai/app/agents/descriptive.py` in full**

```python
import logging

from app.agents.types import AgentPrep
from app.query_engine.executor import answer_question, grouped_count

logger = logging.getLogger("app.agents.descriptive")

SYSTEM = (
    "You are Datacon's descriptive analytics agent. Given a real query result table, "
    "answer the user's question about it in one tight paragraph (3-4 sentences) for a "
    "business audience. Do not invent numbers beyond what's provided."
)

_DISTRIBUTION_DENYLIST = ("email", "name", "url", "phone", "date", "created", "updated", "title", "description")


def _stringify_row(row: list) -> list:
    return [v if v is None or isinstance(v, (int, float, bool, str)) else str(v) for v in row]


def _looks_categorical(columns: list[str], rows: list[list]) -> bool:
    """Two columns, a handful of rows, second column all-numeric — reads
    better as a bar chart than a bare table (e.g. "revenue by region")."""
    if len(columns) != 2 or not (2 <= len(rows) <= 20):
        return False
    return all(isinstance(row[1], (int, float)) and not isinstance(row[1], bool) for row in rows)


def _pick_distribution_column(columns: list[str], rows: list[list]) -> str | None:
    """First column (in column order) that's all-string, not id/email/name/
    url/phone/date-shaped, and has 2-8 distinct values — a candidate for a
    secondary count-by-category chart alongside a wider raw-records table.
    Real identifier columns (_id, *_id, *Id, *ID) are already stripped
    upstream by executor._filter_sensitive_columns, so bare "id" isn't in
    this denylist — it would otherwise false-positive on ordinary words like
    "Provider" or "Video"."""
    for i, name in enumerate(columns):
        lowered = name.lower()
        if any(bad in lowered for bad in _DISTRIBUTION_DENYLIST):
            continue
        values = [row[i] for row in rows]
        if any(v is not None and not isinstance(v, str) for v in values):
            continue
        distinct = {v for v in values if v is not None}
        if 2 <= len(distinct) <= 8:
            return name
    return None


async def prepare(question: str, model: str | None = None) -> AgentPrep:
    result = await answer_question(question, model)

    if not result.ok:
        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\n{result.message}",
            offline_text=result.message,
            payload={"confidence": "low"},
        )

    shown_rows = [_stringify_row(row) for row in result.rows[:20]]
    prompt = f"Question: {question}\n\nQuery result:\nColumns: {result.columns}\nRows: {shown_rows}"
    offline_text = f"Found {len(result.rows)} result row(s) for \"{question}\" across columns {', '.join(result.columns)}."

    payload = {
        "confidence": "high",
        "table": {"columns": result.columns, "rows": shown_rows},
    }
    if _looks_categorical(result.columns, shown_rows):
        payload["chart"] = {
            "type": "bar",
            "title": f"{result.columns[1]} by {result.columns[0]}",
            "data": [{"label": str(row[0]), "value": float(row[1])} for row in shown_rows],
        }
    else:
        column = _pick_distribution_column(result.columns, result.rows)
        if column:
            try:
                grouped = await grouped_count(result.sql, column)
            except Exception:
                logger.exception("Distribution chart query failed for column %s", column)
                grouped = None
            if grouped is not None and grouped.ok and grouped.rows:
                payload["chart"] = {
                    "type": "bar",
                    "title": f"{column} distribution",
                    "data": [{"label": str(row[0]), "value": float(row[1])} for row in grouped.rows],
                }

    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload=payload)
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `"./.venv/Scripts/python.exe" -m pytest tests/agents/test_agents.py -k descriptive -v`
Expected: 6 passed.

- [ ] **Step 5: Run the full backend agent test suite**

Run: `"./.venv/Scripts/python.exe" -m pytest tests/agents/test_agents.py -v`
Expected: 14 passed (11 existing + 3 new descriptive tests; prescriptive's count is unchanged from Task 2 — one existing test gained assertions, the other was replaced in place, not added).

---

### Task 5: `AgentChart.tsx` — shaded confidence-interval band on the forecast line chart

**Files:**
- Modify: `app/web/src/routes/chat/AgentChart.tsx` (full file, currently 73 lines)
- Test: `npx tsc -b --force` from `app/web`

**Interfaces:**
- Consumes: `AgentChart` (type, unchanged — `lower`/`upper` already optional on `ChartPoint`).
- Produces: no interface change — `AgentChart` (component)'s props are unchanged; this task only changes what it renders internally.

- [ ] **Step 1: Confirm current typecheck is clean (baseline)**

Run: `cd app/web && npx tsc -b --force`
Expected: no output (exits 0).

- [ ] **Step 2: Replace `app/web/src/routes/chat/AgentChart.tsx` in full**

```tsx
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { AgentChart as AgentChartData } from "@datacon/shared-types";

function formatMillions(value: number): string {
  return `$${value.toFixed(2)}M`;
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div style={{ font: "600 9px 'IBM Plex Mono',monospace", color: "var(--ac-muted)", marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 13, fontWeight: 700, color: color ?? "var(--ac-fg)" }}>{value}</div>
    </div>
  );
}

export function AgentChart({ chart }: { chart: AgentChartData }) {
  if (!chart.data.length) return null;

  if (chart.type === "bar") {
    return (
      <div style={{ background: "var(--ac-bg-muted)", border: "1px solid var(--ac-border)", borderRadius: "var(--radius-lg)", padding: 14, marginTop: 10 }}>
        <div style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--ac)", marginBottom: 8 }}>
          {chart.title.toUpperCase()}
        </div>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={chart.data} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--ac-border)" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="var(--ac-muted)" />
            <YAxis tick={{ fontSize: 11 }} stroke="var(--ac-muted)" width={40} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <Bar dataKey="value" fill="var(--ac)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  // Line chart: history points followed by one appended forecast point
  // carrying lower/upper — the stat row below reads straight off that last
  // pair of points instead of duplicating formatted fields on the payload.
  const last = chart.data[chart.data.length - 1];
  const prev = chart.data.length > 1 ? chart.data[chart.data.length - 2] : undefined;
  const hasForecast = last.lower !== undefined && last.upper !== undefined;
  const growthPct = hasForecast && prev ? ((last.value - prev.value) / prev.value) * 100 : undefined;

  return (
    <div style={{ background: "var(--ac-bg-muted)", border: "1px solid var(--ac-border)", borderRadius: "var(--radius-lg)", padding: 14, marginTop: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
        <span style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--ac)" }}>{chart.title.toUpperCase()}</span>
        {hasForecast && <span style={{ font: "600 10px 'IBM Plex Mono',monospace", color: "var(--ac-muted)" }}>95% CI</span>}
      </div>
      <ResponsiveContainer width="100%" height={140}>
        {hasForecast ? (
          <ComposedChart data={chart.data} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--ac-border)" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="var(--ac-muted)" />
            <YAxis tick={{ fontSize: 11 }} stroke="var(--ac-muted)" width={40} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <Area type="monotone" dataKey="lower" stroke="none" fill="var(--ac)" fillOpacity={0} legendType="none" />
            <Area type="monotone" dataKey="upper" stroke="none" fill="var(--ac)" fillOpacity={0.12} legendType="none" />
            <Line type="monotone" dataKey="value" stroke="var(--ac)" strokeWidth={2} dot={{ r: 3 }} />
          </ComposedChart>
        ) : (
          <LineChart data={chart.data} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--ac-border)" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="var(--ac-muted)" />
            <YAxis tick={{ fontSize: 11 }} stroke="var(--ac-muted)" width={40} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <Line type="monotone" dataKey="value" stroke="var(--ac)" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        )}
      </ResponsiveContainer>
      {hasForecast && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, textAlign: "center", marginTop: 10 }}>
          <Stat label="PROJECTED" value={formatMillions(last.value)} />
          <Stat label="95% CI" value={`${formatMillions(last.lower as number)}–${formatMillions(last.upper as number)}`} />
          {growthPct !== undefined && (
            <Stat label="GROWTH" value={`${growthPct >= 0 ? "+" : ""}${growthPct.toFixed(1)}%`} color="#0f8a5c" />
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Run typecheck, confirm it's clean**

Run: `cd app/web && npx tsc -b --force`
Expected: no output (exits 0).

---

### Task 6: `AgentVisualization.tsx` — `RecommendationCards` replaces `ActionsTable`

**Files:**
- Modify: `app/web/src/routes/chat/AgentVisualization.tsx` (full file, currently 161 lines)
- Test: `npx tsc -b --force` from `app/web`

**Interfaces:**
- Consumes: `PrescriptiveAction` (Task 1's new fields), `Citation`, `AgentTable` from `@datacon/shared-types`; `CitationChip` (existing, unchanged, reused for per-recommendation chips).
- Produces: no interface change — `AgentVisualization`'s exported props (`message`, `onOpenCitation`) are unchanged; `ActionsTable` (previously exported implicitly as a private function) is replaced by `RecommendationCards`, not consumed anywhere outside this file.

Note: `payload.citations` still also renders as the existing global `Citations` chip row (unchanged, above the recommendation cards) — this is intentional overlap, not a regression: it's the same "sources used across this answer" transparency the diagnostic agent's citations already get, and `RecommendationCards` additionally scopes citations per-action underneath each card.

- [ ] **Step 1: Confirm current typecheck is clean (baseline)**

Run: `cd app/web && npx tsc -b --force`
Expected: no output (exits 0).

- [ ] **Step 2: Replace `app/web/src/routes/chat/AgentVisualization.tsx` in full**

```tsx
import type { ChatMessage } from "../../lib/types";
import type { AgentTable, Citation, PrescriptiveAction } from "@datacon/shared-types";
import { AgentChart } from "./AgentChart";

function CorrelationTag({ text }: { text: string }) {
  return (
    <div
      style={{
        display: "inline-block",
        marginTop: 8,
        background: "var(--ac-soft)",
        color: "var(--ac-deep)",
        fontSize: 11,
        fontWeight: 600,
        padding: "4px 10px",
        borderRadius: "var(--radius-sm)",
      }}
    >
      {text}
    </div>
  );
}

function DataTable({ table }: { table: AgentTable }) {
  if (!table.columns.length || !table.rows.length) return null;
  return (
    <div style={{ border: "1px solid var(--ac-border)", borderRadius: "var(--radius-lg)", overflow: "auto", marginTop: 10 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ background: "var(--ac-bg-muted)" }}>
            {table.columns.map((col) => (
              <th
                key={col}
                style={{
                  textAlign: "left",
                  padding: "8px 12px",
                  fontSize: 10,
                  fontWeight: 700,
                  color: "var(--ac-muted)",
                  fontFamily: "'IBM Plex Mono',monospace",
                  whiteSpace: "nowrap",
                }}
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => (
            <tr key={i} style={{ borderTop: "1px solid var(--ac-border)" }}>
              {row.map((cell, j) => (
                <td key={j} style={{ padding: "8px 12px", color: "var(--ac-fg)", whiteSpace: "nowrap" }}>
                  {cell === null ? "—" : String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CitationChip({ citation, onOpen }: { citation: Citation; onOpen: (c: Citation) => void }) {
  const label = citation.documentTitle.length > 28 ? `${citation.documentTitle.slice(0, 28)}…` : citation.documentTitle;
  return (
    <button
      onClick={() => onOpen(citation)}
      title={citation.documentTitle}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontSize: 11,
        fontWeight: 600,
        color: "var(--ac-deep)",
        background: "var(--ac-soft)",
        border: "1px solid var(--ac-border)",
        borderRadius: "var(--radius-sm)",
        padding: "3px 8px",
        cursor: "pointer",
      }}
    >
      [{citation.id}] {label}
    </button>
  );
}

function Citations({ items, onOpen }: { items: Citation[]; onOpen: (c: Citation) => void }) {
  return (
    <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--ac-muted)", marginBottom: 2 }}>
        SOURCES · {items.length} DOCUMENT CHUNK{items.length === 1 ? "" : "S"}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {items.map((c) => (
          <CitationChip key={c.id} citation={c} onOpen={onOpen} />
        ))}
      </div>
    </div>
  );
}

const EFFORT_COLOR: Record<PrescriptiveAction["effort"], string> = {
  Low: "#0f8a5c",
  Medium: "#a3730c",
  High: "#cf202f",
};

function RecommendationCards({ items, citations, onOpen }: { items: PrescriptiveAction[]; citations: Citation[]; onOpen: (c: Citation) => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
      {items.map((a, i) => {
        const usedCitations = (a.citationIds ?? [])
          .map((id) => citations.find((c) => c.id === id))
          .filter((c): c is Citation => Boolean(c));
        return (
          <div key={i} style={{ border: "1px solid var(--ac-border)", borderRadius: "var(--radius-lg)", padding: 14 }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
              <div
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: "50%",
                  background: "var(--ac)",
                  color: "#fff",
                  fontSize: 11,
                  fontWeight: 700,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                {i + 1}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 600, color: "var(--ac-fg)" }}>{a.title}</span>
                  <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".05em", color: EFFORT_COLOR[a.effort] }}>
                    Effort: {a.effort}
                  </span>
                  <span style={{ fontSize: 10, color: "var(--ac-muted)", textTransform: "uppercase", letterSpacing: ".05em" }}>Owner: {a.owner}</span>
                </div>
                <div style={{ fontSize: 12.5, color: "var(--ac-fg)", marginTop: 6 }}>{a.rationale}</div>
                <div style={{ fontSize: 12, color: "var(--ac-muted)", marginTop: 4 }}>
                  <span style={{ fontWeight: 600 }}>Expected impact:</span> {a.expectedImpact}
                </div>
                {usedCitations.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                    {usedCitations.map((c) => (
                      <CitationChip key={c.id} citation={c} onOpen={onOpen} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function AgentVisualization({ message, onOpenCitation }: { message: ChatMessage; onOpenCitation: (citation: Citation) => void }) {
  if (!message.payload) return null;
  const payload = message.payload;

  return (
    <div style={{ marginTop: 8 }}>
      {payload.correlation && <CorrelationTag text={payload.correlation} />}
      {payload.chart && <AgentChart chart={payload.chart} />}
      {payload.table && <DataTable table={payload.table} />}
      {payload.citations && <Citations items={payload.citations} onOpen={onOpenCitation} />}
      {payload.actions && <RecommendationCards items={payload.actions} citations={payload.citations ?? []} onOpen={onOpenCitation} />}
    </div>
  );
}
```

- [ ] **Step 3: Run typecheck, confirm it's clean**

Run: `cd app/web && npx tsc -b --force`
Expected: no output (exits 0).

---

### Task 7: Manual end-to-end verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full backend test suite**

Run (from `app/ai`): `"./.venv/Scripts/python.exe" -m pytest tests/ -v`
Expected: all tests pass — `tests/agents/test_agents.py` at 14 (Task 4), `tests/query_engine/test_executor.py` at 15 (Task 3), everything else unaffected.

- [ ] **Step 2: Start all three services**

Follow this project's **run** skill (or, if none is configured yet, start `app/ai` via `uvicorn app.main:app --reload --port 8000`, `app/api` via `npm run start:dev`, `app/web` via `npm run dev`).

- [ ] **Step 3: Connect/seed data for all three scenarios**

- A churn snapshot with `churn_pct`/`prev_churn_pct`/`at_risk_accounts` (prescriptive) — reuse whatever seed data the prior two plans' verification passes used.
- A revenue-over-time series (predictive).
- A wide records table with a low-cardinality string column (e.g. a `leads` table/collection with `name`/`email`/`company`/`status`/`source`, `status` having 2-8 distinct values) — reuse the same MongoDB `leads` collection used in `2026-07-16-query-result-sanitization-design.md`'s live-verification pass if still connected.

- [ ] **Step 4: Drive one question per gap through the chat UI and confirm rendering**

- Prescriptive (e.g. "how do we reduce churn?"): confirm each of the 3 recommendation cards shows a numbered badge, effort badge (color-coded), owner, a rationale sentence, an expected-impact sentence, and — for whichever action(s) matched a topic-scoped citation query — citation chip(s) that open the drawer with the correct document/snippet on click.
- Predictive (e.g. "forecast revenue next quarter"): confirm the line chart shows a visibly shaded band from the last history point out through the forecast point, and the PROJECTED/95% CI/GROWTH stat row below still matches the shaded range's bounds.
- Descriptive (e.g. "give leads"): confirm the raw records table renders all its columns (per the query-result-sanitization fix, still no `_id`/nested-value issues) **and** a "status distribution" (or equivalent) bar chart renders above it, matching the reference screenshot's leads-table + status-chart shape.

- [ ] **Step 5: Confirm no regressions in the existing two-column categorical chart path**

Ask a question whose result is genuinely 2 columns (e.g. "revenue by region") and confirm it still renders exactly as before (bar chart titled `"<col2> by <col1>"`) — this task's `else` branch in `descriptive.py` must never fire when `_looks_categorical` is `True`.
