import logging
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

    async def compose(self, system: str, prompt: str, offline_text: str) -> str:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                resp = await litellm.acompletion(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    # Reasoning models (e.g. Gemma's "-it" variants) spend a chunk of
                    # this budget on internal thinking tokens before the visible
                    # answer, so this needs headroom beyond a plain chat model.
                    max_tokens=1024,
                )
                content = resp.choices[0].message.content
                if content:
                    return content
                last_error = RuntimeError("empty completion content")
            except Exception as e:
                last_error = e
                logger.warning("LiteLLM call attempt %d failed for model=%s: %s", attempt, self._model, e)
        # Both attempts failed (or returned empty) — a transient provider outage
        # (rate limit, timeout, etc.) shouldn't break the demo, but silently
        # swallowing this makes "why does chat look static" undiagnosable.
        logger.exception("LiteLLM call failed for model=%s; falling back to offline text", self._model, exc_info=last_error)
        return offline_text
