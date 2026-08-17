from app.pipeline.normalizer import normalize
from app.pipeline.analytics_engine import count_by, count_where, percentage, rank_categories, total_count


def _customers():
    columns = ["customer_id", "name", "tier", "mrr", "seats", "active"]
    rows = [
        ["CUS-1", "Nimbus Retail", "Enterprise", 4200.0, 80, True],
        ["CUS-2", "Fenwick & Co", "Growth", 1100.0, 22, True],
        ["CUS-3", "Acme Labs", "Growth", 800.0, 10, False],
        ["CUS-4", "Globex", "Enterprise", 5000.0, 120, True],
    ]
    return normalize("customers", columns, rows)


def test_total_count_returns_the_row_count():
    assert total_count(_customers()) == 4


def test_count_where_counts_rows_matching_a_predicate():
    assert count_where(_customers(), "active", lambda v: v is True) == 3


def test_count_by_groups_rows_by_a_dimension_value():
    assert count_by(_customers(), "tier") == {"Enterprise": 2, "Growth": 2}


def test_percentage_computes_part_over_whole_as_a_rounded_percent():
    assert percentage(3, 4) == 75.0


def test_percentage_returns_zero_when_whole_is_zero():
    assert percentage(3, 0) == 0.0


def test_percentage_rounds_to_one_decimal_place():
    assert percentage(1, 3) == 33.3


def test_rank_categories_counts_and_ranks_rows_by_dimension_when_no_measure_given():
    result = normalize("tickets", ["category"], [["Billing"], ["Bug"], ["Billing"], ["Feature"], ["Bug"], ["Billing"]])
    assert rank_categories(result, "category") == [("Billing", 3), ("Bug", 2), ("Feature", 1)]


def test_rank_categories_sums_and_ranks_by_measure_when_given():
    result = normalize("sales", ["region", "revenue"], [["EMEA", 120.0], ["APAC", 95.0], ["EMEA", 30.0]])
    assert rank_categories(result, "region", "revenue") == [("EMEA", 150.0), ("APAC", 95.0)]
