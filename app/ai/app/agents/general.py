from app.agents.types import AgentPrep

SYSTEM = (
    "You are a helpful AI assistant. "
    "Answer the user's question clearly and accurately. "
    "Use the provided context if available and do not invent facts."
)

def prepare(question: str, context: dict) -> AgentPrep:
    context_text = f"Context:\n{context}\n\n" if context else ""

    prompt = f"""
{context_text}
User Question:
{question}

Answer the user's question clearly and naturally.
"""

    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text="",
        payload={}
    )