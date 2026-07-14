import psycopg2
from app.connectors.types import TestResult, SyncResult, DatasetResult

ROW_CAP = 20_000


def _connect(config: dict, secrets: dict):
    return psycopg2.connect(
        host=config.get("host"),
        port=int(config.get("port") or 5432),
        dbname=config.get("database"),
        user=config.get("username"),
        password=secrets.get("password", ""),
        sslmode=config.get("sslMode") or "prefer",
        connect_timeout=5,
    )


def test(config: dict, secrets: dict) -> TestResult:
    if not config.get("host") or not config.get("database") or not config.get("username"):
        return TestResult(False, "Host, database and username are required.")
    try:
        conn = _connect(config, secrets)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        conn.close()
        return TestResult(True, "Connection succeeded.")
    except Exception as e:
        return TestResult(False, f"Couldn't connect: {e}")


def sync(config: dict, secrets: dict) -> SyncResult:
    schema = config.get("schema") or "public"
    try:
        conn = _connect(config, secrets)
        cur = conn.cursor()
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s AND table_type = 'BASE TABLE'",
            (schema,),
        )
        tables = [r[0] for r in cur.fetchall()]
        datasets = []
        for table in tables:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
                (schema, table),
            )
            columns = [r[0] for r in cur.fetchall()]
            cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
            row_count = cur.fetchone()[0]
            cur.execute(f'SELECT * FROM "{schema}"."{table}" LIMIT {ROW_CAP}')
            rows = cur.fetchall()
            sample_rows = [[str(v) for v in row] for row in rows[:5]]
            datasets.append(DatasetResult(name=table, columns=columns, row_count=row_count, sample_rows=sample_rows, rows=rows))
        conn.close()
        return SyncResult(True, f"Discovered {len(datasets)} table(s) in schema {schema}.", datasets)
    except Exception as e:
        return SyncResult(False, f"Sync failed: {e}", [])
