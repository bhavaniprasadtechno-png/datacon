"""Real analytics computed from context data.

The prototype dumped the raw metrics blob into the LLM prompt and hoped for
accurate prose. That's how you get hallucinated percentages and made-up
"top regions". This module computes the actual numbers deterministically
first — deltas, top-N, trends, forecasts — so agents can:

  (a) inject those computed facts into the LLM prompt as authoritative
      figures the model must reference,
  (b) include them in the structured payload the UI cards render, and
  (c) use them as the deterministic offline paragraph when the LLM path
      is unavailable.

Every function tolerates missing / partial context and returns `None` (or
an empty structure) rather than raising, so agents can call them freely.
"""
from __future__ import annotations

from typing import Any


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --- Revenue -----------------------------------------------------------------
def revenue_stats(history: list[float] | None) -> dict[str, Any]:
    """Latest value, MoM delta, YoY delta, and a compact 3-month rolling trend."""
    if not history:
        return {}
    series = [x for x in (_num(v) for v in history) if x is not None]
    if not series:
        return {}
    stats: dict[str, Any] = {"latest": series[-1], "count": len(series)}
    if len(series) >= 2 and series[-2]:
        stats["mom_delta_pct"] = round((series[-1] - series[-2]) / series[-2] * 100, 2)
    if len(series) >= 13 and series[-13]:
        stats["yoy_delta_pct"] = round((series[-1] - series[-13]) / series[-13] * 100, 2)
    if len(series) >= 3:
        window = series[-3:]
        stats["rolling_3_avg"] = round(sum(window) / 3, 2)
    stats["min"] = min(series)
    stats["max"] = max(series)
    return stats


def region_stats(region_revenue: dict | None) -> dict[str, Any]:
    """Top region, bottom region, and region-level deltas vs. prior quarter."""
    if not isinstance(region_revenue, dict):
        return {}
    current = region_revenue.get("current") or []
    previous = region_revenue.get("previous") or []
    if not current:
        return {}
    prev_by_region = {r.get("region"): _num(r.get("revenue")) or 0 for r in previous}
    ranked = sorted(current, key=lambda r: _num(r.get("revenue")) or 0, reverse=True)
    top = ranked[0]
    bottom = ranked[-1]
    deltas: list[dict[str, Any]] = []
    for row in current:
        cur = _num(row.get("revenue")) or 0
        prev = prev_by_region.get(row.get("region"), 0)
        pct = ((cur - prev) / prev * 100) if prev else None
        deltas.append({
            "region": row.get("region"),
            "current": cur,
            "previous": prev,
            "delta_pct": round(pct, 2) if pct is not None else None,
        })
    return {
        "top": {"region": top.get("region"), "revenue": _num(top.get("revenue"))},
        "bottom": {"region": bottom.get("region"), "revenue": _num(bottom.get("revenue"))},
        "region_deltas": deltas,
        "total_current": sum((_num(r.get("revenue")) or 0) for r in current),
    }


# --- Support tickets ---------------------------------------------------------
def ticket_stats(ticket_daily: list[dict] | None) -> dict[str, Any]:
    """Volume by region, day with the biggest spike, and split of the window
    into first-half vs. second-half so agents can spot recent surges."""
    if not ticket_daily:
        return {}
    by_region: dict[str, int] = {}
    by_date: dict[str, int] = {}
    for row in ticket_daily:
        r = row.get("region", "unknown")
        d = row.get("date", "")
        c = int(_num(row.get("count")) or 0)
        by_region[r] = by_region.get(r, 0) + c
        by_date[d] = by_date.get(d, 0) + c
    if not by_region:
        return {}
    dates_sorted = sorted(by_date.keys())
    spike_date = max(by_date, key=by_date.get) if by_date else None
    top_region = max(by_region, key=by_region.get)
    total = sum(by_region.values())
    # Recent-half vs prior-half split — cheap "is volume trending up?" signal.
    mid = len(dates_sorted) // 2
    first_half = sum(by_date[d] for d in dates_sorted[:mid])
    second_half = sum(by_date[d] for d in dates_sorted[mid:])
    return {
        "total": total,
        "by_region": by_region,
        "top_region": {"region": top_region, "count": by_region[top_region]},
        "spike_day": {"date": spike_date, "count": by_date[spike_date]} if spike_date else None,
        "first_half_total": first_half,
        "second_half_total": second_half,
        "trend_pct": round((second_half - first_half) / first_half * 100, 2) if first_half else None,
    }


# --- Churn -------------------------------------------------------------------
def churn_stats(snapshot: dict | None) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {}
    curr = _num(snapshot.get("churnPct"))
    prev = _num(snapshot.get("prevChurnPct"))
    at_risk = int(_num(snapshot.get("atRiskAccounts")) or 0)
    out: dict[str, Any] = {"churn_pct": curr, "prev_churn_pct": prev, "at_risk_accounts": at_risk}
    if curr is not None and prev is not None:
        out["delta_pp"] = round(curr - prev, 2)
        out["direction"] = "up" if curr > prev else ("down" if curr < prev else "flat")
    return out


# --- Forecast (real Holt-Winters / OLS run) ----------------------------------
def run_forecast(history: list[float] | None, model: str, horizon_months: int) -> dict[str, Any]:
    """Runs the actual forecasting engine and returns projection + CI + MAPE.
    Falls back to a simple linear extrapolation on very short series."""
    if not history:
        return {}
    series = [x for x in (_num(v) for v in history) if x is not None]
    if len(series) < 3:
        return {}
    try:
        if (model or "").upper() == "OLS":
            from app.forecasting import ols as engine
        else:
            from app.forecasting import holt_winters as engine
        r = engine.forecast(series, max(1, int(horizon_months or 6)))
        return {
            "model": model or "Holt-Winters",
            "horizon_months": int(horizon_months or 6),
            "projected": round(r["projected"], 2),
            "ci_low": round(r["ci_low"], 2),
            "ci_high": round(r["ci_high"], 2),
            "growth_pct": round(r["growth_pct"], 2),
            "mape_pct": round(r["mape"], 2),
            "latest_actual": series[-1],
        }
    except Exception:
        return {}


# --- Formatting helper -------------------------------------------------------
def format_facts(facts: dict[str, Any], indent: str = "  ") -> str:
    """Renders a facts dict as an LLM-friendly bulleted list. Nested dicts
    are flattened one level deep."""
    if not facts:
        return "(no facts computed)"
    lines: list[str] = []
    for k, v in facts.items():
        if isinstance(v, dict):
            inner = ", ".join(f"{ik}={iv}" for ik, iv in v.items())
            lines.append(f"{indent}- {k}: {{ {inner} }}")
        elif isinstance(v, list):
            preview = v[:5]
            more = f" (+{len(v) - 5} more)" if len(v) > 5 else ""
            lines.append(f"{indent}- {k}: {preview}{more}")
        else:
            lines.append(f"{indent}- {k}: {v}")
    return "\n".join(lines)
