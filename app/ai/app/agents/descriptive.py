from app.agents.analytics import (
    format_facts,
    region_stats,
    revenue_stats,
    churn_stats,
    ticket_stats,
)
from app.agents.types import AgentPrep
from app.query_engine.executor import answer_question

SYSTEM = (
    "You are Datacon's descriptive analytics agent. Given a real query result table, "
    "answer the user's question about it in one tight paragraph (3-4 sentences) for a "
    "business audience. Do not invent numbers beyond what's provided."
)


def _stringify_row(row: list) -> list:
    return [v if v is None or isinstance(v, (int, float, bool, str)) else str(v) for v in row]


async def prepare(question: str) -> AgentPrep:
    result = await answer_question(question)

    if not result.ok:
        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\n{result.message}",
            offline_text=result.message,
            payload={"columns": [], "rows": []},
        )

    shown_rows = [_stringify_row(row) for row in result.rows[:20]]
    prompt = f"Question: {question}\n\nQuery result:\nColumns: {result.columns}\nRows: {shown_rows}"
    offline_text = f"Found {len(result.rows)} result row(s) for \"{question}\" across columns {', '.join(result.columns)}."

    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload={"columns": result.columns, "rows": shown_rows})
