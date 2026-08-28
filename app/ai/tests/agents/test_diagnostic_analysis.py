import pandas as pd
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from app.agents.diagnostic import (
    DiagnosticAnalysis,
    diagnosticanalysis,
    DiagnosticAnalysisProcess,
    PrescriptiveAnalysis,
    prescriptiveanalysis,
    PrescriptiveAnalysisProcess,
    load_yaml_schema_from_content,
    SerpApiGoogleSearchTool,
)


def test_aliases():
    assert diagnosticanalysis is DiagnosticAnalysis
    assert DiagnosticAnalysisProcess is DiagnosticAnalysis
    assert PrescriptiveAnalysis is DiagnosticAnalysis
    assert prescriptiveanalysis is DiagnosticAnalysis
    assert PrescriptiveAnalysisProcess is DiagnosticAnalysis


def test_load_yaml_schema_from_content():
    yaml_content = """
    tables:
      - table_name: orders
        description: Order information
        primary_key: order_id
        columns:
          - name: order_id
            type: VARCHAR
          - name: price
            type: FLOAT
            is_measure: true
    """
    schema = load_yaml_schema_from_content(yaml_content)
    assert "orders" in schema
    assert schema["orders"]["description"] == "Order information"
    assert "order_id" in schema["orders"]["primary_key"]
    assert len(schema["orders"]["columns"]) == 2


def test_spec_caching_and_extraction():
    schema = {
        "sales": {
            "columns": [
                {"name": "revenue"},
                {"name": "region"},
                {"name": "discount"}
            ]
        }
    }
    da = DiagnosticAnalysis(schema_info=schema, mode="diagnostic")
    
    with patch("app.agents.diagnostic.get_together_chat_completion") as mock_llm:
        mock_llm.return_value = '```json\n{"target_metric": "revenue", "dimension_columns": ["region"], "driver_columns": ["discount"]}\n```'
        spec1 = da.get_diagnostic_spec("why did revenue decline?")
        assert spec1["target_metric"] == "revenue"
        assert spec1["dimension_columns"] == ["region"]
        assert spec1["driver_columns"] == ["discount"]
        
        # Second call should use cache without calling LLM again
        mock_llm.reset_mock()
        spec2 = da.get_diagnostic_spec("why did revenue decline?")
        assert spec2 == spec1
        mock_llm.assert_not_called()


def test_build_sql_question():
    da = DiagnosticAnalysis()
    spec = {
        "target_metric": "revenue",
        "dimension_columns": ["region", "channel"],
        "driver_columns": ["price", "marketing_spend"]
    }
    question = da.build_sql_question("why did sales drop?", spec)
    assert "revenue" in question
    assert "region, channel" in question
    assert "price, marketing_spend" in question


def test_perform_statistical_analysis():
    da = DiagnosticAnalysis()
    df = pd.DataFrame({
        "revenue": [100.0, 110.0, 105.0, 120.0, 130.0, 500.0]  # with outlier
    })
    stats = da.perform_statistical_analysis(df, target_metric="revenue")
    
    assert "variance_analysis" in stats
    var = stats["variance_analysis"]
    assert var["metric"] == "revenue"
    assert var["mean"] > 0
    assert var["min"] == 100.0
    assert var["max"] == 500.0
    
    assert len(stats["percentage_change"]) == 1
    pct = stats["percentage_change"][0]
    assert pct["direction"] == "growth"
    assert pct["overall_change_pct"] == 400.0
    
    assert len(stats["moving_averages"]) > 0
    assert len(stats["outlier_detection"]) > 0
    assert stats["outlier_detection"][0]["outlier_count"] >= 1


def test_identify_drivers():
    da = DiagnosticAnalysis()
    df = pd.DataFrame({
        "revenue": [100.0, 150.0, 200.0, 250.0, 300.0],
        "price": [10.0, 15.0, 20.0, 25.0, 30.0],  # perfect correlation
        "region": ["East", "East", "West", "West", "West"]
    })
    drivers = da.identify_drivers(df, target_metric="revenue")
    ranked = drivers["ranked_drivers"]
    assert len(ranked) > 0
    
    # Top driver should be price with high correlation
    price_driver = next(d for d in ranked if d["column"] == "price")
    assert abs(price_driver["correlation"] - 1.0) < 1e-4
    assert price_driver["domain"] == "pricing_changes"


def test_should_fetch_external_factors():
    da = DiagnosticAnalysis()
    assert da.should_fetch_external_factors("what market trends caused the decline?") is True
    assert da.should_fetch_external_factors("show me revenue breakdown") is False


def test_compress_helpers():
    da = DiagnosticAnalysis()
    
    # External result compression
    ext_data = {
        "external_context": "Title: Competitor Price War\nSnippet: Competitors reduced prices by 20%\nLink: http://example.com"
    }
    factors = da.compress_external_result(ext_data)
    assert len(factors) == 1
    assert factors[0]["factor"] == "Competitor Price War"
    assert "20%" in factors[0]["evidence"]
    
    # RAG result compression
    raw_rag = "Customer churn rose in EMEA due to delayed shipments.\nPricing in APAC remained steady.\nNo other major events."
    rag_ev = da.compress_rag_result(raw_rag, MAX_RAG_EVIDENCE=2)
    assert len(rag_ev) == 2
    assert "EMEA" in rag_ev[0]


def test_build_compact_evidence():
    da = DiagnosticAnalysis()
    stats = {
        "variance_analysis": {"metric": "churn_rate", "mean": 4.5, "std_dev": 1.2, "min": 2.0, "max": 8.0},
        "percentage_change": [{"overall_change_pct": 25.0}],
        "outlier_detection": [{"outlier_percentage": 5.0}]
    }
    driver_info = {
        "ranked_drivers": [
            {"column": "delivery_delay", "domain": "delivery_performance", "abs_influence": 0.85, "correlation": 0.85}
        ]
    }
    evidence = da.build_compact_evidence(stats, driver_info)
    assert evidence["target"]["metric"] == "churn_rate"
    assert evidence["target"]["mean"] == 4.5
    assert len(evidence["drivers"]) == 1
    assert evidence["drivers"][0]["driver"] == "delivery_delay"


def test_analyze_and_evaluate_flow():
    schema = {"orders": {"columns": [{"name": "price"}, {"name": "delay"}]}}
    da = DiagnosticAnalysis(schema_info=schema, mode="diagnostic")
    
    fake_df = pd.DataFrame({"price": [10, 20, 30], "delay": [1, 2, 3]})
    mock_query_gpt = MagicMock()
    mock_query_gpt._find_exact_match.return_value = (None, None)
    mock_query_gpt.similarity_matcher.find_similar_query.return_value = (None, None, 0.0)
    mock_query_gpt._execute_sql_pipeline.return_value = {
        "sql": "SELECT price, delay FROM orders",
        "results": fake_df
    }
    mock_query_gpt.self_answer_agent._get_vector_db_answer.return_value = "Incident reports show delay issues."
    
    with patch("app.agents.diagnostic.get_together_chat_completion") as mock_llm:
        mock_llm.side_effect = [
            '```json\n{"target_metric": "price", "dimension_columns": [], "driver_columns": ["delay"]}\n```',
            "Root cause analysis: Delivery delays strongly correlated with price spikes."
        ]
        
        result = da.analyze_and_evaluate("why did price spike?", query_gpt=mock_query_gpt)
        assert result["status"] == "success"
        assert result["mode"] == "diagnostic"
        assert result["sql"] == "SELECT price, delay FROM orders"
        assert result["row_count"] == 3
        assert "Root cause analysis" in result["explanation"]
        assert "statistics" in result["diagnostic_eval_info"]
        assert "drivers" in result["diagnostic_eval_info"]
