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
                    # Low temperature so the same computed facts produce the same
                    # written answer run over run, instead of a different wording
                    # (or a different emphasis of the numbers) each time.
                    temperature=0.3,
                    # Reasoning models spend a chunk of
                    # this budget on internal thinking tokens before the visible
                    # answer, so this needs headroom beyond a plain chat model.
                    # (Thinking arrives as delta.reasoning_content, a separate field
                    # — delta.content below is visible answer text only; verified
                    # against Qwen/Qwen3.7-Plus.)
                    max_tokens=3072,
                    stream=True,
                    # Bounded so a slow/hanging provider call fails over to the
                    # retry loop (and ultimately the offline_text fallback) below
                    # instead of hanging until the API gateway's own timeout kills
                    # the connection with no answer at all.
                    timeout=20,
                )
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = getattr(chunk.choices[0].delta, "content", None)
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
