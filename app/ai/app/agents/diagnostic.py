from app.agents.analytics import (
    churn_stats,
    format_facts,
    region_stats,
    revenue_stats,
    ticket_stats,
)
from app.agents.types import AgentPrep
from app.query_engine.executor import answer_question
from app.query_engine.extract import column_index
from app.rag.chroma_store import query as chroma_query

SYSTEM = (
    "You are Datacon's diagnostic analytics agent. Given a real computed spike figure "
    "and real cited document excerpts, write one tight paragraph (3-4 sentences) "
    "explaining the likely root cause. Only reference the provided citations."
)

NO_DATA_TEXT = (
    "No day-by-day event data is connected yet. Connect a data source with a daily "
    "count (e.g. tickets, incidents) to enable spike detection."
)

_DAILY_COUNT_QUESTION = (
    "Count of events per day for the most relevant countable/event log, grouped and "
    "ordered chronologically, for the last 8 days."
)


async def prepare(question: str, model: str | None = None) -> AgentPrep:
    result = await answer_question(_DAILY_COUNT_QUESTION, model)
    region_idx = column_index(result.columns, "region", "category", "group") if result.ok else -1
    count_idx = column_index(result.columns, "count", "total") if result.ok else -1

    if not result.ok or count_idx < 0 or len(result.rows) < 2:
        hits = []
        if question and question.strip():
            try:
                raw_hits = chroma_query(question.strip(), n_results=3)
                hits = [h for h in raw_hits if h.get("distance") is None or h["distance"] <= 1.2]
            except Exception:
                hits = []

        citations = [
            {
                "id": i + 1,
                "documentTitle": h["metadata"].get("title", h["metadata"].get("filename", "Untitled")),
                "filename": h["metadata"].get("filename", ""),
                "chunkIndex": h["metadata"].get("chunk_index", 0),
                "snippet": h.get("snippet", "")[:220],
            }
            for i, h in enumerate(hits)
        ]

        if citations:
            citation_desc = f" findings in {citations[0]['documentTitle']}, which notes: \"{citations[0]['snippet'][:120]}...\""
            offline_text = f"Correlating your question with uploaded Data Sources,{citation_desc}"
            prompt = (
                f"Question: {question}\n\n"
                f"Cited Data Source Excerpts:\n"
                f"{[c['snippet'] for c in citations]}\n\n"
                f"Explain the diagnostic findings or root causes based on the cited excerpts above."
            )
            return AgentPrep(
                system=SYSTEM,
                prompt=prompt,
                offline_text=offline_text,
                payload={
                    "confidence": "high",
                    "citations": citations,
                    "correlation": f"query ↔ {citations[0]['documentTitle']}",
                },
            )

        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\nNo day-by-day event data is connected.",
            offline_text=NO_DATA_TEXT,
            payload={"confidence": "low"},
        )

    daily = [
        {"region": str(row[region_idx]) if region_idx >= 0 else "overall", "count": float(row[count_idx])}
        for row in result.rows
    ]
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
        f"{spike['region']} events rose {pct:+.0f}% versus the baseline average "
        f"({spike['count']:.0f} vs a baseline of {avg:.0f}/day). Correlating this with your uploaded documents,"
        f"{citation_desc}"
    )

    prompt = (
        f"Question: {question}\n\nComputed facts:\n- {spike['region']} count today: {spike['count']:.0f}\n"
        f"- Baseline average: {avg:.1f}\n- Change: {pct:+.0f}%\n"
        f"- Cited excerpts: {[c['snippet'] for c in citations]}"
    )

    payload = {
        "confidence": "high" if citations else "medium",
        "table": {"columns": ["region", "count"], "rows": [[d["region"], d["count"]] for d in daily]},
    }
    if citations:
        payload["citations"] = citations
        payload["correlation"] = f"spike ↔ {citations[0]['documentTitle']}"

    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload=payload)
