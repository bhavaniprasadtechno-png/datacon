from dataclasses import dataclass, field


@dataclass
class TestResult:
    ok: bool
    message: str


@dataclass
class DatasetResult:
    name: str
    columns: list[str]
    row_count: int
    sample_rows: list[list[str]] = field(default_factory=list)
    rows: list[tuple] | None = None
    error: str | None = None


@dataclass
class SyncResult:
    ok: bool
    message: str
    datasets: list[DatasetResult] = field(default_factory=list)
