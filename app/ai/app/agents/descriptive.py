import logging
import re

from app.agents.types import AgentPrep
from app.pipeline.analytics_engine import count_where, percentage, primary_metric
from app.pipeline.contracts import Insight, Metric, Source, StructuredResponse, Summary
from app.pipeline.insight_engine import binary_split_insights, ranking_insight
from app.pipeline.normalizer import NormalizedResult, normalize
from app.pipeline.presentation_planner import category_ranking, plan_table, plan_visualization
from app.pipeline.validator import compute_confidence, validate
from app.query_engine.executor import answer_question

logger = logging.getLogger("app.agents.descriptive")

from app.rag.chroma_store import query as chroma_query

SYSTEM = (
    "You are Datacon's descriptive analytics agent. You are given deterministic, "
    "pre-computed facts about the user's data — never raw database rows. Write a short, "
    "natural-language summary (1-2 sentences) for a business audience, citing ONLY the "
    "numbers listed below. Never state a number that isn't listed."
)

# ponytail: single-table `FROM` match, upgrade to real SQL parsing if a join-heavy
# question ever needs the true source table name. Quoted alternative first —
# quoted identifiers (the common case here; connector/csv-synced table names
# contain hyphens, which `\w` doesn't match) can hold any character except a
# closing quote.
_FROM_TABLE_RE = re.compile(r'FROM\s+(?:"([^"]+)"|([A-Za-z_]\w*))', re.IGNORECASE)
# Connector-synced tables are stored as `conn_{connectorId}_{tableName}` (see
# connectors/service.py) — strip that prefix for a human-facing label. CSV
# uploads (`csv_{documentId}`) have no recoverable human name from the table
# name alone, so they're left as-is.
_CONNECTOR_PREFIX_RE = re.compile(r"^conn_[^_]+_")


def _infer_dataset_name(sql: str | None, fallback: str = "results") -> str:
    if not sql:
        return fallback
    match = _FROM_TABLE_RE.search(sql)
    if not match:
        return fallback
    return match.group(1) or match.group(2)


def _humanize_dataset_name(dataset: str) -> str:
    return _CONNECTOR_PREFIX_RE.sub("", dataset) or dataset


def _sanitize_rows(rows: list[list]) -> list[list]:
    return [[v if v is None or isinstance(v, (int, float, bool, str)) else str(v) for v in row] for row in rows]


def _boolean_split(normalized: NormalizedResult, dataset: str, total_metric_id: str) -> tuple[list[Metric], list[Insight]]:
    """If exactly one boolean dimension exists, add its count/rate as
    metrics and derive grounded positive/attention insights from them."""
    boolean_columns = [c for c in normalized.columns if c.value_type == "boolean"]
    if len(boolean_columns) != 1 or normalized.row_count == 0:
        return [], []

    column = boolean_columns[0].name
    matching = count_where(normalized, column, lambda v: v is True)
    label = column.replace("_", " ").title()
    rate_id, count_id = f"{column}_rate", f"{column}_count"

    metrics = [
        Metric(id=count_id, label=f"{label} Count", value=matching, format="number"),
        Metric(id=rate_id, label=f"{label} Rate", value=percentage(matching, normalized.row_count), format="percentage"),
    ]
    insights = binary_split_insights(
        subject=dataset,
        matching_label=column,
        matching_count=matching,
        total_count=normalized.row_count,
        rate_metric_id=rate_id,
        matching_metric_id=count_id,
        total_metric_id=total_metric_id,
    )
    return metrics, insights


def _category_breakdown(normalized: NormalizedResult, dataset: str) -> tuple[list[Metric], list[Insight]]:
    """If the result is a single-category comparison (e.g. tickets grouped
    by category), add a top-category metric and a ranking insight grounded
    in it — the horizontal-bar chart isn't the only place the breakdown
    should show up."""
    ranked = category_ranking(normalized)
    if not ranked:
        return [], []

    top_label, top_value = ranked[0]
    total = sum(value for _, value in ranked)
    dimension = normalized.dimensions[0]
    metric_id = f"top_{dimension}"

    metric = Metric(id=metric_id, label=f"Top {dimension.replace('_', ' ').title()}", value=top_value, format="number")
    insight = ranking_insight(subject=dataset, top_label=str(top_label), top_value=top_value, top_metric_id=metric_id, total=total)
    return [metric], [insight]


def _offline_summary(dataset: str, total_metric: Metric, insights: list[Insight]) -> str:
    label = dataset.replace("_", " ")
    parts = [f"You have {total_metric.value} {label}."]
    parts.extend(i.text for i in insights)
    return " ".join(parts)


def _facts_prompt(question: str, response: StructuredResponse) -> str:
    fact_lines = [f"- {m.label}: {m.value}{'%' if m.format == 'percentage' else ''}" for m in response.metrics]
    insight_lines = [f"- {i.text}" for i in response.insights]
    return (
        f"Question: {question}\n\n"
        "Computed facts (cite ONLY these numbers, never invent others):\n"
        + ("\n".join(fact_lines) or "  (none)")
        + "\n\nGrounded observations:\n"
        + ("\n".join(insight_lines) or "  (none)")
        + "\n\nWrite the summary now."
    )


def _no_data_response(message: str) -> AgentPrep:
    response = StructuredResponse(summary=Summary(text=message, confidence="low"))
    return AgentPrep(system=SYSTEM, prompt=f"Question unanswerable: {message}", offline_text=message, payload=response.model_dump(by_alias=True))


async def _citation_fallback(question: str) -> AgentPrep | None:
    """Not migrated onto the new structured contract: StructuredResponse has
    no field rich enough to keep citation id/filename/chunkIndex/snippet, and
    dropping them to a Source(dataset, row_count) loses the clickable
    citation chips this path has always rendered. Keeps the pre-migration
    payload shape — the frontend adapter already handles it as-is."""
    if not question or not question.strip():
        return None
    try:
        raw_hits = chroma_query(question.strip(), n_results=4)
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
            "snippet": h.get("snippet", "")[:400],
        }
        for i, h in enumerate(hits)
    ]
    doc_snippets = "\n".join(f"- Document [{c['documentTitle']}] ({c['filename']}): \"{c['snippet']}\"" for c in citations)
    prompt = f"Question: {question}\n\nRelevant Data Source Document Excerpts:\n{doc_snippets}\n\nAnswer using only the excerpts above."
    offline_text = f"According to uploaded Data Source document ({citations[0]['documentTitle']}): \"{citations[0]['snippet']}\""
    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text=offline_text,
        payload={"confidence": "high", "citations": citations},
    )


async def prepare(question: str, model: str | None = None) -> AgentPrep:
    result = await answer_question(question, model)

    if not result.ok or not result.rows:
        fallback = await _citation_fallback(question)
        return fallback if fallback is not None else _no_data_response(result.message)

    dataset = _infer_dataset_name(result.sql)
    display_name = _humanize_dataset_name(dataset)
    normalized = normalize(dataset, result.columns, _sanitize_rows(result.rows), sql=result.sql or "")

    total_metric_id = f"total_{dataset}"
    total_metric = primary_metric(normalized, metric_id=total_metric_id, label=f"Total {display_name.replace('_', ' ').title()}")
    split_metrics, split_insights = _boolean_split(normalized, display_name, total_metric_id)
    category_metrics, category_insights = _category_breakdown(normalized, display_name)
    metrics = [total_metric, *split_metrics, *category_metrics]
    insights = [*split_insights, *category_insights]

    visualization = plan_visualization(metrics, normalized)
    table = plan_table(normalized)
    issues = validate(metrics, insights, [table], normalized, visualizations=[visualization])
    confidence = compute_confidence(query_ok=True, issues=issues)

    offline_text = _offline_summary(display_name, total_metric, insights)
    response = StructuredResponse(
        summary=Summary(text=offline_text, confidence=confidence),
        metrics=metrics,
        insights=insights,
        visualizations=[visualization],
        tables=[table],
        sources=[Source(dataset=display_name, row_count=normalized.row_count)],
    )

    return AgentPrep(
        system=SYSTEM,
        prompt=_facts_prompt(question, response),
        offline_text=offline_text,
        payload=response.model_dump(by_alias=True),
    )
