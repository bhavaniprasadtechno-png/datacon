from app.agents.types import AgentPrep

SYSTEM = (
    "You are Datacon's prescriptive analytics agent.\n"
    "Based on the provided business context and analysis results, recommend practical, "
    "prioritized actions.\n"
    "Only use the information provided. Do not invent metrics, business values, or facts."
)


def prepare(question: str, context: dict) -> AgentPrep:
    context_text = ""

    if context:
        context_text = f"Analysis Results:\n{context}\n\n"

    prompt = f"""
User Question:
{question}

{context_text}

Based on the available information:

1. Recommend practical actions.
2. Explain why each action is useful.
3. Prioritize the recommendations.
4. If there is insufficient information, clearly state what additional data is needed.
5. Do not invent business metrics or recommendations that are unsupported.
"""

    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text="",
        payload=context if context else {},
    )