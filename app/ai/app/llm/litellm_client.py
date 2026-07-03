import logging
import litellm
from app.config import settings

logger = logging.getLogger("app.llm.litellm")


class LiteLLMClient:
    """Routes through LiteLLM's unified completion() API (SRS §2.2 "LLM
    Orchestrator") rather than a provider-specific SDK, so the active model
    is a single "provider/model" string in settings.llm_model — switching
    providers is a config change, not a code change."""

    def __init__(self):
        self._model = settings.llm_model

    async def compose(self, system: str, prompt: str, offline_text: str) -> str:
        try:
            resp = await litellm.acompletion(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
            )
            return resp.choices[0].message.content or offline_text
        except Exception:
            # A transient provider outage (rate limit, timeout, etc.) shouldn't break the demo,
            # but silently swallowing this makes "why does chat look static" undiagnosable —
            # log it so the real cause (bad key, quota, wrong model) shows up in server logs.
            logger.exception("LiteLLM call failed for model=%s; falling back to offline text", self._model)
            return offline_text
