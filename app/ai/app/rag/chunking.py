"""Document text extraction + chunking, per the SRS: PDF/TXT/MD are split into
overlapping word chunks (480 words, 60 overlap) before vector indexing; CSVs
are loaded into a dataframe instead (they feed the Descriptive agent directly,
not the RAG pipeline).

Operates on in-memory bytes rather than a filesystem path: the API service and
this AI service run as separate processes (and in production, separate
containers with no shared disk), so the uploaded file's bytes are passed
directly over the wire rather than by a path only the API service can read.
"""
import io
import pandas as pd
from pypdf import PdfReader

CHUNK_SIZE_WORDS = 480
CHUNK_OVERLAP_WORDS = 60


def extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_text_file(data: bytes) -> str:
    return data.decode("utf-8", errors="ignore")


def chunk_words(text: str, size: int = CHUNK_SIZE_WORDS, overlap: int = CHUNK_OVERLAP_WORDS) -> list[str]:
    words = text.split()
    if not words:
        return []
    step = max(size - overlap, 1)
    chunks = []
    for start in range(0, len(words), step):
        chunk = words[start : start + size]
        if not chunk:
            break
        chunks.append(" ".join(chunk))
        if start + size >= len(words):
            break
    return chunks


PREVIEW_ROWS = 20


def parse_csv(data: bytes) -> tuple[list[str], int, list[list[str]], pd.DataFrame]:
    # keep_default_na=False: pandas' default na_values list includes plain
    # business tokens like "NA", "NULL", "N/A" — this app uses "NA" as the
    # North America region code throughout its own seed data, so without
    # this a region column full of "NA" silently becomes NaN.
    df = pd.read_csv(io.BytesIO(data), keep_default_na=False)
    columns = [str(c) for c in df.columns]
    sample_rows = df.head(PREVIEW_ROWS).astype(str).values.tolist()
    return columns, len(df), sample_rows, df
