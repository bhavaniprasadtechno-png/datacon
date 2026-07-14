"""Dynamic agent router.

The prototype used a hand-rolled regex to pick agents. That routes wrong the
moment a user phrases a question outside those exact keywords (e.g. "how are
we tracking vs last quarter", "walk me through the drop", "what's likely to
happen if we hold prices"). This module now routes in two layers:

  1. `route_dynamic(question, context)` — LLM classifier that reads the
     question AND a compact schema of the data actually available for this
     turn, and returns the set of agents most relevant to it.
  2. `route(question)` — deterministic regex fallback used when the LLM
     isn't configured (no GEMINI_API_KEY), fails, or when the caller wants
     a synchronous decision. Same signature/return shape as before, so
     existing callers keep working.

Both always return a non-empty list of valid intents.
"""
import json
import logging
import re

from app.config import settings

logger = logging.getLogger("app.agents.router")

VALID_INTENTS = ("descriptive", "diagnostic", "predictive", "prescriptive", "general")

# --- Regex fallback (kept from the prototype, slightly broadened) ------------
_PREDICTIVE = re.compile(
    r"forecast|predict|next\s+(quarter|month|year|week|two|few)|projection|will\s+be|"
    r"expect|likely|going to|trend|outlook|future",
    re.I,
)
_DIAGNOSTIC = re.compile(
    r"why|cause|caused|spike|drop|reason|driv|because|root|explain|analyz|"
    r"what happened|walk me through",
    re.I,
)
_PRESCRIPTIVE = re.compile(
    r"reduce|should|recommend|how do we|how can we|improve|cut |lower |action|"
    r"fix|optimi[sz]e|mitigat|plan|next step",
    re.I,
)
_DESCRIPTIVE = re.compile(
    r"how (are|is|did|were)|summari|overview|compare|top |bottom |show me|"
    r"list|breakdown|distribution|current|status",
    re.I,
)
_BUSINESS_CONTEXT = re.compile(
    r"revenue|sales|region|quarter|forecast|growth|churn|customer|account|ticket|support|billing|incident|"
    r"dashboard|metric|kpi|connector|dataset|table|document|upload|insight|trend|anomal|role|permission|user|"
    r"data|report|chart|analysis|analytics",
    re.I,
)


def route(text: str) -> list[str]:
    """Deterministic regex router — used as a synchronous fallback."""
    if not text.strip():
        return ["descriptive"]

    if not _BUSINESS_CONTEXT.search(text):
        return ["general"]

    intents: list[str] = []
    if _PREDICTIVE.search(text):
        intents.append("predictive")
    if _DIAGNOSTIC.search(text):
        intents.append("diagnostic")
    if _PRESCRIPTIVE.search(text):
        intents.append("prescriptive")
    if _DESCRIPTIVE.search(text) and not intents:
        intents.append("descriptive")
    return intents or ["descriptive"]


# --- Dynamic LLM router -------------------------------------------------------
_ROUTER_SYSTEM = (
    "You are the intent router for Datacon, an analytics assistant. "
    "Given a user question and a summary of the data currently available, "
    "decide which analytics agents should answer it. Available agents:\n"
    "  - descriptive: summarise, compare, list, show current values or breakdowns.\n"
    "  - diagnostic:  explain WHY something happened, root causes, drivers.\n"
    "  - predictive:  forecast, project, estimate future values.\n"
    "  - prescriptive: recommend actions, next steps, mitigations, plans.\n"
    "  - general:     the question is NOT about the user's business data\n"
    "                 (small talk, definitions, unrelated topics).\n\n"
    "Rules:\n"
    "  * Return one or more agents when the question naturally covers "
    "multiple analytical modes (e.g. 'why did X spike and what should we do?' "
    "→ diagnostic + prescriptive).\n"
    "  * If the question is unrelated to the available data, return ['general'].\n"
    "  * Never invent agents; only pick from the list above.\n"
    "  * Reply ONLY with compact JSON of the form: "
    '{"intents": ["diagnostic", "prescriptive"]}'
)


def _summarise_context_schema(context: dict | None) -> str:
    """Compact, LLM-friendly description of what data is actually loaded
    for this chat turn. Sending the full metrics blob to the router wastes
    tokens; sending nothing means the router can't judge relevance. This
    lists only field names + a shape hint."""
    if not context:
        return "(no structured data attached to this turn)"
    parts: list[str] = []
    for key, value in context.items():
        if isinstance(value, list):
            parts.append(f"- {key}: list ({len(value)} items)")
        elif isinstance(value, dict):
            sub = ", ".join(value.keys())
            parts.append(f"- {key}: object {{ {sub} }}")
        else:
            parts.append(f"- {key}: {type(value).__name__}")
    return "\n".join(parts)


def _parse_router_response(raw: str) -> list[str] | None:
    """Extract a valid intent list from the LLM's reply. Tolerates code
    fences and stray prose around the JSON."""
    if not raw:
        return None
    # Strip common markdown code fences.
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S)
    # Grab the first {...} block.
    match = re.search(r"\{.*\}", cleaned, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    intents = data.get("intents")
    if not isinstance(intents, list):
        return None
    picked = [i for i in intents if isinstance(i, str) and i.lower() in VALID_INTENTS]
    return [i.lower() for i in picked] or None


async def route_dynamic(question: str, context: dict | None, model: str | None = None) -> list[str]:
    """LLM-driven intent classification with regex fallback.

    Falls back to `route()` when:
      * GEMINI_API_KEY isn't set (offline mode),
      * the LLM call fails,
      * or the reply can't be parsed into a valid intent list.
    """
    fallback = route(question)
    if not settings.gemini_api_key:
        return fallback

    try:
        import litellm

        schema = _summarise_context_schema(context)
        user_prompt = (
            f"User question:\n{question}\n\n"
            f"Data available this turn:\n{schema}\n\n"
            'Respond with JSON only: {"intents": [...]}.'
        )
        response = await litellm.acompletion(
            model=model or settings.llm_model,
            messages=[
                {"role": "system", "content": _ROUTER_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=128,
            temperature=0,
        )
        raw = response.choices[0].message.content or ""
    except Exception as e:
        logger.warning("Dynamic router LLM call failed (%s); using regex fallback.", e)
        return fallback

    picked = _parse_router_response(raw)
    if not picked:
        logger.info("Dynamic router reply unparseable (%r); using regex fallback.", raw[:120])
        return fallback
    return picked
