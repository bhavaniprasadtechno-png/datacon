# Free-form Chat Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chat's Descriptive agent answers the user's actual free-form question grounded in whatever data is really connected/uploaded (any synced connector, any CSV) instead of being restricted to four fixed canonical questions; Diagnostic/Predictive/Prescriptive keep their existing real math but source it by asking the query engine directly instead of through a separate `MetricsService`-mediated layer; MongoDB-sourced data can finally ground anything, since its driver gets the same full-row-loading treatment SQL-native drivers already have.

**Architecture:** The query engine (`ai/app/query_engine/{snapshot_store,generator,executor}.py`) and the DuckDB row-loading already built in the prior "Real Data Grounding" plan are unchanged. This plan moves *who asks the query engine what question* from `api`'s `MetricsService` (which asked four fixed English questions once per chat turn and handed the results to `ai` as `context`) to each of the four chat agents in `ai/app/agents/*.py` asking the query engine directly, in-process — Descriptive with the user's literal question, the other three with their own fixed targeted question (same wording MetricsService used to send, just asked by the agent itself).

**Tech Stack:** Same as the prior plan — Python 3.11 / FastAPI / DuckDB / pandas in `ai/`; TypeScript / NestJS in `api/`.

## Global Constraints

- No fallback to seeded/fake data anywhere — an agent with no real grounding must say so honestly, never fabricate or crash.
- Existing OLS/Holt-Winters forecasting math (`ai/app/forecasting/{ols,holt_winters}.py`), existing ChromaDB RAG citation logic (`chroma_query`), and the existing regex router (`ai/app/agents/router.py`) are unchanged — only how each agent sources its input data changes.
- `MetricsService`'s four data methods (`revenueHistory`, `regionRevenue`, `ticketDaily`, `churnSnapshot`) and `InsightsService`/`ForecastsController` are unchanged — this plan only removes `MetricsService.chatContext()`, which has no other caller.
- Row cap of 20,000 rows per loaded table (`ROW_CAP`) — matches the existing convention in the SQL-native drivers, applies identically to the Mongo driver.
- Follow this repo's existing code conventions exactly.

---

### Task 1: MongoDB driver loads full rows

**Files:**
- Modify: `ai/app/connectors/drivers/mongodb_driver.py`

**Interfaces:**
- Produces: `mongodb_driver.sync()` now populates `DatasetResult.rows` (the field already added to the `DatasetResult` dataclass in the prior plan) with native-typed, capped document data, matching what `sqlite_driver.py`/`postgres_driver.py`/`mysql_driver.py` already produce. No other task in this plan depends on this directly — `ai/app/connectors/service.py`'s `sync_connector()` already loads any driver's `.rows` into DuckDB, unchanged from the prior plan.

There is no local test fixture for a real MongoDB instance in this repo (same situation the prior plan's Task 4 documented for Postgres/MySQL) — this task has no dedicated automated test. Verify it by re-syncing a real MongoDB connector after this change and confirming its collections become queryable (covered in this plan's final manual verification).

- [ ] **Step 1: Read the current file**

Read `ai/app/connectors/drivers/mongodb_driver.py` to confirm it matches what's shown below (it was last touched by the original app scaffold, so it should be unchanged since).

- [ ] **Step 2: Update `sync()` to capture and return full rows**

Modify `ai/app/connectors/drivers/mongodb_driver.py`, replacing the whole file:

```python
from pymongo import MongoClient
from app.connectors.types import TestResult, SyncResult, DatasetResult

ROW_CAP = 20_000


def _client(secrets: dict) -> MongoClient:
    uri = secrets.get("uri")
    if not uri:
        raise ValueError("Connection URI is required.")
    return MongoClient(uri, serverSelectionTimeoutMS=5000)


def test(config: dict, secrets: dict) -> TestResult:
    if not secrets.get("uri") or not config.get("database"):
        return TestResult(False, "Connection URI and database are required.")
    try:
        client = _client(secrets)
        client.admin.command("ping")
        client.close()
        return TestResult(True, "Connection succeeded.")
    except Exception as e:
        return TestResult(False, f"Couldn't connect: {e}")


def sync(config: dict, secrets: dict) -> SyncResult:
    """Best-effort schema discovery: MongoDB is schemaless, so 'columns' is
    derived from a sample document's top-level keys rather than a real schema.
    Full (capped) row data is flattened against that same column list so it
    can be loaded into the query engine like any SQL-native driver's rows."""
    try:
        client = _client(secrets)
        db = client[config["database"]]
        collections = db.list_collection_names()
        datasets = []
        for name in collections:
            coll = db[name]
            row_count = coll.estimated_document_count()
            docs = list(coll.find().limit(ROW_CAP))
            columns = list(docs[0].keys()) if docs else []
            rows = [tuple(doc.get(c) for c in columns) for doc in docs]
            sample_rows = [[str(v) for v in row] for row in rows[:5]]
            datasets.append(DatasetResult(name=name, columns=columns, row_count=row_count, sample_rows=sample_rows, rows=rows))
        client.close()
        return SyncResult(True, f"Discovered {len(datasets)} collection(s).", datasets)
    except Exception as e:
        return SyncResult(False, f"Sync failed: {e}", [])
```

Note the change from the original: `sample_docs = list(coll.find().limit(5))` is replaced by `docs = list(coll.find().limit(ROW_CAP))` (one query instead of a separate 5-doc query, matching the "single-query-with-slice" pattern the prior plan's SQL drivers use), and `rows` keeps native document values (not stringified — `doc.get(c)` not `str(doc.get(c, ""))`) so numeric fields load into DuckDB with correct types. `sample_rows` (the preview shown in the "View table" modal) keeps the original stringified behavior, just sliced from the same fetch.

- [ ] **Step 3: Run the full `ai` test suite to confirm no regressions**

Run: `cd ai && source .venv/Scripts/activate && python -m pytest -v`
Expected: all existing tests still pass (this change only touches `mongodb_driver.py`, which nothing currently tests)

- [ ] **Step 4: Commit**

Per this project's standing rule, do not commit unless explicitly asked. Leave this as an uncommitted change (see the execution notes your controller will give you).

---

### Task 2: Shared column-matching helper

**Files:**
- Create: `ai/app/query_engine/extract.py`
- Test: `ai/tests/query_engine/test_extract.py`

**Interfaces:**
- Produces: `extract.column_index(columns: list[str], *keyword_groups: str) -> int` — case-insensitive substring match against column names, checked in the given keyword priority order, first match wins; returns `-1` if nothing matches. Task 3's diagnostic/predictive/prescriptive agents depend on this exact signature.

This is a direct Python port of `api/src/metrics/metrics.service.ts`'s existing private `colIndex` method (same semantics, including its known substring-collision fragility — e.g. a keyword `"churn_pct"` also matches a column literally named `"prev_churn_pct"` if that column happens to come first — this is an accepted, pre-existing heuristic risk, not something to fix here).

- [ ] **Step 1: Write the failing tests**

Create `ai/tests/query_engine/test_extract.py`:

```python
from app.query_engine.extract import column_index


def test_returns_index_of_first_matching_keyword():
    assert column_index(["month", "total_revenue"], "revenue", "amount") == 1


def test_is_case_insensitive():
    assert column_index(["Region", "Revenue"], "revenue") == 1


def test_checks_keyword_groups_in_priority_order():
    # "churn" matches both columns; scanning left-to-right for THIS keyword
    # returns the first column, regardless of which keyword group found it.
    assert column_index(["prev_churn_pct", "churn_pct"], "churn") == 0


def test_returns_minus_one_when_nothing_matches():
    assert column_index(["a", "b"], "revenue") == -1


def test_returns_minus_one_for_empty_columns():
    assert column_index([], "revenue") == -1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ai && source .venv/Scripts/activate && python -m pytest tests/query_engine/test_extract.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.query_engine.extract'`

- [ ] **Step 3: Implement `extract.py`**

Create `ai/app/query_engine/extract.py`:

```python
def column_index(columns: list[str], *keyword_groups: str) -> int:
    """Case-insensitive substring match against column names, checked in the
    given keyword priority order. Returns the index of the first column
    matching a keyword, or -1 if nothing matches."""
    lower = [c.lower() for c in columns]
    for keyword in keyword_groups:
        for i, c in enumerate(lower):
            if keyword in c:
                return i
    return -1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ai && source .venv/Scripts/activate && python -m pytest tests/query_engine/test_extract.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

Leave uncommitted per this project's standing rule.

---

### Task 3: Rewrite all 4 chat agents for self-served, free-form grounding

**Files:**
- Modify: `ai/app/agents/descriptive.py`
- Modify: `ai/app/agents/diagnostic.py`
- Modify: `ai/app/agents/predictive.py`
- Modify: `ai/app/agents/prescriptive.py`
- Delete: `ai/tests/agents/test_agents_no_data.py` (superseded by the file below — its tests assumed the old `prepare(question, context)` signature, which no longer exists)
- Create: `ai/tests/agents/test_agents.py`

**Interfaces:**
- Consumes: `executor.answer_question(question: str) -> QueryAnswer` (existing, from the prior plan). `extract.column_index(columns, *keyword_groups) -> int` (Task 2).
- Produces: all four agents' `prepare` functions become `async def prepare(question: str) -> AgentPrep` — the `context: dict` parameter is removed entirely. Task 4 (`chat_router.py`) depends on this exact new signature for all four.

All four agents must change together in this one task: `ai/app/internal/chat_router.py` currently calls every agent uniformly (`_AGENTS[intent](payload.message, payload.context)`) in a loop, so changing one agent's signature without changing the others would break that uniform call — Task 4 (which fixes the caller) can only land once all four agents already share the new signature.

- [ ] **Step 1: Write the failing tests**

Create `ai/tests/agents/test_agents.py`:

```python
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from app.agents import descriptive, diagnostic, predictive, prescriptive
from app.query_engine import executor, snapshot_store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot_store.settings, "query_engine_db_path", str(tmp_path / "test.duckdb"))
    yield


@pytest.mark.asyncio
async def test_descriptive_reports_no_data_when_nothing_is_connected():
    prep = await descriptive.prepare("what are total leads")
    assert "no data is connected" in prep.offline_text.lower()
    assert prep.payload == {"columns": [], "rows": []}


@pytest.mark.asyncio
async def test_descriptive_answers_a_free_form_question_grounded_in_real_data():
    snapshot_store.load_dataset("leads", pd.DataFrame({"id": [1, 2, 3]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT COUNT(*) AS total_leads FROM leads")):
        prep = await descriptive.prepare("what are total leads")
    assert prep.payload == {"columns": ["total_leads"], "rows": [[3]]}
    assert "total_leads" in prep.prompt


@pytest.mark.asyncio
async def test_diagnostic_reports_no_data_when_nothing_is_connected():
    prep = await diagnostic.prepare("why did tickets spike?")
    assert "no day-by-day event data" in prep.offline_text.lower()
    assert prep.payload == {"citations": [], "correlation": None}


@pytest.mark.asyncio
async def test_diagnostic_computes_a_real_spike_from_a_free_form_query():
    snapshot_store.load_dataset("tickets", pd.DataFrame({"day": [1, 2], "region": ["EMEA", "EMEA"], "count": [40, 98]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT day, region, count FROM tickets ORDER BY day")), \
         patch.object(diagnostic, "chroma_query", return_value=[]):
        prep = await diagnostic.prepare("why did tickets spike?")
    assert "EMEA" in prep.offline_text
    assert "+145%" in prep.offline_text


@pytest.mark.asyncio
async def test_predictive_reports_no_data_when_nothing_is_connected():
    prep = await predictive.prepare("forecast next quarter")
    assert "no revenue history" in prep.offline_text.lower()
    assert prep.payload == {"series": []}


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


@pytest.mark.asyncio
async def test_prescriptive_reports_no_data_when_nothing_is_connected():
    prep = await prescriptive.prepare("how do we reduce churn?")
    assert "no churn data" in prep.offline_text.lower()
    assert prep.payload == {"actions": []}


@pytest.mark.asyncio
async def test_prescriptive_builds_actions_from_a_real_free_form_query():
    snapshot_store.load_dataset("churn", pd.DataFrame({"churn_pct": [3.1], "prev_churn_pct": [3.5], "at_risk_accounts": [12]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT churn_pct, prev_churn_pct, at_risk_accounts FROM churn")):
        prep = await prescriptive.prepare("how do we reduce churn?")
    assert len(prep.payload["actions"]) == 3
    assert "12 at-risk" in prep.payload["actions"][0]["title"]
    assert "3.1" in prep.offline_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ai && source .venv/Scripts/activate && python -m pytest tests/agents/test_agents.py -v`
Expected: FAIL — `TypeError: prepare() missing 1 required positional argument` (or similar) against the current `prepare(question, context)` signatures.

- [ ] **Step 3: Rewrite `descriptive.py`**

Modify `ai/app/agents/descriptive.py`, replacing the whole file:

```python
from app.agents.types import AgentPrep
from app.query_engine.executor import answer_question

SYSTEM = (
    "You are Datacon's descriptive analytics agent. Given a real query result table, "
    "answer the user's question about it in one tight paragraph (3-4 sentences) for a "
    "business audience. Do not invent numbers beyond what's provided."
)


async def prepare(question: str) -> AgentPrep:
    result = await answer_question(question)

    if not result.ok:
        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\n{result.message}",
            offline_text=result.message,
            payload={"columns": [], "rows": []},
        )

    shown_rows = result.rows[:20]
    prompt = f"Question: {question}\n\nQuery result:\nColumns: {result.columns}\nRows: {shown_rows}"
    offline_text = f"Found {len(result.rows)} result row(s) for \"{question}\" across columns {', '.join(result.columns)}."

    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload={"columns": result.columns, "rows": shown_rows})
```

- [ ] **Step 4: Rewrite `diagnostic.py`**

Modify `ai/app/agents/diagnostic.py`, replacing the whole file:

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
            payload={"citations": [], "correlation": None},
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

    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text=offline_text,
        payload={"citations": citations, "correlation": f"spike ↔ {citations[0]['documentTitle']}" if citations else None},
    )
```

- [ ] **Step 5: Rewrite `predictive.py`**

Modify `ai/app/agents/predictive.py`, replacing the whole file:

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


async def prepare(question: str) -> AgentPrep:
    result = await answer_question(_REVENUE_SERIES_QUESTION)
    revenue_idx = column_index(result.columns, "revenue", "amount", "total") if result.ok else -1

    if not result.ok or revenue_idx < 0:
        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\nNo revenue history is connected.",
            offline_text=NO_DATA_TEXT,
            payload={"series": []},
        )

    series = [float(row[revenue_idx]) for row in result.rows if row[revenue_idx] is not None]

    if len(series) < 2:
        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\nNo revenue history is connected.",
            offline_text=NO_DATA_TEXT,
            payload={"series": []},
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
        "model": MODEL,
        "projected": f"${forecast['projected']:.2f}M",
        "ciLow": f"${forecast['ci_low']:.2f}M",
        "ciHigh": f"${forecast['ci_high']:.2f}M",
        "growth": f"{forecast['growth_pct']:+.1f}%",
        "mape": f"{forecast['mape']:.1f}%",
        "series": [{"label": f"p{i}", "value": v} for i, v in enumerate(series)],
    }
    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload=payload)
```

- [ ] **Step 6: Rewrite `prescriptive.py`**

Modify `ai/app/agents/prescriptive.py`, replacing the whole file:

```python
from app.agents.types import AgentPrep
from app.query_engine.executor import answer_question
from app.query_engine.extract import column_index

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
            payload={"actions": []},
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

    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload={"actions": actions})
```

- [ ] **Step 7: Delete the superseded test file**

Delete `ai/tests/agents/test_agents_no_data.py` (its tests call the old `prepare(question, context)` signature, which no longer exists on any of the four agents).

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd ai && source .venv/Scripts/activate && python -m pytest tests/agents/test_agents.py -v`
Expected: 8 passed

- [ ] **Step 9: Run the full `ai` test suite**

Run: `cd ai && source .venv/Scripts/activate && python -m pytest -v`
Expected: all tests pass (this will fail until Task 4 updates `chat_router.py` if anything there is exercised by another test — if `ai/tests/internal/test_chat_router.py` doesn't exist yet, this step should otherwise pass cleanly; if some other existing test imports one of the four agent modules with the old signature, fix that test's call site to match the new signature before proceeding)

- [ ] **Step 10: Commit**

Leave uncommitted per this project's standing rule.

---

### Task 4: Update `chat_router.py` to the new agent signature

**Files:**
- Modify: `ai/app/internal/chat_router.py`
- Test: `ai/tests/internal/test_chat_router.py`

**Interfaces:**
- Consumes: all four agents' `async def prepare(question: str) -> AgentPrep` (Task 3).
- Produces: `ChatPayload` drops its `context: dict` field (keeps `message: str`, `model: str | None = None`). Task 5 (`api`'s `chat.controller.ts`) depends on the route no longer requiring `context` in the request body — but tolerates it being sent, for backward-compatible rollout ordering.

- [ ] **Step 1: Write the failing tests**

Create `ai/tests/internal/test_chat_router.py`:

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.query_engine import snapshot_store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot_store.settings, "query_engine_db_path", str(tmp_path / "test.duckdb"))
    monkeypatch.setattr(settings, "gemini_api_key", None)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _auth_headers():
    return {"X-Internal-Auth": settings.internal_auth_token}


def test_stream_accepts_a_payload_without_a_context_field(client):
    res = client.post("/internal/chat/stream", json={"message": "what are total leads"}, headers=_auth_headers())
    assert res.status_code == 200
    assert "no data is connected" in res.text.lower()


def test_stream_tolerates_a_stray_context_field_for_backward_compatible_rollout(client):
    res = client.post(
        "/internal/chat/stream",
        json={"message": "what are total leads", "context": {"anything": "here"}},
        headers=_auth_headers(),
    )
    assert res.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ai && source .venv/Scripts/activate && python -m pytest tests/internal/test_chat_router.py -v`
Expected: FAIL — the current `ChatPayload` requires `context`, so the first request (with no `context` key) gets a 422 validation error instead of 200.

- [ ] **Step 3: Update `chat_router.py`**

Read `ai/app/internal/chat_router.py` first to confirm its current content matches what's described below (it was last touched when `payload.context` was introduced).

Modify `ai/app/internal/chat_router.py`, replacing the `ChatPayload` class and the `stream` function:

```python
class ChatPayload(BaseModel):
    message: str
    model: str | None = None
```

```python
@router.post("/stream")
async def stream(payload: ChatPayload):
    intents = route(payload.message)
    llm = get_llm_client(payload.model)

    async def event_gen():
        # Upfront agent assignment (SRS Fig. 2 step 3), then one sequential
        # pass per assigned agent (Fig. 2's "For Each Assigned Agent Type"
        # loop), each streaming true LLM deltas as they're generated rather
        # than replaying a completed answer.
        yield _sse("agents", {"intents": intents})
        results = []
        for intent in intents:
            prep = await _AGENTS[intent](payload.message)
            yield _sse("agent_start", {"intent": intent})
            text_parts: list[str] = []
            async for delta in llm.compose_stream(prep.system, prep.prompt, prep.offline_text):
                text_parts.append(delta)
                yield _sse("agent_delta", {"intent": intent, "text": delta})
            text = "".join(text_parts) or prep.offline_text
            result = {"intent": intent, "text": text, "payload": prep.payload}
            results.append(result)
            yield _sse("agent_done", result)
        yield _sse("done", {"results": results})

    return StreamingResponse(event_gen(), media_type="text/event-stream")
```

The only functional change from the current file is `payload.context` being dropped from the `_AGENTS[intent](...)` call and `await` being added, since every agent's `prepare` is now `async`. Everything else (the route decorator, `_sse`, `_AGENTS` dict, imports) stays exactly as it is today.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ai && source .venv/Scripts/activate && python -m pytest tests/internal/test_chat_router.py -v`
Expected: 2 passed

- [ ] **Step 5: Run the full `ai` test suite**

Run: `cd ai && source .venv/Scripts/activate && python -m pytest -v`
Expected: all tests pass

- [ ] **Step 6: Commit**

Leave uncommitted per this project's standing rule.

---

### Task 5: Remove `context` from the `api` side

**Files:**
- Modify: `api/src/chat/chat.controller.ts`
- Modify: `api/src/metrics/metrics.service.ts`

**Interfaces:**
- Consumes: `POST /internal/chat/stream` no longer requiring `context` (Task 4).
- Produces: nothing new — this is a pure removal, verified by `npm run build` (a stale reference becomes a compile error) rather than new tests, matching the prior plan's convention for removal-type tasks.

- [ ] **Step 1: Confirm nothing else calls `chatContext`**

Run: `cd app && grep -rn "chatContext" api/src`

Expected output: only the definition in `metrics.service.ts` and the one call site in `chat.controller.ts` — if anything else shows up, stop and investigate before proceeding.

- [ ] **Step 2: Read `chat.controller.ts`**

Read `api/src/chat/chat.controller.ts` in full to see its current `stream()` method and confirm whether `DEFAULT_MODEL`/`DEFAULT_HORIZON` (the two constants near the top of the file) are used anywhere else in the file besides the `chatContext(...)` call you're about to remove.

- [ ] **Step 3: Remove the `chatContext` call from `chat.controller.ts`**

In the `stream()` method, delete this line:

```typescript
    const context = await this.metrics.chatContext(DEFAULT_MODEL, DEFAULT_HORIZON);
```

And in the `this.ai.client.post("/internal/chat/stream", ...)` call a few lines below, remove `context` from the request body object, so it sends only `{ message: dto.message, model: dto.model }`.

If Step 2 showed `DEFAULT_MODEL`/`DEFAULT_HORIZON` are now unused anywhere else in the file, delete those two constant declarations too. If either is still used elsewhere (e.g. by an unrelated method in the same controller), leave it.

- [ ] **Step 4: Remove `chatContext` from `metrics.service.ts`**

In `api/src/metrics/metrics.service.ts`, delete the `chatContext` method entirely:

```typescript
  /** Bundles everything the AI service's agents need for a chat turn or a forecast call. */
  async chatContext(model: string, horizonMonths: number) {
    const [revenueHistory, regionRevenue, ticketDaily, churnSnapshot, topIncidentTitle] = await Promise.all([
      this.revenueHistory(),
      this.regionRevenue(),
      this.ticketDaily(),
      this.churnSnapshot(),
      this.topIncidentTitle(),
    ]);
    return { revenueHistory, regionRevenue, ticketDaily, churnSnapshot, topIncidentTitle, model, horizonMonths };
  }
```

`revenueHistory`, `regionRevenue`, `ticketDaily`, `churnSnapshot`, `ticketTableRowCount`, and `topIncidentTitle` all stay exactly as they are — they're still used by `InsightsService`/`ForecastsController`.

- [ ] **Step 5: Verify the build**

Run: `cd app && npm run build`
Expected: `shared-types → api → web` succeeds with zero TypeScript errors — this is the real check that nothing else referenced `chatContext` or the removed `context` variable.

- [ ] **Step 6: Run the full `api` test suite**

Run: `cd app/api && npx jest`
Expected: all tests still pass (no test in this repo currently targets `chatContext` directly, per the prior plan's `metrics.service.spec.ts`, so none should need updating)

- [ ] **Step 7: Commit**

Leave uncommitted per this project's standing rule.

---

## Manual end-to-end verification (after all tasks)

1. `npm run dev` from `app/` (boots `api`, `ai`, `web`).
2. In Chat, ask a free-form question against your synced MongoDB connector's data (e.g. "what are total leads") — confirm the answer reflects the real collection contents, not a "no data connected" message.
3. Ask a free-form question against your uploaded Airbnb CSV (e.g. "percentage of private room in airbnb") — confirm the answer reflects the real file contents.
4. Ask a diagnostic-shaped question ("why did tickets spike?"), a predictive-shaped question ("forecast next quarter"), and a prescriptive-shaped question ("how do we reduce churn?") against whatever data you have connected — confirm each either grounds in real numbers or honestly says what's missing, and none crash.
5. Revisit Insights and Forecasts — confirm they're unaffected (still working exactly as they did before this plan, since `MetricsService`'s four data methods and `/internal/metrics/query` are untouched).
