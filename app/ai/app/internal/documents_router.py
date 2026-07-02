import base64
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.internal.auth import require_internal_auth
from app.rag.chunking import extract_pdf_text, extract_text_file, chunk_words, parse_csv
from app.rag.chroma_store import index_chunks, delete_document

router = APIRouter(prefix="/internal/documents", tags=["internal-documents"], dependencies=[Depends(require_internal_auth)])


class IngestPayload(BaseModel):
    documentId: str
    title: str
    filename: str
    contentBase64: str
    docType: str  # "pdf" | "csv" | "txt" | "md"


class IngestOut(BaseModel):
    ok: bool
    message: str
    chunkCount: int | None = None
    rowCount: int | None = None
    colCount: int | None = None


@router.post("/ingest", response_model=IngestOut)
async def ingest(payload: IngestPayload):
    doc_type = payload.docType.lower()
    data = base64.b64decode(payload.contentBase64)
    try:
        if doc_type == "csv":
            columns, row_count = parse_csv(data)
            return IngestOut(ok=True, message=f"Parsed {row_count} rows.", rowCount=row_count, colCount=len(columns))

        if doc_type == "pdf":
            text = extract_pdf_text(data)
        else:
            text = extract_text_file(data)

        chunks = chunk_words(text)
        index_chunks(payload.documentId, payload.title, payload.filename, chunks)
        return IngestOut(ok=True, message=f"Indexed {len(chunks)} chunk(s).", chunkCount=len(chunks))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Ingestion failed: {e}")


@router.delete("/{document_id}", response_model=IngestOut)
async def remove(document_id: str):
    delete_document(document_id)
    return IngestOut(ok=True, message="Removed from index.")
