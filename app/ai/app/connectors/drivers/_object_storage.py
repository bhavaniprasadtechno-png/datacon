"""Shared helpers for the object-storage connector drivers (S3, Azure Blob, GCS):
which object keys are readable tabular data, what dataset name to give them, and
how to parse their bytes. Listing and auth differ per cloud and stay in each driver.
"""
import io

import pandas as pd

SUPPORTED_EXTENSIONS = (".csv", ".parquet", ".json")

# ponytail: fixed ceiling, bump if a legitimate object needs to be larger
MAX_OBJECT_BYTES = 50_000_000


def is_data_object(key: str) -> bool:
    if key.endswith("/"):
        return False
    return key.lower().endswith(SUPPORTED_EXTENSIONS)


def dataset_name(key: str, prefix: str = "") -> str:
    if prefix and key.startswith(prefix):
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
    if lower.endswith(".json"):
        try:
            return pd.read_json(buf)
        except ValueError:
            buf.seek(0)
            return pd.read_json(buf, lines=True)
    return pd.read_csv(buf)
