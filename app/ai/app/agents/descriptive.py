import logging

from app.agents.types import AgentPrep
from app.query_engine.executor import answer_question, grouped_count

logger = logging.getLogger("app.agents.descriptive")

from app.rag.chroma_store import query as chroma_query

SYSTEM = (
    "You are Datacon's descriptive analytics agent. Given a real query result table "
    "or cited Data Source document excerpts, answer the user's question clearly in one tight paragraph "
    "for a business audience. Reference cited document titles when answering from Data Sources."
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
    """Column (among all qualifying ones) with the fewest distinct values —
    that's all-string, not id/email/name/url/phone/date-shaped, and has 2-8
    distinct values — a candidate for a secondary count-by-category chart
    alongside a wider raw-records table. Ties broken by column order.
    Preferring minimum cardinality over "first in column order" avoids
    picking an incidentally-low-cardinality free-text column (e.g. a
    "company" name that happens to repeat a few times in a small sample)
    over a genuine small-enum column (e.g. "status") that appears later.
    Real identifier columns (_id, *_id, *Id, *ID) are already stripped
    upstream by executor._filter_sensitive_columns, so bare "id" isn't in
    this denylist — it would otherwise false-positive on ordinary words like
    "Provider" or "Video"."""
    candidates: list[tuple[int, str]] = []
    for i, name in enumerate(columns):
        lowered = name.lower()
        if any(bad in lowered for bad in _DISTRIBUTION_DENYLIST):
            continue
        values = [row[i] for row in rows]
        if any(v is not None and not isinstance(v, str) for v in values):
            continue
        distinct = {v for v in values if v is not None}
        if 2 <= len(distinct) <= 8:
            candidates.append((len(distinct), name))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    return candidates[0][1]


async def prepare(question: str, model: str | None = None) -> AgentPrep:
    result = await answer_question(question, model)

    if not result.ok or not result.rows:
        # Tier 2: Check Data Sources (uploaded documents in ChromaDB)
        hits = []
        if question and question.strip():
            try:
                raw_hits = chroma_query(question.strip(), n_results=4)
                hits = [h for h in raw_hits if h.get("distance") is None or h["distance"] <= 1.2]
            except Exception:
                hits = []

        citations = [
            {
                "id": i + 1,
                "documentTitle": h["metadata"].get("title", h["metadata"].get("filename", "Untitled")),
                "filename": h["metadata"].get("filename", ""),
                "chunkIndex": h["metadata"].get("chunk_index", 0),
                "snippet": h.get("snippet", "")[:400],
            }
            for i, h in enumerate(hits)
        ]

        if citations:
            doc_snippets = "\n".join(
                [f"- Document [{c['documentTitle']}] ({c['filename']}): \"{c['snippet']}\"" for c in citations]
            )
            prompt = (
                f"Question: {question}\n\n"
                f"Relevant Data Source Document Excerpts:\n{doc_snippets}\n\n"
                f"Answer the user's question clearly using the uploaded Data Source document excerpts above."
            )
            offline_text = f"According to uploaded Data Source document ({citations[0]['documentTitle']}): \"{citations[0]['snippet']}\""
            return AgentPrep(
                system=SYSTEM,
                prompt=prompt,
                offline_text=offline_text,
                payload={"confidence": "high", "citations": citations},
            )

        # Tier 3: Low confidence / general fallback
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
