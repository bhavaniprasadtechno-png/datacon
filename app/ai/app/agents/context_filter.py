"""Question- and intent-aware context filtering.

The chat controller currently ships the *full* metrics blob to every agent
on every turn — revenueHistory, regionRevenue, ticketDaily, churnSnapshot,
topIncidentTitle, model, horizonMonths — regardless of what the user asked.
That has two problems:

  1. Agents (and the LLM behind them) drown in irrelevant data. Asking
     "why did tickets spike?" shouldn't dump 18 months of revenue at the
     model.
  2. Predictive's payload was being set to the raw metrics blob, so the
     forecast visualization on the UI rendered nonsense.

`filter_context` returns a copy of the context narrowed to the topics the
question actually touches + the intent's natural scope. It's a heuristic
based on keywords over the field names — cheap, deterministic, and never
removes something a keyword directly asks for.
"""
from __future__ import annotations

import re
from typing import Any

# Which context fields each *topic* keyword pattern implies. A field is kept
# if ANY of its associated patterns matches the question.
_TOPIC_FIELDS: dict[str, re.Pattern[str]] = {
    "revenueHistory": re.compile(r"revenue|sales|growth|top.?line|arr|mrr|income", re.I),
    "regionRevenue": re.compile(r"region|geograph|country|market|territor|quarter", re.I),
    "ticketDaily": re.compile(r"ticket|support|incident|volume|issue|case", re.I),
    "churnSnapshot": re.compile(r"churn|retention|at.?risk|attrition|cancell", re.I),
    "topIncidentTitle": re.compile(r"incident|outage|top issue|top document|report", re.I),
}

# Every intent gets these baseline fields regardless of question wording,
# because they're the minimum the agent needs to say anything sensible.
_INTENT_DEFAULTS: dict[str, tuple[str, ...]] = {
    "descriptive": ("revenueHistory", "regionRevenue", "churnSnapshot"),
    "diagnostic": ("ticketDaily", "topIncidentTitle", "churnSnapshot"),
    "predictive": ("revenueHistory", "model", "horizonMonths"),
    "prescriptive": ("churnSnapshot", "ticketDaily", "regionRevenue"),
    "general": (),
}

# Always-passthrough fields (control values, not data).
_ALWAYS = ("model", "horizonMonths")


def filter_context(context: dict[str, Any] | None, question: str, intent: str) -> dict[str, Any]:
    """Return a copy of ``context`` narrowed to fields relevant to the
    given question and intent. Missing fields are simply omitted."""
    if not context:
        return {}
    q = question or ""
    keep: set[str] = set(_ALWAYS)
    keep.update(_INTENT_DEFAULTS.get(intent, ()))
    for field, pattern in _TOPIC_FIELDS.items():
        if pattern.search(q):
            keep.add(field)
    # If the question mentions none of the tracked topics and the intent
    # has no defaults (general), return an empty dict rather than the full
    # blob — the general agent shouldn't pretend to know business data.
    if intent == "general" and not any(p.search(q) for p in _TOPIC_FIELDS.values()):
        return {}
    return {k: v for k, v in context.items() if k in keep}


def forecast_payload(context: dict[str, Any] | None) -> dict[str, Any]:
    """Payload shape the predictive UI card expects — never the raw metrics
    blob. Called by the predictive agent to build its structured payload."""
    if not context:
        return {}
    out: dict[str, Any] = {}
    if "revenueHistory" in context:
        out["history"] = context["revenueHistory"]
    if "model" in context:
        out["model"] = context["model"]
    if "horizonMonths" in context:
        out["horizonMonths"] = context["horizonMonths"]
    return out
