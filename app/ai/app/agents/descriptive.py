from app.agents.analytics import (
    format_facts,
    region_stats,
    revenue_stats,
    churn_stats,
    ticket_stats,
)
from app.agents.types import AgentPrep

SYSTEM = (
    "You are Datacon's descriptive analytics agent.\n"
    "You are given a set of PRE-COMPUTED facts extracted from the user's real data. "
    "Your job is to describe the state of the business in clear, natural prose, "
    "citing the exact numbers from the computed facts.\n"
    "Rules:\n"
    "  * Never invent numbers — only use the values in COMPUTED FACTS below.\n"
    "  * If a fact isn't in the list, say you don't have that data rather than guessing.\n"
    "  * Round percentages to one decimal place and currency to the nearest unit.\n"
    "  * Keep the answer under ~120 words unless the user asked for a full report."
)


def _compute(context: dict) -> dict:
    return {
        "revenue": revenue_stats(context.get("revenueHistory")),
        "regions": region_stats(context.get("regionRevenue")),
        "tickets": ticket_stats(context.get("ticketDaily")),
        "churn": churn_stats(context.get("churnSnapshot")),
    }


def _offline_summary(facts: dict) -> str:
    parts: list[str] = []
    rev = facts.get("revenue") or {}
    if "latest" in rev:
        line = f"Latest revenue: {rev['latest']:,.2f}."
        if "mom_delta_pct" in rev:
            line += f" That's {rev['mom_delta_pct']:+.1f}% MoM."
        if "yoy_delta_pct" in rev:
            line += f" YoY {rev['yoy_delta_pct']:+.1f}%."
        parts.append(line)
    reg = facts.get("regions") or {}
    if reg.get("top"):
        parts.append(
            f"Top region: {reg['top']['region']} at {reg['top']['revenue']:,.2f}; "
            f"weakest: {reg['bottom']['region']} at {reg['bottom']['revenue']:,.2f}."
        )
    tick = facts.get("tickets") or {}
    if tick.get("top_region"):
        parts.append(
            f"Support tickets total {tick['total']} in the window, "
            f"led by {tick['top_region']['region']} ({tick['top_region']['count']})."
        )
    ch = facts.get("churn") or {}
    if ch.get("churn_pct") is not None:
        line = f"Churn is {ch['churn_pct']:.1f}%"
        if "delta_pp" in ch:
            line += f" ({ch['delta_pp']:+.1f}pp vs prior)"
        if ch.get("at_risk_accounts"):
            line += f", {ch['at_risk_accounts']} accounts at risk"
        parts.append(line + ".")
    return " ".join(parts) or (
        "I don't have enough structured data attached to this turn to describe "
        "the current state. Connect a data source or narrow the question."
    )


def prepare(question: str, context: dict) -> AgentPrep:
    facts = _compute(context or {})
    prompt = f"""User Question:
{question}

COMPUTED FACTS (authoritative — use these exact numbers):
{format_facts({k: v for k, v in facts.items() if v})}

Answer the question by describing what these facts show. Only cite numbers
that appear above. If the facts don't cover what was asked, say so plainly.
"""
    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text=_offline_summary(facts),
        payload={"facts": facts},
    )
