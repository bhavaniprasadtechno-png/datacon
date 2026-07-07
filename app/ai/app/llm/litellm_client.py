import logging
from typing import AsyncIterator

import litellm
from app.config import settings

logger = logging.getLogger("app.llm.litellm")


class LiteLLMClient:
    """Routes through LiteLLM's unified completion() API (SRS §2.2 "LLM
    Orchestrator") rather than a provider-specific SDK, so the active model
    is a single "provider/model" string — switching providers is a config
    (or per-request override) change, not a code change."""

    def __init__(self, model: str | None = None):
        self._model = model or settings.llm_model

    async def compose_stream(self, system: str, prompt: str, offline_text: str) -> AsyncIterator[str]:
        emitted = False
        for attempt in range(2):
            try:
                stream = await litellm.acompletion(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    # Reasoning models (e.g. Gemma's "-it" variants) spend a chunk of
                    # this budget on internal thinking tokens before the visible
                    # answer, so this needs headroom beyond a plain chat model.
                    # (Thinking arrives as delta.reasoning_content, a separate field
                    # — delta.content below is visible answer text only; verified
                    # against both gemini-2.5-flash and gemma-4-31b-it.)
                    max_tokens=1024,
                    stream=True,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        emitted = True
                        yield delta
                if emitted:
                    return
                # Stream completed without any visible content — treat like a
                # failed attempt (retry once, then offline fallback).
                logger.warning("LiteLLM stream attempt %d for model=%s produced no visible content", attempt, self._model)
            except Exception as e:
                if emitted:
                    # Partial answer already reached the client — stopping here
                    # beats splicing unrelated offline text onto a real answer.
                    logger.exception("LiteLLM stream for model=%s died mid-answer", self._model, exc_info=e)
                    return
                logger.warning("LiteLLM stream attempt %d failed for model=%s: %s", attempt, self._model, e)
        # Both attempts failed (or produced nothing) — a transient provider outage
        # (rate limit, timeout, etc.) shouldn't break the demo, but silently
        # swallowing this makes "why does chat look static" undiagnosable.
        logger.error("LiteLLM stream failed for model=%s; falling back to offline text", self._model)
        yield offline_text
