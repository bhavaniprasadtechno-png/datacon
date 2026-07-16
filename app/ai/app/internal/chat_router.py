import json
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.internal.auth import require_internal_auth
from app.agents.router import route
from app.agents import descriptive, diagnostic, predictive, prescriptive
from app.llm.client import get_llm_client
from app.llm.models import AVAILABLE_MODELS

logger = logging.getLogger("app.internal.chat_router")

router = APIRouter(prefix="/internal/chat", tags=["internal-chat"], dependencies=[Depends(require_internal_auth)])

_AGENTS = {
    "descriptive": descriptive.prepare,
    "diagnostic": diagnostic.prepare,
    "predictive": predictive.prepare,
    "prescriptive": prescriptive.prepare,
}


class ChatPayload(BaseModel):
    message: str
    model: str | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/stream")
async def stream(payload: ChatPayload):
    logger.info("[ChatRouter] Streaming chat request received: message='%s', model=%s", payload.message, payload.model)
    intents = route(payload.message)
    logger.info("[ChatRouter] Router routed message to intents: %s", intents)
    # Validated once here so both the prose-composition client (compose_stream)
    # and each agent's SQL-generation call (generate_sql) see the same
    # resolved model — previously only compose_stream received the override,
    # so switching models in the UI silently never affected SQL generation.
    model = payload.model if payload.model in AVAILABLE_MODELS else None
    llm = get_llm_client(model)

    async def event_gen():
        # Upfront agent assignment (SRS Fig. 2 step 3), then one sequential
        # pass per assigned agent (Fig. 2's "For Each Assigned Agent Type"
        # loop), each streaming true LLM deltas as they're generated rather
        # than replaying a completed answer.
        logger.info("[ChatRouter] Emitting SSE 'agents' event with intents: %s", intents)
        yield _sse("agents", {"intents": intents})
        results = []
        for intent in intents:
            logger.info("[ChatRouter] Running agent for intent '%s'...", intent)
            prep = await _AGENTS[intent](payload.message, model)
            logger.info("[ChatRouter] Agent '%s' prepared. Emitting 'agent_start' event.", intent)
            yield _sse("agent_start", {"intent": intent})
            
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
            
        logger.info("[ChatRouter] All agents completed. Emitting 'done' SSE event.")
        yield _sse("done", {"results": results})

    return StreamingResponse(event_gen(), media_type="text/event-stream")

