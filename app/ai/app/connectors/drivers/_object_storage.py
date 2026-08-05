"""Shared helpers for the object-storage connector drivers (S3, Azure Blob, GCS):
which object keys are readable tabular data, what dataset name to give them, and
how to parse their bytes. Listing and auth differ per cloud and stay in each driver.
"""
import io

import pandas as pd

SUPPORTED_EXTENSIONS = (".csv", ".parquet", ".json")


def is_data_object(key: str) -> bool:
    if key.endswith("/"):
        return False
    return key.lower().endswith(SUPPORTED_EXTENSIONS)


def dataset_name(key: str) -> str:
    base = key.rsplit("/", 1)[-1]
    lower = base.lower()
    for ext in SUPPORTED_EXTENSIONS:
        if lower.endswith(ext):
            return base[: -len(ext)]
    return base


def read_table(data: bytes, key: str) -> pd.DataFrame:
    buf = io.BytesIO(data)
    lower = key.lower()
    if lower.endswith(".parquet"):
        return pd.read_parquet(buf)
    if lower.endswith(".json"):
        return pd.read_json(buf)
    return pd.read_csv(buf)
