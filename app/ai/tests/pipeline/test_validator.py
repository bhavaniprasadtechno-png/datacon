from app.pipeline.contracts import Insight, Metric, Table, Visualization
from app.pipeline.normalizer import normalize
from app.pipeline.validator import compute_confidence, validate


def _result():
    return normalize("customers", ["customer_id", "name"], [["CUS-1", "Nimbus"]])


def test_insight_with_no_evidence_is_a_blocking_issue():
    issues = validate(metrics=[], insights=[Insight(type="positive", text="x", evidence=[])], tables=[], result=_result())
    assert any(i.severity == "blocking" and "evidence" in i.message for i in issues)


def test_insight_referencing_an_unknown_metric_is_a_blocking_issue():
    metrics = [Metric(id="total_customers", label="Total", value=1, format="number")]
    insights = [Insight(type="positive", text="x", evidence=["made_up_metric"])]
    issues = validate(metrics=metrics, insights=insights, tables=[], result=_result())
    assert any("made_up_metric" in i.message for i in issues)


def test_insight_referencing_a_real_metric_produces_no_issue():
    metrics = [Metric(id="total_customers", label="Total", value=1, format="number")]
    insights = [Insight(type="positive", text="x", evidence=["total_customers"])]
    issues = validate(metrics=metrics, insights=insights, tables=[], result=_result())
    assert issues == []


def test_table_column_not_in_source_result_is_a_blocking_issue():
    tables = [Table(columns=["customer_id", "made_up_column"], rows=[], collapsed=True)]
    issues = validate(metrics=[], insights=[], tables=tables, result=_result())
    assert any("made_up_column" in i.message for i in issues)


def test_table_columns_that_exist_in_source_produce_no_issue():
    tables = [Table(columns=["customer_id", "name"], rows=[], collapsed=True)]
    issues = validate(metrics=[], insights=[], tables=tables, result=_result())
    assert issues == []


def test_visualization_of_type_none_carrying_data_is_a_blocking_issue():
    issues = validate(metrics=[], insights=[], tables=[], result=_result(), visualizations=[Visualization(type="none", data=[{"label": "x", "value": 1}])])
    assert any(i.severity == "blocking" and "none" in i.message for i in issues)


def test_visualization_of_type_kpi_carrying_data_is_a_blocking_issue():
    issues = validate(metrics=[], insights=[], tables=[], result=_result(), visualizations=[Visualization(type="kpi", data=[{"label": "x", "value": 1}])])
    assert any(i.severity == "blocking" and "kpi" in i.message for i in issues)


def test_visualization_of_type_kpi_with_no_data_produces_no_issue():
    issues = validate(metrics=[], insights=[], tables=[], result=_result(), visualizations=[Visualization(type="kpi")])
    assert issues == []


def test_confidence_is_low_when_the_query_did_not_succeed():
    assert compute_confidence(query_ok=False, issues=[]) == "low"


def test_confidence_is_high_when_query_succeeded_and_no_issues():
    assert compute_confidence(query_ok=True, issues=[]) == "high"


def test_confidence_is_low_when_there_is_a_blocking_issue():
    from app.pipeline.validator import ValidationIssue
    issues = [ValidationIssue(severity="blocking", message="bad")]
    assert compute_confidence(query_ok=True, issues=issues) == "low"


def test_confidence_is_medium_when_there_is_only_a_minor_issue():
    from app.pipeline.validator import ValidationIssue
    issues = [ValidationIssue(severity="minor", message="meh")]
    assert compute_confidence(query_ok=True, issues=issues) == "medium"
