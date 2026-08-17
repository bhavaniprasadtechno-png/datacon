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


def normalize(dataset: str, columns: list[str], rows: list[list[Any]], sql: str = "") -> NormalizedResult:
    normalized_columns = []
    for i, name in enumerate(columns):
        values = [row[i] for row in rows]
        role, value_type = _classify(name, values)
        normalized_columns.append(NormalizedColumn(name=name, role=role, value_type=value_type))
    return NormalizedResult(dataset=dataset, row_count=len(rows), columns=normalized_columns, rows=rows, sql=sql)
