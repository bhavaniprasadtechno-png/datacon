from app.agents.types import AgentPrep

SYSTEM = (
    "You are Datacon's predictive analytics agent.\n"
    "Present predictive analysis results clearly and professionally.\n"
    "Use only the provided forecast results and context.\n"
    "Do not invent numbers or predictions."
)


def prepare(question: str, context: dict) -> AgentPrep:
    context_text = ""

    if context:
        context_text = f"Prediction Results:\n{context}\n\n"

    prompt = f"""
User Question:
{question}

{context_text}

Summarize the prediction.
Explain what the forecast means.
Mention confidence intervals, trends, accuracy metrics, or other prediction details only if they are present in the provided context.
Do not invent missing information.
"""

    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text="",
        payload=context if context else {},
    )