from app.pipeline.insight_engine import binary_split_insights, ranking_insight


def test_majority_share_produces_a_positive_insight_grounded_in_the_rate_metric():
    insights = binary_split_insights(
        subject="customers",
        matching_label="active",
        matching_count=3,
        total_count=4,
        rate_metric_id="active_rate",
        matching_metric_id="active_customers",
        total_metric_id="total_customers",
    )
    positive = next(i for i in insights if i.type == "positive")
    assert positive.text == "75.0% of customers are active."
    assert positive.evidence == ["active_rate"]


def test_nonzero_remainder_produces_an_attention_insight_grounded_in_the_raw_counts():
    insights = binary_split_insights(
        subject="customers",
        matching_label="active",
        matching_count=3,
        total_count=4,
        rate_metric_id="active_rate",
        matching_metric_id="active_customers",
        total_metric_id="total_customers",
    )
    attention = next(i for i in insights if i.type == "attention")
    assert attention.text == "1 customer is not active."
    assert attention.evidence == ["total_customers", "active_customers"]


def test_zero_remainder_produces_no_attention_insight():
    insights = binary_split_insights(
        subject="customers",
        matching_label="active",
        matching_count=4,
        total_count=4,
        rate_metric_id="active_rate",
        matching_metric_id="active_customers",
        total_metric_id="total_customers",
    )
    assert [i.type for i in insights] == ["positive"]


def test_pluralizes_the_remainder_count_correctly():
    insights = binary_split_insights(
        subject="customers",
        matching_label="active",
        matching_count=2,
        total_count=4,
        rate_metric_id="active_rate",
        matching_metric_id="active_customers",
        total_metric_id="total_customers",
    )
    attention = next(i for i in insights if i.type == "attention")
    assert attention.text == "2 customers are not active."


def test_ranking_insight_reports_the_top_category_with_its_share():
    insight = ranking_insight(subject="tickets", top_label="Billing", top_value=3, top_metric_id="top_category", total=6)
    assert insight.type == "neutral"
    assert insight.text == "Billing has the most tickets (3, 50.0%)."
    assert insight.evidence == ["top_category"]


def test_zero_total_produces_no_insights():
    insights = binary_split_insights(
        subject="customers",
        matching_label="active",
        matching_count=0,
        total_count=0,
        rate_metric_id="active_rate",
        matching_metric_id="active_customers",
        total_metric_id="total_customers",
    )
    assert insights == []
