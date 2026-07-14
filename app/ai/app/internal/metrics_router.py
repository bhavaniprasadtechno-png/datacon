from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.internal.auth import require_internal_auth
from app.query_engine.executor import answer_question

router = APIRouter(prefix="/internal/metrics", tags=["internal-metrics"], dependencies=[Depends(require_internal_auth)])


class MetricsQueryPayload(BaseModel):
    question: str


class MetricsQueryOut(BaseModel):
    ok: bool
    columns: list[str]
    rows: list[list[Any]]
    message: str


def _stringify(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, bool, str)):
        return value
    return str(value)


@router.post("/query", response_model=MetricsQueryOut)
async def query(payload: MetricsQueryPayload):
    result = await answer_question(payload.question)
    return MetricsQueryOut(
        ok=result.ok,
        columns=result.columns,
        rows=[[_stringify(v) for v in row] for row in result.rows],
        message=result.message,
    )
