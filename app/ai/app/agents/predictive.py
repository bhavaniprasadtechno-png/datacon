from app.agents.analytics import format_facts, region_stats, revenue_stats, run_forecast
from app.agents.types import AgentPrep
from app.forecasting import ols, holt_winters
from app.query_engine.executor import answer_question
from app.query_engine.extract import column_index

SYSTEM = (
    "You are Datacon's predictive analytics agent.\n"
    "You are given the output of a REAL forecast run (Holt-Winters or OLS) "
    "over the user's actual revenue history, plus region breakdowns.\n"
    "Rules:\n"
    "  * Report ONLY the projected value, confidence interval, growth %, and "
    "MAPE that appear in COMPUTED FACTS below.\n"
    "  * Never fabricate a projection or CI — if the facts are empty, say the "
    "series was too short for a forecast.\n"
    "  * Note the model used (Holt-Winters vs OLS) and the horizon."
)


def _offline_forecast(facts: dict) -> str:
    fc = facts.get("forecast") or {}
    if not fc:
        return (
            "I need at least three points of history to run a forecast, and "
            "the attached series is shorter than that. Attach a longer time "
            "series and try again."
        )
    line = (
        f"Using {fc['model']} on the attached revenue series, the {fc['horizon_months']}-month "
        f"projection is {fc['projected']:,.2f} "
        f"(95% CI {fc['ci_low']:,.2f}–{fc['ci_high']:,.2f}), "
        f"a {fc['growth_pct']:+.1f}% change from the latest actual of "
        f"{fc['latest_actual']:,.2f}. Model in-sample MAPE: {fc['mape_pct']:.1f}%."
    )
    return line

NO_DATA_TEXT = (
    "No revenue history is connected yet. Connect a data source with a revenue-over-time "
    "series to enable forecasting."
)

_REVENUE_SERIES_QUESTION = "Total revenue for each month, ordered chronologically, with columns for month and revenue."

MODEL = "Holt-Winters"
HORIZON_MONTHS = 6


async def prepare(question: str) -> AgentPrep:
    result = await answer_question(_REVENUE_SERIES_QUESTION)
    revenue_idx = column_index(result.columns, "revenue", "amount", "total") if result.ok else -1

    if not result.ok or revenue_idx < 0:
        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\nNo revenue history is connected.",
            offline_text=NO_DATA_TEXT,
            payload={"series": []},
        )

    series = [float(row[revenue_idx]) for row in result.rows if row[revenue_idx] is not None]

    if len(series) < 2:
        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\nNo revenue history is connected.",
            offline_text=NO_DATA_TEXT,
            payload={"series": []},
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

    payload = {
        "model": MODEL,
        "projected": f"${forecast['projected']:.2f}M",
        "ciLow": f"${forecast['ci_low']:.2f}M",
        "ciHigh": f"${forecast['ci_high']:.2f}M",
        "growth": f"{forecast['growth_pct']:+.1f}%",
        "mape": f"{forecast['mape']:.1f}%",
        "series": [{"label": f"p{i}", "value": v} for i, v in enumerate(series)],
    }
    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload=payload)
