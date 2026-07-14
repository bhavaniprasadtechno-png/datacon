"""Retriever — stage 1 of the multi-agent pipeline.

Per the system prompt spec, this stage checks two sources IN ORDER before
any analysis runs:

  1. Connected database (via the configured connector). Two paths:
     a. Pre-computed metrics blob — the structured fields NestJS ships in
        ``chatContext`` (populated from Prisma models loaded via connector
        syncs). Fast + free; tagged here with source table names.
     b. LIVE query via a connector driver — used when the question needs
        data outside the pre-computed blob AND the caller supplied both
        a catalog and connector configs. The LLM planner in
        ``agents/live_query.py`` picks the query; ``connectors/query.py``
        executes it safely (whitelisted identifiers, parameterised values,
        row cap).

  2. Uploaded data sources (files/documents indexed into ChromaDB). We
     retrieve the top-k chunks most relevant to the user's question so
     the diagnostic/responder stages can quote them.

The retriever is otherwise deterministic — the LLM only fires for live
query planning, and only when the caller opted in by supplying a catalog.
"""
from __future__ import annotations

from typing import Any

from app.agents.live_query import plan_query
from app.connectors.query import run_select
from app.rag.chroma_store import query as chroma_query

# Which Prisma table each context field originates in — used for source
# citation ("from DB: revenue_metrics table"). If the shape of the
# NestJS chatContext blob changes, add mappings here.
_FIELD_TO_SOURCE: dict[str, str] = {
    "revenueHistory": "revenue_metrics",
    "regionRevenue": "region_revenue",
    "ticketDaily": "ticket_daily",
    "churnSnapshot": "churn_snapshot",
    "topIncidentTitle": "data_sources",
}


def _shape(v: Any) -> str:
    if isinstance(v, list):
        return f"list[{len(v)}]"
    if isinstance(v, dict):
        return f"object({', '.join(v.keys())})"
    return type(v).__name__


def retrieve(question: str, context: dict, n_docs: int = 4) -> dict[str, Any]:
    """Return a structured retrieval bundle for a chat turn.

    Shape::

        {
          "db_facts":   [ { field, source, shape, value } , ... ],
          "live_facts": [ { connector_id, engine, table, columns,
                            row_count, rows, why } , ... ],
          "doc_facts":  [ { id, documentTitle, filename, chunkIndex, snippet } , ... ],
          "sources":    [ "DB: revenue_metrics", "Live: orders", "Doc: Q3.pdf", ... ],
          "coverage":   { "db_fields_present": [...], "db_fields_missing": [...],
                          "live_query_run": bool }
        }
    """
    # Live queries need the async planner — the sync path returns an
    # empty live_facts list. Kept for callers that don't `await`; the
    # chat pipeline uses `retrieve_async` below.
    return _build_bundle(question, context, n_docs, live_facts=[])


async def retrieve_async(question: str, context: dict, n_docs: int = 4, model: str | None = None) -> dict[str, Any]:
    """Same shape as `retrieve()` but also runs a LIVE connector query
    when the context supplies a catalog + connectors dict AND the LLM
    planner decides a query is warranted."""
    catalog = context.get("catalog") if isinstance(context, dict) else None
    connectors = context.get("connectors") if isinstance(context, dict) else None
    live_facts: list[dict[str, Any]] = []
    if catalog and connectors:
        plan = await plan_query(question, catalog, model=model)
        if plan is not None:
            entry = _find_catalog_entry(catalog, plan.connector_id, plan.table)
            connector_cfg = connectors.get(plan.connector_id) if isinstance(connectors, dict) else None
            if entry and connector_cfg:
                catalog_map = {entry["table"]: entry["columns"]}
                result = run_select(
                    plan,
                    connector_cfg.get("config", {}),
                    connector_cfg.get("secrets", {}),
                    catalog_map,
                )
                if result.ok:
                    live_facts.append({
                        "connector_id": plan.connector_id,
                        "engine": plan.engine,
                        "table": plan.table,
                        "columns": result.columns,
                        "row_count": result.row_count,
                        "rows": result.rows[:50],  # cap rendered rows
                        "filters": plan.filters,
                        "limit": plan.limit,
                    })
    return _build_bundle(question, context, n_docs, live_facts=live_facts)


def _find_catalog_entry(catalog: list[dict], connector_id: str, table: str) -> dict | None:
    for e in catalog or []:
        if e.get("connector_id") == connector_id and e.get("table") == table:
            return e
    return None


def _build_bundle(question: str, context: dict, n_docs: int, live_facts: list[dict]) -> dict[str, Any]:
    ctx = context or {}
    db_facts: list[dict[str, Any]] = []
    present: list[str] = []
    for field, source in _FIELD_TO_SOURCE.items():
        if field in ctx and ctx[field] not in (None, [], {}, ""):
            db_facts.append({
                "field": field,
                "source": source,
                "shape": _shape(ctx[field]),
                "value": ctx[field],
            })
            present.append(field)
    missing = [f for f in _FIELD_TO_SOURCE if f not in present]

    # Uploaded documents — only queried if the question could benefit from
    # RAG (empty question or catalog-lookup questions skip this to save
    # embedding CPU on every turn).
    doc_facts: list[dict[str, Any]] = []
    if question.strip():
        try:
            hits = chroma_query(question, n_results=n_docs)
        except Exception:
            hits = []
        for i, h in enumerate(hits):
            md = h.get("metadata") or {}
            doc_facts.append({
                "id": i + 1,
                "documentTitle": md.get("title", md.get("filename", "Untitled")),
                "filename": md.get("filename", ""),
                "chunkIndex": md.get("chunk_index", 0),
                "snippet": (h.get("snippet") or "")[:400],
                "source": "uploaded_document",
            })

    sources: list[str] = []
    for f in db_facts:
        sources.append(f"DB: {f['source']}")
    for lf in live_facts:
        sources.append(f"Live: {lf['table']}")
    for d in doc_facts:
        sources.append(f"Doc: {d['documentTitle']}")

    return {
        "db_facts": db_facts,
        "live_facts": live_facts,
        "doc_facts": doc_facts,
        "sources": list(dict.fromkeys(sources)),  # de-dupe, preserve order
        "coverage": {
            "db_fields_present": present,
            "db_fields_missing": missing,
            "live_query_run": bool(live_facts),
        },
    }
