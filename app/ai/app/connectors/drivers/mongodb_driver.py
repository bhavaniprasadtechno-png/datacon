import logging
from pymongo import MongoClient
from app.connectors.types import TestResult, SyncResult, DatasetResult

ROW_CAP = 20_000

logger = logging.getLogger("app.connectors.drivers.mongodb")


def _client(secrets: dict) -> MongoClient:
    uri = secrets.get("uri")
    if not uri:
        raise ValueError("Connection URI is required.")
    return MongoClient(uri, serverSelectionTimeoutMS=5000)


def test(config: dict, secrets: dict) -> TestResult:
    db_name = config.get("database")
    logger.info("[MongoDB] Testing connection for database '%s'...", db_name)
    if not secrets.get("uri") or not db_name:
        logger.warning("[MongoDB] Connection test failed: missing URI or database in config.")
        return TestResult(False, "Connection URI and database are required.")
    try:
        client = _client(secrets)
        client.admin.command("ping")
        client.close()
        logger.info("[MongoDB] Connection test succeeded.")
        return TestResult(True, "Connection succeeded.")
    except Exception as e:
        logger.exception("[MongoDB] Connection test failed: %s", e)
        return TestResult(False, f"Couldn't connect: {e}")


def _to_cell(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def sync(config: dict, secrets: dict) -> SyncResult:
    """Best-effort schema discovery: MongoDB is schemaless, so 'columns' is
    derived from a sample document's top-level keys rather than a real schema.
    Full (capped) row data is flattened against that same column list so it
    can be loaded into the query engine like any SQL-native driver's rows."""
    try:
        db_name = config.get("database")
        logger.info("[MongoDB] Sync starting for database: '%s'...", db_name)
        client = _client(secrets)
        db = client[db_name]
        collections = db.list_collection_names()
        logger.info("[MongoDB] Discovered %d collections: %s", len(collections), collections)
        datasets = []
        for name in collections:
            coll = db[name]
            row_count = coll.estimated_document_count()
            logger.info("[MongoDB] Discovered collection '%s' (estimated docs: %d). Fetching up to cap %d...", name, row_count, ROW_CAP)
            docs = list(coll.find().limit(ROW_CAP))
            columns = list(docs[0].keys()) if docs else []
            logger.info("[MongoDB] Collection '%s': fetched %d documents. Top-level keys discovered: %s", name, len(docs), columns)
            rows = [tuple(_to_cell(doc.get(c)) for c in columns) for doc in docs]
            sample_rows = [[str(v) for v in row] for row in rows[:5]]
            logger.info("[MongoDB] Collection '%s': flattened %d rows for DuckDB sync.", name, len(rows))
            datasets.append(DatasetResult(name=name, columns=columns, row_count=row_count, sample_rows=sample_rows, rows=rows))
        client.close()
        logger.info("[MongoDB] Sync completed successfully for database: '%s'", db_name)
        return SyncResult(True, f"Discovered {len(datasets)} collection(s).", datasets)
    except Exception as e:
        logger.exception("[MongoDB] Sync failed: %s", e)
        return SyncResult(False, f"Sync failed: {e}", [])
