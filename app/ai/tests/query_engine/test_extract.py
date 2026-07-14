from app.query_engine.extract import column_index


def test_returns_index_of_first_matching_keyword():
    assert column_index(["month", "total_revenue"], "revenue", "amount") == 1


def test_is_case_insensitive():
    assert column_index(["Region", "Revenue"], "revenue") == 1


def test_checks_keyword_groups_in_priority_order():
    # "churn" matches both columns; scanning left-to-right for THIS keyword
    # returns the first column, regardless of which keyword group found it.
    assert column_index(["prev_churn_pct", "churn_pct"], "churn") == 0


def test_returns_minus_one_when_nothing_matches():
    assert column_index(["a", "b"], "revenue") == -1


def test_returns_minus_one_for_empty_columns():
    assert column_index([], "revenue") == -1
