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
