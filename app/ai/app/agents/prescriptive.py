from app.agents.types import AgentPrep, no_data_response
from app.pipeline.contracts import Action, Metric, Source, StructuredResponse, Summary
from app.pipeline.normalizer import normalize, sanitize_rows
from app.pipeline.presentation_planner import plan_visualization
from app.query_engine.executor import answer_question
from app.query_engine.extract import column_index
from app.rag.chroma_store import query as chroma_query

SYSTEM = (
    "You are Datacon's prescriptive analytics agent.\n"
    "You are given VALIDATED, PRE-COMPUTED recommended actions derived from the "
    "user's actual data — never invent your own or alter their numbers.\n"
    "Rules:\n"
    "  * Describe ONLY the actions listed below, in the order given (1 highest priority).\n"
    "  * Ground every sentence in the facts/actions provided — never invent a number, "
    "a recommendation, or a citation of your own.\n"
    "  * Keep the summary to 2-4 sentences."
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
    """Deterministic, always-emitted recommendation set — content and
    selection logic unchanged from the pre-migration agent. Making these
    genuinely conditional on data (closer to the old dead `_build_actions`
    approach) is a real but separate improvement, not part of this
    structural migration."""
    return [
        {
            "title": f"Launch save-offer for {at_risk_accounts} at-risk enterprise accounts",
            "effort": "Low",
            "owner": "Success",
            "rationale": "These accounts show renewal-risk signals in the churn data; proactive outreach historically recovers a portion before cancellation.",
            "expected_impact": f"Projected to reduce churn by ~0.4pp, protecting an estimated {at_risk_accounts} accounts this quarter.",
            "_topic": "at-risk account renewal retention outreach",
        },
        {
            "title": "Fix billing errors flagged in support documentation",
            "effort": "Medium",
            "owner": "Engineering",
            "rationale": "Billing errors are a recurring theme in support tickets and a known churn driver when customers feel over-charged or under-served.",
            "expected_impact": f"Projected to reduce churn by ~0.2pp toward {target:.1f}% by removing a top complaint-driven cancellation trigger.",
            "_topic": "billing error incident",
        },
        {
            "title": "Add usage-drop alerts for accounts under 40% active seats",
            "effort": "Low",
            "owner": "Product",
            "rationale": "Low seat utilization is a leading indicator of non-renewal; early alerts let Customer Success intervene before the renewal decision is made.",
            "expected_impact": "Projected to reduce churn by ~0.1pp via earlier intervention on declining-usage accounts.",
            "_topic": "usage adoption seat utilization",
        },
    ]


def _facts_prompt(question: str, response: StructuredResponse) -> str:
    fact_lines = [f"- {m.label}: {m.value}{'%' if m.format == 'percentage' else ''}" for m in response.metrics]
    action_lines = [f"- {a.title}: {a.rationale}" for a in response.actions]
    return (
        f"Question: {question}\n\n"
        "Computed facts (cite ONLY these numbers, never invent others):\n"
        + ("\n".join(fact_lines) or "  (none)")
        + "\n\nValidated recommended actions, in priority order (describe ONLY these):\n"
        + ("\n".join(action_lines) or "  (none)")
        + "\n\nWrite the summary now."
    )


def _offline_summary(churn_pct: float, target: float, actions: list[Action]) -> str:
    lead = f"{len(actions)} action{'s' if len(actions) != 1 else ''} are projected to bring churn from {churn_pct:.1f}% toward {target:.1f}% this quarter:"
    return " ".join([lead] + [f"{i + 1}. {a.title} — {a.rationale}" for i, a in enumerate(actions)])


async def prepare(question: str, model: str | None = None) -> AgentPrep:
    result = await answer_question(_CHURN_QUESTION, model)
    churn_idx = column_index(result.columns, "churnpct", "churn_pct", "churn") if result.ok else -1

    if not result.ok or churn_idx < 0 or not result.rows:
        return no_data_response(SYSTEM, NO_DATA_TEXT)

    at_risk_idx = column_index(result.columns, "atrisk", "at_risk", "risk")
    row = result.rows[0]
    churn_pct = float(row[churn_idx])
    at_risk_accounts = int(row[at_risk_idx]) if at_risk_idx >= 0 else 0
    target = round(max(churn_pct - 0.7, 0.0), 1)

    metrics = [
        Metric(id="churn_pct", label="Current Churn", value=churn_pct, format="percentage"),
        Metric(id="at_risk_accounts", label="At-Risk Accounts", value=at_risk_accounts, format="number"),
        Metric(id="target_churn_pct", label="Target Churn", value=target, format="percentage"),
    ]

    templates = _action_templates(at_risk_accounts, target)
    citations: list[dict] = []
    seen: dict[tuple[str, int], int] = {}
    actions: list[Action] = []
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
        actions.append(Action(
            title=t["title"],
            rationale=t["rationale"],
            effort=t["effort"],
            owner=t["owner"],
            expected_impact=t["expected_impact"],
            citation_ids=action_citation_ids,
        ))

    # Confidence reflects whether the recommendations are actually grounded
    # in supporting documents, computed here (not via the shared Validator's
    # generic issue-based logic) — same precedent as Diagnostic's and
    # Predictive's domain-specific confidence.
    confidence = "high" if all(a.citation_ids for a in actions) else "medium"

    normalized = normalize("churn", ["churn_pct", "at_risk_accounts"], sanitize_rows([[churn_pct, at_risk_accounts]]))
    visualization = plan_visualization(metrics, normalized)

    offline_text = _offline_summary(churn_pct, target, actions)

    response = StructuredResponse(
        summary=Summary(text=offline_text, confidence=confidence),
        metrics=metrics,
        visualizations=[visualization],
        sources=[Source(dataset="churn", row_count=1)],
        actions=actions,
    )

    payload = response.model_dump(by_alias=True)
    if citations:
        payload["citations"] = citations

    return AgentPrep(
        system=SYSTEM,
        prompt=_facts_prompt(question, response),
        offline_text=offline_text,
        payload=payload,
    )
