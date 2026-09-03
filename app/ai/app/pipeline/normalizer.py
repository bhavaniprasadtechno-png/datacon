"""Result Normalizer — converts an arbitrary query-engine result (columns +
rows) into a consistent internal representation the rest of the pipeline
(Analytics Engine, Insight Engine, Presentation Planner) can rely on.

Classification is deterministic, from column names and observed values —
no LLM involvement.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Any, Literal

ValueType = Literal["categorical", "numeric", "percentage", "currency", "date", "boolean"]
ColumnRole = Literal["dimension", "measure"]

_CURRENCY_HINTS = ("revenue", "mrr", "amount", "price", "cost", "arr", "spend", "net")
_PERCENTAGE_HINTS = ("pct", "percent", "rate", "ratio")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

# ponytail: single-table `FROM` match, upgrade to real SQL parsing if a
# join-heavy question ever needs the true source table name. Quoted
# alternative first — quoted identifiers (connector/csv-synced table names
# contain hyphens, which `\w` doesn't match) can hold any character except a
# closing quote.
_FROM_TABLE_RE = re.compile(r'FROM\s+(?:"([^"]+)"|([A-Za-z_]\w*))', re.IGNORECASE)
# Connector-synced tables are stored as `conn_{connectorId}_{tableName}` (see
# connectors/service.py) — strip that prefix for a human-facing label. CSV
# uploads (`csv_{documentId}`) have no recoverable human name from the table
# name alone, so they're left as-is.
_CONNECTOR_PREFIX_RE = re.compile(r"^conn_[^_]+_")


@dataclass
class NormalizedColumn:
    name: str
    role: ColumnRole
    value_type: ValueType


@dataclass
class NormalizedResult:
    dataset: str
    row_count: int
    columns: list[NormalizedColumn]
    rows: list[list[Any]]
    sql: str = ""

    @property
    def dimensions(self) -> list[str]:
        return [c.name for c in self.columns if c.role == "dimension"]

    @property
    def measures(self) -> list[str]:
        return [c.name for c in self.columns if c.role == "measure"]


def _looks_like_date(value: Any) -> bool:
    if isinstance(value, (datetime.date, datetime.datetime)):
        return True
    if isinstance(value, str):
        return bool(_ISO_DATE_RE.match(value))
    return False


def _classify(name: str, values: list[Any]) -> tuple[ColumnRole, ValueType]:
    non_null = [v for v in values if v is not None]
    if non_null and all(isinstance(v, bool) for v in non_null):
        return "dimension", "boolean"
    if non_null and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_null):
        lname = name.lower()
        if any(h in lname for h in _PERCENTAGE_HINTS):
            return "measure", "percentage"
        if any(h in lname for h in _CURRENCY_HINTS):
            return "measure", "currency"
        return "measure", "numeric"
    if non_null and all(_looks_like_date(v) for v in non_null):
        return "dimension", "date"
    return "dimension", "categorical"


def infer_dataset_name(sql: str | None, fallback: str = "results") -> str:
    if not sql:
        return fallback
    match = _FROM_TABLE_RE.search(sql)
    if not match:
        return fallback
    return match.group(1) or match.group(2)


def humanize_dataset_name(dataset: str) -> str:
    return _CONNECTOR_PREFIX_RE.sub("", dataset) or dataset


def sanitize_rows(rows: list[list[Any]]) -> list[list[Any]]:
    """Coerces any non-JSON-primitive cell (e.g. a DB-driver-specific numeric
    or date wrapper type) to a string, so raw query rows are always safe to
    hand to `normalize()` and, later, to serialize on the wire."""
    return [[v if v is None or isinstance(v, (int, float, bool, str)) else str(v) for v in row] for row in rows]


def normalize(dataset: str, columns: list[str], rows: list[list[Any]], sql: str = "") -> NormalizedResult:
    normalized_columns = []
    for i, name in enumerate(columns):
        values = [row[i] for row in rows]
        role, value_type = _classify(name, values)
        normalized_columns.append(NormalizedColumn(name=name, role=role, value_type=value_type))
    return NormalizedResult(dataset=dataset, row_count=len(rows), columns=normalized_columns, rows=rows, sql=sql)
