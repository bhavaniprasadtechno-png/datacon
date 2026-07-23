import logging
from typing import AsyncIterator, Protocol
from app.config import settings
from app.llm.models import AVAILABLE_MODELS

logger = logging.getLogger("app.llm.client")


class LLMClient(Protocol):
    def compose_stream(self, system: str, prompt: str, offline_text: str) -> AsyncIterator[str]:
        """Streams a natural-language paragraph as text deltas, generated from
        a system prompt + a prompt describing already-computed facts.
        `offline_text` is a deterministic paragraph built from the same real
        facts, used by the offline client and as a safety-net fallback when
        the real provider fails before producing any visible content — the
        generator always yields *something*. Never invents facts — those come
        from real retrieval/computation upstream, in both paths."""
        ...


def get_llm_client(model: str | None = None) -> LLMClient:
    import os

    if model and model not in AVAILABLE_MODELS:
        logger.warning("Rejected unknown model override %r, falling back to default.", model)
        model = None
    if settings.is_llm_configured:
        active_model = model or settings.llm_model
        if settings.together_api_key or os.environ.get("TOGETHER_API_KEY") or "qwen" in active_model.lower():
            from app.llm.together_client import TogetherClient

            logger.info("Using TogetherClient (model=%s)", active_model)
            return TogetherClient(model)
        from app.llm.litellm_client import LiteLLMClient

        logger.info("Using LiteLLMClient (model=%s)", active_model)
        return LiteLLMClient(model)
    from app.llm.offline_client import OfflineLLMClient

    logger.warning("Using OfflineLLMClient — no LLM API key set, chat will use static templates.")
    return OfflineLLMClient()
