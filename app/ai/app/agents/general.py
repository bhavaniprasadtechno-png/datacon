from app.agents.types import AgentPrep

SYSTEM = (
    "You are a helpful AI assistant. "
    "Answer the user's question clearly and accurately. "
    "Use the provided context if available and do not invent facts."
)


async def prepare(question: str, model: str | None = None) -> AgentPrep:
    prompt = f"""
User Question:
{question}

Answer the user's question clearly and naturally.
"""
    # A short, on-brand fallback so chat never renders an empty bubble even
    # when the LLM is unreachable and the question is off-domain.
    offline_text = (
        "I'm the Datacon assistant. I can't reach the language model right now, "
        "but I can still help with questions about your connected data — try "
        "asking about revenue, churn, tickets, or a forecast."
    )
    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload={})
