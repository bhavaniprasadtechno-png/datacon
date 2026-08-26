import base64
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.internal.auth import require_internal_auth
from app.rag.chunking import extract_pdf_text, extract_text_file, chunk_words, parse_csv, parse_tabular_data
from app.rag.chroma_store import index_chunks, delete_document
from app.query_engine import snapshot_store, semantic_model

logger = logging.getLogger("app.internal.documents_router")

router = APIRouter(prefix="/internal/documents", tags=["internal-documents"], dependencies=[Depends(require_internal_auth)])


class IngestPayload(BaseModel):
    documentId: str
    title: str
    filename: str
    contentBase64: str
    docType: str  # "pdf" | "csv" | "xlsx" | "xls" | "txt" | "md"


class IngestOut(BaseModel):
    ok: bool
    message: str
    chunkCount: int | None = None
    rowCount: int | None = None
    colCount: int | None = None
    columns: list[str] | None = None
    sampleRows: list[list[str]] | None = None


@router.post("/ingest", response_model=IngestOut)
async def ingest(payload: IngestPayload):
    doc_type = payload.docType.lower()
    fn_lower = payload.filename.lower()
    is_tabular = doc_type in ("csv", "xlsx", "xls", "excel") or fn_lower.endswith((".csv", ".xlsx", ".xls"))
    logger.info("[Ingest] Starting ingestion for document ID: %s, filename: '%s', type: %s", payload.documentId, payload.filename, doc_type)
    data = base64.b64decode(payload.contentBase64)
    try:
        if is_tabular:
            file_ext = payload.filename.rsplit(".", 1)[-1] if "." in payload.filename else doc_type
            logger.info("[Ingest] Decoding and parsing tabular (%s) data for document ID: %s", file_ext, payload.documentId)
            columns, row_count, sample_rows, df = parse_tabular_data(data, file_ext=file_ext)
            table_name = f"csv_{payload.documentId}"
            logger.info("[Ingest] Tabular data parsed. Rows: %s, Columns: %s. Loading into DuckDB cache...", row_count, len(columns))
            snapshot_store.load_dataset(table_name, df)

            try:
                all_tables = snapshot_store.get_all_tables(sample_size=1000)
                all_tables.update({table_name: df})
                yaml_name, yaml_path = semantic_model.generate_and_save_semantic_model(
                    tables_dict=all_tables,
                    dataset_name=payload.title or payload.filename,
                    source_id=f"doc_{payload.documentId}",
                    generated_by="datasource_upload_pipeline",
                )
                logger.info("[Ingest] Generated semantic model YAML for document ID %s: %s", payload.documentId, yaml_path)
            except Exception as se:
                logger.warning("[Ingest] Failed to generate semantic model YAML for document %s: %s", payload.documentId, se)


            logger.info("[Ingest] Ingestion completed successfully for tabular document ID: %s", payload.documentId)
            return IngestOut(
                ok=True,
                message=f"Parsed {row_count} rows.",
                rowCount=row_count,
                colCount=len(columns),
                columns=columns,
                sampleRows=sample_rows,
            )


        logger.info("[Ingest] Extracting text for unstructured document ID: %s", payload.documentId)
        if doc_type == "pdf":
            text = extract_pdf_text(data)
        else:
            text = extract_text_file(data)

        logger.info("[Ingest] Segmenting text into chunks for document ID: %s", payload.documentId)
        chunks = chunk_words(text)
        logger.info("[Ingest] Indexing %s chunks in ChromaDB for document ID: %s", len(chunks), payload.documentId)
        index_chunks(payload.documentId, payload.title, payload.filename, chunks)
        logger.info("[Ingest] Ingestion completed successfully for unstructured document ID: %s", payload.documentId)
        return IngestOut(ok=True, message=f"Indexed {len(chunks)} chunk(s).", chunkCount=len(chunks))
    except Exception as e:
        logger.exception("[Ingest] Ingestion failed for document ID: %s", payload.documentId)
        raise HTTPException(status_code=422, detail=f"Ingestion failed: {e}")


@router.delete("/{document_id}", response_model=IngestOut)
async def remove(document_id: str):
    logger.info("[Ingest] Removing document ID: %s from indexes", document_id)
    delete_document(document_id)
    logger.info("[Ingest] Dropping DuckDB cache prefix csv_%s if exists", document_id)
    snapshot_store.drop_datasets(f"csv_{document_id}")
    logger.info("[Ingest] Removal completed for document ID: %s", document_id)
    return IngestOut(ok=True, message="Removed from index.")

