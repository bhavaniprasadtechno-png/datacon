from app.agents.types import AgentPrep, no_data_response
from app.forecasting import holt_winters, ols
from app.pipeline.contracts import Metric, Source, StructuredResponse, Summary
from app.pipeline.normalizer import humanize_dataset_name, infer_dataset_name, normalize, sanitize_rows
from app.pipeline.presentation_planner import plan_table, plan_visualization
from app.query_engine.executor import answer_question
from app.query_engine.extract import column_index

SYSTEM = (
    "You are Datacon's predictive analytics agent.\n"
    "You are given deterministic, pre-computed facts about a REAL forecast run "
    "(Holt-Winters or OLS) over the user's actual revenue history — never raw rows.\n"
    "Rules:\n"
    "  * Report ONLY the projected value, confidence interval, and growth % that "
    "appear in the computed facts below.\n"
    "  * Never fabricate a projection or CI — if the facts are empty, say the "
    "series was too short for a forecast.\n"
    "  * Note the model used (Holt-Winters vs OLS) and the horizon."
)

NO_DATA_TEXT = (
    "No revenue history is connected yet. Connect a data source with a revenue-over-time "
    "series to enable forecasting."
)

_REVENUE_SERIES_QUESTION = "Total revenue for each month, ordered chronologically, with columns for month and revenue."

MODEL = "Holt-Winters"
HORIZON_MONTHS = 6


def _confidence(mape: float) -> str:
    if mape < 15:
        return "high"
    if mape < 30:
        return "medium"
    return "low"


def _facts_prompt(question: str, response: StructuredResponse) -> str:
    fact_lines = [f"- {m.label}: {m.value}{'%' if m.format == 'percentage' else ''}" for m in response.metrics]
    return (
        f"Question: {question}\n\n"
        f"Computed forecast ({MODEL}, {HORIZON_MONTHS}-month horizon):\n"
        + ("\n".join(fact_lines) or "  (none)")
        + "\n\nWrite the summary now."
    )


async def prepare(question: str, model: str | None = None) -> AgentPrep:
    result = await answer_question(_REVENUE_SERIES_QUESTION, model)
    month_idx = column_index(result.columns, "month", "period", "date") if result.ok else -1
    revenue_idx = column_index(result.columns, "revenue", "amount", "total") if result.ok else -1

    if not result.ok or month_idx < 0 or revenue_idx < 0:
        return no_data_response(SYSTEM, NO_DATA_TEXT)

    rows = sanitize_rows([
        [row[month_idx], row[revenue_idx]] for row in result.rows if row[revenue_idx] is not None
    ])
    series = [float(row[1]) for row in rows]
    if len(series) < 2:
        return no_data_response(SYSTEM, NO_DATA_TEXT)

    dataset = humanize_dataset_name(infer_dataset_name(result.sql, fallback="revenue"))
    normalized = normalize(dataset, [result.columns[month_idx], result.columns[revenue_idx]], rows, sql=result.sql or "")

    engine = ols if MODEL == "OLS" else holt_winters
    forecast = engine.forecast(series, HORIZON_MONTHS)
    confidence = _confidence(forecast["mape"])

    projected, ci_low, ci_high = round(forecast["projected"], 2), round(forecast["ci_low"], 2), round(forecast["ci_high"], 2)
    growth_pct = round(forecast["growth_pct"], 1)
    metrics = [
        Metric(id="projected", label="Projected", value=projected, format="currency"),
        Metric(id="ci_low", label="95% CI Low", value=ci_low, format="currency"),
        Metric(id="ci_high", label="95% CI High", value=ci_high, format="currency"),
        Metric(id="growth_pct", label="Growth", value=growth_pct, format="percentage"),
    ]

    visualization = plan_visualization(metrics, normalized)
    chart_data = list(visualization.data)
    if chart_data:
        last = chart_data[-1]
        # Anchor the band's start at the last historical point (zero-width
        # bound at its own value) so recharts has two adjacent bound-bearing
        # points — last actual and forecast — to span, instead of a single
        # point that collapses the shaded confidence-interval area to zero
        # width.
        chart_data[-1] = {**last, "lower": last["value"], "upper": last["value"]}
    chart_data.append({"label": "forecast", "value": projected, "lower": ci_low, "upper": ci_high})
    visualization = visualization.model_copy(update={"data": chart_data, "title": f"{MODEL} revenue forecast"})

    table = plan_table(normalized)

    offline_text = (
        f"Using a {MODEL} model on {len(series)} periods of revenue, the next {HORIZON_MONTHS} periods are "
        f"projected at {projected:.2f} (95% CI: {ci_low:.2f}-{ci_high:.2f}), a {growth_pct:+.1f}% change. "
        f"Model fit error (MAPE) is {forecast['mape']:.1f}%."
    )

    response = StructuredResponse(
        summary=Summary(text=offline_text, confidence=confidence),
        metrics=metrics,
        visualizations=[visualization],
        tables=[table],
        sources=[Source(dataset=dataset, row_count=normalized.row_count)],
    )

    return AgentPrep(
        system=SYSTEM,
        prompt=_facts_prompt(question, response),
        offline_text=offline_text,
        payload=response.model_dump(by_alias=True),
    )
