import asyncio
import json
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings

from app.agents import (
    descriptive,
    diagnostic,
    general,
    predictive,
    prescriptive,
)
from app.agents.router import route_dynamic
from app.internal.auth import require_internal_auth
from app.llm.client import get_llm_client
from app.llm.models import AVAILABLE_MODELS

logger = logging.getLogger("app.internal.chat_router")

router = APIRouter(prefix="/internal/chat", tags=["internal-chat"], dependencies=[Depends(require_internal_auth)])

_ANALYSTS = {
    "descriptive": descriptive.prepare,
    "diagnostic": diagnostic.prepare,
    "predictive": predictive.prepare,
    "prescriptive": prescriptive.prepare,
    "general": general.prepare,
}


class ChatPayload(BaseModel):
    message: str
    model: str | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _primary_intent(intents: list[str]) -> str:
    """Pick the intent tag used on the visible chat bubble. `general`
    stays as-is (off-domain question); otherwise fall back to the first
    domain analyst so the bubble uses that pill/badge color."""
    if intents == ["general"]:
        return "general"
    for i in intents:
        if i in ("descriptive", "diagnostic", "predictive", "prescriptive"):
            return i
    return "descriptive"


@router.get("/models")
async def get_models():
    options = []
    for m in sorted(list(AVAILABLE_MODELS)):
        clean = m.split("/")[-1].replace("-", " ")
        options.append({
            "id": m,
            "label": clean,
            "description": f"Model: {m}"
        })
    return {"models": options}


@router.post("/stream")
async def stream(payload: ChatPayload):
    import os
    logger.info("[ChatRouter] Streaming chat request received: message='%s', model=%s", payload.message, payload.model)

    req_model = payload.model
    if not req_model or req_model not in AVAILABLE_MODELS:
        req_model = settings.llm_model

    model = req_model if req_model in AVAILABLE_MODELS else settings.llm_model

    async def event_gen():
        intents = await route_dynamic(payload.message, None, model)
        logger.info("[ChatRouter] Router routed message to intents: %s", intents)
        llm = get_llm_client(model)

        # Upfront agent assignment (SRS Fig. 2 step 3), then one sequential
        # pass per assigned agent (Fig. 2's "For Each Assigned Agent Type"
        # loop), each streaming true LLM deltas as they're generated rather
        # than replaying a completed answer.
        logger.info("[ChatRouter] Emitting SSE 'agents' event with intents: %s", intents)
        yield _sse("agents", {"intents": intents})
        results = []
        for intent in intents:
            try:
                logger.info("[ChatRouter] Running agent for intent '%s'...", intent)
                prep = await _ANALYSTS[intent](payload.message, model)
                logger.info("[ChatRouter] Agent '%s' prepared. Emitting 'agent_start' event.", intent)
                yield _sse("agent_start", {"intent": intent})

                # Stream the dynamic LLM output from the specialized agent if available
                if prep.payload and prep.payload.get("insightsText"):
                    dynamic_text = str(prep.payload["insightsText"]).strip()
                    logger.info("[ChatRouter] Streaming dynamic LLM insights (%d chars) for agent '%s'...", len(dynamic_text), intent)
                    chunk_size = 12
                    for i in range(0, len(dynamic_text), chunk_size):
                        delta = dynamic_text[i : i + chunk_size]
                        yield _sse("agent_delta", {"intent": intent, "text": delta})
                        await asyncio.sleep(0.005)
                    text = dynamic_text
                else:
                    logger.info("[ChatRouter] Initiating LLM compose stream for agent '%s'...", intent)
                    text_parts: list[str] = []
                    async for delta in llm.compose_stream(prep.system, prep.prompt, prep.offline_text):
                        text_parts.append(delta)
                        yield _sse("agent_delta", {"intent": intent, "text": delta})
                    text = "".join(text_parts) or prep.offline_text

                logger.info("[ChatRouter] LLM stream finished for agent '%s'. Total response characters: %s. Emitting 'agent_done'.", intent, len(text))

                result = {"intent": intent, "text": text, "payload": prep.payload}
                results.append(result)
                yield _sse("agent_done", result)
            except Exception:
                # Never leak internal exception details to the client — log
                # the real error server-side, surface a safe status instead.
                logger.exception("[ChatRouter] Agent '%s' failed while streaming.", intent)
                yield _sse("error", {"intent": intent, "message": "Something went wrong while analyzing this question."})

        logger.info("[ChatRouter] All agents completed. Emitting 'done' SSE event.")
        yield _sse("done", {"results": results})

    return StreamingResponse(event_gen(), media_type="text/event-stream")