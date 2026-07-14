from app.agents.types import AgentPrep

SYSTEM = (
    "You are Datacon's descriptive analytics agent.\n"
    "Answer the user's question clearly and concisely, using ONLY the "
    "structured data provided in the context.\n"
    "Quote actual numbers from the context. Never invent facts."
)


def _offline_summary(question: str, context: dict) -> str:
    """Deterministic paragraph built from real context data — displayed
    verbatim when no LLM is configured, and used as a safety net when the
    LLM call fails before producing any tokens."""
    if not context:
        return (
            "I don't have any structured data attached to this turn, "
            "so I can't produce a descriptive summary yet. Try connecting "
            "a data source or asking about a specific metric."
        )
    lines: list[str] = []
    rev = context.get("revenueHistory")
    if isinstance(rev, list) and rev:
        latest = rev[-1]
        prior = rev[-2] if len(rev) > 1 else None
        line = f"Latest revenue point: {latest:,.0f}."
        if prior is not None and prior:
            delta = (latest - prior) / prior * 100
            line += f" That's {delta:+.1f}% vs the prior period."
        lines.append(line)
    region = context.get("regionRevenue")
    if isinstance(region, dict) and region.get("current"):
        top = max(region["current"], key=lambda r: r.get("revenue", 0))
        lines.append(f"Top region this quarter: {top['region']} at {top['revenue']:,.0f}.")
    churn = context.get("churnSnapshot")
    if isinstance(churn, dict) and churn.get("churnPct") is not None:
        lines.append(
            f"Churn is running at {churn['churnPct']:.1f}% "
            f"(prior period {churn.get('prevChurnPct', 0):.1f}%, "
            f"{churn.get('atRiskAccounts', 0)} accounts at risk)."
        )
    if not lines:
        return "The available data doesn't clearly cover your question — try rephrasing or attaching a more specific dataset."
    return " ".join(lines)


def prepare(question: str, context: dict) -> AgentPrep:
    context_text = f"Available Context:\n{context}\n\n" if context else ""
    prompt = (
        f"{context_text}"
        f"User Question:\n{question}\n\n"
        "Provide a descriptive analysis based only on the available information. "
        "Cite specific numbers from the context."
    )
    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text=_offline_summary(question, context),
        payload={},
    )
