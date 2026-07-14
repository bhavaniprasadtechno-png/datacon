from app.agents.context_filter import forecast_payload
from app.agents.types import AgentPrep

SYSTEM = (
    "You are Datacon's predictive analytics agent.\n"
    "Present forecast results clearly and professionally.\n"
    "Use only the provided historical data and model settings.\n"
    "Do not invent numbers or predictions."
)


def _offline_forecast(question: str, context: dict) -> str:
    history = context.get("revenueHistory") if context else None
    horizon = (context or {}).get("horizonMonths", 6)
    model = (context or {}).get("model", "Holt-Winters")
    if not isinstance(history, list) or len(history) < 3:
        return (
            "I don't have enough history to project a forecast yet — "
            "attach a longer time-series and try again."
        )
    latest = history[-1]
    # Simple average-of-recent-deltas projection as a deterministic
    # placeholder; the real forecast is computed by the /forecast endpoint.
    recent = history[-6:] if len(history) >= 6 else history
    deltas = [recent[i] - recent[i - 1] for i in range(1, len(recent))]
    avg_delta = sum(deltas) / len(deltas) if deltas else 0
    projection = latest + avg_delta * horizon
    direction = "up" if avg_delta >= 0 else "down"
    return (
        f"Using {model} on {len(history)} historical points, the trend is "
        f"{direction} by ~{avg_delta:,.0f} per period on average. Projecting "
        f"{horizon} periods ahead lands near {projection:,.0f} "
        f"(from a latest observed value of {latest:,.0f})."
    )


def prepare(question: str, context: dict) -> AgentPrep:
    context_text = f"Prediction Context:\n{context}\n\n" if context else ""
    prompt = f"""
User Question:
{question}

{context_text}
Summarize the prediction. Explain what the forecast means. Mention
confidence intervals, trends, or accuracy metrics only if they are
present in the provided context. Do not invent missing information.
"""
    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text=_offline_forecast(question, context or {}),
        # Payload for the UI's forecast card — only forecast-shaped fields,
        # never the raw metrics blob (that made the visualization render
        # nonsense in the previous version).
        payload=forecast_payload(context),
    )
