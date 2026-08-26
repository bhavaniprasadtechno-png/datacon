import logging

import pandas as pd
from app.connectors.types import TestResult, SyncResult
from app.connectors.drivers import sqlite_driver, postgres_driver, mysql_driver, mongodb_driver, http_driver, bigquery_driver, snowflake_driver, supabase_driver, s3_driver, azure_driver, gcs_driver
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
    "s3": s3_driver,
    "azure": azure_driver,
    "gcs": gcs_driver,
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
        loaded_tables: dict[str, pd.DataFrame] = {}
        for dataset in result.datasets:
            if dataset.rows:
                table_name = f"conn_{connector_id}_{dataset.name}"
                logger.info("[Sync] Loading dataset '%s' into DuckDB table '%s' (%d rows, %d columns)...", dataset.name, table_name, len(dataset.rows), len(dataset.columns))
                try:
                    df = pd.DataFrame(dataset.rows, columns=dataset.columns)
                    snapshot_store.load_dataset(table_name, df)
                    loaded_tables[table_name] = df
                    logger.info("[Sync] Table '%s' loaded successfully.", table_name)
                except Exception as e:
                    logger.exception("[Sync] Failed to load dataset %s into the query engine table %s: %s", dataset.name, table_name, e)
            else:
                logger.warning("[Sync] Dataset '%s' has 0 rows, skipping DuckDB table registration.", dataset.name)

        if loaded_tables:
            try:
                from app.query_engine import semantic_model
                all_tables = snapshot_store.get_all_tables(sample_size=1000)
                all_tables.update(loaded_tables)
                dataset_label = config.get("database") or config.get("databaseName") or config.get("bucket") or f"{engine}_connector"
                yaml_name, yaml_path = semantic_model.generate_and_save_semantic_model(
                    tables_dict=all_tables,
                    dataset_name=str(dataset_label),
                    source_id=f"conn_{connector_id}",
                    generated_by=f"{engine}_connector_pipeline",
                )
                logger.info("[Sync] Generated semantic model YAML for connector %s: %s", connector_id, yaml_path)
            except Exception as e:
                logger.warning("[Sync] Failed to generate semantic model YAML for connector %s: %s", connector_id, e)


    return result

