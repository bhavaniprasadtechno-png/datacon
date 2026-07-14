"""Responder — stage 4 of the multi-agent pipeline.

Given the retriever facts, per-analyst computed payloads, and validator
notes, the Responder composes ONE coherent user-facing answer. This is
the ONLY stage that calls the LLM for prose in the pipeline — the
analytical modes contribute their deterministic computed facts (revenue
deltas, forecast values, ranked actions, doc citations) as authoritative
inputs the responder must cite verbatim.

Design choices:
  * Cites source labels ("from DB: revenue_metrics", "from Doc: Q3.pdf")
    inline so the user can verify the answer.
  * If validator flagged conflicts, the responder must surface BOTH
    values and label the discrepancy — never silently pick one.
  * If validator flagged gaps ("no revenue history retrieved"), the
    responder must say the data isn't available rather than invent one.
  * When the LLM is unavailable, an offline deterministic template
    synthesises the same information from the pipeline outputs.
"""
from __future__ import annotations

import json
from typing import Any

from app.agents.types import AgentPrep


SYSTEM = (
    "You are Datacon's final Responder in a multi-agent pipeline.\n"
    "Upstream agents have already:\n"
    "  1. Retrieved facts from the connected database and uploaded documents.\n"
    "  2. Computed analytics (deltas, forecasts, ranked actions, citations).\n"
    "  3. Validated the data for conflicts and gaps.\n"
    "Your job is to compose ONE coherent, plain-language answer for the user.\n\n"
    "RULES (all must be followed):\n"
    "  * Only cite numbers that appear in the RETRIEVED FACTS or ANALYST PAYLOADS below. "
    "Do NOT invent any figure.\n"
    "  * Cite the source of each data-derived claim inline, e.g. "
    "\"(from DB: revenue_metrics)\" or \"(from Doc: Q3_sales.pdf)\".\n"
    "  * If VALIDATOR flagged a conflict, present BOTH values and clearly say they disagree.\n"
    "  * If VALIDATOR flagged a gap (no data), say so explicitly instead of guessing.\n"
    "  * If a document supports a claim, add a bracket citation like [1] pointing to the "
    "matching Doc entry.\n"
    "  * End with a compact \"Sources\" line listing the DB tables + documents actually used.\n"
    "  * Keep the answer scannable: short paragraphs, ≤ 220 words unless the user asked for a full report."
)


def _facts_snippet(retrieved: dict) -> str:
    """Compact rendering of retriever output for the prompt."""
    lines: list[str] = []
    for f in retrieved.get("db_facts", []):
        lines.append(f"  - DB[{f['source']}].{f['field']} ({f['shape']}) = {json.dumps(f['value'], default=str)[:400]}")
    for d in retrieved.get("doc_facts", []):
        lines.append(f"  - Doc[{d['id']}] {d['documentTitle']} ({d['filename']}, chunk {d['chunkIndex']}): "
                     f"\"{d['snippet'][:220]}\"")
    return "\n".join(lines) or "  (no facts retrieved)"


def _analyst_snippet(results: list[dict]) -> str:
    if not results:
        return "  (no analytical modes ran)"
    lines: list[str] = []
    for r in results:
        payload_str = json.dumps(r.get("payload") or {}, default=str)[:600]
        lines.append(f"  - {r['intent']}: {payload_str}")
    return "\n".join(lines)


def _validator_snippet(v: dict) -> str:
    parts: list[str] = []
    if v.get("conflicts"):
        parts.append(f"  CONFLICTS ({len(v['conflicts'])}):")
        for c in v["conflicts"][:5]:
            parts.append(f"    - {c['note']}")
    if v.get("gaps"):
        parts.append("  GAPS:")
        for g in v["gaps"]:
            parts.append(f"    - {g}")
    if v.get("freshness_notes"):
        parts.append("  FRESHNESS:")
        for f in v["freshness_notes"]:
            parts.append(f"    - {f}")
    return "\n".join(parts) or "  (no issues flagged)"


def prepare(question: str, retrieved: dict, analyst_results: list[dict], validator_notes: dict) -> AgentPrep:
    prompt = f"""User Question:
{question}

RETRIEVED FACTS (authoritative — cite by source when quoted):
{_facts_snippet(retrieved)}

ANALYST PAYLOADS (deterministic computations from the facts above):
{_analyst_snippet(analyst_results)}

VALIDATOR NOTES (must be reflected in the answer):
{_validator_snippet(validator_notes)}

Compose the final answer. Cite sources inline (DB tables / Doc titles).
If there is a conflict, present both values. If there is a gap, say so.
End with a "Sources:" line.
"""
    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text=_offline_answer(question, retrieved, analyst_results, validator_notes),
        payload={},
    )


# --- Offline deterministic composer -----------------------------------------
def _offline_answer(question: str, retrieved: dict, analyst_results: list[dict], v: dict) -> str:
    """When the LLM is unreachable, still emit a coherent, source-cited
    summary built from the deterministic pipeline outputs. Ensures the
    chat bubble is never blank."""
    parts: list[str] = []
    # Lead line — assemble the primary claim from the strongest analyst.
    lead: str | None = None
    for r in analyst_results:
        payload = r.get("payload") or {}
        facts = payload.get("facts") or {}
        rev = facts.get("revenue") or {}
        forecast = payload.get("forecast") or {}
        actions = payload.get("actions") or []
        citations = payload.get("citations") or []
        if forecast:
            lead = (
                f"Forecast ({forecast.get('model', 'Holt-Winters')}, "
                f"{forecast.get('horizon_months', 6)}-month horizon): projected "
                f"{forecast.get('projected'):,.2f} "
                f"(95% CI {forecast.get('ci_low'):,.2f}–{forecast.get('ci_high'):,.2f}, "
                f"{forecast.get('growth_pct'):+.1f}% vs latest {forecast.get('latest_actual')}) "
                "(from DB: revenue_metrics)."
            )
            break
        if rev.get("latest") is not None:
            lead = (
                f"Latest revenue: {rev['latest']:,.2f}"
                + (f" ({rev.get('mom_delta_pct'):+.1f}% MoM)" if "mom_delta_pct" in rev else "")
                + " (from DB: revenue_metrics)."
            )
            break
        if actions:
            lead = f"{actions[0]['action']} — {actions[0]['rationale']} (from DB: multiple tables)."
            break
        if citations:
            lead = f"Retrieved evidence in {citations[0]['documentTitle']} (from Doc)."
            break
    if lead:
        parts.append(lead)

    # Follow-up numbers from any other analysts.
    for r in analyst_results:
        payload = r.get("payload") or {}
        actions = payload.get("actions") or []
        for a in actions[:3]:
            parts.append(f"- {a['action']}: {a['rationale']}")

    # Validator surfacing.
    for c in (v.get("conflicts") or [])[:3]:
        parts.append(f"⚠ CONFLICT: {c['note']}")
    for g in (v.get("gaps") or [])[:3]:
        parts.append(f"⚠ GAP: {g}")

    # Sources line.
    sources = retrieved.get("sources") or []
    if sources:
        parts.append("Sources: " + ", ".join(sources[:6]))

    return "\n".join(parts) or (
        "I couldn't retrieve enough data from either the connected database or "
        "the uploaded documents to answer that. Please connect a data source "
        "or upload a relevant file and try again."
    )
