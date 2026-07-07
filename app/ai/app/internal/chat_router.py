import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.internal.auth import require_internal_auth
from app.agents.router import route
from app.agents import descriptive, diagnostic, predictive, prescriptive
from app.llm.client import get_llm_client

router = APIRouter(prefix="/internal/chat", tags=["internal-chat"], dependencies=[Depends(require_internal_auth)])

_AGENTS = {
    "descriptive": descriptive.prepare,
    "diagnostic": diagnostic.prepare,
    "predictive": predictive.prepare,
    "prescriptive": prescriptive.prepare,
}


class ChatPayload(BaseModel):
    message: str
    context: dict
    model: str | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/stream")
async def stream(payload: ChatPayload):
    intents = route(payload.message)
    llm = get_llm_client(payload.model)

    async def event_gen():
        # Upfront agent assignment (SRS Fig. 2 step 3), then one sequential
        # pass per assigned agent (Fig. 2's "For Each Assigned Agent Type"
        # loop), each streaming true LLM deltas as they're generated rather
        # than replaying a completed answer.
        yield _sse("agents", {"intents": intents})
        results = []
        for intent in intents:
            prep = _AGENTS[intent](payload.message, payload.context)
            yield _sse("agent_start", {"intent": intent})
            text_parts: list[str] = []
            async for delta in llm.compose_stream(prep.system, prep.prompt, prep.offline_text):
                text_parts.append(delta)
                yield _sse("agent_delta", {"intent": intent, "text": delta})
            text = "".join(text_parts) or prep.offline_text
            result = {"intent": intent, "text": text, "payload": prep.payload}
            results.append(result)
            yield _sse("agent_done", result)
        yield _sse("done", {"results": results})

    return StreamingResponse(event_gen(), media_type="text/event-stream")
