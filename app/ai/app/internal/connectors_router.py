from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.internal.auth import require_internal_auth
from app.connectors import service as connectors_service

router = APIRouter(prefix="/internal/connectors", tags=["internal-connectors"], dependencies=[Depends(require_internal_auth)])


class ConnectorPayload(BaseModel):
    engine: str
    config: dict
    secrets: dict
    connectorId: str | None = None


class DatasetOut(BaseModel):
    name: str
    columns: list[str]
    rowCount: int
    sampleRows: list[list[str]]


class TestOut(BaseModel):
    ok: bool
    message: str


class SyncOut(BaseModel):
    ok: bool
    message: str
    datasets: list[DatasetOut]


@router.post("/test", response_model=TestOut)
async def test_connector(payload: ConnectorPayload):
    result = connectors_service.test_connection(payload.engine, payload.config, payload.secrets)
    return TestOut(ok=result.ok, message=result.message)


@router.post("/sync", response_model=SyncOut)
async def sync_connector(payload: ConnectorPayload):
    result = connectors_service.sync_connector(payload.engine, payload.config, payload.secrets, payload.connectorId)
    return SyncOut(
        ok=result.ok,
        message=result.message,
        datasets=[DatasetOut(name=d.name, columns=d.columns, rowCount=d.row_count, sampleRows=d.sample_rows) for d in result.datasets],
    )
