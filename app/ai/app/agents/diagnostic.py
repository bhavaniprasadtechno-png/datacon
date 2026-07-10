from app.agents.types import AgentPrep
from app.rag.chroma_store import query as chroma_query

SYSTEM = (
    "You are Datacon's diagnostic analytics agent.\n"
    "Analyze the user's question using the provided context and retrieved documents.\n"
    "Identify possible causes, explain your reasoning, and only use information that is available.\n"
    "Do not invent facts or citations."
)


def prepare(question: str, context: dict) -> AgentPrep:
    # Retrieve relevant document chunks based on the user's actual question
    hits = chroma_query(question, n_results=3)

    citations = [
        {
            "id": i + 1,
            "documentTitle": h["metadata"].get(
                "title",
                h["metadata"].get("filename", "Untitled")
            ),
            "filename": h["metadata"].get("filename", ""),
            "chunkIndex": h["metadata"].get("chunk_index", 0),
            "snippet": h["snippet"][:300],
        }
        for i, h in enumerate(hits)
    ]

    context_text = ""

    if context:
        context_text = f"Structured Context:\n{context}\n\n"

    citation_text = ""

    if citations:
        citation_text = "\n".join(
            [
                f"[{c['id']}] {c['documentTitle']}: {c['snippet']}"
                for c in citations
            ]
        )
    else:
        citation_text = "No relevant supporting documents were found."

    prompt = f"""
User Question:
{question}

{context_text}

Retrieved Documents:
{citation_text}

Perform a diagnostic analysis based only on the available information.
Explain the likely causes.
If there is insufficient evidence, clearly state that.
"""

    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text="",
        payload={
            "citations": citations
        },
    )