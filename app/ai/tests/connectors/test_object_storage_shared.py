import io

import pandas as pd
from app.connectors.drivers._object_storage import is_data_object, dataset_name, read_table


def test_is_data_object_accepts_supported_extensions():
    assert is_data_object("exports/sales.csv") is True
    assert is_data_object("exports/sales.parquet") is True
    assert is_data_object("exports/sales.json") is True


def test_is_data_object_rejects_unsupported_extensions_and_directory_markers():
    assert is_data_object("exports/readme.txt") is False
    assert is_data_object("exports/sales/2026/") is False


def test_dataset_name_strips_prefix_and_extension():
    assert dataset_name("exports/sales/2026/orders.csv") == "orders"
    assert dataset_name("orders.PARQUET") == "orders"


def test_read_table_parses_csv_bytes():
    df = read_table(b"a,b\n1,2\n3,4\n", "exports/data.csv")
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 2


def test_read_table_parses_json_bytes():
    df = read_table(b'[{"a": 1, "b": 2}, {"a": 3, "b": 4}]', "exports/data.json")
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 2


def test_read_table_parses_parquet_bytes():
    buf = io.BytesIO()
    pd.DataFrame({"a": [1, 3], "b": [2, 4]}).to_parquet(buf)
    df = read_table(buf.getvalue(), "exports/data.parquet")
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 2
