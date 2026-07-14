import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents import (
    descriptive,
    diagnostic,
    general,
    predictive,
    prescriptive,
    responder,
    retriever,
    validator,
)
from app.agents.context_filter import filter_context
from app.agents.router import route_dynamic
from app.internal.auth import require_internal_auth
from app.llm.client import get_llm_client

router = APIRouter(prefix="/internal/chat", tags=["internal-chat"], dependencies=[Depends(require_internal_auth)])

# The four *analytical modes* still exist as focused specialists — the router
# picks which of them are relevant to the question, they each compute their
# deterministic payload (facts / forecast / actions / citations), and those
# payloads flow into the Responder which composes the final LLM answer.
# Compared to the previous design, each analytical mode no longer runs its
# own LLM call — the Responder is the single visible LLM stage. That
# eliminates redundant round-trips and matches the spec's "one coherent
# response, not four disjointed outputs".
_ANALYSTS = {
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


@router.post("/stream")
async def stream(payload: ChatPayload):
    async def event_gen():
        # --- Stage 1: Retriever (deterministic + optional LIVE query) ----
        retrieved = await retriever.retrieve_async(payload.message, payload.context, model=payload.model)
        yield _sse("retriever_done", {
            "sources": retrieved["sources"],
            "db_field_count": len(retrieved["db_facts"]),
            "live_query_count": len(retrieved.get("live_facts", [])),
            "doc_chunk_count": len(retrieved["doc_facts"]),
            "coverage": retrieved["coverage"],
        })

        # --- Stage 2: Router (cached LLM) --------------------------------
        intents = await route_dynamic(payload.message, payload.context, payload.model)
        primary = _primary_intent(intents)

        # --- Stage 3: Analytical modes (deterministic payloads only) -----
        analyst_results: list[dict] = []
        for intent in intents:
            prep_fn = _ANALYSTS.get(intent, descriptive.prepare)
            scoped_context = filter_context(payload.context, payload.message, intent)
            prep = prep_fn(payload.message, scoped_context)
            analyst_results.append({"intent": intent, "payload": prep.payload})

        # --- Stage 4: Validator (deterministic) --------------------------
        validator_notes = validator.validate(payload.message, retrieved, analyst_results)
        yield _sse("validator_done", validator_notes)

        # --- Stage 5: Responder (single visible LLM call, streamed) ------
        # The frontend renders a single bubble per turn — tagged with the
        # primary analytical intent so existing INTENT_META styling still
        # works — that streams the responder's coherent answer.
        yield _sse("agents", {"intents": [primary]})
        yield _sse("agent_start", {"intent": primary})

        # Small-talk / off-domain path: bypass the analytics-grounded
        # responder (its SYSTEM prompt refuses to answer without facts) and
        # let the plain "general" agent reply conversationally. Everything
        # else runs the full retrieve → analyse → validate → respond
        # pipeline.
        if intents == ["general"]:
            resp_prep = general.prepare(payload.message, {})
        else:
            resp_prep = responder.prepare(payload.message, retrieved, analyst_results, validator_notes)
        llm = get_llm_client(payload.model)
        text_parts: list[str] = []
        async for delta in llm.compose_stream(resp_prep.system, resp_prep.prompt, resp_prep.offline_text):
            text_parts.append(delta)
            yield _sse("agent_delta", {"intent": primary, "text": delta})
        text = "".join(text_parts) or resp_prep.offline_text

        # `payload.details` carries the whole pipeline breakdown for the
        # frontend's expandable "Show reasoning" panel. Keeping it inside
        # payload preserves the existing SSE contract (one agent_done
        # frame closes the visible bubble).
        agent_done_payload = {
            "details": {
                "retriever": {
                    "db_facts": retrieved["db_facts"],
                    "live_facts": retrieved.get("live_facts", []),
                    "doc_facts": retrieved["doc_facts"],
                    "sources": retrieved["sources"],
                    "coverage": retrieved["coverage"],
                },
                "analysts": analyst_results,
                "validator": validator_notes,
                "intents_selected": intents,
            }
        }
        yield _sse("agent_done", {"intent": primary, "text": text, "payload": agent_done_payload})
        yield _sse("done", {"results": [{"intent": primary, "text": text, "payload": agent_done_payload}]})

    return StreamingResponse(event_gen(), media_type="text/event-stream")
