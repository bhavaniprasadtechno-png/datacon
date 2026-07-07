from app.agents.types import AgentPrep
from app.forecasting import ols, holt_winters

SYSTEM = (
    "You are Datacon's predictive analytics agent. Given a real computed revenue forecast "
    "(point estimate, 95% confidence interval, growth rate), write one tight paragraph "
    "(2-3 sentences) presenting it. Do not invent numbers beyond what's provided."
)


def prepare(question: str, context: dict) -> AgentPrep:
    series = context["revenueHistory"]  # list[float], chronological monthly revenue ($M)
    model = context.get("model", "Holt-Winters")
    horizon = int(context.get("horizonMonths", 6))

    engine = ols if model == "OLS" else holt_winters
    result = engine.forecast(series, horizon)

    offline_text = (
        f"Using a {model} model on {len(series)} months of revenue, the next {horizon} months are "
        f"projected at ${result['projected']:.2f}M (95% CI: ${result['ci_low']:.2f}M–${result['ci_high']:.2f}M), "
        f"a {result['growth_pct']:+.1f}% change. Model fit error (MAPE) is {result['mape']:.1f}%."
    )

    prompt = (
        f"Question: {question}\n\nComputed forecast ({model}, {horizon}-month horizon):\n"
        f"- Projected: ${result['projected']:.2f}M\n- 95% CI: ${result['ci_low']:.2f}M - ${result['ci_high']:.2f}M\n"
        f"- Growth: {result['growth_pct']:+.1f}%\n- MAPE: {result['mape']:.1f}%"
    )

    payload = {
        "model": model,
        "projected": f"${result['projected']:.2f}M",
        "ciLow": f"${result['ci_low']:.2f}M",
        "ciHigh": f"${result['ci_high']:.2f}M",
        "growth": f"{result['growth_pct']:+.1f}%",
        "mape": f"{result['mape']:.1f}%",
        "series": [{"label": f"m{i}", "value": v} for i, v in enumerate(series)],
    }
    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload=payload)
