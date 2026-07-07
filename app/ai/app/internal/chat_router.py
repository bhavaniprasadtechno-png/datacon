import asyncio
import json
import random
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.internal.auth import require_internal_auth
from app.agents.router import route
from app.agents import descriptive, diagnostic, predictive, prescriptive
from app.llm.client import get_llm_client

router = APIRouter(prefix="/internal/chat", tags=["internal-chat"], dependencies=[Depends(require_internal_auth)])

_AGENTS = {
    "descriptive": descriptive.run,
    "diagnostic": diagnostic.run,
    "predictive": predictive.run,
    "prescriptive": prescriptive.run,
}


class ChatPayload(BaseModel):
    message: str
    context: dict
    model: str | None = None


def _tokenize(text: str) -> list[str]:
    """Reveals 3-6 characters per tick, matching the prototype's streaming-reveal UX exactly."""
    chunks = []
    i = 0
    while i < len(text):
        step = 3 + random.randint(0, 3)
        chunks.append(text[i : i + step])
        i += step
    return chunks


@router.post("/stream")
async def stream(payload: ChatPayload):
    intent = route(payload.message)
    agent_fn = _AGENTS[intent]
    result = await agent_fn(payload.message, payload.context, get_llm_client(payload.model))

    async def event_gen():
        yield f"event: intent\ndata: {json.dumps({'intent': intent})}\n\n"
        for chunk in _tokenize(result.text):
            yield f"event: token\ndata: {json.dumps({'text': chunk})}\n\n"
            await asyncio.sleep(0.024)
        yield f"event: done\ndata: {json.dumps({'intent': intent, 'text': result.text, 'payload': result.payload})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
