import logging
from typing import Protocol
from app.config import settings

logger = logging.getLogger("app.llm.client")


class LLMClient(Protocol):
    async def compose(self, system: str, prompt: str, offline_text: str) -> str:
        """Turns a system prompt + a prompt describing already-computed facts
        into a natural-language paragraph. `offline_text` is a deterministic
        paragraph built from the same real facts, used verbatim by the offline
        client and as a safety-net fallback if the real provider call fails.
        Never invents facts — those come from real retrieval/computation
        upstream of this call, in both the online and offline paths."""
        ...


def get_llm_client() -> LLMClient:
    if settings.gemini_api_key:
        from app.llm.litellm_client import LiteLLMClient

        logger.info("Using LiteLLMClient (model=%s) — GEMINI_API_KEY is set.", settings.llm_model)
        return LiteLLMClient()
    from app.llm.offline_client import OfflineLLMClient

    logger.warning("Using OfflineLLMClient — GEMINI_API_KEY is not set, chat will use static templates.")
    return OfflineLLMClient()
