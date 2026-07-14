from app.agents.analytics import (
    churn_stats,
    format_facts,
    region_stats,
    revenue_stats,
    ticket_stats,
)
from app.agents.types import AgentPrep
from app.rag.chroma_store import query as chroma_query

SYSTEM = (
    "You are Datacon's diagnostic analytics agent.\n"
    "You are given PRE-COMPUTED facts from real business data plus retrieved "
    "document excerpts. Your job is to explain the most likely causes of the "
    "pattern the user is asking about.\n"
    "Rules:\n"
    "  * Ground every causal claim either in a computed fact or a cited document.\n"
    "  * Cite documents inline as [1], [2] matching the numbered snippets below.\n"
    "  * If evidence is insufficient, say so plainly — do NOT fabricate causes.\n"
    "  * Keep to 2-3 short paragraphs unless the user asked for a full report."
)


def _compute(context: dict) -> dict:
    return {
        "revenue": revenue_stats(context.get("revenueHistory")),
        "regions": region_stats(context.get("regionRevenue")),
        "tickets": ticket_stats(context.get("ticketDaily")),
        "churn": churn_stats(context.get("churnSnapshot")),
    }


def _offline_diagnosis(question: str, facts: dict, citations: list[dict]) -> str:
    parts: list[str] = []
    tick = facts.get("tickets") or {}
    if tick.get("trend_pct") is not None and tick["trend_pct"] > 10:
        parts.append(
            f"Support-ticket volume rose {tick['trend_pct']:+.1f}% in the "
            f"second half of the window (from {tick['first_half_total']} to "
            f"{tick['second_half_total']}), concentrated in "
            f"{tick['top_region']['region']} — a likely driver of the pattern."
        )
    ch = facts.get("churn") or {}
    if ch.get("direction") == "up":
        parts.append(
            f"Churn moved {ch['delta_pp']:+.1f}pp to {ch['churn_pct']:.1f}%, "
            f"with {ch['at_risk_accounts']} accounts at risk — this typically "
            "correlates with revenue softness in the following quarter."
        )
    reg = facts.get("regions") or {}
    laggards = [
        d for d in (reg.get("region_deltas") or [])
        if d.get("delta_pct") is not None and d["delta_pct"] < 0
    ]
    if laggards:
        names = ", ".join(f"{d['region']} ({d['delta_pct']:+.1f}%)" for d in laggards[:3])
        parts.append(f"Regions declining vs. prior quarter: {names}.")
    if citations:
        titles = "; ".join(f"[{c['id']}] {c['documentTitle']}" for c in citations[:3])
        parts.append(f"Supporting evidence: {titles}.")
    if not parts:
        return (
            "The attached data doesn't show a clear driver for what you're asking about, "
            "and no supporting documents were retrieved. Try attaching related documents "
            "or narrowing the question to a specific metric and time window."
        )
    return " ".join(parts)


def prepare(question: str, context: dict) -> AgentPrep:
    hits = chroma_query(question, n_results=3)
    citations = [
        {
            "id": i + 1,
            "documentTitle": h["metadata"].get("title", h["metadata"].get("filename", "Untitled")),
            "filename": h["metadata"].get("filename", ""),
            "chunkIndex": h["metadata"].get("chunk_index", 0),
            "snippet": h["snippet"][:300],
        }
        for i, h in enumerate(hits)
    ]
    facts = _compute(context or {})
    citation_text = (
        "\n".join(f"[{c['id']}] {c['documentTitle']}: {c['snippet']}" for c in citations)
        if citations else "No relevant supporting documents were found."
    )
    prompt = f"""User Question:
{question}

COMPUTED FACTS (authoritative — use these exact numbers):
{format_facts({k: v for k, v in facts.items() if v})}

RETRIEVED DOCUMENTS (cite as [1], [2] where relevant):
{citation_text}

Explain the most likely causes of what the user is asking about. Only use
facts and citations above. If evidence is insufficient, say so plainly.
"""
    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text=_offline_diagnosis(question, facts, citations),
        payload={"facts": facts, "citations": citations},
    )
