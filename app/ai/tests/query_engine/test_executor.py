from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from app.query_engine import executor, snapshot_store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot_store.settings, "query_engine_db_path", str(tmp_path / "test.duckdb"))
    yield


@pytest.mark.asyncio
async def test_no_data_connected_short_circuits_before_calling_the_generator():
    with patch.object(executor.generator, "generate_sql", new=AsyncMock()) as mock_generate:
        result = await executor.answer_question("total revenue")
    mock_generate.assert_not_called()
    assert result.ok is False
    assert "No data is connected" in result.message


@pytest.mark.asyncio
async def test_successful_query_returns_columns_and_rows():
    snapshot_store.load_dataset("orders", pd.DataFrame({"revenue": [10, 20]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT SUM(revenue) AS total FROM orders")):
        result = await executor.answer_question("total revenue")
    assert result.ok is True
    assert result.columns == ["total"]
    assert result.rows == [[30]]


@pytest.mark.asyncio
async def test_generator_declining_returns_a_not_ok_answer():
    snapshot_store.load_dataset("orders", pd.DataFrame({"revenue": [10]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value=None)):
        result = await executor.answer_question("total revenue")
    assert result.ok is False


@pytest.mark.asyncio
async def test_rejects_a_write_statement_even_if_the_model_generated_one():
    snapshot_store.load_dataset("orders", pd.DataFrame({"revenue": [10]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="DROP TABLE orders")):
        result = await executor.answer_question("delete everything")
    assert result.ok is False
    assert "rejected" in result.message.lower()


@pytest.mark.asyncio
async def test_rejects_multiple_statements():
    snapshot_store.load_dataset("orders", pd.DataFrame({"revenue": [10]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT 1; DROP TABLE orders")):
        result = await executor.answer_question("total revenue")
    assert result.ok is False


@pytest.mark.asyncio
async def test_execution_error_triggers_one_repair_retry_then_succeeds():
    snapshot_store.load_dataset("orders", pd.DataFrame({"revenue": [10]}))
    generate_mock = AsyncMock(side_effect=["SELECT nonexistent_column FROM orders", "SELECT revenue FROM orders"])
    with patch.object(executor.generator, "generate_sql", new=generate_mock):
        result = await executor.answer_question("total revenue")
    assert result.ok is True
    assert result.rows == [[10]]
    assert generate_mock.call_count == 2


@pytest.mark.asyncio
async def test_execution_error_twice_gives_up_with_a_message():
    snapshot_store.load_dataset("orders", pd.DataFrame({"revenue": [10]}))
    generate_mock = AsyncMock(return_value="SELECT nonexistent_column FROM orders")
    with patch.object(executor.generator, "generate_sql", new=generate_mock):
        result = await executor.answer_question("total revenue")
    assert result.ok is False
    assert generate_mock.call_count == 2
