from app.pipeline.normalizer import humanize_dataset_name, infer_dataset_name, normalize, sanitize_rows


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


def test_infer_dataset_name_extracts_the_unquoted_table_name():
    assert infer_dataset_name("SELECT * FROM customers") == "customers"


def test_infer_dataset_name_extracts_the_quoted_table_name_with_hyphens():
    assert infer_dataset_name('SELECT * FROM "conn_prod-postgres_customers"') == "conn_prod-postgres_customers"


def test_infer_dataset_name_falls_back_when_sql_is_empty():
    assert infer_dataset_name(None) == "results"
    assert infer_dataset_name("", fallback="revenue") == "revenue"


def test_infer_dataset_name_falls_back_when_no_from_clause_matches():
    assert infer_dataset_name("SELECT 1", fallback="revenue") == "revenue"


def test_humanize_dataset_name_strips_the_connector_sync_prefix():
    assert humanize_dataset_name("conn_cmrkfxcm4000i_customers") == "customers"


def test_humanize_dataset_name_leaves_a_name_without_the_prefix_unchanged():
    assert humanize_dataset_name("customers") == "customers"


def test_sanitize_rows_leaves_json_primitives_unchanged():
    assert sanitize_rows([["CUS-1", 4200.0, True, None]]) == [["CUS-1", 4200.0, True, None]]


def test_sanitize_rows_stringifies_non_primitive_values():
    import datetime
    assert sanitize_rows([[datetime.date(2026, 8, 1)]]) == [["2026-08-01"]]
