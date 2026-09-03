from app.agents.types import AgentPrep, facts_prompt, no_data_response
from app.pipeline.analytics_engine import column_index as measure_column_index
from app.pipeline.analytics_engine import percent_change
from app.pipeline.contracts import Insight, Metric, Source, StructuredResponse, Summary
from app.pipeline.insight_engine import spike_insight
from app.pipeline.normalizer import normalize, sanitize_rows
from app.pipeline.presentation_planner import plan_table, plan_visualization
from app.query_engine.executor import answer_question
from app.query_engine.extract import column_index
from app.rag.chroma_store import query as chroma_query

SYSTEM = (
    "You are Datacon's diagnostic analytics agent. You are given deterministic, "
    "pre-computed facts about a day-by-day trend — never raw database rows. Write a "
    "short, natural-language paragraph (2-3 sentences) explaining what changed, citing "
    "ONLY the numbers listed below. Never state a number that isn't listed."
)

NO_DATA_TEXT = (
    "No day-by-day event data is connected yet. Connect a data source with a daily "
    "count (e.g. tickets, incidents) to enable spike detection."
)

_DAILY_COUNT_QUESTION = (
    "Count of events per day for the most relevant countable/event log, with columns "
    "for the date and the count, grouped and ordered chronologically, for the last 8 days."
)

# The agent has no reliable notion of what the connected daily count actually
# represents (tickets, incidents, signups, ...), so facts/insights use this
# deliberately generic subject rather than guessing a domain-specific label.
_SUBJECT = "Events"


async def _citation_fallback(question: str) -> AgentPrep | None:
    """Not migrated onto the new structured contract: StructuredResponse has
    no field rich enough to keep citation id/filename/chunkIndex/snippet.
    Keeps the pre-migration flat payload shape, same pattern as
    Descriptive's document-QA fallback."""
    if not question or not question.strip():
        return None
    try:
        raw_hits = chroma_query(question.strip(), n_results=3)
        hits = [h for h in raw_hits if h.get("distance") is None or h["distance"] <= 1.2]
    except Exception:
        hits = []
    if not hits:
        return None

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
    citation_desc = f" findings in {citations[0]['documentTitle']}, which notes: \"{citations[0]['snippet'][:120]}...\""
    offline_text = f"Correlating your question with uploaded Data Sources,{citation_desc}"
    prompt = (
        f"Question: {question}\n\n"
        f"Cited Data Source Excerpts:\n{[c['snippet'] for c in citations]}\n\n"
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


async def prepare(question: str, model: str | None = None) -> AgentPrep:
    result = await answer_question(_DAILY_COUNT_QUESTION, model)
    date_idx = column_index(result.columns, "date", "day") if result.ok else -1
    count_idx = column_index(result.columns, "count", "total") if result.ok else -1

    if not result.ok or date_idx < 0 or count_idx < 0 or len(result.rows) < 2:
        fallback = await _citation_fallback(question)
        return fallback if fallback is not None else no_data_response(SYSTEM, NO_DATA_TEXT)

    columns = [result.columns[date_idx], result.columns[count_idx]]
    rows = sanitize_rows([[row[date_idx], row[count_idx]] for row in result.rows])
    normalized = normalize("events", columns, rows, sql=result.sql or "")

    measure_col = normalized.measures[0]
    measure_idx = measure_column_index(normalized, measure_col)
    baseline = [float(row[measure_idx]) for row in normalized.rows[:-1]]
    spike_value = float(normalized.rows[-1][measure_idx])
    baseline_avg = round(sum(baseline) / len(baseline), 1) if baseline else spike_value
    change_pct = percent_change(spike_value, baseline)

    spike_metric_id, baseline_metric_id = "spike_count", "baseline_avg"
    metrics = [
        Metric(id=spike_metric_id, label="Latest Count", value=spike_value, format="number"),
        Metric(id=baseline_metric_id, label="Baseline Average", value=baseline_avg, format="number"),
        Metric(id="percent_change", label="Change", value=change_pct, format="percentage"),
    ]
    insights: list[Insight] = [
        spike_insight(
            subject=_SUBJECT,
            value=spike_value,
            baseline_average=baseline_avg,
            change_pct=change_pct,
            value_metric_id=spike_metric_id,
            baseline_metric_id=baseline_metric_id,
        )
    ]

    visualization = plan_visualization(metrics, normalized)
    table = plan_table(normalized)

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
    confidence = "high" if citations else "medium"
    offline_text = insights[0].text

    response = StructuredResponse(
        summary=Summary(text=offline_text, confidence=confidence),
        metrics=metrics,
        insights=insights,
        visualizations=[visualization],
        tables=[table],
        sources=[Source(dataset=_SUBJECT.lower(), row_count=normalized.row_count)],
    )

    payload = response.model_dump(by_alias=True)
    if citations:
        payload["citations"] = citations
        payload["correlation"] = f"spike ↔ {citations[0]['documentTitle']}"

    return AgentPrep(
        system=SYSTEM,
        prompt=facts_prompt(question, response),
        offline_text=offline_text,
        payload=payload,
    )
