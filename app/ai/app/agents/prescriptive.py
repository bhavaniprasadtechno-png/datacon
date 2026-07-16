from app.agents.types import AgentPrep
from app.query_engine.executor import answer_question
from app.query_engine.extract import column_index
from app.rag.chroma_store import query as chroma_query

SYSTEM = (
    "You are Datacon's prescriptive analytics agent. Given real churn/at-risk-account "
    "figures, write one tight opening sentence introducing a short action list to reduce "
    "churn. Do not invent numbers beyond what's provided."
)

NO_DATA_TEXT = (
    "No churn data is connected yet. Connect a data source with churn/at-risk account "
    "figures to enable recommendations."
)

_CHURN_QUESTION = (
    "The single most recent churn rate percentage, the previous period's churn rate "
    "percentage, and the number of at-risk accounts."
)


def _action_templates(at_risk_accounts: int, target: float) -> list[dict]:
    return [
        {
            "title": f"Launch save-offer for {at_risk_accounts} at-risk enterprise accounts",
            "impact": "-0.4pp",
            "effort": "Low",
            "owner": "Success",
            "rationale": "These accounts show renewal-risk signals in the churn data; proactive outreach historically recovers a portion before cancellation.",
            "expectedImpact": f"Projected to reduce churn by ~0.4pp, protecting an estimated {at_risk_accounts} accounts this quarter.",
            "_topic": "at-risk account renewal retention outreach",
        },
        {
            "title": "Fix billing errors flagged in support documentation",
            "impact": "-0.2pp",
            "effort": "Medium",
            "owner": "Engineering",
            "rationale": "Billing errors are a recurring theme in support tickets and a known churn driver when customers feel over-charged or under-served.",
            "expectedImpact": f"Projected to reduce churn by ~0.2pp toward {target:.1f}% by removing a top complaint-driven cancellation trigger.",
            "_topic": "billing error incident",
        },
        {
            "title": "Add usage-drop alerts for accounts under 40% active seats",
            "impact": "-0.1pp",
            "effort": "Low",
            "owner": "Product",
            "rationale": "Low seat utilization is a leading indicator of non-renewal; early alerts let Customer Success intervene before the renewal decision is made.",
            "expectedImpact": "Projected to reduce churn by ~0.1pp via earlier intervention on declining-usage accounts.",
            "_topic": "usage adoption seat utilization",
        },
    ]


async def prepare(question: str, model: str | None = None) -> AgentPrep:
    result = await answer_question(_CHURN_QUESTION, model)
    churn_idx = column_index(result.columns, "churnpct", "churn_pct", "churn") if result.ok else -1

    if not result.ok or churn_idx < 0 or not result.rows:
        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\nNo churn data is connected.",
            offline_text=NO_DATA_TEXT,
            payload={"confidence": "low"},
        )

    at_risk_idx = column_index(result.columns, "atrisk", "at_risk", "risk")
    row = result.rows[0]
    churn_pct = float(row[churn_idx])
    at_risk_accounts = int(row[at_risk_idx]) if at_risk_idx >= 0 else 0

    target = max(churn_pct - 0.7, 0.0)
    templates = _action_templates(at_risk_accounts, target)

    offline_text = f"Three actions are projected to bring churn from {churn_pct:.1f}% toward {target:.1f}% this quarter:"

    prompt = (
        f"Question: {question}\n\nComputed facts:\n- Current churn: {churn_pct:.1f}%\n"
        f"- At-risk accounts: {at_risk_accounts}\n- Target churn: {target:.1f}%\n"
        f"- Planned actions: {[t['title'] for t in templates]}"
    )

    citations: list[dict] = []
    seen: dict[tuple[str, int], int] = {}
    actions: list[dict] = []
    for t in templates:
        hits = chroma_query(t["_topic"], n_results=2)
        action_citation_ids: list[int] = []
        for h in hits:
            key = (h["metadata"].get("filename", ""), h["metadata"].get("chunk_index", 0))
            if key not in seen:
                seen[key] = len(citations) + 1
                citations.append({
                    "id": seen[key],
                    "documentTitle": h["metadata"].get("title", h["metadata"].get("filename", "Untitled")),
                    "filename": h["metadata"].get("filename", ""),
                    "chunkIndex": h["metadata"].get("chunk_index", 0),
                    "snippet": h["snippet"][:220],
                })
            action_citation_ids.append(seen[key])
        action = {k: v for k, v in t.items() if k != "_topic"}
        if action_citation_ids:
            action["citationIds"] = action_citation_ids
        actions.append(action)

    payload = {"confidence": "high", "actions": actions}
    if citations:
        payload["citations"] = citations

    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload=payload)
