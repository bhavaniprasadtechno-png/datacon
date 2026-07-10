from app.agents.types import AgentPrep

SYSTEM = (
    "You are Datacon's descriptive analytics agent.\n"
    "Answer the user's question clearly and concisely.\n"
    "If structured data is provided in the context, summarize it accurately.\n"
    "Do not make up facts or numbers."
)


def prepare(question: str, context: dict) -> AgentPrep:
    # Pass any available context to the LLM
    context_text = ""

    if context:
        context_text = f"Available Context:\n{context}\n\n"

    prompt = (
        f"{context_text}"
        f"User Question:\n{question}\n\n"
        "Provide a descriptive analysis based only on the available information."
    )

    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text="",
        payload={}
    )