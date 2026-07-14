from app.agents.analytics import format_facts, region_stats, revenue_stats, run_forecast
from app.agents.types import AgentPrep

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


def prepare(question: str, context: dict) -> AgentPrep:
    ctx = context or {}
    forecast_facts = run_forecast(
        ctx.get("revenueHistory"),
        ctx.get("model", "Holt-Winters"),
        ctx.get("horizonMonths", 6),
    )
    facts = {
        "revenue": revenue_stats(ctx.get("revenueHistory")),
        "regions": region_stats(ctx.get("regionRevenue")),
        "forecast": forecast_facts,
    }
    prompt = f"""User Question:
{question}

COMPUTED FACTS (authoritative — use these exact numbers):
{format_facts({k: v for k, v in facts.items() if v})}

Summarise the forecast for the user. Report the projected value, CI, growth %,
model used, and horizon. If the forecast dict is empty, tell the user the
series was too short.
"""
    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text=_offline_forecast(facts),
        # Payload the UI forecast card renders — real forecast numbers only.
        payload={
            "forecast": forecast_facts,
            "history": ctx.get("revenueHistory") or [],
            "model": ctx.get("model"),
            "horizonMonths": ctx.get("horizonMonths"),
        },
    )
