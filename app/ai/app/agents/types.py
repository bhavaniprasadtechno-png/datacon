from dataclasses import dataclass
from typing import Any


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


@dataclass
class AgentResult:
    text: str
    payload: dict[str, Any]
