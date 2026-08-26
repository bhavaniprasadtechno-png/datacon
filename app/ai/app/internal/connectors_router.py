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
    sampleRows: list[list[str | None]] = []


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
    datasets = []
    for d in result.datasets:
        clean_sample_rows: list[list[str]] = []
        for row in (d.sample_rows or []):
            row_out = []
            for v in row:
                if v is None:
                    row_out.append("")
                elif isinstance(v, float) and (v != v):  # NaN check
                    row_out.append("")
                elif str(v).lower() in ("nan", "none", "null"):
                    row_out.append("")
                else:
                    row_out.append(str(v))
            clean_sample_rows.append(row_out)
        datasets.append(DatasetOut(name=d.name, columns=d.columns, rowCount=d.row_count, sampleRows=clean_sample_rows))
    return SyncOut(
        ok=result.ok,
        message=result.message,
        datasets=datasets,
    )

