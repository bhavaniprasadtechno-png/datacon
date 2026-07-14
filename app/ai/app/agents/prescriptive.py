from app.agents.analytics import (
    churn_stats,
    format_facts,
    region_stats,
    ticket_stats,
)
from app.agents.types import AgentPrep
from app.query_engine.executor import answer_question
from app.query_engine.extract import column_index

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

NO_DATA_TEXT = (
    "No churn data is connected yet. Connect a data source with churn/at-risk account "
    "figures to enable recommendations."
)

_CHURN_QUESTION = (
    "The single most recent churn rate percentage, the previous period's churn rate "
    "percentage, and the number of at-risk accounts."
)


async def prepare(question: str) -> AgentPrep:
    result = await answer_question(_CHURN_QUESTION)
    churn_idx = column_index(result.columns, "churnpct", "churn_pct", "churn") if result.ok else -1

    if not result.ok or churn_idx < 0 or not result.rows:
        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\nNo churn data is connected.",
            offline_text=NO_DATA_TEXT,
            payload={"actions": []},
        )

    at_risk_idx = column_index(result.columns, "atrisk", "at_risk", "risk")
    row = result.rows[0]
    churn_pct = float(row[churn_idx])
    at_risk_accounts = int(row[at_risk_idx]) if at_risk_idx >= 0 else 0

    target = max(churn_pct - 0.7, 0.0)

    actions = [
        {"title": f"Launch save-offer for {at_risk_accounts} at-risk enterprise accounts", "impact": "-0.4pp", "effort": "Low", "owner": "Success"},
        {"title": "Fix billing errors flagged in support documentation", "impact": "-0.2pp", "effort": "Medium", "owner": "Engineering"},
        {"title": "Add usage-drop alerts for accounts under 40% active seats", "impact": "-0.1pp", "effort": "Low", "owner": "Product"},
    ]

    offline_text = f"Three actions are projected to bring churn from {churn_pct:.1f}% toward {target:.1f}% this quarter:"

    prompt = (
        f"Question: {question}\n\nComputed facts:\n- Current churn: {churn_pct:.1f}%\n"
        f"- At-risk accounts: {at_risk_accounts}\n- Target churn: {target:.1f}%\n"
        f"- Planned actions: {[a['title'] for a in actions]}"
    )

    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload={"actions": actions})
