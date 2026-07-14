"""Retriever — stage 1 of the multi-agent pipeline.

Per the system prompt spec, this stage checks two sources IN ORDER before
any analysis runs:

  1. Connected database (via the configured connector). In this app the
     structured metrics blob shipped by NestJS is populated from Prisma
     models (RevenueMetric, RegionRevenue, TicketDaily, ChurnSnapshot,
     DataSource) that were themselves loaded via the connector engines.
     This retriever tags each field with its source table so downstream
     agents (and the responder) can cite it.

  2. Uploaded data sources (files/documents indexed into ChromaDB). We
     retrieve the top-k chunks most relevant to the user's question so
     the diagnostic/responder stages can quote them.

The retriever is deterministic (no LLM call) — it just annotates and
retrieves. Cost stays flat regardless of question count.
"""
from __future__ import annotations

from typing import Any

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
          "db_facts":  [ { field, source, shape, value } , ... ],
          "doc_facts": [ { id, documentTitle, filename, chunkIndex, snippet } , ... ],
          "sources":   [ "DB: revenue_metrics", "Doc: Q3_sales.pdf", ... ],
          "coverage":  { "db_fields_present": [...], "db_fields_missing": [...] }
        }
    """
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
    for d in doc_facts:
        sources.append(f"Doc: {d['documentTitle']}")

    return {
        "db_facts": db_facts,
        "doc_facts": doc_facts,
        "sources": list(dict.fromkeys(sources)),  # de-dupe, preserve order
        "coverage": {
            "db_fields_present": present,
            "db_fields_missing": missing,
        },
    }
