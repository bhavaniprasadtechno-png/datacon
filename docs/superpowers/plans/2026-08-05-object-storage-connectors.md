# Object Storage Connectors (AWS S3, Azure Blob Storage, Google Cloud Storage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three object-storage connector engines — AWS S3, Azure Blob Storage, Google Cloud Storage — to the existing connector system, matching the field specs in the design mockup.

**Architecture:** The connector system is fully data-driven off one shared JSON registry (`connector-engines.json`) consumed by the React modal, the NestJS DTO/service, and (via a Python loader) the AI service. Adding an engine means adding one registry entry, one Prisma enum value + migration, one allow-list entry, one style-map entry, and one Python driver module registered in a dispatch dict — no changes to the modal component or the NestJS service logic, both of which are already generic.

**Tech Stack:** TypeScript (React, NestJS, Prisma), Python (FastAPI, pandas, boto3, azure-storage-blob, google-cloud-storage).

## Global Constraints

- Field keys, labels, placeholders and help text for the three new engines must match the design mockup exactly (spec: `docs/superpowers/specs/2026-08-05-object-storage-connectors-design.md`).
- `AddConnectorModal.tsx` and `ConnectorsService` (NestJS) must not be modified — the design is entirely driven by the shared registry.
- New drivers must not set `DatasetResult.rows` — matches the documented precedent that file/API-based connectors (Mongo/HTTP/BigQuery/Snowflake) are discovery + preview only, not full-row DuckDB loading (see `docs/superpowers/plans/2026-07-13-real-data-grounding.md`, Task 4).
- `test()`/`sync()` must never raise — every failure path returns `ok=False` with a message, matching every existing driver.
- Object listing per sync is capped at `OBJECT_CAP = 200` per driver (ponytail ceiling — no pagination beyond this cap in this plan).
- New cloud SDKs (`boto3`, `azure-storage-blob`, `google-cloud-storage`) are optional dependencies (the `cloud` extra), same as `google-cloud-bigquery` and `snowflake-connector-python` today.

---

### Task 1: Shared engine field registry — S3, Azure, GCS entries

**Files:**
- Modify: `app/packages/shared-types/src/connector-engines.json`
- Modify: `app/packages/shared-types/src/connector-engines.ts`

**Interfaces:**
- Produces: registry entries for `s3`, `azure`, `gcs` under the existing `EngineDef` shape (`id`, `name`, `description`, `typeLetter`, `primary: EngineField`, `secondary: EngineField[]`); `ConnectorEngineId` gains `"s3" | "azure" | "gcs"`; `ENGINE_FIELDS` and `ENGINE_LIST` gain the three new entries. Consumed by Task 3 (DTO), Task 4 (connectorMeta), and indirectly by `AddConnectorModal.tsx` and `ConnectorsService` (both unmodified).

There is no existing test file for `connector-engines.ts` (it's pure data — no driver logic lives here). Because `ENGINE_FIELDS` is typed as `Record<ConnectorEngineId, EngineDef>`, a TypeScript build is the correctness check: forgetting an entry for a new id in `ConnectorEngineId` fails the build.

- [ ] **Step 1: Add the three registry entries to the JSON file**

Open `app/packages/shared-types/src/connector-engines.json` and add these three keys after the existing `"snowflake"` entry (before the closing `}` of the top-level object), matching the mockup's field specs:

```json
  "s3": {
    "id": "s3",
    "name": "AWS S3 bucket",
    "description": "Read CSV/Parquet/JSON objects from an S3 bucket or prefix.",
    "typeLetter": "S3",
    "primary": { "key": "bucket", "label": "Bucket name", "placeholder": "lyra-analytics-exports" },
    "secondary": [
      { "key": "prefix", "label": "Object key / prefix", "placeholder": "exports/sales/2026/", "required": true, "help": "A single file key or a prefix to sync every object under it." },
      { "key": "region", "label": "Region", "placeholder": "us-east-1", "required": true },
      { "key": "accessKeyId", "label": "Access key ID", "placeholder": "AKIAIOSFODNN7EXAMPLE", "required": true },
      { "key": "secretAccessKey", "label": "Secret access key", "placeholder": "••••••••••••••", "type": "password", "required": true, "secret": true },
      { "key": "format", "label": "File format", "placeholder": "csv, parquet or json" }
    ]
  },
  "azure": {
    "id": "azure",
    "name": "Azure Blob Storage",
    "description": "Read tabular files from an Azure Storage container.",
    "typeLetter": "A",
    "primary": { "key": "account", "label": "Storage account name", "placeholder": "lyraanalytics" },
    "secondary": [
      { "key": "container", "label": "Container name", "placeholder": "exports", "required": true },
      { "key": "prefix", "label": "Blob path / prefix", "placeholder": "sales/2026/", "required": true },
      { "key": "connectionString", "label": "Connection string", "kind": "textarea", "placeholder": "DefaultEndpointsProtocol=https;AccountName=…;AccountKey=…;EndpointSuffix=core.windows.net", "required": true, "secret": true, "help": "From Storage account → Access keys. Stored encrypted at rest." }
    ]
  },
  "gcs": {
    "id": "gcs",
    "name": "Google Cloud Storage",
    "description": "Read tabular files from a GCS bucket via service account.",
    "typeLetter": "G",
    "primary": { "key": "bucket", "label": "Bucket name", "placeholder": "lyra-analytics-exports" },
    "secondary": [
      { "key": "prefix", "label": "Object path / prefix", "placeholder": "exports/sales/2026/", "required": true },
      { "key": "serviceAccountJson", "label": "Service-account JSON", "kind": "textarea", "placeholder": "{\"type\":\"service_account\",\"project_id\":\"…\",\"private_key\":\"-----BEGIN…\"}", "required": true, "secret": true, "help": "Paste the full JSON contents of your service-account key. Stored encrypted at rest." }
    ]
  }
```

Remember to add a trailing comma after the existing `"snowflake": { ... }` entry's closing brace.

- [ ] **Step 2: Extend the TypeScript union and exports**

In `app/packages/shared-types/src/connector-engines.ts`:

```typescript
export type ConnectorEngineId = "sqlite" | "postgres" | "mysql" | "mongodb" | "http" | "bigquery" | "snowflake" | "supabase" | "s3" | "azure" | "gcs";
```

```typescript
export const ENGINE_FIELDS: Record<ConnectorEngineId, EngineDef> = {
  sqlite: file.sqlite as EngineDef,
  postgres: file.postgres as EngineDef,
  supabase: file.supabase as EngineDef,
  mysql: file.mysql as EngineDef,
  mongodb: file.mongodb as EngineDef,
  http: file.http as EngineDef,
  bigquery: file.bigquery as EngineDef,
  snowflake: file.snowflake as EngineDef,
  s3: file.s3 as EngineDef,
  azure: file.azure as EngineDef,
  gcs: file.gcs as EngineDef,
};

export const ENGINE_LIST: EngineDef[] = [
  ENGINE_FIELDS.sqlite,
  ENGINE_FIELDS.postgres,
  ENGINE_FIELDS.supabase,
  ENGINE_FIELDS.mysql,
  ENGINE_FIELDS.mongodb,
  ENGINE_FIELDS.http,
  ENGINE_FIELDS.bigquery,
  ENGINE_FIELDS.snowflake,
  ENGINE_FIELDS.s3,
  ENGINE_FIELDS.azure,
  ENGINE_FIELDS.gcs,
];
```

- [ ] **Step 3: Build the package to verify the types are complete**

Run: `npm run build --workspace=packages/shared-types`
Expected: builds with no TypeScript errors (this is the regression check — a missing `ENGINE_FIELDS` entry for a new `ConnectorEngineId` fails this build).

- [ ] **Step 4: Commit**

```bash
git add app/packages/shared-types/src/connector-engines.json app/packages/shared-types/src/connector-engines.ts
git commit -m "feat(shared-types): add S3, Azure and GCS connector field registries"
```

---

### Task 2: Prisma `ConnectorEngine` enum + migration

**Files:**
- Modify: `app/packages/prisma/schema.prisma:115-124`
- Create: `app/packages/prisma/migrations/20260805130000_add_object_storage_connector_engines/migration.sql`
- Modify: `app/packages/prisma/index.ts:3-12`

**Interfaces:**
- Produces: `ConnectorEngine` enum gains `S3`, `AZURE`, `GCS` values in the Prisma schema. **`app/packages/prisma/index.ts` hand-maintains its own `ConnectorEngine` const/type as a manual mirror of the schema enum (it does not re-export the generated Prisma Client type) — this must be updated in the same task or `ConnectorsService`'s calls into the generically-typed Prisma client (e.g. `connectors.service.ts:145,212`) fail to compile.**

- [ ] **Step 1: Add the enum values**

In `app/packages/prisma/schema.prisma`, replace lines 115-124:

```prisma
enum ConnectorEngine {
  SQLITE
  POSTGRES
  SUPABASE
  MYSQL
  MONGODB
  HTTP
  BIGQUERY
  SNOWFLAKE
  S3
  AZURE
  GCS
}
```

- [ ] **Step 2: Write the migration**

Create `app/packages/prisma/migrations/20260805130000_add_object_storage_connector_engines/migration.sql`:

```sql
-- AlterEnum
ALTER TYPE "ConnectorEngine" ADD VALUE 'S3';
ALTER TYPE "ConnectorEngine" ADD VALUE 'AZURE';
ALTER TYPE "ConnectorEngine" ADD VALUE 'GCS';
```

- [ ] **Step 3: Validate the schema**

Run: `npm run generate --workspace=packages/prisma` (this runs `prisma generate`, which also validates schema syntax)
Expected: completes with no errors, regenerates the Prisma client with `S3`/`AZURE`/`GCS` on the `ConnectorEngine` type.

- [ ] **Step 4: Update the hand-maintained `ConnectorEngine` mirror in `app/packages/prisma/index.ts`**

`app/packages/prisma/index.ts` does not re-export the generated Prisma Client enum — it hand-maintains its own `ConnectorEngine` const object (a workaround so downstream packages don't need `@prisma/client` as a direct dependency). Add the three new keys, keeping the existing style:

```typescript
export const ConnectorEngine = {
  SQLITE: "SQLITE",
  POSTGRES: "POSTGRES",
  SUPABASE: "SUPABASE",
  MYSQL: "MYSQL",
  MONGODB: "MONGODB",
  HTTP: "HTTP",
  BIGQUERY: "BIGQUERY",
  SNOWFLAKE: "SNOWFLAKE",
  S3: "S3",
  AZURE: "AZURE",
  GCS: "GCS",
} as const;
```

- [ ] **Step 5: Build the prisma package and the API workspace**

Run: `npm run build --workspace=packages/prisma && npm run build --workspace=api`
Expected: both build with no TypeScript errors — this is what catches a mismatch between the hand-maintained `ConnectorEngine` mirror and the Prisma-generated type, since `ConnectorsService` (`app/api/src/connectors/connectors.service.ts`) passes values typed against `@datacon/prisma`'s `ConnectorEngine` into calls typed against the generated Prisma Client's `ConnectorEngine`.

- [ ] **Step 6: Apply the migration to your local dev database**

Run: `npm run prisma:migrate --workspace=packages/prisma` (requires a running local Postgres matching `DATABASE_URL`)
Expected: `Your database is now in sync with your schema.` and the new migration is recorded in `_prisma_migrations`.

- [ ] **Step 7: Commit**

```bash
git add app/packages/prisma/schema.prisma app/packages/prisma/migrations/20260805130000_add_object_storage_connector_engines app/packages/prisma/index.ts
git commit -m "feat(prisma): add S3, Azure and GCS to ConnectorEngine enum"
```

---

### Task 3: NestJS DTO allow-list

**Files:**
- Modify: `app/api/src/connectors/dto/save-connector.dto.ts:4`

**Interfaces:**
- Consumes: `ConnectorEngineId` from `@datacon/shared-types` (Task 1).
- Produces: `SaveConnectorDto.engine` now accepts `"s3" | "azure" | "gcs"` in addition to the existing ids; validated by `class-validator`'s `@IsIn`.

There is no existing test file for this DTO (no `.spec.ts` under `app/api/src/connectors`), so the check here is the TypeScript build plus the class-validator array being in sync with the shared union — both are compile/runtime-trivial for a literal-array append.

- [ ] **Step 1: Extend the allow-list**

In `app/api/src/connectors/dto/save-connector.dto.ts`:

```typescript
const ENGINE_IDS: ConnectorEngineId[] = ["sqlite", "postgres", "supabase", "mysql", "mongodb", "http", "bigquery", "snowflake", "s3", "azure", "gcs"];
```

- [ ] **Step 2: Build the API workspace**

Run: `npm run build --workspace=api`
Expected: builds with no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add app/api/src/connectors/dto/save-connector.dto.ts
git commit -m "feat(api): allow s3/azure/gcs connector engines in SaveConnectorDto"
```

---

### Task 4: Connector badge styling

**Files:**
- Modify: `app/web/src/lib/connectorMeta.ts:4-13`

**Interfaces:**
- Consumes: `ConnectorEngineId` from `@datacon/shared-types` (Task 1).
- Produces: `TYPE_STYLE` entries for `s3`, `azure`, `gcs`, consumed by `AddConnectorModal.tsx` and `ConnectorsPage.tsx` (both unmodified, already read `TYPE_STYLE[engine]` generically).

`TYPE_STYLE` is typed `Record<ConnectorEngineId, {...}>`, so a missing entry for a new id fails the build — that's the regression check.

- [ ] **Step 1: Add the three style entries**

In `app/web/src/lib/connectorMeta.ts`:

```typescript
export const TYPE_STYLE: Record<ConnectorEngineId, { letter: string; bg: string; color: string }> = {
  postgres: { letter: "P", bg: "#e9eefc", color: "#3b6fd4" },
  supabase: { letter: "U", bg: "#e6f9f0", color: "#1a9c6b" },
  mysql: { letter: "M", bg: "#fdf0e6", color: "#d9822b" },
  snowflake: { letter: "S", bg: "#e3f6fb", color: "#2ba6c4" },
  bigquery: { letter: "B", bg: "#eef0f4", color: "#5a6b86" },
  sqlite: { letter: "L", bg: "#e6f6ee", color: "#3a9d6a" },
  mongodb: { letter: "G", bg: "#e6f6ee", color: "#1d8e5a" },
  http: { letter: "H", bg: "var(--ac-soft)", color: "var(--ac)" },
  s3: { letter: "S3", bg: "#fdf3e3", color: "#b9791f" },
  azure: { letter: "A", bg: "#e9f2fd", color: "#2a6fc9" },
  gcs: { letter: "G", bg: "#eef0f4", color: "#5a6b86" },
};
```

- [ ] **Step 2: Build the web workspace**

Run: `npm run build --workspace=web`
Expected: builds with no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add app/web/src/lib/connectorMeta.ts
git commit -m "feat(web): add badge styling for S3, Azure and GCS connectors"
```

---

### Task 5: Optional cloud SDK dependencies

**Files:**
- Modify: `app/ai/pyproject.toml:23-27`

**Interfaces:**
- Produces: `boto3`, `azure-storage-blob`, `google-cloud-storage` become available under the `cloud` extra, imported lazily inside Tasks 7-9's driver modules (same lazy-import-inside-function pattern as `bigquery_driver.py`).

- [ ] **Step 1: Add the three packages to the `cloud` extra**

In `app/ai/pyproject.toml`:

```toml
[project.optional-dependencies]
cloud = [
    "google-cloud-bigquery>=3.26.0",
    "snowflake-connector-python>=3.12.3",
    "boto3>=1.35.0",
    "azure-storage-blob>=12.23.0",
    "google-cloud-storage>=2.18.0",
]
```

- [ ] **Step 2: Install the extra locally to confirm it resolves**

Run (from `app/ai`): `pip install -e ".[cloud]"`
Expected: resolves and installs without conflicts.

- [ ] **Step 3: Commit**

```bash
git add app/ai/pyproject.toml
git commit -m "feat(ai): add boto3, azure-storage-blob and google-cloud-storage as optional cloud deps"
```

---

### Task 6: Shared object-storage helpers

**Files:**
- Create: `app/ai/app/connectors/drivers/_object_storage.py`
- Test: `app/ai/tests/connectors/test_object_storage_shared.py`

**Interfaces:**
- Produces: `is_data_object(key: str) -> bool`, `dataset_name(key: str) -> str`, `read_table(data: bytes, key: str) -> pandas.DataFrame` — used by Tasks 7, 8, 9's `s3_driver`, `azure_driver`, `gcs_driver`.

This is the one piece of genuinely shared logic across the three drivers (identical extension filtering and format dispatch, only the listing/auth code differs per cloud), so it's factored out once instead of copy-pasted three times.

- [ ] **Step 1: Write the failing tests**

Create `app/ai/tests/connectors/test_object_storage_shared.py`:

```python
import io

import pandas as pd
from app.connectors.drivers._object_storage import is_data_object, dataset_name, read_table


def test_is_data_object_accepts_supported_extensions():
    assert is_data_object("exports/sales.csv") is True
    assert is_data_object("exports/sales.parquet") is True
    assert is_data_object("exports/sales.json") is True


def test_is_data_object_rejects_unsupported_extensions_and_directory_markers():
    assert is_data_object("exports/readme.txt") is False
    assert is_data_object("exports/sales/2026/") is False


def test_dataset_name_strips_prefix_and_extension():
    assert dataset_name("exports/sales/2026/orders.csv") == "orders"
    assert dataset_name("orders.PARQUET") == "orders"


def test_read_table_parses_csv_bytes():
    df = read_table(b"a,b\n1,2\n3,4\n", "exports/data.csv")
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 2


def test_read_table_parses_json_bytes():
    df = read_table(b'[{"a": 1, "b": 2}, {"a": 3, "b": 4}]', "exports/data.json")
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 2


def test_read_table_parses_parquet_bytes():
    buf = io.BytesIO()
    pd.DataFrame({"a": [1, 3], "b": [2, 4]}).to_parquet(buf)
    df = read_table(buf.getvalue(), "exports/data.parquet")
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app/ai && python -m pytest tests/connectors/test_object_storage_shared.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.connectors.drivers._object_storage'`

- [ ] **Step 3: Write the implementation**

Create `app/ai/app/connectors/drivers/_object_storage.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd app/ai && python -m pytest tests/connectors/test_object_storage_shared.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add app/ai/app/connectors/drivers/_object_storage.py app/ai/tests/connectors/test_object_storage_shared.py
git commit -m "feat(ai): add shared object-storage key filtering and table parsing helpers"
```

---

### Task 7: S3 driver

**Files:**
- Create: `app/ai/app/connectors/drivers/s3_driver.py`
- Test: `app/ai/tests/connectors/test_s3_driver.py`

**Interfaces:**
- Consumes: `TestResult`, `SyncResult`, `DatasetResult` from `app.connectors.types`; `is_data_object`, `dataset_name`, `read_table` from `app.connectors.drivers._object_storage` (Task 6).
- Produces: `s3_driver.test(config: dict, secrets: dict) -> TestResult`, `s3_driver.sync(config: dict, secrets: dict) -> SyncResult`. Registration in `service.py._DRIVERS` happens in Task 10, once all three drivers exist — kept separate so this task is independently testable.

Config keys: `bucket`, `prefix`, `region`, `format` (unused — accepted for parity with the mockup; extension-based detection already covers csv/parquet/json). Secret keys: `accessKeyId`, `secretAccessKey`.

- [ ] **Step 1: Write the failing test**

Create `app/ai/tests/connectors/test_s3_driver.py`:

```python
from app.connectors.drivers import s3_driver


def test_test_rejects_missing_required_fields_without_touching_boto3():
    result = s3_driver.test({}, {})

    assert result.ok is False
    assert "required" in result.message.lower()


def test_sync_rejects_missing_required_fields_without_touching_boto3():
    result = s3_driver.sync({}, {})

    assert result.ok is False
    assert result.datasets == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app/ai && python -m pytest tests/connectors/test_s3_driver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.connectors.drivers.s3_driver'`

- [ ] **Step 3: Write the driver**

Create `app/ai/app/connectors/drivers/s3_driver.py`:

```python
from app.connectors.types import TestResult, SyncResult, DatasetResult
from app.connectors.drivers._object_storage import is_data_object, dataset_name, read_table

OBJECT_CAP = 200  # ponytail: fixed page size, paginate if a bucket needs more matching objects than this


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
                count += 1
                try:
                    body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
                    df = read_table(body, key)
                    columns = [str(c) for c in df.columns]
                    sample_rows = df.head(5).astype(str).values.tolist()
                    datasets.append(DatasetResult(name=dataset_name(key), columns=columns, row_count=len(df), sample_rows=sample_rows))
                except Exception:
                    continue
            if count >= OBJECT_CAP:
                break
        return SyncResult(True, f"Discovered {len(datasets)} object(s).", datasets)
    except ImportError:
        return SyncResult(False, "boto3 isn't installed (pip install '.[cloud]').", [])
    except Exception as e:
        return SyncResult(False, f"Sync failed: {e}", [])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app/ai && python -m pytest tests/connectors/test_s3_driver.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/ai/app/connectors/drivers/s3_driver.py app/ai/tests/connectors/test_s3_driver.py
git commit -m "feat(ai): add S3 connector driver"
```

---

### Task 8: Azure Blob Storage driver

**Files:**
- Create: `app/ai/app/connectors/drivers/azure_driver.py`
- Test: `app/ai/tests/connectors/test_azure_driver.py`

**Interfaces:**
- Consumes: same shared helpers as Task 7 (`app.connectors.drivers._object_storage`).
- Produces: `azure_driver.test(config, secrets) -> TestResult`, `azure_driver.sync(config, secrets) -> SyncResult`. Registration in `service.py._DRIVERS` happens in Task 10.

Config keys: `account`, `container`, `prefix`. Secret keys: `connectionString`.

- [ ] **Step 1: Write the failing test**

Create `app/ai/tests/connectors/test_azure_driver.py`:

```python
from app.connectors.drivers import azure_driver


def test_test_rejects_missing_required_fields_without_touching_sdk():
    result = azure_driver.test({}, {})

    assert result.ok is False
    assert "required" in result.message.lower()


def test_sync_rejects_missing_required_fields_without_touching_sdk():
    result = azure_driver.sync({}, {})

    assert result.ok is False
    assert result.datasets == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app/ai && python -m pytest tests/connectors/test_azure_driver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.connectors.drivers.azure_driver'`

- [ ] **Step 3: Write the driver**

Create `app/ai/app/connectors/drivers/azure_driver.py`:

```python
from app.connectors.types import TestResult, SyncResult, DatasetResult
from app.connectors.drivers._object_storage import is_data_object, dataset_name, read_table

OBJECT_CAP = 200  # ponytail: fixed page size, paginate if a container needs more matching objects than this


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
    prefix = config.get("prefix") or ""
    try:
        client = _container_client(config, secrets)
        datasets = []
        count = 0
        for blob in client.list_blobs(name_starts_with=prefix):
            key = blob.name
            if not is_data_object(key):
                continue
            if count >= OBJECT_CAP:
                break
            count += 1
            try:
                data = client.download_blob(key).readall()
                df = read_table(data, key)
                columns = [str(c) for c in df.columns]
                sample_rows = df.head(5).astype(str).values.tolist()
                datasets.append(DatasetResult(name=dataset_name(key), columns=columns, row_count=len(df), sample_rows=sample_rows))
            except Exception:
                continue
        return SyncResult(True, f"Discovered {len(datasets)} object(s).", datasets)
    except ImportError:
        return SyncResult(False, "azure-storage-blob isn't installed (pip install '.[cloud]').", [])
    except Exception as e:
        return SyncResult(False, f"Sync failed: {e}", [])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app/ai && python -m pytest tests/connectors/test_azure_driver.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/ai/app/connectors/drivers/azure_driver.py app/ai/tests/connectors/test_azure_driver.py
git commit -m "feat(ai): add Azure Blob Storage connector driver"
```

---

### Task 9: Google Cloud Storage driver

**Files:**
- Create: `app/ai/app/connectors/drivers/gcs_driver.py`
- Test: `app/ai/tests/connectors/test_gcs_driver.py`

**Interfaces:**
- Consumes: same shared helpers as Task 7 (`app.connectors.drivers._object_storage`).
- Produces: `gcs_driver.test(config, secrets) -> TestResult`, `gcs_driver.sync(config, secrets) -> SyncResult`. Registration in `service.py._DRIVERS` happens in Task 10.

Config keys: `bucket`, `prefix`. Secret keys: `serviceAccountJson`.

- [ ] **Step 1: Write the failing test**

Create `app/ai/tests/connectors/test_gcs_driver.py`:

```python
from app.connectors.drivers import gcs_driver


def test_test_rejects_missing_required_fields_without_touching_sdk():
    result = gcs_driver.test({}, {})

    assert result.ok is False
    assert "required" in result.message.lower()


def test_sync_rejects_missing_required_fields_without_touching_sdk():
    result = gcs_driver.sync({}, {})

    assert result.ok is False
    assert result.datasets == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app/ai && python -m pytest tests/connectors/test_gcs_driver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.connectors.drivers.gcs_driver'`

- [ ] **Step 3: Write the driver**

Create `app/ai/app/connectors/drivers/gcs_driver.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app/ai && python -m pytest tests/connectors/test_gcs_driver.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/ai/app/connectors/drivers/gcs_driver.py app/ai/tests/connectors/test_gcs_driver.py
git commit -m "feat(ai): add Google Cloud Storage connector driver"
```

---

### Task 10: Register the three drivers in the service dispatch dict

**Files:**
- Modify: `app/ai/app/connectors/service.py:5,10-19`
- Test: `app/ai/tests/connectors/test_engine_registration.py`

**Interfaces:**
- Consumes: `s3_driver`, `azure_driver`, `gcs_driver` modules (Tasks 7-9).
- Produces: `_DRIVERS["s3"|"azure"|"gcs"]`, consumed by `connectors_service.test_connection`/`sync_connector` — the same entry points `ConnectorsController` already calls for every other engine.

- [ ] **Step 1: Write the failing tests**

Create `app/ai/tests/connectors/test_engine_registration.py`:

```python
from app.connectors import service as connectors_service


def test_service_dispatches_to_s3_driver_not_unknown_engine():
    result = connectors_service.test_connection("s3", {}, {})

    assert "unknown engine" not in result.message.lower()
    assert "required" in result.message.lower()


def test_service_dispatches_to_azure_driver_not_unknown_engine():
    result = connectors_service.test_connection("azure", {}, {})

    assert "unknown engine" not in result.message.lower()
    assert "required" in result.message.lower()


def test_service_dispatches_to_gcs_driver_not_unknown_engine():
    result = connectors_service.test_connection("gcs", {}, {})

    assert "unknown engine" not in result.message.lower()
    assert "required" in result.message.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app/ai && python -m pytest tests/connectors/test_engine_registration.py -v`
Expected: FAIL — all 3 assert `"unknown engine" not in ...` but `_DRIVERS` doesn't have `s3`/`azure`/`gcs` yet, so the message is literally `"Unknown engine: s3"` etc.

- [ ] **Step 3: Register the drivers**

In `app/ai/app/connectors/service.py`, update the import and `_DRIVERS`:

```python
from app.connectors.drivers import sqlite_driver, postgres_driver, mysql_driver, mongodb_driver, http_driver, bigquery_driver, snowflake_driver, supabase_driver, s3_driver, azure_driver, gcs_driver

_DRIVERS = {
    "sqlite": sqlite_driver,
    "postgres": postgres_driver,
    "supabase": supabase_driver,
    "mysql": mysql_driver,
    "mongodb": mongodb_driver,
    "http": http_driver,
    "bigquery": bigquery_driver,
    "snowflake": snowflake_driver,
    "s3": s3_driver,
    "azure": azure_driver,
    "gcs": gcs_driver,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd app/ai && python -m pytest tests/connectors/test_engine_registration.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the full connectors test suite**

Run: `cd app/ai && python -m pytest tests/connectors/ -v`
Expected: all tests pass, including the pre-existing `test_service.py`, `test_sqlite_driver.py`, `test_mongodb_driver.py`, and every new file from Tasks 6-10.

- [ ] **Step 6: Commit**

```bash
git add app/ai/app/connectors/service.py app/ai/tests/connectors/test_engine_registration.py
git commit -m "feat(ai): register S3, Azure and GCS drivers in the connector service"
```

---

### Task 11: End-to-end verification in the running app

**Files:** none (manual verification only)

- [ ] **Step 1: Start the app**

Run: `npm run dev` (from `app/`)

- [ ] **Step 2: Open the connectors page and the Add Connector modal**

Navigate to the Connectors page, click "Add connector". Confirm the picker now shows 11 engines including "AWS S3 bucket", "Azure Blob Storage" and "Google Cloud Storage" with the badges/colors from the mockup.

- [ ] **Step 3: Confirm the config forms match the mockup**

Click each of the three new engines and confirm the fields shown (labels, placeholders, required markers, secret/password masking, textarea for connection string / service-account JSON) match `docs/superpowers/specs/2026-08-05-object-storage-connectors-design.md`.

- [ ] **Step 4: Confirm "Test connection" surfaces driver validation messages**

With no fields filled in, click "Test connection" for each of the three engines and confirm the message is the specific "X, Y and Z are required." text from the driver (not a generic error), proving the request reaches the AI service and dispatches to the right driver end-to-end (NestJS → `/internal/connectors/test` → `connectors_service.test_connection` → driver).
