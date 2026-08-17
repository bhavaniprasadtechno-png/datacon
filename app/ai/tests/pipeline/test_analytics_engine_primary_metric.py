from app.pipeline.analytics_engine import primary_metric
from app.pipeline.normalizer import normalize


def test_primary_metric_uses_row_count_for_an_entity_listing_result():
    result = normalize("customers", ["customer_id", "name"], [["CUS-1", "Nimbus"], ["CUS-2", "Fenwick"]])
    metric = primary_metric(result, metric_id="total_customers", label="Total Customers")
    assert metric.value == 2
    assert metric.format == "number"


def test_primary_metric_uses_the_cell_value_for_a_pre_aggregated_single_row_result():
    result = normalize("leads", ["total_leads"], [[3]])
    metric = primary_metric(result, metric_id="total_leads", label="Total Leads")
    assert metric.value == 3


def test_primary_metric_uses_percentage_format_for_a_pre_aggregated_percentage_column():
    result = normalize("leads", ["conversion_rate"], [[75.0]])
    metric = primary_metric(result, metric_id="conversion_rate", label="Conversion Rate")
    assert metric.value == 75.0
    assert metric.format == "percentage"

    result = normalize("leads", ["conversion_pct"], [[75.0]])
    metric = primary_metric(result, metric_id="conversion_pct", label="Conversion Rate")
    assert metric.format == "percentage"


def test_primary_metric_uses_currency_format_for_a_pre_aggregated_currency_column():
    result = normalize("orders", ["revenue"], [[64200.0]])
    metric = primary_metric(result, metric_id="revenue", label="Revenue")
    assert metric.value == 64200.0
    assert metric.format == "currency"


def test_primary_metric_falls_back_to_row_count_when_more_than_one_row_is_returned():
    result = normalize("orders", ["amount", "region"], [[10.0, "NA"], [20.0, "EMEA"]])
    metric = primary_metric(result, metric_id="total_orders", label="Total Orders")
    assert metric.value == 2


def test_primary_metric_falls_back_to_row_count_when_a_single_row_has_multiple_measures():
    result = normalize("orders", ["amount", "tax"], [[10.0, 1.0]])
    metric = primary_metric(result, metric_id="total_orders", label="Total Orders")
    assert metric.value == 1
