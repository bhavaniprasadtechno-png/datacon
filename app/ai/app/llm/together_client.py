import logging
import os
from typing import AsyncIterator

from app.config import settings

logger = logging.getLogger("app.llm.together")


class TogetherClient:
    def __init__(self, model: str | None = None):
        if not model:
            self._model = settings.llm_model
        else:
            self._model = model

    async def compose_stream(self, system: str, prompt: str, offline_text: str) -> AsyncIterator[str]:
        emitted = False
        api_key = settings.together_api_key or os.environ.get("TOGETHER_API_KEY")
        
        for attempt in range(2):
            try:
                try:
                    from together import AsyncTogether

                    client = AsyncTogether(api_key=api_key)
                    response = await client.chat.completions.create(
                        model=self._model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.3,
                        max_tokens=3072,
                        stream=True,
                    )
                    async for chunk in response:
                        if not chunk.choices:
                            continue
                        delta = getattr(chunk.choices[0].delta, "content", None)
                        if delta:
                            emitted = True
                            yield delta
                    if emitted:
                        return
                except ImportError:
                    import litellm

                    model_name = self._model if "together" in self._model.lower() else f"together_ai/{self._model}"
                    stream = await litellm.acompletion(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.3,
                        max_tokens=3072,
                        stream=True,
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
                logger.warning("Together stream attempt %d for model=%s produced no visible content", attempt, self._model)
            except Exception as e:
                if emitted:
                    logger.exception("Together stream for model=%s died mid-answer", self._model, exc_info=e)
                    return
                logger.warning("Together stream attempt %d failed for model=%s: %s", attempt, self._model, e)
        logger.error("Together stream failed for model=%s; falling back to offline text", self._model)
        yield offline_text
