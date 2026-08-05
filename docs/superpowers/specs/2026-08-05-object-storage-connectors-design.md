# Object storage connectors: AWS S3, Azure Blob Storage, Google Cloud Storage

## Context

The connector catalog currently supports SQLite, Postgres/Redshift, Supabase, MySQL/MariaDB, MongoDB, HTTP CSV/Parquet, BigQuery and Snowflake. The design mockup (`Datacon.dc.html`, screens `s3-config.png` / `azure-config.png` / `connectors-new-engines.png`) adds three object-storage engines to the "Add data connector" picker: **AWS S3 bucket**, **Azure Blob Storage**, **Google Cloud Storage**. This spec adds them to the real app using the existing connector architecture, unchanged.

## Why this is purely additive

The connector system is fully data-driven off one shared registry (`app/packages/shared-types/src/connector-engines.json`):
- `AddConnectorModal.tsx` renders the engine picker and config form entirely from `ENGINE_LIST` / `ENGINE_FIELDS` — no per-engine UI code.
- `ConnectorsService` (NestJS) splits submitted fields into `config` vs `secrets` and encrypts secrets purely by reading each field's `secret: true` flag from the registry (`splitFields`, `connectors.service.ts:36`) — no per-engine service code.
- `SaveConnectorDto` validates the engine id against a flat allow-list.
- The AI service dispatches `test()`/`sync()` to a driver module keyed by engine id (`app/ai/app/connectors/service.py`'s `_DRIVERS` dict).

So adding an engine = one registry entry + one Prisma enum value + one driver module + one dict entry. No new abstractions.

## Field specs (from the mockup, reused verbatim)

**S3** — primary: Bucket name. Secondary: Object key / prefix* (help: "a single file key or a prefix to sync every object under it"), Region*, Access key ID*, Secret access key* (secret), File format (free text, optional).

**Azure Blob Storage** — primary: Storage account name. Secondary: Container name*, Blob path / prefix*, Connection string* (secret, textarea).

**Google Cloud Storage** — primary: Bucket name. Secondary: Object path / prefix*, Service-account JSON* (secret, textarea).

(* = required)

Badge styling (from the mockup): S3 = amber `#fdf3e3` / `#b9791f`, letter "S3". Azure = blue `#e9f2fd` / `#2a6fc9`, letter "A". GCS = grey `#eef0f4` / `#5a6b86`, letter "G" (shares BigQuery's palette, matching the mockup).

## Touch points

1. **`app/packages/shared-types/src/connector-engines.json`** — add `s3`, `azure`, `gcs` entries with the fields above.
2. **`app/packages/shared-types/src/connector-engines.ts`** — extend `ConnectorEngineId` union, `ENGINE_FIELDS`, `ENGINE_LIST`.
3. **`app/packages/prisma/schema.prisma`** — add `S3`, `AZURE`, `GCS` to the `ConnectorEngine` enum.
4. **New Prisma migration** (`ALTER TYPE "ConnectorEngine" ADD VALUE '...'` ×3), same shape as `20260709044915_add_supabase_connector_engine`.
5. **`app/api/src/connectors/dto/save-connector.dto.ts`** — extend `ENGINE_IDS`.
6. **`app/web/src/lib/connectorMeta.ts`** — add the three `TYPE_STYLE` entries above.
7. **New driver modules** in `app/ai/app/connectors/drivers/`: `s3_driver.py`, `azure_driver.py`, `gcs_driver.py`.
8. **`app/ai/app/connectors/service.py`** — register the three drivers in `_DRIVERS`.
9. **`app/ai/pyproject.toml`** — add `boto3`, `azure-storage-blob`, `google-cloud-storage` to the existing `[project.optional-dependencies] cloud` extra (alongside `google-cloud-bigquery`, `snowflake-connector-python`).

`AddConnectorModal.tsx` and `ConnectorsService` need no changes.

## Driver design

Each driver exposes the same two functions as every other driver (`test(config, secrets) -> TestResult`, `sync(config, secrets) -> SyncResult`), following `http_driver.py`'s file/format handling and `bigquery_driver.py`'s optional-SDK + credentials pattern.

- **`test()`**: validate required fields are present, then do a cheap existence check — S3 `head_bucket`, Azure `get_container_properties`, GCS `bucket.exists()`. Missing SDK is caught as `ImportError` and returns `"<package> isn't installed (pip install '.[cloud]').`", matching `bigquery_driver.test()`. Any other exception returns `TestResult(False, f"Couldn't connect: {e}")`.
- **`sync()`**: list objects under the bucket + prefix, capped at `OBJECT_CAP = 200` (`# ponytail: fixed cap, raise or paginate if a real bucket needs more`). Keep keys ending in `.csv`, `.parquet`, or `.json`; skip directory-marker keys (trailing `/`, zero size). Read each into a pandas DataFrame via a shared `_read(bytes, extension)` helper (extends `http_driver._detect_format` with a json branch: `pd.read_json`). Emit one `DatasetResult(name=<basename without extension>, columns=.., row_count=len(df), sample_rows=df.head(5)...)` per object. A single bad object is caught per-iteration and skipped (message logged) rather than failing the whole sync — same resilience shape as `bigquery_driver`'s per-table loop, just applied per-object instead of failing outright.
- **`rows` stays unset** (`None`). The project's own plan doc (`docs/superpowers/plans/2026-07-13-real-data-grounding.md`, Task 4) explicitly scopes full-row loading to SQL-native drivers only (Postgres/MySQL/SQLite) and leaves Mongo/HTTP/BigQuery/Snowflake as discovery + 5-row-preview only. S3/Azure/GCS are file-based like HTTP, so they follow that same precedent: sync gives table discovery and a preview, not full SQL-queryable data. (`connectors_service.sync_connector` already no-ops the DuckDB load step when `dataset.rows` is falsy, so this is a no-op integration, not a new gap.)

**Auth specifics**:
- S3: `boto3.client("s3", aws_access_key_id=..., aws_secret_access_key=..., region_name=...)` — static keys only, no IAM-role/profile fallback (matches the mockup's explicit key fields).
- Azure: `BlobServiceClient.from_connection_string(secrets["connectionString"]).get_container_client(container)`.
- GCS: `storage.Client.from_service_account_info(json.loads(secrets["serviceAccountJson"]))`, mirroring `bigquery_driver._client()`.

## Error handling

Same contract as every existing driver: `test()`/`sync()` never raise — all failure paths return `ok=False` with a human-readable `message`. Per-object read failures inside `sync()` are swallowed and the object is skipped, so one malformed file doesn't abort discovery of the rest of the bucket.

## Testing

Match the project's existing coverage depth for this driver tier: BigQuery, Snowflake and HTTP currently ship without a dedicated driver test file (only `mongodb_driver` and `sqlite_driver` have one, testing pure-logic helpers like value coercion). For S3/Azure/GCS, add one thin test file per driver covering the pure-logic pieces that don't require a live/mocked cloud SDK — extension filtering and format dispatch — at the same level BigQuery/HTTP have today. No broader test investment unless asked.

## Out of scope

- Object pagination beyond the 200-object cap.
- IAM role assumption / workload identity / SDK default-credential chains — static keys and connection strings only, matching the mockup.
- Full-row loading into DuckDB for these engines (see precedent above).
- Any change to `AddConnectorModal.tsx`, `ConnectorsService`, or the encryption/masking pipeline — all already generic.
