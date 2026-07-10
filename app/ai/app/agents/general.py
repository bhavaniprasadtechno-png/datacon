from app.agents.types import AgentPrep

SYSTEM = (
    "You are Datacon's general assistant. Answer the user's question directly and concisely. "
    "If the user is asking for general product/AI knowledge, answer normally. "
    "If they are asking for Datacon analytics help, guide them toward revenue, churn, ticket spikes, forecasts, "
    "documents, connectors, roles, or users."
)


def prepare(question: str, context: dict) -> AgentPrep:
    topic = (question or "that topic").strip()
    offline_text = (
        f"I can help with Datacon analytics questions, but I don't have a grounded general-knowledge answer for "
        f"\"{topic}\" in offline mode. Ask about revenue, churn, ticket spikes, forecasts, documents, or connectors, "
        f"or enable a live LLM model for open-ended questions."
    )

    prompt = (
        f"Question: {question}\n\n"
        "Answer the question directly. If it is unrelated to Datacon analytics, still answer it helpfully. "
        "If the user is looking for Datacon-specific help, point them to the supported analytics workflows."
    )

    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload={})
