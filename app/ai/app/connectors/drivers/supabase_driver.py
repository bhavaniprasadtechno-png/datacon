from app.connectors.drivers import postgres_driver
from app.connectors.types import TestResult, SyncResult


def _with_ssl_default(config: dict) -> dict:
    # Supabase requires SSL on every external connection; postgres_driver
    # defaults sslMode to "prefer" when unset, which Supabase rejects.
    return {**config, "sslMode": config.get("sslMode") or "require"}


def test(config: dict, secrets: dict) -> TestResult:
    return postgres_driver.test(_with_ssl_default(config), secrets)


def sync(config: dict, secrets: dict) -> SyncResult:
    return postgres_driver.sync(_with_ssl_default(config), secrets)
