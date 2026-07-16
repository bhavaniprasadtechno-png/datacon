"""Validator — stage 3 of the multi-agent pipeline.

Per the system prompt spec:

  "If the same fact appears in both the database and an uploaded file and
   they conflict, flag the discrepancy instead of silently picking one."

This stage takes the retriever output and the per-analyst computed facts
and looks for:

  * Conflicts — a numeric value that appears in a document snippet AND in
    the DB facts, but disagrees. The user must be told BOTH values.
  * Gaps — the question implies data the retriever didn't find in either
    source (e.g. "forecast next quarter" but no revenueHistory).
  * Freshness — DB fields present but empty/stale.

Deterministic (no LLM). Returns structured notes that the responder must
surface in the final answer.
"""
from __future__ import annotations

import re
from typing import Any


# Numbers with 1-4 digits + optional decimal — the shapes actually seen in
# document snippets (e.g. "revenue grew to 6.2M", "churn 4.8%"). Larger
# free-form numbers (page footers, boilerplate IDs) are ignored to avoid
# false positives.
_NUMBER_RE = re.compile(r"(?<![\w.])(\d{1,4}(?:\.\d{1,3})?)(?![\w])")


def _collect_db_numbers(db_facts: list[dict]) -> dict[str, float]:
    """Flatten DB facts into `path -> float` for cross-checking."""
    out: dict[str, float] = {}

    def walk(prefix: str, v: Any) -> None:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[prefix] = float(v)
        elif isinstance(v, dict):
            for k, iv in v.items():
                walk(f"{prefix}.{k}" if prefix else k, iv)
        elif isinstance(v, list):
            for i, iv in enumerate(v):
                walk(f"{prefix}[{i}]", iv)

    for f in db_facts:
        walk(f["field"], f["value"])
    return out


def _extract_doc_numbers(doc_facts: list[dict]) -> list[tuple[float, dict]]:
    """Every number in each doc snippet, tagged with its source doc."""
    out: list[tuple[float, dict]] = []
    for d in doc_facts:
        for m in _NUMBER_RE.finditer(d.get("snippet") or ""):
            try:
                out.append((float(m.group(1)), d))
            except ValueError:
                continue
    return out


def _question_implies(question: str, keywords: tuple[str, ...]) -> bool:
    q = (question or "").lower()
    return any(k in q for k in keywords)


def validate(question: str, retrieved: dict, analyst_results: list[dict]) -> dict[str, Any]:
    """Return conflicts + gaps + freshness notes."""
    db_facts = retrieved.get("db_facts", [])
    doc_facts = retrieved.get("doc_facts", [])
    coverage = retrieved.get("coverage", {})

    conflicts: list[dict[str, Any]] = []
    db_numbers = _collect_db_numbers(db_facts)
    doc_numbers = _extract_doc_numbers(doc_facts)

    # A "conflict" fires when a DB number and a doc number are numerically
    # close (same order of magnitude, same integer part) but differ beyond
    # a small tolerance — that's the shape of a genuine disagreement (e.g.
    # revenue said as 6.2 in the DB and 6.5 in the doc). We keep the check
    # tight to avoid firing on unrelated numbers that happen to appear in
    # both sources.
    for db_path, db_val in db_numbers.items():
        for doc_val, doc in doc_numbers:
            if db_val == 0 or doc_val == 0:
                continue
            ratio = doc_val / db_val
            if 0.5 <= ratio <= 2.0 and abs(doc_val - db_val) / max(abs(db_val), 1e-9) > 0.05:
                conflicts.append({
                    "db_path": db_path,
                    "db_value": db_val,
                    "doc_value": doc_val,
                    "doc_title": doc.get("documentTitle"),
                    "doc_filename": doc.get("filename"),
                    "note": (
                        f"DB {db_path}={db_val} vs {doc.get('documentTitle')} snippet "
                        f"mentions {doc_val} (differs > 5%)."
                    ),
                })

    # Gaps — question implies data we didn't retrieve.
    gaps: list[str] = []
    if _question_implies(question, ("forecast", "predict", "project", "next quarter", "next month")):
        if "revenueHistory" in coverage.get("db_fields_missing", []):
            gaps.append("No revenue history retrieved — forecast cannot be grounded in real data.")
    if _question_implies(question, ("region", "geograph", "country")):
        if "regionRevenue" in coverage.get("db_fields_missing", []):
            gaps.append("No region revenue retrieved — regional analysis unavailable.")
    if _question_implies(question, ("churn", "retention")):
        if "churnSnapshot" in coverage.get("db_fields_missing", []):
            gaps.append("No churn snapshot retrieved — retention analysis unavailable.")

    # Freshness — if an analyst reported "empty" facts, flag it.
    freshness: list[str] = []
    for r in analyst_results:
        payload = r.get("payload") or {}
        facts = payload.get("facts") or {}
        for k, v in facts.items():
            if v == {} and k in ("revenue", "regions", "tickets", "churn"):
                freshness.append(f"{r.get('intent')} agent found no {k} data in the retrieved context.")

    return {
        "conflicts": conflicts,
        "gaps": gaps,
        "freshness_notes": freshness,
        "has_issues": bool(conflicts or gaps or freshness),
    }
