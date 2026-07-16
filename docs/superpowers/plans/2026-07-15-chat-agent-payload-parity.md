# Chat Agent Payload Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every chat agent (descriptive/diagnostic/predictive/prescriptive) can surface any combination of a data table, a chart, citations, and a recommendations list, tagged with a deterministic confidence level — matching the level of detail *and* interaction feel shown in the reference app at `C:\Users\pc\Desktop\datavue` (icon-per-agent badges, header confidence text, clickable citation chips + a slide-in drawer), without adopting its LLM-authored-JSON-envelope architecture.

**Architecture:** One unified `AgentPayload` TypeScript type (`confidence` + optional `table`/`chart`/`citations`/`actions`/`correlation`) replaces today's four separate per-intent payload interfaces. Each Python agent's `prepare()` fills in only the fields it has real computed facts for. The frontend renders by field presence, not by `intent` branching. `ChatPage.tsx`'s existing per-agent card layout (already close to datavue's) gains icon badges, header-level confidence text, and a citation drawer on top of that.

**Tech Stack:** FastAPI + Python (agents), NestJS (SSE passthrough, unchanged), React + TypeScript + `recharts` (already an `app/web` dependency, currently unused anywhere).

## Global Constraints

- `AgentPayload` (in `app/packages/shared-types/src/chat.ts`) is the sole chat payload contract — no per-intent TypeScript types. Every field except `confidence` is optional; a field is **omitted**, never an empty array/null placeholder, when there's no real content for it.
- `confidence` is always computed deterministically in Python from real facts — never by the LLM, never left out.
- No automated frontend test runner exists in `app/web` (confirmed: no `jest`/`vitest` config or `.test.*` files). Frontend "tests" in this plan are `npx tsc -b --force` (run from `app/web`) plus one manual end-to-end pass at the end.
- `recharts` (`^2.13.0` per `app/web/package.json`, `2.15.4` installed) replaces the hand-rolled `<svg><polyline>` predictive chart — no new dependency needed.
- Per this project's `CLAUDE.md`: do not run `git commit` unless the user explicitly asks for it in that turn. Each task below ends with a "stage + draft commit message" step, not an unconditional `git commit` — get the user's go-ahead before actually committing, regardless of what this plan's step says.
- Python test command (run from `app/ai`): `"./.venv/Scripts/python.exe" -m pytest tests/agents/test_agents.py -v`

---

### Task 1: Shared payload contract (`AgentPayload`)

**Files:**
- Modify: `app/packages/shared-types/src/chat.ts` (full rewrite of the payload types, lines 1-53)
- Modify: `app/web/src/lib/types.ts:1-11` (import + `ChatPayload` alias)
- Test: `npx tsc -b --force` from `app/web`

**Interfaces:**
- Produces: `AgentPayload` (`confidence: Confidence`, `table?: AgentTable`, `chart?: AgentChart`, `citations?: Citation[]`, `actions?: PrescriptiveAction[]`, `correlation?: string`), and its constituent types `Confidence`, `AgentTable`, `ChartPoint`, `AgentChart`, `Citation`, `PrescriptiveAction` — all exported from `@datacon/shared-types`. `ChatPayload` (in `app/web/src/lib/types.ts`) becomes an alias for `AgentPayload`.
- Consumed by: Task 6 (`AgentVisualization.tsx`, `AgentChart.tsx`) and Task 7 (`ChatPage.tsx`, which imports `Citation`) on the frontend; Tasks 2-5 build Python dicts matching this shape (no static cross-language check, but the pytest assertions in those tasks pin the exact dict shape).

This task has no behavior to unit-test (it's a type-only change) — the "test" is the typecheck. It will show pre-existing errors in `AgentVisualization.tsx` until Task 6 lands; that's expected and resolved in that task, not this one.

- [ ] **Step 1: Confirm current typecheck is clean (baseline)**

Run: `cd app/web && npx tsc -b --force`
Expected: no output (exits 0).

- [ ] **Step 2: Replace `app/packages/shared-types/src/chat.ts` lines 1-53**

Replace the existing `DescriptivePayload`/`DiagnosticPayload`/`PredictivePayload`/`PrescriptivePayload`/`ForecastPoint`/`AgentPayload` block (current lines 1-53) with:

```ts
export type ChatIntent = "descriptive" | "diagnostic" | "predictive" | "prescriptive";

export type Confidence = "high" | "medium" | "low";

export interface AgentTable {
  columns: string[];
  rows: (string | number | boolean | null)[][];
}

export interface ChartPoint {
  label: string;
  value: number;
  lower?: number;
  upper?: number;
}

export interface AgentChart {
  type: "bar" | "line";
  title: string;
  data: ChartPoint[];
}

export interface Citation {
  id: number;
  documentTitle: string;
  filename: string;
  chunkIndex: number;
  snippet: string;
}

export interface PrescriptiveAction {
  title: string;
  impact: string;
  effort: "Low" | "Medium" | "High";
  owner: string;
}

export interface AgentPayload {
  confidence: Confidence;
  table?: AgentTable;
  chart?: AgentChart;
  citations?: Citation[];
  actions?: PrescriptiveAction[];
  correlation?: string;
}
```

Leave the rest of the file (`CHAT_SUGGESTIONS`, `INTENT_META`, `LlmModelOption`, `AVAILABLE_LLM_MODELS`) untouched.

- [ ] **Step 3: Update `app/web/src/lib/types.ts` lines 1-11**

Replace:
```ts
import type {
  ChatIntent,
  ConnectorEngineId,
  DescriptivePayload,
  DiagnosticPayload,
  PermissionKey,
  PredictivePayload,
  PrescriptivePayload,
} from "@datacon/shared-types";

export type ChatPayload = DescriptivePayload | DiagnosticPayload | PredictivePayload | PrescriptivePayload;
```
with:
```ts
import type {
  AgentPayload,
  ChatIntent,
  ConnectorEngineId,
  PermissionKey,
} from "@datacon/shared-types";

export type ChatPayload = AgentPayload;
```

- [ ] **Step 4: Run typecheck, confirm the expected (temporary) failure**

Run: `cd app/web && npx tsc -b --force`
Expected: errors in `src/routes/chat/AgentVisualization.tsx` only (e.g. `Property 'columns' does not exist on type 'AgentPayload'`) — this is expected and resolved by Task 6. No errors anywhere else.

- [ ] **Step 5: Stage and draft commit message (do not commit without user go-ahead)**

```bash
git add app/packages/shared-types/src/chat.ts app/web/src/lib/types.ts
```
Draft message: `refactor(chat): unify per-intent payload types into AgentPayload`

---

### Task 2: `descriptive.py` payload — table + categorical bar chart + confidence

**Files:**
- Modify: `app/ai/app/agents/descriptive.py` (full file, currently 31 lines)
- Test: `app/ai/tests/agents/test_agents.py` (descriptive tests, lines 16-28)

**Interfaces:**
- Consumes: `app.query_engine.executor.answer_question(question) -> QueryAnswer` (unchanged, `ok`/`columns`/`rows`/`message` fields).
- Produces: `AgentPrep.payload` shaped `{"confidence": "high"|"low", "table"?: {"columns": [...], "rows": [...]}, "chart"?: {"type": "bar", "title": str, "data": [{"label", "value"}, ...]}}`.

- [ ] **Step 1: Update the two existing descriptive tests and add a new chart test**

In `app/ai/tests/agents/test_agents.py`, replace:
```python
@pytest.mark.asyncio
async def test_descriptive_reports_no_data_when_nothing_is_connected():
    prep = await descriptive.prepare("what are total leads")
    assert "no data is connected" in prep.offline_text.lower()
    assert prep.payload == {"columns": [], "rows": []}
```
with:
```python
@pytest.mark.asyncio
async def test_descriptive_reports_no_data_when_nothing_is_connected():
    prep = await descriptive.prepare("what are total leads")
    assert "no data is connected" in prep.offline_text.lower()
    assert prep.payload == {"confidence": "low"}
```

Replace:
```python
@pytest.mark.asyncio
async def test_descriptive_answers_a_free_form_question_grounded_in_real_data():
    snapshot_store.load_dataset("leads", pd.DataFrame({"id": [1, 2, 3]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT COUNT(*) AS total_leads FROM leads")):
        prep = await descriptive.prepare("what are total leads")
    assert prep.payload == {"columns": ["total_leads"], "rows": [[3]]}
    assert "total_leads" in prep.prompt
```
with:
```python
@pytest.mark.asyncio
async def test_descriptive_answers_a_free_form_question_grounded_in_real_data():
    snapshot_store.load_dataset("leads", pd.DataFrame({"id": [1, 2, 3]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT COUNT(*) AS total_leads FROM leads")):
        prep = await descriptive.prepare("what are total leads")
    assert prep.payload == {
        "confidence": "high",
        "table": {"columns": ["total_leads"], "rows": [[3]]},
    }
    assert "total_leads" in prep.prompt


@pytest.mark.asyncio
async def test_descriptive_adds_a_bar_chart_when_the_result_is_a_small_categorical_comparison():
    snapshot_store.load_dataset("sales", pd.DataFrame({"region": ["EMEA", "APAC"], "revenue": [120.0, 95.0]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT region, revenue FROM sales")):
        prep = await descriptive.prepare("revenue by region")
    assert prep.payload["chart"] == {
        "type": "bar",
        "title": "revenue by region",
        "data": [
            {"label": "EMEA", "value": 120.0},
            {"label": "APAC", "value": 95.0},
        ],
    }
```

- [ ] **Step 2: Run tests, confirm they fail against current code**

Run (from `app/ai`): `"./.venv/Scripts/python.exe" -m pytest tests/agents/test_agents.py -k descriptive -v`
Expected: FAIL — `test_descriptive_reports_no_data_when_nothing_is_connected` and `test_descriptive_answers_a_free_form_question_grounded_in_real_data` fail on the payload assertion (still returns `columns`/`rows` at the top level, not nested under `table`/`confidence`); `test_descriptive_adds_a_bar_chart...` fails with `KeyError: 'chart'`.

- [ ] **Step 3: Replace `app/ai/app/agents/descriptive.py` in full**

```python
from app.agents.types import AgentPrep
from app.query_engine.executor import answer_question

SYSTEM = (
    "You are Datacon's descriptive analytics agent. Given a real query result table, "
    "answer the user's question about it in one tight paragraph (3-4 sentences) for a "
    "business audience. Do not invent numbers beyond what's provided."
)


def _stringify_row(row: list) -> list:
    return [v if v is None or isinstance(v, (int, float, bool, str)) else str(v) for v in row]


def _looks_categorical(columns: list[str], rows: list[list]) -> bool:
    """Two columns, a handful of rows, second column all-numeric — reads
    better as a bar chart than a bare table (e.g. "revenue by region")."""
    if len(columns) != 2 or not (2 <= len(rows) <= 20):
        return False
    return all(isinstance(row[1], (int, float)) and not isinstance(row[1], bool) for row in rows)


async def prepare(question: str) -> AgentPrep:
    result = await answer_question(question)

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

    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload=payload)
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `"./.venv/Scripts/python.exe" -m pytest tests/agents/test_agents.py -k descriptive -v`
Expected: 3 passed.

- [ ] **Step 5: Stage and draft commit message**

```bash
git add app/ai/app/agents/descriptive.py app/ai/tests/agents/test_agents.py
```
Draft message: `feat(chat): give descriptive agent a table + categorical bar chart`

---

### Task 3: `diagnostic.py` payload — table + confidence, citations become optional

**Files:**
- Modify: `app/ai/app/agents/diagnostic.py` (full file, currently 81 lines)
- Test: `app/ai/tests/agents/test_agents.py` (diagnostic tests, lines 31-45)

**Interfaces:**
- Consumes: unchanged (`answer_question`, `column_index`, `chroma_query`).
- Produces: `AgentPrep.payload` shaped `{"confidence": "high"|"medium"|"low", "table"?: {...}, "citations"?: Citation[], "correlation"?: str}`. `citations`/`correlation` are **omitted entirely** when no citation was found (not `[]`/`None`).

- [ ] **Step 1: Update the two existing diagnostic tests and add a citation-found test**

Replace:
```python
@pytest.mark.asyncio
async def test_diagnostic_reports_no_data_when_nothing_is_connected():
    prep = await diagnostic.prepare("why did tickets spike?")
    assert "no day-by-day event data" in prep.offline_text.lower()
    assert prep.payload == {"citations": [], "correlation": None}
```
with:
```python
@pytest.mark.asyncio
async def test_diagnostic_reports_no_data_when_nothing_is_connected():
    prep = await diagnostic.prepare("why did tickets spike?")
    assert "no day-by-day event data" in prep.offline_text.lower()
    assert prep.payload == {"confidence": "low"}
```

Replace:
```python
@pytest.mark.asyncio
async def test_diagnostic_computes_a_real_spike_from_a_free_form_query():
    snapshot_store.load_dataset("tickets", pd.DataFrame({"day": [1, 2], "region": ["EMEA", "EMEA"], "count": [40, 98]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT day, region, count FROM tickets ORDER BY day")), \
         patch.object(diagnostic, "chroma_query", return_value=[]):
        prep = await diagnostic.prepare("why did tickets spike?")
    assert "EMEA" in prep.offline_text
    assert "+145%" in prep.offline_text
```
with:
```python
@pytest.mark.asyncio
async def test_diagnostic_computes_a_real_spike_from_a_free_form_query():
    snapshot_store.load_dataset("tickets", pd.DataFrame({"day": [1, 2], "region": ["EMEA", "EMEA"], "count": [40, 98]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT day, region, count FROM tickets ORDER BY day")), \
         patch.object(diagnostic, "chroma_query", return_value=[]):
        prep = await diagnostic.prepare("why did tickets spike?")
    assert "EMEA" in prep.offline_text
    assert "+145%" in prep.offline_text
    assert prep.payload == {
        "confidence": "medium",
        "table": {"columns": ["region", "count"], "rows": [["EMEA", 40.0], ["EMEA", 98.0]]},
    }


@pytest.mark.asyncio
async def test_diagnostic_marks_high_confidence_with_correlation_when_a_citation_is_found():
    snapshot_store.load_dataset("tickets", pd.DataFrame({"day": [1, 2], "region": ["EMEA", "EMEA"], "count": [40, 98]}))
    hit = {"metadata": {"title": "Incident Report", "filename": "incident.pdf", "chunk_index": 2}, "snippet": "root cause text", "distance": 0.1}
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT day, region, count FROM tickets ORDER BY day")), \
         patch.object(diagnostic, "chroma_query", return_value=[hit]):
        prep = await diagnostic.prepare("why did tickets spike?")
    assert prep.payload["confidence"] == "high"
    assert prep.payload["correlation"] == "spike ↔ Incident Report"
    assert prep.payload["citations"] == [
        {"id": 1, "documentTitle": "Incident Report", "filename": "incident.pdf", "chunkIndex": 2, "snippet": "root cause text"}
    ]
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `"./.venv/Scripts/python.exe" -m pytest tests/agents/test_agents.py -k diagnostic -v`
Expected: FAIL on payload assertions (current code still returns `{"citations": [...], "correlation": ...}` at top level, no `confidence`/`table`).

- [ ] **Step 3: Replace `app/ai/app/agents/diagnostic.py` in full**

```python
from app.agents.types import AgentPrep
from app.query_engine.executor import answer_question
from app.query_engine.extract import column_index
from app.rag.chroma_store import query as chroma_query

SYSTEM = (
    "You are Datacon's diagnostic analytics agent. Given a real computed spike figure "
    "and real cited document excerpts, write one tight paragraph (3-4 sentences) "
    "explaining the likely root cause. Only reference the provided citations."
)

NO_DATA_TEXT = (
    "No day-by-day event data is connected yet. Connect a data source with a daily "
    "count (e.g. tickets, incidents) to enable spike detection."
)

_DAILY_COUNT_QUESTION = (
    "Count of events per day for the most relevant countable/event log, grouped and "
    "ordered chronologically, for the last 8 days."
)


async def prepare(question: str) -> AgentPrep:
    result = await answer_question(_DAILY_COUNT_QUESTION)
    region_idx = column_index(result.columns, "region", "category", "group") if result.ok else -1
    count_idx = column_index(result.columns, "count", "total") if result.ok else -1

    if not result.ok or count_idx < 0 or len(result.rows) < 2:
        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\nNo day-by-day event data is connected.",
            offline_text=NO_DATA_TEXT,
            payload={"confidence": "low"},
        )

    daily = [
        {"region": str(row[region_idx]) if region_idx >= 0 else "overall", "count": float(row[count_idx])}
        for row in result.rows
    ]
    baseline = daily[:-1]
    spike = daily[-1]
    avg = sum(d["count"] for d in baseline) / len(baseline) if baseline else spike["count"]
    pct = (spike["count"] - avg) / avg * 100 if avg else 0.0

    hits = chroma_query(question or "billing incident ticket spike EMEA", n_results=2)
    citations = [
        {
            "id": i + 1,
            "documentTitle": h["metadata"].get("title", h["metadata"].get("filename", "Untitled")),
            "filename": h["metadata"].get("filename", ""),
            "chunkIndex": h["metadata"].get("chunk_index", 0),
            "snippet": h["snippet"][:220],
        }
        for i, h in enumerate(hits)
    ]

    citation_desc = (
        f" the spike aligns with findings in {citations[0]['documentTitle']}, which notes: \"{citations[0]['snippet'][:120]}...\""
        if citations
        else " no indexed documents currently correlate with this spike — upload an incident report to enable root-cause citation."
    )

    offline_text = (
        f"{spike['region']} events rose {pct:+.0f}% versus the baseline average "
        f"({spike['count']:.0f} vs a baseline of {avg:.0f}/day). Correlating this with your uploaded documents,"
        f"{citation_desc}"
    )

    prompt = (
        f"Question: {question}\n\nComputed facts:\n- {spike['region']} count today: {spike['count']:.0f}\n"
        f"- Baseline average: {avg:.1f}\n- Change: {pct:+.0f}%\n"
        f"- Cited excerpts: {[c['snippet'] for c in citations]}"
    )

    payload = {
        "confidence": "high" if citations else "medium",
        "table": {"columns": ["region", "count"], "rows": [[d["region"], d["count"]] for d in daily]},
    }
    if citations:
        payload["citations"] = citations
        payload["correlation"] = f"spike ↔ {citations[0]['documentTitle']}"

    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload=payload)
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `"./.venv/Scripts/python.exe" -m pytest tests/agents/test_agents.py -k diagnostic -v`
Expected: 3 passed.

- [ ] **Step 5: Stage and draft commit message**

```bash
git add app/ai/app/agents/diagnostic.py app/ai/tests/agents/test_agents.py
```
Draft message: `feat(chat): give diagnostic agent a data table, confidence, optional citations`

---

### Task 4: `predictive.py` payload — table + line chart with forecast point + confidence

**Files:**
- Modify: `app/ai/app/agents/predictive.py` (full file, currently 69 lines)
- Test: `app/ai/tests/agents/test_agents.py` (predictive tests, lines 48-66)

**Interfaces:**
- Consumes: unchanged (`answer_question`, `column_index`, `holt_winters.forecast`/`ols.forecast` returning `{"projected", "ci_low", "ci_high", "growth_pct", "mape", "fitted"}`).
- Produces: `AgentPrep.payload` shaped `{"confidence": ..., "table": {"columns": ["period","revenue"], "rows": [...history..., ["forecast", projected]]}, "chart": {"type": "line", "title": str, "data": [...history points..., {"label":"forecast","value":...,"lower":...,"upper":...}]}}`. No more top-level `model`/`projected`/`ciLow`/`ciHigh`/`growth`/`mape`/`series` fields — Task 6's `AgentChart` derives the PROJECTED/95% CI/GROWTH stat row straight from the last two `chart.data` points instead (keeps the payload schema uniform across all four agents; see Task 6 for why).

- [ ] **Step 1: Update the two existing predictive tests**

Replace:
```python
@pytest.mark.asyncio
async def test_predictive_reports_no_data_when_nothing_is_connected():
    prep = await predictive.prepare("forecast next quarter")
    assert "no revenue history" in prep.offline_text.lower()
    assert prep.payload == {"series": []}
```
with:
```python
@pytest.mark.asyncio
async def test_predictive_reports_no_data_when_nothing_is_connected():
    prep = await predictive.prepare("forecast next quarter")
    assert "no revenue history" in prep.offline_text.lower()
    assert prep.payload == {"confidence": "low"}
```

Replace:
```python
@pytest.mark.asyncio
async def test_predictive_forecasts_from_a_real_free_form_query():
    snapshot_store.load_dataset("revenue", pd.DataFrame({"month": [1, 2, 3, 4], "revenue": [3.0, 3.1, 3.3, 3.5]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT month, revenue FROM revenue ORDER BY month")):
        prep = await predictive.prepare("forecast next quarter")
    assert prep.payload["series"] == [
        {"label": "p0", "value": 3.0},
        {"label": "p1", "value": 3.1},
        {"label": "p2", "value": 3.3},
        {"label": "p3", "value": 3.5},
    ]
    assert prep.payload["model"] == "Holt-Winters"
```
with:
```python
@pytest.mark.asyncio
async def test_predictive_forecasts_from_a_real_free_form_query():
    snapshot_store.load_dataset("revenue", pd.DataFrame({"month": [1, 2, 3, 4], "revenue": [3.0, 3.1, 3.3, 3.5]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT month, revenue FROM revenue ORDER BY month")):
        prep = await predictive.prepare("forecast next quarter")

    history = [
        {"label": "p0", "value": 3.0},
        {"label": "p1", "value": 3.1},
        {"label": "p2", "value": 3.3},
        {"label": "p3", "value": 3.5},
    ]
    assert prep.payload["chart"]["type"] == "line"
    assert prep.payload["chart"]["title"] == "Holt-Winters revenue forecast"
    assert prep.payload["chart"]["data"][:4] == history
    forecast_point = prep.payload["chart"]["data"][4]
    assert forecast_point["label"] == "forecast"
    assert forecast_point["lower"] < forecast_point["value"] < forecast_point["upper"]

    assert prep.payload["table"]["columns"] == ["period", "revenue"]
    assert prep.payload["table"]["rows"][:4] == [["p0", 3.0], ["p1", 3.1], ["p2", 3.3], ["p3", 3.5]]
    assert prep.payload["table"]["rows"][4][0] == "forecast"

    assert prep.payload["confidence"] in ("high", "medium", "low")
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `"./.venv/Scripts/python.exe" -m pytest tests/agents/test_agents.py -k predictive -v`
Expected: FAIL — current code returns `series`/`model` at the top level, no `chart`/`table`/`confidence` keys.

- [ ] **Step 3: Replace `app/ai/app/agents/predictive.py` in full**

```python
from app.agents.types import AgentPrep
from app.forecasting import ols, holt_winters
from app.query_engine.executor import answer_question
from app.query_engine.extract import column_index

SYSTEM = (
    "You are Datacon's predictive analytics agent. Given a real computed revenue forecast "
    "(point estimate, 95% confidence interval, growth rate), write one tight paragraph "
    "(2-3 sentences) presenting it. Do not invent numbers beyond what's provided."
)

NO_DATA_TEXT = (
    "No revenue history is connected yet. Connect a data source with a revenue-over-time "
    "series to enable forecasting."
)

_REVENUE_SERIES_QUESTION = "Total revenue for each month, ordered chronologically, with columns for month and revenue."

MODEL = "Holt-Winters"
HORIZON_MONTHS = 6


def _confidence(mape: float) -> str:
    if mape < 15:
        return "high"
    if mape < 30:
        return "medium"
    return "low"


async def prepare(question: str) -> AgentPrep:
    result = await answer_question(_REVENUE_SERIES_QUESTION)
    revenue_idx = column_index(result.columns, "revenue", "amount", "total") if result.ok else -1

    if not result.ok or revenue_idx < 0:
        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\nNo revenue history is connected.",
            offline_text=NO_DATA_TEXT,
            payload={"confidence": "low"},
        )

    series = [float(row[revenue_idx]) for row in result.rows if row[revenue_idx] is not None]

    if len(series) < 2:
        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\nNo revenue history is connected.",
            offline_text=NO_DATA_TEXT,
            payload={"confidence": "low"},
        )

    engine = ols if MODEL == "OLS" else holt_winters
    forecast = engine.forecast(series, HORIZON_MONTHS)

    offline_text = (
        f"Using a {MODEL} model on {len(series)} periods of revenue, the next {HORIZON_MONTHS} periods are "
        f"projected at ${forecast['projected']:.2f}M (95% CI: ${forecast['ci_low']:.2f}M-${forecast['ci_high']:.2f}M), "
        f"a {forecast['growth_pct']:+.1f}% change. Model fit error (MAPE) is {forecast['mape']:.1f}%."
    )

    prompt = (
        f"Question: {question}\n\nComputed forecast ({MODEL}, {HORIZON_MONTHS}-period horizon):\n"
        f"- Projected: ${forecast['projected']:.2f}M\n- 95% CI: ${forecast['ci_low']:.2f}M - ${forecast['ci_high']:.2f}M\n"
        f"- Growth: {forecast['growth_pct']:+.1f}%\n- MAPE: {forecast['mape']:.1f}%"
    )

    payload = {
        "confidence": _confidence(forecast["mape"]),
        "table": {
            "columns": ["period", "revenue"],
            "rows": [[f"p{i}", v] for i, v in enumerate(series)] + [["forecast", forecast["projected"]]],
        },
        "chart": {
            "type": "line",
            "title": f"{MODEL} revenue forecast",
            "data": [{"label": f"p{i}", "value": v} for i, v in enumerate(series)] + [
                {
                    "label": "forecast",
                    "value": forecast["projected"],
                    "lower": forecast["ci_low"],
                    "upper": forecast["ci_high"],
                }
            ],
        },
    }

    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload=payload)
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `"./.venv/Scripts/python.exe" -m pytest tests/agents/test_agents.py -k predictive -v`
Expected: 2 passed.

- [ ] **Step 5: Stage and draft commit message**

```bash
git add app/ai/app/agents/predictive.py app/ai/tests/agents/test_agents.py
```
Draft message: `feat(chat): give predictive agent a data table and forecast-point chart`

---

### Task 5: `prescriptive.py` payload — optional citations + confidence

**Files:**
- Modify: `app/ai/app/agents/prescriptive.py` (full file, currently 55 lines)
- Test: `app/ai/tests/agents/test_agents.py` (prescriptive tests, lines 69-83)

**Interfaces:**
- Consumes: `answer_question`, `column_index` (unchanged), plus `app.rag.chroma_store.query` (new import, same function `diagnostic.py` already uses).
- Produces: `AgentPrep.payload` shaped `{"confidence": "high"|"low", "actions": [...], "citations"?: Citation[]}`. `citations` omitted when no supporting document is found.

- [ ] **Step 1: Update the two existing prescriptive tests and add a citations-found test**

Replace:
```python
@pytest.mark.asyncio
async def test_prescriptive_reports_no_data_when_nothing_is_connected():
    prep = await prescriptive.prepare("how do we reduce churn?")
    assert "no churn data" in prep.offline_text.lower()
    assert prep.payload == {"actions": []}
```
with:
```python
@pytest.mark.asyncio
async def test_prescriptive_reports_no_data_when_nothing_is_connected():
    prep = await prescriptive.prepare("how do we reduce churn?")
    assert "no churn data" in prep.offline_text.lower()
    assert prep.payload == {"confidence": "low"}
```

Replace:
```python
@pytest.mark.asyncio
async def test_prescriptive_builds_actions_from_a_real_free_form_query():
    snapshot_store.load_dataset("churn", pd.DataFrame({"churn_pct": [3.1], "prev_churn_pct": [3.5], "at_risk_accounts": [12]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT churn_pct, prev_churn_pct, at_risk_accounts FROM churn")):
        prep = await prescriptive.prepare("how do we reduce churn?")
    assert len(prep.payload["actions"]) == 3
    assert "12 at-risk" in prep.payload["actions"][0]["title"]
    assert "3.1" in prep.offline_text
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

- [ ] **Step 2: Run tests, confirm they fail**

Run: `"./.venv/Scripts/python.exe" -m pytest tests/agents/test_agents.py -k prescriptive -v`
Expected: FAIL — current code has no `chroma_query` import/attribute on `prescriptive` (the `patch.object(prescriptive, "chroma_query", ...)` calls raise `AttributeError`), and payload assertions don't match today's `{"actions": [...]}`-only shape.

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


async def prepare(question: str) -> AgentPrep:
    result = await answer_question(_CHURN_QUESTION)
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

    actions = [
        {"title": f"Launch save-offer for {at_risk_accounts} at-risk enterprise accounts", "impact": "-0.4pp", "effort": "Low", "owner": "Success"},
        {"title": "Fix billing errors flagged in support documentation", "impact": "-0.2pp", "effort": "Medium", "owner": "Engineering"},
        {"title": "Add usage-drop alerts for accounts under 40% active seats", "impact": "-0.1pp", "effort": "Low", "owner": "Product"},
    ]

    offline_text = f"Three actions are projected to bring churn from {churn_pct:.1f}% toward {target:.1f}% this quarter:"

    prompt = (
        f"Question: {question}\n\nComputed facts:\n- Current churn: {churn_pct:.1f}%\n"
        f"- At-risk accounts: {at_risk_accounts}\n- Target churn: {target:.1f}%\n"
        f"- Planned actions: {[a['title'] for a in actions]}"
    )

    hits = chroma_query(question or "churn retention billing incident", n_results=2)
    citations = [
        {
            "id": i + 1,
            "documentTitle": h["metadata"].get("title", h["metadata"].get("filename", "Untitled")),
            "filename": h["metadata"].get("filename", ""),
            "chunkIndex": h["metadata"].get("chunk_index", 0),
            "snippet": h["snippet"][:220],
        }
        for i, h in enumerate(hits)
    ]

    payload = {"confidence": "high", "actions": actions}
    if citations:
        payload["citations"] = citations

    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload=payload)
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `"./.venv/Scripts/python.exe" -m pytest tests/agents/test_agents.py -k prescriptive -v`
Expected: 3 passed.

- [ ] **Step 5: Run the full agent test suite, confirm all green**

Run: `"./.venv/Scripts/python.exe" -m pytest tests/agents/test_agents.py -v`
Expected: 11 passed — the original 8 (assertions rewritten in place across Tasks 2-5) plus 3 new ones added (one each in Tasks 2, 3, and 5; Task 4 only rewrote existing assertions).

- [ ] **Step 6: Stage and draft commit message**

```bash
git add app/ai/app/agents/prescriptive.py app/ai/tests/agents/test_agents.py
```
Draft message: `feat(chat): give prescriptive agent optional supporting citations`

---

### Task 6: Frontend rendering — `AgentChart.tsx` (new) + `AgentVisualization.tsx` rewrite

**Files:**
- Create: `app/web/src/routes/chat/AgentChart.tsx`
- Modify: `app/web/src/routes/chat/AgentVisualization.tsx` (full rewrite, currently 124 lines)
- Test: `npx tsc -b --force` from `app/web`

**Interfaces:**
- Consumes: `AgentPayload`, `AgentTable`, `AgentChart` (type), `Citation`, `PrescriptiveAction` from `@datacon/shared-types` (Task 1). `ChatMessage` from `app/web/src/lib/types.ts` (unchanged shape).
- Produces: `AgentChart` (component, named export `export function AgentChart(...)`) consumed by `AgentVisualization`. `AgentVisualization` now takes a required `onOpenCitation: (citation: Citation) => void` prop (new — Task 7's `ChatPage.tsx` supplies it and owns the drawer state). Confidence is **not** rendered by this component at all — Task 7 reads `message.payload?.confidence` directly in `ChatPage.tsx`'s header instead.

Before writing this task's code, pull in the **dataviz** skill for chart palette/accessibility guidance rather than inventing colors ad hoc — the file below uses the existing `var(--ac)`/`var(--ac-muted)` tokens already in use elsewhere in this file, which is consistent with that guidance for this app's design system.

- [ ] **Step 1: Create `app/web/src/routes/chat/AgentChart.tsx`**

```tsx
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
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
        <LineChart data={chart.data} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--ac-border)" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="var(--ac-muted)" />
          <YAxis tick={{ fontSize: 11 }} stroke="var(--ac-muted)" width={40} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
          <Line type="monotone" dataKey="value" stroke="var(--ac)" strokeWidth={2} dot={{ r: 3 }} />
        </LineChart>
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

function ActionsTable({ items }: { items: PrescriptiveAction[] }) {
  return (
    <div style={{ border: "1px solid var(--ac-border)", borderRadius: "var(--radius-lg)", overflow: "hidden", marginTop: 10 }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 82px 64px 82px",
          background: "var(--ac-bg-muted)",
          padding: "8px 12px",
          fontSize: 10,
          fontWeight: 700,
          color: "var(--ac-muted)",
          fontFamily: "'IBM Plex Mono',monospace",
        }}
      >
        <span>RECOMMENDED ACTION</span>
        <span>IMPACT</span>
        <span>EFFORT</span>
        <span>OWNER</span>
      </div>
      {items.map((a, i) => (
        <div
          key={i}
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 82px 64px 82px",
            padding: "9px 12px",
            fontSize: 12,
            borderTop: "1px solid var(--ac-border)",
            alignItems: "center",
          }}
        >
          <span style={{ fontWeight: 500, color: "var(--ac-fg)" }}>{a.title}</span>
          <span style={{ color: "#0f8a5c", fontWeight: 700 }}>{a.impact}</span>
          <span style={{ color: a.effort === "Low" ? "#0f8a5c" : "#cf202f", fontWeight: 600 }}>{a.effort}</span>
          <span style={{ color: "var(--ac-muted)" }}>{a.owner}</span>
        </div>
      ))}
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
      {payload.actions && <ActionsTable items={payload.actions} />}
    </div>
  );
}
```

- [ ] **Step 3: Run typecheck, confirm the expected (temporary) failure**

Run: `cd app/web && npx tsc -b --force`
Expected: one error in `src/routes/chat/ChatPage.tsx` — `<AgentVisualization message={m} />` is now missing the required `onOpenCitation` prop. Resolved in Task 7.

- [ ] **Step 4: Stage and draft commit message**

```bash
git add app/web/src/routes/chat/AgentChart.tsx app/web/src/routes/chat/AgentVisualization.tsx
```
Draft message: `feat(chat): compose chat visuals by payload field, add recharts-based AgentChart`

---

### Task 7: `ChatPage.tsx` — intent-badge icons, header confidence, citation drawer

**Files:**
- Modify: `app/web/src/routes/chat/ChatPage.tsx` (imports at lines 1-20; message-header JSX at lines 196-207; the `<AgentVisualization message={m} />` call at line 221; new drawer JSX + state)
- Test: `npx tsc -b --force` from `app/web`

**Interfaces:**
- Consumes: `Citation` from `@datacon/shared-types` (new import). `AgentVisualization`'s new `onOpenCitation` prop (Task 6).
- Produces: nothing consumed by later tasks — this is the last frontend task.

- [ ] **Step 1: Add the `Citation` type import**

In `app/web/src/routes/chat/ChatPage.tsx`, change:
```tsx
import { AVAILABLE_LLM_MODELS, CHAT_SUGGESTIONS, INTENT_META, type ChatIntent } from "@datacon/shared-types";
```
to:
```tsx
import { AVAILABLE_LLM_MODELS, CHAT_SUGGESTIONS, INTENT_META, type ChatIntent, type Citation } from "@datacon/shared-types";
```

- [ ] **Step 2: Add `openCitation` state**

Immediately after the existing `const sentPending = useRef(false);` line, add:
```tsx
const [openCitation, setOpenCitation] = useState<Citation | null>(null);
```

- [ ] **Step 3: Add the intent-icon map and confidence label/color maps**

Immediately before `export function ChatPage() {`, add:
```tsx
const INTENT_ICON: Record<ChatIntent, typeof FileText> = {
  descriptive: FileText,
  diagnostic: Compass,
  predictive: LineChart,
  prescriptive: Play,
};

const CONFIDENCE_LABEL = { high: "High confidence", medium: "Medium confidence", low: "Low confidence" } as const;
const CONFIDENCE_COLOR = { high: "#0f8a5c", medium: "#a3730c", low: "#7a7f8a" } as const;
```
(`FileText`/`Compass`/`LineChart`/`Play` are already imported in this file for the empty-state suggestion cards — no new icon imports needed.)

- [ ] **Step 4: Add the icon to the per-message intent badge and confidence text to the header**

Replace:
```tsx
                    {m.intent && (
                      <span style={{ font: "600 9.5px 'IBM Plex Mono',monospace", color: INTENT_META[m.intent].color, background: INTENT_META[m.intent].bg, padding: "2px 8px", borderRadius: 20 }}>
                        {INTENT_META[m.intent].label}
                      </span>
                    )}
                  </div>
```
with:
```tsx
                    {m.intent && (
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 4, font: "600 9.5px 'IBM Plex Mono',monospace", color: INTENT_META[m.intent].color, background: INTENT_META[m.intent].bg, padding: "2px 8px", borderRadius: 20 }}>
                        {(() => {
                          const Icon = INTENT_ICON[m.intent];
                          return <Icon size={10} />;
                        })()}
                        {INTENT_META[m.intent].label}
                      </span>
                    )}
                    {!m.streaming && m.payload && (
                      <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 700, color: CONFIDENCE_COLOR[m.payload.confidence] }}>
                        {CONFIDENCE_LABEL[m.payload.confidence]}
                      </span>
                    )}
                  </div>
```

- [ ] **Step 5: Pass `onOpenCitation` to `AgentVisualization`**

Replace:
```tsx
                    {!m.streaming && <AgentVisualization message={m} />}
```
with:
```tsx
                    {!m.streaming && <AgentVisualization message={m} onOpenCitation={setOpenCitation} />}
```

- [ ] **Step 6: Add the citation drawer, rendered at the end of the component**

Immediately before the final closing `</div>` of the component's returned JSX (right after the input form's wrapping `<div>` closes), add:
```tsx
        {openCitation && (
          <div
            onClick={() => setOpenCitation(null)}
            style={{ position: "fixed", inset: 0, zIndex: 40, background: "rgba(0,0,0,0.3)" }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                position: "absolute",
                right: 0,
                top: 0,
                height: "100%",
                width: "min(480px, 100%)",
                background: "#fff",
                borderLeft: "1px solid var(--ac-border)",
                padding: 24,
                overflowY: "auto",
              }}
            >
              <div style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--ac-muted)" }}>SOURCE CITATION</div>
              <div style={{ fontSize: 19, fontWeight: 800, marginTop: 8 }}>{openCitation.documentTitle}</div>
              <div style={{ font: "500 11px 'IBM Plex Mono',monospace", color: "var(--ac-muted)", marginTop: 4 }}>
                {openCitation.filename} · chunk {openCitation.chunkIndex}
              </div>
              <div style={{ fontSize: 13, lineHeight: 1.6, color: "var(--ac-fg)", marginTop: 16, background: "var(--ac-bg-muted)", border: "1px solid var(--ac-border)", borderRadius: "var(--radius-sm)", padding: 14, whiteSpace: "pre-wrap" }}>
                {openCitation.snippet}
              </div>
              <button
                onClick={() => setOpenCitation(null)}
                style={{ marginTop: 20, padding: "8px 14px", borderRadius: "var(--radius-sm)", background: "var(--ac-bg-muted)", border: "1px solid var(--ac-border)", fontSize: 12.5, fontWeight: 600 }}
              >
                Close
              </button>
            </div>
          </div>
        )}
```

- [ ] **Step 7: Run typecheck, confirm it's clean**

Run: `cd app/web && npx tsc -b --force`
Expected: no output (exits 0) — confirms Task 6's temporary `onOpenCitation` error is resolved and nothing else regressed.

- [ ] **Step 8: Stage and draft commit message**

```bash
git add app/web/src/routes/chat/ChatPage.tsx
```
Draft message: `feat(chat): add intent-badge icons, header confidence, and a citation drawer`

---

### Task 8: Manual end-to-end verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full backend test suite**

Run (from `app/ai`): `"./.venv/Scripts/python.exe" -m pytest tests/ -v`
Expected: all tests pass, including the 11 in `tests/agents/test_agents.py` and the existing `tests/internal/test_chat_router.py` (unaffected — it only asserts on `res.text` containing the offline "no data is connected" string, which is unchanged).

- [ ] **Step 2: Start all three services**

Follow this project's **run** skill (or, if none is configured yet, start `app/ai` via `uvicorn app.main:app --reload --port 8000`, `app/api` via `npm run start:dev`, `app/web` via `npm run dev`).

- [ ] **Step 3: Load a small dataset so agents have real data to ground on**

Upload or connect at least: a table with 2+ categorical rows for descriptive's bar-chart path (e.g. `region`/`revenue`), a daily ticket/incident count series for diagnostic, a revenue-over-time series for predictive, and a churn snapshot for prescriptive — reusing whatever seed/sample data this project already provides for those four shapes (per `2026-07-13-real-data-grounding-design.md` / `2026-07-14-free-form-chat-grounding-design.md`).

- [ ] **Step 4: Drive one question per intent through the chat UI and confirm rendering**

- Descriptive (e.g. "revenue by region"): confirm the intent badge shows its icon, "High/Medium/Low confidence" text appears in the header once streaming finishes, and a bar chart + data table render in the body.
- Diagnostic (e.g. "why did tickets spike?"): confirm the badge icon, header confidence text, and data table render; if a matching document was indexed, confirm a citation chip appears and clicking it opens the drawer with the correct title/filename/chunk/snippet, and closes on the X/overlay click.
- Predictive (e.g. "forecast revenue next quarter"): confirm the badge icon, header confidence text, a line chart (history + one forecast point), a data table, and the PROJECTED/95% CI/GROWTH stat row all render.
- Prescriptive (e.g. "how do we reduce churn?"): confirm the badge icon, header confidence text, and an actions table render; if a matching document was indexed, confirm a citation chip + drawer work the same as diagnostic's.

- [ ] **Step 5: Confirm no regressions in the SSE stream itself**

In the browser devtools Network tab, inspect the `/chat/stream` response for one of the above questions — confirm `agent_delta` events still stream token-by-token (the temperature/timeout fixes from earlier in this session shouldn't have changed) and the final `agent_done` event's `payload` matches the shape asserted in Tasks 2-5.
