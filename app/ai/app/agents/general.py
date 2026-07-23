import logging
from app.agents.types import AgentPrep
from app.query_engine.executor import answer_question
from app.rag.chroma_store import query as chroma_query

logger = logging.getLogger("app.agents.general")

SYSTEM = (
    "You are Datacon's general assistant. "
    "Answer the user's question clearly, accurately, and naturally."
)

MAX_DOC_DISTANCE = 1.2


async def prepare(question: str, model: str | None = None) -> AgentPrep:
    # Tier 1: Check Database Connector Tables first
    if question and question.strip():
        try:
            db_result = await answer_question(question, model)
            if db_result.ok and db_result.rows:
                shown_rows = [
                    [v if v is None or isinstance(v, (int, float, bool, str)) else str(v) for v in row]
                    for row in db_result.rows[:20]
                ]
                prompt = (
                    f"Question: {question}\n\n"
                    f"Connector Query Result:\nColumns: {db_result.columns}\nRows: {shown_rows}\n\n"
                    f"Answer the user's question clearly based on the database connector query result above."
                )
                offline_text = f"Found {len(db_result.rows)} result row(s) for \"{question}\" across database connector tables."
                return AgentPrep(
                    system=SYSTEM,
                    prompt=prompt,
                    offline_text=offline_text,
                    payload={"confidence": "high", "table": {"columns": db_result.columns, "rows": shown_rows}},
                )
        except Exception as e:
            logger.warning("[GeneralAgent] DB connector check failed: %s", e)

    # Tier 2: Check Data Sources (uploaded documents in ChromaDB)
    hits = []
    if question and question.strip():
        try:
            raw_hits = chroma_query(question.strip(), n_results=4)
            hits = [h for h in raw_hits if h.get("distance") is None or h["distance"] <= MAX_DOC_DISTANCE]
        except Exception as e:
            logger.warning("[GeneralAgent] Chroma query failed: %s", e)
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
        prompt = f"""User Question:
{question}

Relevant Data Source Document Excerpts:
{doc_snippets}

Answer the user's question using the Data Source document excerpts above.
Cite the relevant document titles or filenames when drawing facts from them.
"""
        offline_text = (
            f"Based on uploaded data source ({citations[0]['documentTitle']}): "
            f"\"{citations[0]['snippet']}\""
        )
        return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload={"confidence": "high", "citations": citations})

    # Tier 3: General / LLM Fallback (not in DB connector tables, not in Data Sources)
    prompt = f"""User Question:
{question}

Answer the user's question clearly and naturally.
"""
    offline_text = (
        "I'm the Datacon assistant. I can't reach the language model right now, "
        "but I can help with questions about your connected data or uploaded documents."
    )
    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload={})


