from app.agents.types import AgentPrep

SYSTEM = (
    "You are Datacon's prescriptive analytics agent.\n"
    "Based on the provided business context and analysis results, recommend practical, "
    "prioritized actions.\n"
    "Only use the information provided. Do not invent metrics, business values, or facts."
)


def _offline_actions(question: str, context: dict) -> str:
    actions: list[str] = []
    churn = context.get("churnSnapshot") if context else None
    if isinstance(churn, dict) and (churn.get("atRiskAccounts") or 0) > 0:
        actions.append(
            f"1. Launch a retention play for the {churn['atRiskAccounts']} at-risk accounts "
            "before they enter the renewal window."
        )
    tickets = context.get("ticketDaily") if context else None
    if isinstance(tickets, list) and tickets:
        totals: dict[str, int] = {}
        for row in tickets:
            r = row.get("region", "unknown")
            totals[r] = totals.get(r, 0) + int(row.get("count", 0))
        if totals:
            worst = max(totals.items(), key=lambda kv: kv[1])
            actions.append(
                f"{len(actions) + 1}. Increase support coverage in {worst[0]} — "
                f"it accounts for the largest share of tickets ({worst[1]})."
            )
    region = context.get("regionRevenue") if context else None
    if isinstance(region, dict) and region.get("current") and region.get("previous"):
        cur = {r["region"]: r["revenue"] for r in region["current"]}
        prev = {r["region"]: r["revenue"] for r in region["previous"]}
        laggards = [r for r in cur if r in prev and cur[r] < prev[r]]
        if laggards:
            actions.append(
                f"{len(actions) + 1}. Investigate revenue softness in "
                f"{', '.join(laggards)} — these regions declined vs. the prior quarter."
            )
    if not actions:
        return (
            "I don't yet have enough context to recommend specific actions. "
            "Share the metric or dataset you want me to act on, and I'll "
            "produce a prioritized plan."
        )
    return " ".join(actions)


def prepare(question: str, context: dict) -> AgentPrep:
    context_text = f"Analysis Context:\n{context}\n\n" if context else ""
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
        offline_text=_offline_actions(question, context or {}),
        payload=context if context else {},
    )
