from unittest.mock import AsyncMock, patch

import litellm
import pytest
from app.query_engine import generator


def _fake_response(content: str):
    message = type("M", (), {"content": content})()
    choice = type("C", (), {"message": message})()
    return type("R", (), {"choices": [choice]})()


@pytest.mark.asyncio
async def test_returns_none_when_no_api_key_configured(monkeypatch):
    monkeypatch.setattr(generator.settings, "gemini_api_key", None)
    result = await generator.generate_sql("total revenue", {"orders": ["id", "revenue"]})
    assert result is None


@pytest.mark.asyncio
async def test_returns_none_when_schema_is_empty(monkeypatch):
    monkeypatch.setattr(generator.settings, "gemini_api_key", "fake-key")
    result = await generator.generate_sql("total revenue", {})
    assert result is None


@pytest.mark.asyncio
async def test_returns_generated_sql_stripped_of_markdown_fences(monkeypatch):
    monkeypatch.setattr(generator.settings, "gemini_api_key", "fake-key")
    with patch.object(litellm, "acompletion", new=AsyncMock(return_value=_fake_response("```sql\nSELECT SUM(revenue) FROM orders\n```"))):
        result = await generator.generate_sql("total revenue", {"orders": ["id", "revenue"]})
    assert result == "SELECT SUM(revenue) FROM orders"


@pytest.mark.asyncio
async def test_returns_none_when_model_declines():
    with patch.object(generator.settings, "gemini_api_key", "fake-key"), \
         patch.object(litellm, "acompletion", new=AsyncMock(return_value=_fake_response("NO_ANSWER"))):
        result = await generator.generate_sql("what is the meaning of life", {"orders": ["id"]})
    assert result is None


@pytest.mark.asyncio
async def test_returns_none_when_the_provider_call_raises():
    with patch.object(generator.settings, "gemini_api_key", "fake-key"), \
         patch.object(litellm, "acompletion", new=AsyncMock(side_effect=RuntimeError("boom"))):
        result = await generator.generate_sql("total revenue", {"orders": ["id", "revenue"]})
    assert result is None


@pytest.mark.asyncio
async def test_error_context_is_included_in_the_retry_prompt():
    captured = {}

    async def fake_acompletion(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _fake_response("SELECT 1")

    with patch.object(generator.settings, "gemini_api_key", "fake-key"), \
         patch.object(litellm, "acompletion", new=fake_acompletion):
        await generator.generate_sql("total revenue", {"orders": ["id"]}, error_context="SQL: SELECT x\nError: no such column x")

    user_message = captured["messages"][1]["content"]
    assert "no such column x" in user_message
