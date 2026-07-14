from app.agents.analytics import (
    churn_stats,
    format_facts,
    region_stats,
    ticket_stats,
)
from app.agents.types import AgentPrep

SYSTEM = (
    "You are Datacon's prescriptive analytics agent.\n"
    "You are given PRE-COMPUTED facts derived from the user's actual data. "
    "Your job is to recommend prioritized, practical actions.\n"
    "Rules:\n"
    "  * Every recommendation MUST be grounded in a fact from the list below "
    "(quote the underlying number).\n"
    "  * Number recommendations in priority order (1 highest).\n"
    "  * If the facts don't support a specific action, say what additional "
    "data would be needed — never invent business advice.\n"
    "  * Keep to 3-5 recommendations max."
)


def _build_actions(facts: dict) -> list[dict]:
    """Deterministic ranked action list computed from real facts. Used both
    to build the offline paragraph and as the structured payload."""
    actions: list[dict] = []
    ch = facts.get("churn") or {}
    if ch.get("at_risk_accounts"):
        actions.append({
            "priority": len(actions) + 1,
            "action": "Launch retention play for at-risk accounts",
            "rationale": (
                f"{ch['at_risk_accounts']} accounts flagged at risk; churn is "
                f"{ch.get('churn_pct', 0):.1f}%"
                + (f" ({ch['delta_pp']:+.1f}pp vs prior)" if "delta_pp" in ch else "")
                + "."
            ),
            "impact_metric": "churn_pct",
        })
    tick = facts.get("tickets") or {}
    if tick.get("trend_pct") is not None and tick["trend_pct"] > 10:
        actions.append({
            "priority": len(actions) + 1,
            "action": f"Add support capacity in {tick['top_region']['region']}",
            "rationale": (
                f"Ticket volume rose {tick['trend_pct']:+.1f}% in the second half, "
                f"led by {tick['top_region']['region']} ({tick['top_region']['count']} tickets)."
            ),
            "impact_metric": "ticket_volume",
        })
    reg = facts.get("regions") or {}
    laggards = sorted(
        [d for d in (reg.get("region_deltas") or []) if d.get("delta_pct") is not None and d["delta_pct"] < 0],
        key=lambda d: d["delta_pct"],
    )
    if laggards:
        worst = laggards[0]
        actions.append({
            "priority": len(actions) + 1,
            "action": f"Investigate revenue softness in {worst['region']}",
            "rationale": (
                f"{worst['region']} declined {worst['delta_pct']:+.1f}% vs prior quarter "
                f"({worst['previous']:,.2f} → {worst['current']:,.2f})."
            ),
            "impact_metric": "region_revenue",
        })
    if reg.get("top"):
        top = reg["top"]
        actions.append({
            "priority": len(actions) + 1,
            "action": f"Double down on {top['region']} — highest-revenue region",
            "rationale": f"{top['region']} leads at {top['revenue']:,.2f}; replicate its playbook elsewhere.",
            "impact_metric": "region_revenue",
        })
    return actions


def _offline_actions(actions: list[dict]) -> str:
    if not actions:
        return (
            "I don't yet have enough grounded facts to recommend specific actions. "
            "Share the metric or dataset you want me to act on and I'll produce "
            "a prioritized plan."
        )
    return " ".join(
        f"{a['priority']}. {a['action']} — {a['rationale']}"
        for a in actions
    )


def prepare(question: str, context: dict) -> AgentPrep:
    ctx = context or {}
    facts = {
        "regions": region_stats(ctx.get("regionRevenue")),
        "tickets": ticket_stats(ctx.get("ticketDaily")),
        "churn": churn_stats(ctx.get("churnSnapshot")),
    }
    actions = _build_actions(facts)
    prompt = f"""User Question:
{question}

COMPUTED FACTS (authoritative — use these exact numbers):
{format_facts({k: v for k, v in facts.items() if v})}

CANDIDATE ACTIONS (ranked, grounded in the facts above):
{format_facts({str(a['priority']): a for a in actions}) if actions else '(none)'}

Present a prioritized list of recommendations. Ground each in the specific
numbers above. If facts are insufficient, say what additional data is needed.
"""
    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text=_offline_actions(actions),
        payload={"facts": facts, "actions": actions},
    )
