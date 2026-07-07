from app.agents.types import AgentPrep

SYSTEM = (
    "You are Datacon's descriptive analytics agent. Given real computed revenue-by-region "
    "figures, write one tight paragraph (3-4 sentences) summarizing them for a business "
    "audience. Do not invent numbers beyond what's provided."
)


def prepare(question: str, context: dict) -> AgentPrep:
    current = context["regionRevenue"]["current"]  # [{region, revenue}]
    previous = context["regionRevenue"]["previous"]

    current_sorted = sorted(current, key=lambda r: -r["revenue"])
    total_current = sum(r["revenue"] for r in current)
    total_previous = sum(r["revenue"] for r in previous)
    growth_pct = (total_current - total_previous) / total_previous * 100
    top_region = current_sorted[0]

    max_rev = current_sorted[0]["revenue"]
    bars = [
        {"label": r["region"], "value": f"${r['revenue']:.2f}M", "pct": round(r["revenue"] / max_rev * 90) + 10}
        for r in current_sorted
    ]

    region_parts = [f"{r['region']} at ${r['revenue']:.2f}M ({r['revenue'] / total_current * 100:.0f}%)" for r in current_sorted]
    region_desc = ", ".join(region_parts)
    region_sentence = region_parts[0] if len(region_parts) == 1 else f"{region_parts[0]}, followed by {', '.join(region_parts[1:])}"

    offline_text = (
        f"Revenue last quarter totaled ${total_current:.2f}M across four regions. "
        f"{region_sentence}. "
        f"Quarter-over-quarter growth was {'+' if growth_pct >= 0 else ''}{growth_pct:.1f}%, "
        f"driven mainly by {top_region['region']} enterprise renewals."
    )

    prompt = (
        f"Question: {question}\n\n"
        f"Computed facts:\n- Total revenue last quarter: ${total_current:.2f}M\n"
        f"- By region: {region_desc}\n- QoQ growth: {growth_pct:+.1f}%\n"
        f"- Leading region: {top_region['region']}"
    )

    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload={"bars": bars})
