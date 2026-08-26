"""Shared helpers for the object-storage connector drivers (S3, Azure Blob, GCS):
which object keys are readable tabular data, what dataset name to give them, and
how to parse their bytes. Listing and auth differ per cloud and stay in each driver.
"""
import io

import pandas as pd

SUPPORTED_EXTENSIONS = (".csv", ".parquet", ".json", ".xlsx", ".xls")

# ponytail: fixed ceiling, bump if a legitimate object needs to be larger
MAX_OBJECT_BYTES = 50_000_000
ROW_CAP = 20_000


def is_data_object(key: str) -> bool:
    if key.endswith("/"):
        return False
    return key.lower().endswith(SUPPORTED_EXTENSIONS)


def clean_prefix(prefix: str, bucket: str = "") -> str:
    if not prefix:
        return ""
    p = prefix.strip()
    # Strip protocol prefixes like s3://, gs://, gcs://, https://, etc.
    for proto in ("s3://", "gs://", "gcs://", "wasbs://", "wasb://", "abfss://", "abfs://", "https://", "http://"):
        if p.startswith(proto):
            p = p[len(proto):]
            break
    # If the user pasted an S3/GCS URL containing domain/bucket name
    if "/" in p:
        domain_or_bucket, rest = p.split("/", 1)
        if bucket and domain_or_bucket.lower() in (
            bucket.lower(),
            f"{bucket.lower()}.s3.amazonaws.com",
            f"{bucket.lower()}.s3-{bucket.lower()}.amazonaws.com",
        ) or domain_or_bucket in ("storage.googleapis.com", "blob.core.windows.net", "s3.amazonaws.com"):
            p = rest
            if bucket and p.lower().startswith(f"{bucket.lower()}/"):
                p = p[len(bucket) + 1:]
        elif bucket and domain_or_bucket.lower() == bucket.lower():
            p = rest
    elif bucket and p.lower() == bucket.lower():
        p = ""

    return p.lstrip("/")


def dataset_name(key: str, prefix: str = "") -> str:
    cleaned = clean_prefix(prefix)
    if cleaned and key.startswith(cleaned):
        relative = key[len(cleaned):].strip("/")
    elif prefix and key.startswith(prefix):
        relative = key[len(prefix):].strip("/")
    else:
        # No (matching) prefix: fall back to basename-only, matching pre-fix behavior.
        relative = key.rsplit("/", 1)[-1]
    lower = relative.lower()
    for ext in SUPPORTED_EXTENSIONS:
        if lower.endswith(ext):
            relative = relative[: -len(ext)]
            break
    relative = relative.replace("/", "_")
    return relative or key.rsplit("/", 1)[-1]


def read_table(data: bytes, key: str) -> pd.DataFrame:
    buf = io.BytesIO(data)
    lower = key.lower()
    if lower.endswith(".parquet"):
        return pd.read_parquet(buf)
    if lower.endswith((".xlsx", ".xls")):
        return pd.read_excel(buf)
    if lower.endswith(".json"):
        try:
            return pd.read_json(buf)
        except ValueError:
            buf.seek(0)
            return pd.read_json(buf, lines=True)
    return pd.read_csv(buf)



def extract_sample_rows(df: pd.DataFrame, n: int = 5) -> list[list[str]]:
    sample = df.head(n)
    out = []
    for row in sample.itertuples(index=False, name=None):
        out.append([("" if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v)) for v in row])
    return out


def extract_rows(df: pd.DataFrame, cap: int = ROW_CAP) -> list[tuple]:
    capped = df.iloc[:cap]
    out = []
    for row in capped.itertuples(index=False, name=None):
        out.append(tuple(None if (v is None or (isinstance(v, float) and pd.isna(v))) else v for v in row))
    return out
