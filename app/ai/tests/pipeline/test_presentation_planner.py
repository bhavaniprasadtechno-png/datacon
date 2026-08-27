from app.pipeline.contracts import Metric
from app.pipeline.normalizer import normalize
from app.pipeline.presentation_planner import category_ranking, plan_table, plan_visualization


def _customers_result():
    columns = ["customer_id", "name", "tier", "mrr", "seats", "active"]
    rows = [
        ["CUS-1", "Nimbus Retail", "Enterprise", 4200.0, 80, True],
        ["CUS-2", "Fenwick & Co", "Growth", 1100.0, 22, True],
    ]
    return normalize("customers", columns, rows)


def test_plan_visualization_picks_kpi_when_metrics_exist():
    metrics = [Metric(id="total_customers", label="Total Customers", value=4, format="number")]
    viz = plan_visualization(metrics, _customers_result())
    assert viz.type == "kpi"


def test_plan_visualization_picks_none_when_there_are_no_metrics():
    viz = plan_visualization([], _customers_result())
    assert viz.type == "none"


def test_plan_visualization_never_defaults_to_bar():
    metrics = [Metric(id="total_customers", label="Total Customers", value=4, format="number")]
    viz = plan_visualization(metrics, _customers_result())
    assert viz.type != "bar"


def _category_comparison_result():
    columns = ["category"]
    rows = [["Billing"], ["Bug"], ["Billing"], ["Feature"], ["Bug"], ["Billing"]]
    return normalize("tickets", columns, rows)


def test_plan_visualization_picks_horizontal_bar_for_a_single_category_comparison():
    viz = plan_visualization([], _category_comparison_result())
    assert viz.type == "horizontal_bar"
    assert viz.data == [
        {"label": "Billing", "value": 3},
        {"label": "Bug", "value": 2},
        {"label": "Feature", "value": 1},
    ]


def test_plan_visualization_ranks_by_measure_when_a_single_measure_is_present():
    result = normalize("sales", ["region", "revenue"], [["EMEA", 120.0], ["APAC", 95.0]])
    viz = plan_visualization([], result)
    assert viz.type == "horizontal_bar"
    assert viz.data == [{"label": "EMEA", "value": 120.0}, {"label": "APAC", "value": 95.0}]


def test_plan_visualization_picks_line_for_temporal_data():
    result = normalize("sales", ["order_date", "revenue"], [["2024-01-01", 100.0], ["2024-01-02", 150.0]])
    viz = plan_visualization([], result)
    assert viz.type == "line"
    assert viz.data == [{"label": "2024-01-01", "value": 100.0}, {"label": "2024-01-02", "value": 150.0}]


def test_plot_catalog_recommendation_picks_horizontal_bar_for_category_breakdown():
    result = normalize("products", ["category", "sales"], [["electronics_and_accessories", 500.0], ["home_and_kitchen", 350.0]])
    viz = plan_visualization([], result)
    assert viz.type == "horizontal_bar"
    assert len(viz.data) == 2


def test_category_ranking_returns_none_when_more_than_one_dimension_is_present():
    assert category_ranking(_customers_result()) is None


def test_category_ranking_returns_none_for_a_single_row():
    result = normalize("tickets", ["category"], [["Billing"]])
    assert category_ranking(result) is None


def test_plan_table_includes_all_non_internal_columns():
    table = plan_table(_customers_result())
    assert table.columns == ["customer_id", "name", "tier", "mrr", "seats", "active"]
    assert table.rows == [
        ["CUS-1", "Nimbus Retail", "Enterprise", 4200.0, 80, True],
        ["CUS-2", "Fenwick & Co", "Growth", 1100.0, 22, True],
    ]


def test_plan_table_excludes_internal_looking_columns():
    result = normalize(
        "customers",
        ["customer_id", "name", "embedding_vector", "raw_json_blob"],
        [["CUS-1", "Nimbus Retail", [0.1, 0.2], "{}"]],
    )
    table = plan_table(result)
    assert table.columns == ["customer_id", "name"]
    assert table.rows == [["CUS-1", "Nimbus Retail"]]


def test_plan_table_defaults_to_collapsed():
    table = plan_table(_customers_result())
    assert table.collapsed is True


def test_plan_table_caps_rows_at_max_rows():
    rows = [[f"CUS-{i}", "Name", "Tier", 100.0, 1, True] for i in range(30)]
    result = normalize("customers", ["customer_id", "name", "tier", "mrr", "seats", "active"], rows)
    table = plan_table(result, max_rows=20)
    assert len(table.rows) == 20
