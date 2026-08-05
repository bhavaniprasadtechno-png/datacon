import json

from app.connectors.types import TestResult, SyncResult, DatasetResult
from app.connectors.drivers._object_storage import is_data_object, dataset_name, read_table

OBJECT_CAP = 200  # ponytail: fixed page size, paginate if a bucket needs more matching objects than this


def _missing_required(config: dict, secrets: dict) -> str | None:
    if not config.get("bucket") or not secrets.get("serviceAccountJson"):
        return "Bucket name and service-account JSON are required."
    return None


def _bucket(config: dict, secrets: dict):
    from google.cloud import storage

    info = json.loads(secrets.get("serviceAccountJson"))
    client = storage.Client.from_service_account_info(info)
    return client.bucket(config.get("bucket"))


def test(config: dict, secrets: dict) -> TestResult:
    missing = _missing_required(config, secrets)
    if missing:
        return TestResult(False, missing)
    try:
        bucket = _bucket(config, secrets)
        if not bucket.exists():
            return TestResult(False, f"Bucket '{config.get('bucket')}' doesn't exist or isn't accessible.")
        return TestResult(True, "Connection succeeded.")
    except ImportError:
        return TestResult(False, "google-cloud-storage isn't installed (pip install '.[cloud]').")
    except Exception as e:
        return TestResult(False, f"Couldn't connect: {e}")


def sync(config: dict, secrets: dict) -> SyncResult:
    missing = _missing_required(config, secrets)
    if missing:
        return SyncResult(False, missing, [])
    prefix = config.get("prefix") or ""
    try:
        bucket = _bucket(config, secrets)
        datasets = []
        count = 0
        for blob in bucket.list_blobs(prefix=prefix):
            key = blob.name
            if not is_data_object(key):
                continue
            if count >= OBJECT_CAP:
                break
            count += 1
            try:
                data = blob.download_as_bytes()
                df = read_table(data, key)
                columns = [str(c) for c in df.columns]
                sample_rows = df.head(5).astype(str).values.tolist()
                datasets.append(DatasetResult(name=dataset_name(key), columns=columns, row_count=len(df), sample_rows=sample_rows))
            except Exception:
                continue
        return SyncResult(True, f"Discovered {len(datasets)} object(s).", datasets)
    except ImportError:
        return SyncResult(False, "google-cloud-storage isn't installed (pip install '.[cloud]').", [])
    except Exception as e:
        return SyncResult(False, f"Sync failed: {e}", [])
