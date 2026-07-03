import logging
import httpx
from app.config import settings

logger = logging.getLogger("app.llm.gemini")

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiRestClient:
    """Calls Gemini's REST API directly via httpx (already a dependency used
    elsewhere) instead of routing through the `litellm` package. LiteLLM's
    own __init__ unconditionally imports its entire provider matrix
    (Anthropic handlers, the full OpenAI SDK/types, proxy types, GCS logging
    integration, etc.) just to reach one provider — measured at +134MB RSS
    on first use, which was OOM-killing this service on Render's free
    512MB plan the moment a real chat request landed (vs. ~5MB for this
    direct approach, since httpx is already loaded). Keeps the same
    "provider/model" string in settings.llm_model (still stripping a
    "gemini/" prefix if present) so switching *models* stays a config
    change — this only gives up switching to a *different provider*
    without a code change, which the memory budget doesn't allow for here."""

    def __init__(self):
        model = settings.llm_model
        self._model = model.split("/", 1)[1] if "/" in model else model

    async def compose(self, system: str, prompt: str, offline_text: str) -> str:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    resp = await client.post(
                        f"{_API_BASE}/{self._model}:generateContent",
                        params={"key": settings.gemini_api_key},
                        json={
                            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                            "systemInstruction": {"parts": [{"text": system}]},
                            # Reasoning models (e.g. Gemma's "-it" variants) spend a
                            # chunk of this budget on internal thinking tokens before
                            # the visible answer, so this needs headroom beyond a
                            # plain chat model.
                            "generationConfig": {"maxOutputTokens": 1024},
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                parts = data["candidates"][0]["content"]["parts"]
                # Reasoning models mark internal "thinking" parts with thought: true —
                # only the remaining part(s) are the actual visible answer.
                text = "".join(p["text"] for p in parts if not p.get("thought"))
                if text:
                    return text
                last_error = RuntimeError("empty completion content")
            except Exception as e:
                last_error = e
                logger.warning("Gemini call attempt %d failed for model=%s: %s", attempt, self._model, e)
        # Both attempts failed (or returned empty) — a transient provider outage
        # (rate limit, timeout, etc.) shouldn't break the demo, but silently
        # swallowing this makes "why does chat look static" undiagnosable.
        logger.exception("Gemini call failed for model=%s; falling back to offline text", self._model, exc_info=last_error)
        return offline_text
