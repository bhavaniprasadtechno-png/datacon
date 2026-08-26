import logging

from app.connectors.types import TestResult, SyncResult, DatasetResult
from app.connectors.drivers._object_storage import is_data_object, dataset_name, read_table, clean_prefix, extract_sample_rows, extract_rows, MAX_OBJECT_BYTES, ROW_CAP

OBJECT_CAP = 200  # ponytail: fixed page size, paginate if a container needs more matching objects than this

logger = logging.getLogger("app.connectors.drivers.azure")


def _missing_required(config: dict, secrets: dict) -> str | None:
    if not config.get("account") or not config.get("container") or not secrets.get("connectionString"):
        return "Storage account name, container name and connection string are required."
    return None


def _container_client(config: dict, secrets: dict):
    from azure.storage.blob import BlobServiceClient

    service_client = BlobServiceClient.from_connection_string(secrets.get("connectionString"))
    return service_client.get_container_client(config.get("container"))


def test(config: dict, secrets: dict) -> TestResult:
    missing = _missing_required(config, secrets)
    if missing:
        return TestResult(False, missing)
    try:
        client = _container_client(config, secrets)
        client.get_container_properties()
        return TestResult(True, "Connection succeeded.")
    except ImportError:
        return TestResult(False, "azure-storage-blob isn't installed (pip install '.[cloud]').")
    except Exception as e:
        return TestResult(False, f"Couldn't connect: {e}")


def sync(config: dict, secrets: dict) -> SyncResult:
    missing = _missing_required(config, secrets)
    if missing:
        return SyncResult(False, missing, [])
    container = config.get("container") or ""
    prefix = clean_prefix(config.get("prefix") or "", container)
    try:
        from concurrent.futures import ThreadPoolExecutor

        client = _container_client(config, secrets)

        matching_keys = []
        for blob in client.list_blobs(name_starts_with=prefix):
            key = blob.name
            if not is_data_object(key):
                continue
            if len(matching_keys) >= OBJECT_CAP:
                break
            size = blob.size or 0
            if size <= 0 or size > MAX_OBJECT_BYTES:
                # Zero-byte or oversized blob: skip silently, same as not matching is_data_object.
                continue
            matching_keys.append(key)
            if len(matching_keys) >= OBJECT_CAP:
                break

        def _fetch_blob(key: str) -> DatasetResult | None:
            try:
                data = client.download_blob(key).readall()
                df = read_table(data, key)
                columns = [str(c) for c in df.columns]
                sample_rows = extract_sample_rows(df, 5)
                rows = extract_rows(df, ROW_CAP)
                return DatasetResult(name=dataset_name(key, prefix), columns=columns, row_count=len(df), sample_rows=sample_rows, rows=rows)
            except Exception as e:
                logger.warning("[Azure] Skipping %s: %s", key, e)
                return None

        datasets = []
        if matching_keys:
            workers = min(8, len(matching_keys))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                for res in executor.map(_fetch_blob, matching_keys):
                    if res is not None:
                        datasets.append(res)

        return SyncResult(True, f"Discovered {len(datasets)} object(s).", datasets)
    except ImportError:
        return SyncResult(False, "azure-storage-blob isn't installed (pip install '.[cloud]').", [])
    except Exception as e:
        return SyncResult(False, f"Sync failed: {e}", [])

