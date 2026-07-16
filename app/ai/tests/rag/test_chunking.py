from app.rag.chunking import parse_csv


def test_parse_csv_returns_full_dataframe_alongside_the_preview():
    data = b"region,revenue\nNA,10.5\nEMEA,20.0\nAPAC,5.0\n"
    columns, row_count, sample_rows, df = parse_csv(data)

    assert columns == ["region", "revenue"]
    assert row_count == 3
    assert len(sample_rows) == 3
    assert len(df) == 3
    assert list(df.columns) == ["region", "revenue"]
    assert df["revenue"].tolist() == [10.5, 20.0, 5.0]


def test_parse_csv_non_utf8_encoding():
    # 0x84 is invalid UTF-8 but represents the low-double quote '„' in Windows-1252 (cp1252)
    data = b"region,description\nEurope,\x84quote\x84\n"
    columns, row_count, sample_rows, df = parse_csv(data)

    assert columns == ["region", "description"]
    assert row_count == 1
    assert df["description"].iloc[0] == "„quote„"

