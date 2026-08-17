from app.pipeline.normalizer import normalize


def test_classifies_numeric_column_as_a_measure():
    result = normalize("customers", ["seats"], [[10], [20], [30]])
    assert result.measures == ["seats"]
    assert result.dimensions == []


def test_classifies_text_column_as_a_categorical_dimension():
    result = normalize("customers", ["tier"], [["Enterprise"], ["Growth"]])
    assert result.dimensions == ["tier"]
    assert result.columns[0].value_type == "categorical"


def test_classifies_boolean_column_as_a_dimension_not_a_measure():
    result = normalize("customers", ["active"], [[True], [False], [True]])
    assert result.dimensions == ["active"]
    assert result.columns[0].value_type == "boolean"


def test_classifies_currency_hinted_numeric_column_by_name():
    result = normalize("customers", ["mrr"], [[4200.0], [1100.0]])
    assert result.columns[0].value_type == "currency"
    assert result.measures == ["mrr"]


def test_classifies_percentage_hinted_numeric_column_by_name():
    result = normalize("churn_scores", ["churn_rate"], [[0.12], [0.08]])
    assert result.columns[0].value_type == "percentage"


def test_classifies_iso_date_string_column_as_a_date_dimension():
    result = normalize("orders", ["created_at"], [["2026-06-29"], ["2026-06-28"]])
    assert result.columns[0].value_type == "date"
    assert result.dimensions == ["created_at"]


def test_row_count_and_rows_and_sql_are_preserved():
    rows = [["CUS-1", "Nimbus", "Enterprise"], ["CUS-2", "Fenwick", "Growth"]]
    result = normalize("customers", ["customer_id", "name", "tier"], rows, sql="SELECT * FROM customers")
    assert result.row_count == 2
    assert result.rows == rows
    assert result.sql == "SELECT * FROM customers"
    assert result.dataset == "customers"


def test_mixed_dimensions_and_measures_split_correctly():
    columns = ["customer_id", "name", "tier", "mrr", "seats", "active"]
    rows = [
        ["CUS-2231", "Nimbus Retail", "Enterprise", 4200.0, 80, True],
        ["CUS-1187", "Fenwick & Co", "Growth", 1100.0, 22, True],
    ]
    result = normalize("customers", columns, rows)
    assert set(result.dimensions) == {"customer_id", "name", "tier", "active"}
    assert set(result.measures) == {"mrr", "seats"}


def test_a_column_with_no_non_null_values_defaults_to_categorical():
    result = normalize("customers", ["notes"], [[None], [None]])
    assert result.columns[0].value_type == "categorical"
