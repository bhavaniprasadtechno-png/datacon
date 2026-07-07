from app.agents.types import AgentPrep
from app.rag.chroma_store import query as chroma_query

SYSTEM = (
    "You are Datacon's diagnostic analytics agent. Given a real computed ticket-spike "
    "figure and real cited document excerpts, write one tight paragraph (3-4 sentences) "
    "explaining the likely root cause. Only reference the provided citations."
)


def prepare(question: str, context: dict) -> AgentPrep:
    daily = context["ticketDaily"]  # [{date, region, count}], chronological, last = today
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
        f"{spike['region']} support tickets rose {pct:+.0f}% versus the 7-day average "
        f"({spike['count']} vs a baseline of {avg:.0f}/day). Correlating the ticket database with your uploaded incident memos,"
        f"{citation_desc}"
    )

    prompt = (
        f"Question: {question}\n\nComputed facts:\n- {spike['region']} tickets today: {spike['count']}\n"
        f"- 7-day baseline average: {avg:.1f}\n- Change: {pct:+.0f}%\n"
        f"- Cited excerpts: {[c['snippet'] for c in citations]}"
    )

    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text=offline_text,
        payload={"citations": citations, "correlation": f"ticket spike ↔ {citations[0]['documentTitle']}" if citations else None},
    )
