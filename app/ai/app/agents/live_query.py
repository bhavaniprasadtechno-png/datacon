"""LLM-driven query planner for LIVE connector retrieval.

Given a user question + the catalog of tables available across the user's
connected data sources, this planner decides:
  * Which connector to hit.
  * Which table + columns to project.
  * Any equality/comparison filters implied by the question.
  * Sort order + row limit.

The output is a ``QueryPlan`` that ``connectors/query.py`` executes safely
(whitelisted identifiers, parameterised values, hard row cap).

If no ``TOGETHER_API_KEY`` is configured OR the LLM's plan is unparseable /
invalid against the catalog, this planner returns ``None`` and the
retriever silently skips live querying — the pre-computed metrics blob
remains the answer's source.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import settings
from app.connectors.query import QueryPlan

logger = logging.getLogger("app.agents.live_query")


_PLANNER_SYSTEM = (
    "You are a data-query planner. Given a user's plain-English question "
    "and a catalog of tables the user has connected, output a JSON plan "
    "describing the single most useful SELECT query to answer the question.\n\n"
    "Output schema (JSON only, no prose):\n"
    "{\n"
    '  "needed": true|false,   // false if no table in the catalog can help\n'
    '  "connector_id": "<id>", // must appear in the catalog\n'
    '  "engine":       "<engine>",\n'
    '  "table":        "<table>",\n'
    '  "columns":      ["col1","col2"],   // [] means SELECT *\n'
    '  "filters":      [ {"column":"c","op":"=|<|>|<=|>=|!=|like","value":<v>} ],\n'
    '  "order_by":     "<col or null>",\n'
    '  "order_dir":    "ASC|DESC",\n'
    '  "limit":        <int 1..200>,\n'
    '  "why":          "<one short sentence>"\n'
    "}\n\n"
    "Rules:\n"
    "  * Table + column names MUST exist verbatim in the catalog.\n"
    "  * If the question is already answerable from the pre-computed "
    "metrics context (revenue/regions/tickets/churn), set needed=false.\n"
    "  * Prefer aggregatable columns; keep limit small (<= 50).\n"
    "  * If nothing matches, set needed=false and leave other fields empty."
)


def _catalog_snippet(catalog: list[dict]) -> str:
    """Compact prompt-friendly rendering of the catalog."""
    if not catalog:
        return "(no connected tables)"
    lines: list[str] = []
    for entry in catalog:
        cols = ", ".join(entry.get("columns", [])[:20])
        lines.append(
            f"- connector={entry['connector_id']} engine={entry['engine']} "
            f"table={entry['table']} columns=[{cols}] rows≈{entry.get('row_count', '?')}"
        )
    return "\n".join(lines)


def _parse_plan(raw: str) -> dict | None:
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S)
    match = re.search(r"\{.*\}", cleaned, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _to_plan(data: dict) -> QueryPlan | None:
    if not data.get("needed"):
        return None
    try:
        return QueryPlan(
            connector_id=str(data["connector_id"]),
            engine=str(data["engine"]),
            table=str(data["table"]),
            columns=list(data.get("columns") or []),
            filters=list(data.get("filters") or []),
            order_by=data.get("order_by") or None,
            order_dir=str(data.get("order_dir") or "ASC").upper(),
            limit=int(data.get("limit") or 20),
        )
    except (KeyError, ValueError, TypeError):
        return None


async def plan_query(question: str, catalog: list[dict], model: str | None = None) -> QueryPlan | None:
    """Return a QueryPlan (executable by ``connectors.query.run_select``)
    or ``None`` if live querying isn't warranted / possible."""
    if not catalog:
        return None
    if not settings.is_llm_configured:
        return None
    try:
        import litellm

        user_prompt = (
            f"User question:\n{question}\n\n"
            f"Available tables:\n{_catalog_snippet(catalog)}\n\n"
            "Respond with JSON only."
        )
        target_model = model or settings.llm_model
        if not target_model:
            target_model = f"together_ai/{settings.llm_model}"
        elif not target_model.startswith("together"):
            target_model = f"together_ai/{target_model}"

        stream = await litellm.acompletion(
            model=target_model,
            messages=[
                {"role": "system", "content": _PLANNER_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=512,
            temperature=0,
            stream=True,
            timeout=15,
        )
        parts = []
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = getattr(chunk.choices[0].delta, "content", None)
            if delta:
                parts.append(delta)
        raw = "".join(parts)
    except Exception as e:
        logger.warning("Live query planner LLM call failed (%s); skipping live query.", e)
        return None

    data = _parse_plan(raw)
    if not data:
        logger.info("Live query planner reply unparseable (%r).", raw[:120])
        return None
    return _to_plan(data)
