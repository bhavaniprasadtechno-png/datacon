import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.internal.auth import require_internal_auth
from app.agents.router import route_dynamic
from app.agents.context_filter import filter_context
from app.agents import descriptive, diagnostic, predictive, prescriptive, general
from app.llm.client import get_llm_client

router = APIRouter(prefix="/internal/chat", tags=["internal-chat"], dependencies=[Depends(require_internal_auth)])

_AGENTS = {
    "descriptive": descriptive.prepare,
    "diagnostic": diagnostic.prepare,
    "predictive": predictive.prepare,
    "prescriptive": prescriptive.prepare,
    "general": general.prepare,
}


class ChatPayload(BaseModel):
    message: str
    context: dict
    model: str | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/stream")
async def stream(payload: ChatPayload):
    # Dynamic, LLM-driven routing keyed on both the question AND the shape
    # of data attached to this turn — falls back to a broadened regex router
    # when GEMINI_API_KEY isn't set or the LLM router fails.
    intents = await route_dynamic(payload.message, payload.context, payload.model)
    llm = get_llm_client(payload.model)

    async def event_gen():
        yield _sse("agents", {"intents": intents})
        results = []
        for intent in intents:
            agent = _AGENTS.get(intent, descriptive.prepare)
            # Narrow the context to what THIS intent + question actually
            # need, instead of dumping the full metrics blob into every
            # agent's prompt.
            scoped_context = filter_context(payload.context, payload.message, intent)
            prep = agent(payload.message, scoped_context)
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
