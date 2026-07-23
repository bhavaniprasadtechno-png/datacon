import asyncio
import random
from typing import AsyncIterator


class OfflineLLMClient:
    """Zero-secrets fallback: the deterministic paragraph passed in was already
    built from real retrieved/computed data by the calling agent — this client
    just reveals it, so chat is fully usable with no TOGETHER_API_KEY set.
    Reveals 3-6 characters per tick to match the prototype's streaming UX."""

    async def compose_stream(self, system: str, prompt: str, offline_text: str) -> AsyncIterator[str]:
        i = 0
        while i < len(offline_text):
            step = 3 + random.randint(0, 3)
            yield offline_text[i : i + step]
            i += step
            await asyncio.sleep(0.024)
