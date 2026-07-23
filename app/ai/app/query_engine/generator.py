import logging

from app.config import settings

logger = logging.getLogger("app.query_engine.generator")

SYSTEM_PROMPT = (
    "You translate a business question into a single read-only DuckDB SQL query "
    "against the given schema. Reply with ONLY the SQL query — no explanation, no "
    "markdown fences. The query MUST start with SELECT or WITH and reference only "
    "the tables and columns listed in the schema. If the question cannot be "
    "answered from the schema, reply with exactly: NO_ANSWER"
)


def _get_connector_metadata() -> dict[str, dict]:
    if not settings.database_url:
        return {}
    import psycopg2
    import json
    try:
        conn = psycopg2.connect(settings.database_url)
        cur = conn.cursor()
        cur.execute("SELECT id, name, engine, config FROM connectors")
        rows = cur.fetchall()
        metadata = {}
        for row in rows:
            conn_id, name, engine, config_val = row
            config = config_val if isinstance(config_val, dict) else json.loads(config_val)
            metadata[conn_id] = {
                "name": name,
                "engine": engine,
                "database": config.get("database") or config.get("databaseName") or config.get("filePath")
            }
        cur.close()
        conn.close()
        return metadata
    except Exception as e:
        logger.warning("[Generator] Failed to fetch connector metadata: %s", e)
        return {}


def _get_datasource_metadata() -> dict[str, dict]:
    if not settings.database_url:
        return {}
    import psycopg2
    try:
        conn = psycopg2.connect(settings.database_url)
        cur = conn.cursor()
        cur.execute("SELECT id, title, filename FROM data_sources")
        rows = cur.fetchall()
        metadata = {}
        for row in rows:
            ds_id, title, filename = row
            metadata[ds_id] = {
                "title": title,
                "filename": filename
            }
        cur.close()
        conn.close()
        return metadata
    except Exception as e:
        logger.warning("[Generator] Failed to fetch datasource metadata: %s", e)
        return {}


def _format_connector_context(metadata: dict[str, dict]) -> str:
    if not metadata:
        return ""
    lines = ["Connector Source Mappings:"]
    for conn_id, meta in metadata.items():
        db_info = f", database: '{meta['database']}'" if meta.get("database") else ""
        lines.append(f"- Prefix 'conn_{conn_id}_' corresponds to connector '{meta['name']}' (engine: {meta['engine']}{db_info})")
    return "\n".join(lines) + "\n\n"


def _format_datasource_context(metadata: dict[str, dict]) -> str:
    if not metadata:
        return ""
    lines = ["CSV File Source Mappings:"]
    for ds_id, meta in metadata.items():
        lines.append(f"- Table 'csv_{ds_id}' corresponds to uploaded file '{meta['filename']}' (title: '{meta['title']}')")
    return "\n".join(lines) + "\n\n"


def _format_schema(schema: dict[str, list[str]]) -> str:
    return "\n".join(f"- {table}({', '.join(cols)})" for table, cols in schema.items())


def _clean(text: str) -> str:
    text = text.strip().strip("`").strip()
    if text.lower().startswith("sql\n"):
        text = text[4:]
    return text.strip()


def _fallback_sql(question: str, schema: dict[str, list[str]]) -> str | None:
    if not schema:
        return None
    import re
    q_words = re.findall(r"\w+", question.lower())
    for table_name in schema.keys():
        clean_name = table_name.lower().split("_")[-1]
        full_name = table_name.lower()
        for word in q_words:
            if len(word) >= 3 and (word == clean_name or word in clean_name or clean_name in word or word in full_name):
                return f'SELECT * FROM "{table_name}" LIMIT 100;'
    first_table = list(schema.keys())[0]
    return f'SELECT * FROM "{first_table}" LIMIT 100;'


async def generate_sql(question: str, schema: dict[str, list[str]], error_context: str | None = None, model: str | None = None) -> str | None:
    """Returns a single SQL string, or fallback SQL if the provider call fails,
    or None if the schema is empty."""
    if not schema:
        return None

    if not settings.is_llm_configured:
        logger.info("[Generator] No LLM configured; using schema fallback SQL.")
        return _fallback_sql(question, schema)

    # Enrich prompt with metadata about connectors and uploaded data sources
    conn_meta = _get_connector_metadata()
    ds_meta = _get_datasource_metadata()
    connector_context = _format_connector_context(conn_meta)
    datasource_context = _format_datasource_context(ds_meta)

    prompt = (
        f"Schema:\n{_format_schema(schema)}\n\n"
        f"{connector_context}"
        f"{datasource_context}"
        f"Question: {question}"
    )
    if error_context:
        prompt += f"\n\nThe previous attempt failed:\n{error_context}\nWrite a corrected query."

    import litellm

    import os
    resolved_model = model or settings.llm_model
    if not resolved_model:
        resolved_model = f"together_ai/{settings.llm_model}"
    elif not resolved_model.startswith("together"):
        resolved_model = f"together_ai/{resolved_model}"

    for attempt in range(2):
        try:
            logger.info("[Generator] Calling LiteLLM (attempt %d/2) for model=%s...", attempt + 1, resolved_model)
            stream = await litellm.acompletion(
                model=resolved_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=1024,
                stream=True,
                timeout=25,
            )
            parts = []
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = getattr(chunk.choices[0].delta, "content", None)
                if delta:
                    parts.append(delta)
            text = _clean("".join(parts))
            logger.info("[Generator] LLM raw response text (attempt %d/2): '%s'", attempt + 1, text)
            
            if text and text.upper() != "NO_ANSWER":
                return text
            
            if text.upper() == "NO_ANSWER":
                logger.warning("[Generator] LLM declined to answer the question (returned NO_ANSWER).")
                return _fallback_sql(question, schema)
                
            logger.warning("[Generator] LLM returned empty response on attempt %d/2", attempt + 1)
        except Exception as e:
            logger.warning("[Generator] SQL generation attempt %d/2 failed: %s", attempt + 1, e)
            if attempt == 1:
                logger.warning("[Generator] All LLM SQL generation attempts failed; using schema fallback SQL.")
                return _fallback_sql(question, schema)

    return _fallback_sql(question, schema)
