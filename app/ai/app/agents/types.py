from dataclasses import dataclass
from typing import Any

from app.pipeline.contracts import StructuredResponse, Summary


@dataclass
class AgentPrep:
    """Everything an agent computes *before* prose generation: the real
    facts (payload) plus the prompts that turn them into a paragraph.
    Separated from the LLM call itself so the chat stream can emit true
    token deltas while they're generated (SRS Fig. 2 steps 7-9), instead
    of waiting for a complete compose() round-trip."""

    system: str
    prompt: str
    offline_text: str
    payload: dict[str, Any]


def no_data_response(system: str, message: str) -> AgentPrep:
    """A real low-confidence StructuredResponse for the true-empty case —
    shared by every migrated agent's "nothing connected" / "not enough
    data" branch."""
    response = StructuredResponse(summary=Summary(text=message, confidence="low"))
    return AgentPrep(
        system=system,
        prompt=f"Question unanswerable: {message}",
        offline_text=message,
        payload=response.model_dump(by_alias=True),
    )


def facts_prompt(question: str, response: StructuredResponse) -> str:
    """The LLM prompt for a metrics-and-insights response: computed facts
    plus grounded observations, nothing else — constrains the summary prose
    to numbers that were actually calculated."""
    fact_lines = [f"- {m.label}: {m.value}{'%' if m.format == 'percentage' else ''}" for m in response.metrics]
    insight_lines = [f"- {i.text}" for i in response.insights]
    return (
        f"Question: {question}\n\n"
        "Computed facts (cite ONLY these numbers, never invent others):\n"
        + ("\n".join(fact_lines) or "  (none)")
        + "\n\nGrounded observations:\n"
        + ("\n".join(insight_lines) or "  (none)")
        + "\n\nWrite the summary now."
    )
