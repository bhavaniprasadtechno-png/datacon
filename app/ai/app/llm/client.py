import logging
from typing import Protocol
from app.config import settings
from app.llm.models import AVAILABLE_MODELS

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


def get_llm_client(model: str | None = None) -> LLMClient:
    if model and model not in AVAILABLE_MODELS:
        logger.warning("Rejected unknown model override %r, falling back to default.", model)
        model = None
    if settings.gemini_api_key:
        from app.llm.litellm_client import LiteLLMClient

        logger.info("Using LiteLLMClient (model=%s) — GEMINI_API_KEY is set.", model or settings.llm_model)
        return LiteLLMClient(model)
    from app.llm.offline_client import OfflineLLMClient

    logger.warning("Using OfflineLLMClient — GEMINI_API_KEY is not set, chat will use static templates.")
    return OfflineLLMClient()
