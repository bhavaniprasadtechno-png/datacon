import logging

import pandas as pd
from app.connectors.types import TestResult, SyncResult
from app.connectors.drivers import sqlite_driver, postgres_driver, mysql_driver, mongodb_driver, http_driver, bigquery_driver, snowflake_driver
from app.query_engine import snapshot_store

logger = logging.getLogger("app.connectors.service")

_DRIVERS = {
    "sqlite": sqlite_driver,
    "postgres": postgres_driver,
    "supabase": supabase_driver,
    "mysql": mysql_driver,
    "mongodb": mongodb_driver,
    "http": http_driver,
    "bigquery": bigquery_driver,
    "snowflake": snowflake_driver,
}


def test_connection(engine: str, config: dict, secrets: dict) -> TestResult:
    logger.info("[Sync] Testing connection for engine '%s'...", engine)
    driver = _DRIVERS.get(engine)
    if not driver:
        logger.error("[Sync] Engine '%s' not supported.", engine)
        return TestResult(False, f"Unknown engine: {engine}")
    result = driver.test(config, secrets)
    logger.info("[Sync] Connection test result for engine '%s': ok=%s, message='%s'", engine, result.ok, result.message)
    return result


def sync_connector(engine: str, config: dict, secrets: dict, connector_id: str | None = None) -> SyncResult:
    logger.info("[Sync] Starting sync for connector %s with engine '%s'...", connector_id, engine)
    driver = _DRIVERS.get(engine)
    if not driver:
        logger.error("[Sync] Engine '%s' not supported.", engine)
        return SyncResult(False, f"Unknown engine: {engine}", [])
        
    result = driver.sync(config, secrets)
    logger.info("[Sync] Driver sync result: ok=%s, message='%s', datasets_found=%d", result.ok, result.message, len(result.datasets))
    
    if result.ok and connector_id:
        prefix = f"conn_{connector_id}_"
        logger.info("[Sync] Dropping existing DuckDB tables with prefix '%s'...", prefix)
        snapshot_store.drop_datasets(prefix)
        for dataset in result.datasets:
            if dataset.rows:
                table_name = f"conn_{connector_id}_{dataset.name}"
                logger.info("[Sync] Loading dataset '%s' into DuckDB table '%s' (%d rows, %d columns)...", dataset.name, table_name, len(dataset.rows), len(dataset.columns))
                try:
                    snapshot_store.load_dataset(table_name, pd.DataFrame(dataset.rows, columns=dataset.columns))
                    logger.info("[Sync] Table '%s' loaded successfully.", table_name)
                except Exception as e:
                    logger.exception("[Sync] Failed to load dataset %s into the query engine table %s: %s", dataset.name, table_name, e)
            else:
                logger.warning("[Sync] Dataset '%s' has 0 rows, skipping DuckDB table registration.", dataset.name)
    return result
