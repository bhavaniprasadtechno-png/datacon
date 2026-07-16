from app.agents.types import AgentPrep
from app.forecasting import ols, holt_winters
from app.query_engine.executor import answer_question
from app.query_engine.extract import column_index

SYSTEM = (
    "You are Datacon's predictive analytics agent. Given a real computed revenue forecast "
    "(point estimate, 95% confidence interval, growth rate), write one tight paragraph "
    "(2-3 sentences) presenting it. Do not invent numbers beyond what's provided."
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


async def prepare(question: str, model: str | None = None) -> AgentPrep:
    result = await answer_question(_REVENUE_SERIES_QUESTION, model)
    revenue_idx = column_index(result.columns, "revenue", "amount", "total") if result.ok else -1

    if not result.ok or revenue_idx < 0:
        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\nNo revenue history is connected.",
            offline_text=NO_DATA_TEXT,
            payload={"confidence": "low"},
        )

    series = [float(row[revenue_idx]) for row in result.rows if row[revenue_idx] is not None]

    if len(series) < 2:
        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\nNo revenue history is connected.",
            offline_text=NO_DATA_TEXT,
            payload={"confidence": "low"},
        )

    engine = ols if MODEL == "OLS" else holt_winters
    forecast = engine.forecast(series, HORIZON_MONTHS)

    offline_text = (
        f"Using a {MODEL} model on {len(series)} periods of revenue, the next {HORIZON_MONTHS} periods are "
        f"projected at ${forecast['projected']:.2f}M (95% CI: ${forecast['ci_low']:.2f}M-${forecast['ci_high']:.2f}M), "
        f"a {forecast['growth_pct']:+.1f}% change. Model fit error (MAPE) is {forecast['mape']:.1f}%."
    )

    prompt = (
        f"Question: {question}\n\nComputed forecast ({MODEL}, {HORIZON_MONTHS}-period horizon):\n"
        f"- Projected: ${forecast['projected']:.2f}M\n- 95% CI: ${forecast['ci_low']:.2f}M - ${forecast['ci_high']:.2f}M\n"
        f"- Growth: {forecast['growth_pct']:+.1f}%\n- MAPE: {forecast['mape']:.1f}%"
    )

    history_points = [{"label": f"p{i}", "value": v} for i, v in enumerate(series)]
    # Anchor the band's start at the last historical point (zero-width bound at
    # its own value) so recharts has two adjacent bound-bearing points -
    # last actual and forecast - to span, instead of a single point that
    # collapses the shaded confidence-interval area to zero width.
    history_points[-1] = {
        **history_points[-1],
        "lower": history_points[-1]["value"],
        "upper": history_points[-1]["value"],
    }

    payload = {
        "confidence": _confidence(forecast["mape"]),
        "table": {
            "columns": ["period", "revenue"],
            "rows": [[f"p{i}", v] for i, v in enumerate(series)] + [["forecast", forecast["projected"]]],
        },
        "chart": {
            "type": "line",
            "title": f"{MODEL} revenue forecast",
            "data": history_points + [
                {
                    "label": "forecast",
                    "value": forecast["projected"],
                    "lower": forecast["ci_low"],
                    "upper": forecast["ci_high"],
                }
            ],
        },
    }

    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload=payload)
