from app.agents.types import AgentPrep
from app.rag.chroma_store import query as chroma_query

SYSTEM = (
    "You are Datacon's diagnostic analytics agent.\n"
    "Analyze the user's question using the provided context and retrieved documents.\n"
    "Identify possible causes, explain your reasoning, and only use information that is available.\n"
    "Cite retrieved documents inline as [1], [2] where relevant. Never invent citations."
)


def _offline_diagnosis(question: str, context: dict, citations: list[dict]) -> str:
    lines: list[str] = []
    tickets = context.get("ticketDaily") if context else None
    if isinstance(tickets, list) and tickets:
        totals: dict[str, int] = {}
        for row in tickets:
            r = row.get("region", "unknown")
            totals[r] = totals.get(r, 0) + int(row.get("count", 0))
        if totals:
            worst = max(totals.items(), key=lambda kv: kv[1])
            lines.append(f"Support-ticket volume is concentrated in {worst[0]} ({worst[1]} tickets in the window).")
    churn = context.get("churnSnapshot") if context else None
    if isinstance(churn, dict):
        prev = churn.get("prevChurnPct", 0) or 0
        curr = churn.get("churnPct", 0) or 0
        if curr > prev:
            lines.append(f"Churn ticked up from {prev:.1f}% to {curr:.1f}%, which likely contributes to the pattern you're asking about.")
    if citations:
        titles = ", ".join({c["documentTitle"] for c in citations[:3]})
        lines.append(f"Supporting evidence was found in: {titles}.")
    if not lines:
        return (
            "I couldn't find enough evidence in the attached data or documents "
            "to explain that yet. Try attaching related documents or narrowing "
            "the question to a specific metric and time window."
        )
    return " ".join(lines)


def prepare(question: str, context: dict) -> AgentPrep:
    # Retrieve relevant document chunks based on the user's actual question
    hits = chroma_query(question, n_results=3)

    citations = [
        {
            "id": i + 1,
            "documentTitle": h["metadata"].get(
                "title",
                h["metadata"].get("filename", "Untitled"),
            ),
            "filename": h["metadata"].get("filename", ""),
            "chunkIndex": h["metadata"].get("chunk_index", 0),
            "snippet": h["snippet"][:300],
        }
        for i, h in enumerate(hits)
    ]

    context_text = f"Structured Context:\n{context}\n\n" if context else ""
    if citations:
        citation_text = "\n".join(
            f"[{c['id']}] {c['documentTitle']}: {c['snippet']}" for c in citations
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
Explain the likely causes and cite documents as [1], [2] where they support
your reasoning. If there is insufficient evidence, clearly state that.
"""

    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text=_offline_diagnosis(question, context or {}, citations),
        payload={"citations": citations},
    )
