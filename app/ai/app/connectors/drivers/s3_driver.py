import logging

from app.connectors.types import TestResult, SyncResult, DatasetResult
from app.connectors.drivers._object_storage import is_data_object, dataset_name, read_table, MAX_OBJECT_BYTES

OBJECT_CAP = 200  # ponytail: fixed page size, paginate if a bucket needs more matching objects than this

logger = logging.getLogger("app.connectors.drivers.s3")


def _client(config: dict, secrets: dict):
    import boto3

    return boto3.client(
        "s3",
        aws_access_key_id=secrets.get("accessKeyId"),
        aws_secret_access_key=secrets.get("secretAccessKey"),
        region_name=config.get("region"),
    )


def _missing_required(config: dict, secrets: dict) -> str | None:
    if not config.get("bucket") or not config.get("region") or not secrets.get("accessKeyId") or not secrets.get("secretAccessKey"):
        return "Bucket name, region, access key ID and secret access key are required."
    return None


def test(config: dict, secrets: dict) -> TestResult:
    missing = _missing_required(config, secrets)
    if missing:
        return TestResult(False, missing)
    try:
        client = _client(config, secrets)
        client.head_bucket(Bucket=config["bucket"])
        return TestResult(True, "Connection succeeded.")
    except ImportError:
        return TestResult(False, "boto3 isn't installed (pip install '.[cloud]').")
    except Exception as e:
        return TestResult(False, f"Couldn't connect: {e}")


def sync(config: dict, secrets: dict) -> SyncResult:
    missing = _missing_required(config, secrets)
    if missing:
        return SyncResult(False, missing, [])
    bucket = config["bucket"]
    prefix = config.get("prefix") or ""
    try:
        client = _client(config, secrets)
        paginator = client.get_paginator("list_objects_v2")
        datasets = []
        count = 0
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not is_data_object(key):
                    continue
                if count >= OBJECT_CAP:
                    break
                size = obj.get("Size", 0)
                if size <= 0 or size > MAX_OBJECT_BYTES:
                    # Zero-byte or oversized object: skip silently, same as not matching is_data_object.
                    continue
                try:
                    body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
                    df = read_table(body, key)
                    columns = [str(c) for c in df.columns]
                    sample_rows = df.head(5).astype(str).values.tolist()
                    datasets.append(DatasetResult(name=dataset_name(key, prefix), columns=columns, row_count=len(df), sample_rows=sample_rows))
                    count += 1
                except Exception as e:
                    logger.warning("[S3] Skipping %s: %s", key, e)
                    continue
            if count >= OBJECT_CAP:
                break
        return SyncResult(True, f"Discovered {len(datasets)} object(s).", datasets)
    except ImportError:
        return SyncResult(False, "boto3 isn't installed (pip install '.[cloud]').", [])
    except Exception as e:
        return SyncResult(False, f"Sync failed: {e}", [])
