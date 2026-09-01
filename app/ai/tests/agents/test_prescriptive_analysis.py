import pandas as pd
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from app.agents.prescriptive import (
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
    assert PrescriptiveAnalysis is DiagnosticAnalysis
    assert prescriptiveanalysis is DiagnosticAnalysis
    assert PrescriptiveAnalysisProcess is DiagnosticAnalysis
    assert diagnosticanalysis is DiagnosticAnalysis
    assert DiagnosticAnalysisProcess is DiagnosticAnalysis


def test_load_yaml_schema_from_content():
    yaml_content = """
    tables:
      - table_name: sales_data
        description: Sales and revenue records
        primary_key: sale_id
        columns:
          - name: sale_id
            type: VARCHAR
          - name: revenue
            type: FLOAT
            is_measure: true
          - name: discount_rate
            type: FLOAT
    """
    schema = load_yaml_schema_from_content(yaml_content)
    assert "sales_data" in schema
    assert schema["sales_data"]["description"] == "Sales and revenue records"
    assert "sale_id" in schema["sales_data"]["primary_key"]
    assert len(schema["sales_data"]["columns"]) == 3


def test_spec_caching_and_extraction_prescriptive():
    schema = {
        "sales": {
            "columns": [
                {"name": "revenue"},
                {"name": "region"},
                {"name": "discount"}
            ]
        }
    }
    pa = PrescriptiveAnalysis(schema_info=schema, mode="prescriptive")
    
    with patch("app.agents.prescriptive.get_together_chat_completion") as mock_llm:
        mock_llm.return_value = '```json\n{"target_metric": "revenue", "dimension_columns": ["region"], "driver_columns": ["discount"]}\n```'
        spec1 = pa.get_diagnostic_spec("how do we optimize revenue?")
        assert spec1["target_metric"] == "revenue"
        assert spec1["dimension_columns"] == ["region"]
        assert spec1["driver_columns"] == ["discount"]
        
        # Second call should use cache without calling LLM again
        mock_llm.reset_mock()
        spec2 = pa.get_prescriptive_spec("how do we optimize revenue?")
        assert spec2 == spec1
        mock_llm.assert_not_called()


def test_build_sql_question():
    pa = PrescriptiveAnalysis()
    spec = {
        "target_metric": "profit_margin",
        "dimension_columns": ["segment", "channel"],
        "driver_columns": ["shipping_cost", "marketing_spend"]
    }
    question = pa.build_sql_question("what actions should we take to increase margin?", spec)
    assert "profit_margin" in question
    assert "segment, channel" in question
    assert "shipping_cost, marketing_spend" in question


def test_perform_statistical_analysis():
    pa = PrescriptiveAnalysis()
    df = pd.DataFrame({
        "revenue": [200.0, 220.0, 210.0, 240.0, 260.0, 900.0]  # with outlier
    })
    stats = pa.perform_statistical_analysis(df, target_metric="revenue")
    
    assert "variance_analysis" in stats
    var = stats["variance_analysis"]
    assert var["metric"] == "revenue"
    assert var["mean"] > 0
    assert var["min"] == 200.0
    assert var["max"] == 900.0
    
    assert len(stats["percentage_change"]) == 1
    pct = stats["percentage_change"][0]
    assert pct["direction"] == "growth"
    assert pct["overall_change_pct"] == 350.0
    
    assert len(stats["moving_averages"]) > 0
    assert len(stats["outlier_detection"]) > 0
    assert stats["outlier_detection"][0]["outlier_count"] >= 1


def test_identify_drivers():
    pa = PrescriptiveAnalysis()
    df = pd.DataFrame({
        "revenue": [100.0, 200.0, 300.0, 400.0, 500.0],
        "price": [10.0, 20.0, 30.0, 40.0, 50.0],  # perfect correlation
        "channel": ["Online", "Online", "Retail", "Retail", "Retail"]
    })
    drivers = pa.identify_drivers(df, target_metric="revenue")
    ranked = drivers["ranked_drivers"]
    assert len(ranked) > 0
    
    # Top driver should be price with high correlation
    price_driver = next(d for d in ranked if d["column"] == "price")
    assert abs(price_driver["correlation"] - 1.0) < 1e-4
    assert price_driver["domain"] == "pricing_changes"


def test_should_fetch_external_factors():
    pa = PrescriptiveAnalysis()
    assert pa.should_fetch_external_factors("what market trends and competitor moves should we counter?") is True
    assert pa.should_fetch_external_factors("show me quarterly recommendations") is False


def test_compress_helpers():
    pa = PrescriptiveAnalysis()
    
    # External result compression
    ext_data = {
        "external_context": "Title: Market Expansion Strategy\nSnippet: Competitors shifting budget to digital channels\nLink: http://example.com"
    }
    factors = pa.compress_external_result(ext_data)
    assert len(factors) == 1
    assert factors[0]["factor"] == "Market Expansion Strategy"
    assert "digital channels" in factors[0]["evidence"]
    
    # RAG result compression
    raw_rag = "Customer retention improved 15% following loyalty program launch.\nMarketing costs reduced across digital campaigns.\nNo other major events."
    rag_ev = pa.compress_rag_result(raw_rag, MAX_RAG_EVIDENCE=2)
    assert len(rag_ev) == 2
    assert "loyalty program" in rag_ev[0]


def test_build_compact_evidence():
    pa = PrescriptiveAnalysis()
    stats = {
        "variance_analysis": {"metric": "churn_rate", "mean": 3.8, "std_dev": 0.9, "min": 2.0, "max": 7.0},
        "percentage_change": [{"overall_change_pct": -12.0}],
        "outlier_detection": [{"outlier_percentage": 3.0}]
    }
    driver_info = {
        "ranked_drivers": [
            {"column": "discount_rate", "domain": "pricing_changes", "abs_influence": 0.92, "correlation": -0.92}
        ]
    }
    evidence = pa.build_compact_evidence(stats, driver_info)
    assert evidence["target"]["metric"] == "churn_rate"
    assert evidence["target"]["mean"] == 3.8
    assert len(evidence["drivers"]) == 1
    assert evidence["drivers"][0]["driver"] == "discount_rate"


def test_perform_llm_business_reasoning_prescriptive():
    pa = PrescriptiveAnalysis(mode="prescriptive")
    spec = {"target_metric": "churn_rate"}
    evidence = {
        "statistics": {"metric": "churn_rate", "mean": 3.8},
        "drivers": [{"driver": "discount_rate", "abs_influence": 0.92}]
    }
    
    with patch("app.agents.prescriptive.get_together_chat_completion") as mock_llm:
        mock_llm.return_value = "1. Expand targeted discounts for at-risk tiers.\n2. Reallocate marketing budget."
        report = pa.perform_llm_business_reasoning(
            user_query="how do we reduce churn?",
            spec=spec,
            evidence=evidence,
            mode="prescriptive"
        )
        assert "Expand targeted discounts" in report
        mock_llm.assert_called_once()
        args, kwargs = mock_llm.call_args
        assert kwargs.get("agent_name") == "Prescriptive Strategy Agent"
        messages = kwargs.get("messages", [])
        assert any("Executive Prescriptive Business Strategist" in m["content"] for m in messages if m["role"] == "system")


def test_analyze_and_evaluate_prescriptive_flow():
    schema = {"orders": {"columns": [{"name": "price"}, {"name": "discount"}]}}
    pa = PrescriptiveAnalysis(schema_info=schema, mode="prescriptive")
    
    fake_df = pd.DataFrame({"price": [100, 120, 150], "discount": [5, 10, 15]})
    mock_query_gpt = MagicMock()
    mock_query_gpt._find_exact_match.return_value = (None, None)
    mock_query_gpt.similarity_matcher.find_similar_query.return_value = (None, None, 0.0)
    mock_query_gpt._execute_sql_pipeline.return_value = {
        "sql": "SELECT price, discount FROM orders",
        "results": fake_df
    }
    mock_query_gpt.self_answer_agent._get_vector_db_answer.return_value = "Customer playbooks recommend personalized offers."
    
    with patch("app.agents.prescriptive.get_together_chat_completion") as mock_llm:
        mock_llm.side_effect = [
            '```json\n{"target_metric": "price", "dimension_columns": [], "driver_columns": ["discount"]}\n```',
            "Prescriptive Recommendations: 1. Optimize discount tiers to maximize revenue."
        ]
        
        result = pa.analyze_and_evaluate("what strategies will boost price realization?", query_gpt=mock_query_gpt)
        assert result["status"] == "success"
        assert result["mode"] == "prescriptive"
        assert result["sql"] == "SELECT price, discount FROM orders"
        assert result["row_count"] == 3
        assert "Prescriptive Recommendations" in result["explanation"]
        assert "statistics" in result["prescriptive_eval_info"]
        assert "drivers" in result["prescriptive_eval_info"]


def test_run_prescriptive_evaluation():
    pa = PrescriptiveAnalysis(mode="prescriptive")
    df = pd.DataFrame({
        "sales": [100.0, 120.0, 140.0],
        "discount": [5.0, 10.0, 15.0]
    })
    pa_details = {
        "target_metric": "sales",
        "driver_columns": ["discount"],
        "reasoning": "Prescriptive revenue strategy"
    }
    
    with patch("app.agents.prescriptive.get_together_chat_completion") as mock_llm:
        mock_llm.return_value = "Strategic actions: Adjust discount structures across accounts."
        res = pa.run_prescriptive_evaluation(df, pa_details)
        assert res["status"] == "success"
        assert res["mode"] == "prescriptive"
        assert "Strategic actions" in res["business_reasoning"]
        assert "statistical_analysis" in res
        assert "driver_identification" in res
