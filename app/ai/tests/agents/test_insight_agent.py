"""Unit tests for InsightAgent and insight_analyzer context builder."""
from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest

from app.agents.descriptive import InsightAgent
from app.agents.insight_analyzer import (
    analyze_anomaly,
    analyze_comparison,
    analyze_ranking,
    analyze_time_series,
    build_insight_context,
    determine_analytical_intent,
    get_output_token_budget,
)


# ============================================================================
# CONTEXT BUILDER & ANALYZER TESTS
# ============================================================================

def test_build_insight_context_empty_or_none():
    res_none = build_insight_context(None, "what is revenue?")
    assert res_none["intent"] == "empty"
    assert "0 rows" in res_none["formatted_context"]

    empty_df = pd.DataFrame()
    res_empty = build_insight_context(empty_df, "what is revenue?")
    assert res_empty["intent"] == "empty"
    assert "0 rows" in res_empty["formatted_context"]


def test_determine_analytical_intent():
    # 1. 1-row DataFrame -> aggregate
    df_1row = pd.DataFrame({"total_revenue": [150000.0]})
    assert determine_analytical_intent("what is total revenue?", df_1row) == "aggregate"

    # 2. Anomaly keywords
    df_anomaly = pd.DataFrame({"month": ["2023-01", "2023-02", "2023-03"], "sales": [100, 500, 110]})
    assert determine_analytical_intent("why was there a sudden spike in sales?", df_anomaly) == "anomaly"

    # 3. Comparison keywords
    df_comp = pd.DataFrame({"region": ["North", "South"], "sales": [12000, 15000]})
    assert determine_analytical_intent("compare North vs South region sales", df_comp) == "comparison"

    # 4. Ranking keywords
    df_rank = pd.DataFrame({
        "category": [f"Cat_{i}" for i in range(10)],
        "revenue": [1000 - i * 50 for i in range(10)]
    })
    assert determine_analytical_intent("top 5 product categories by revenue", df_rank) == "ranking"

    # 5. Time series keywords
    df_ts = pd.DataFrame({
        "month": [f"2023-{i:02d}" for i in range(1, 13)],
        "revenue": [10000 + i * 500 for i in range(1, 13)]
    })
    assert determine_analytical_intent("monthly revenue trend over time", df_ts) == "time_series"


def test_analyze_time_series():
    # 24 months of data spanning 2022 and 2023
    months = [f"2022-{i:02d}" for i in range(1, 13)] + [f"2023-{i:02d}" for i in range(1, 13)]
    revenues = [1000 + i * 100 for i in range(24)]
    df = pd.DataFrame({"month": months, "revenue": revenues})

    analysis = analyze_time_series(df, "monthly revenue trend")
    assert analysis["period_count"] == 24
    assert analysis["start_period"] == "2022-01"
    assert analysis["end_period"] == "2023-12"
    assert analysis["overall_change_pct"] > 0
    assert analysis["peak_period"]["period"] == "2023-12"
    assert analysis["trough_period"]["period"] == "2022-01"
    assert analysis["yearly_summary"] is not None
    assert len(analysis["yearly_summary"]) == 2


def test_analyze_ranking_and_pareto():
    categories = [f"Category_{i}" for i in range(1, 16)]
    # Top 3 command most of the revenue
    revenues = [50000, 30000, 20000] + [1000 for _ in range(12)]
    df = pd.DataFrame({"product_category": categories, "revenue": revenues})

    analysis = analyze_ranking(df, "top product categories")
    assert analysis["total_categories_or_items"] == 15
    assert len(analysis["top_items"]) == 5
    assert analysis["top_items"][0]["entity"] == "Category_1"
    assert analysis["top_items"][0]["rank"] == 1
    assert analysis["top_3_cumulative_share_pct"] > 80.0
    assert "Highly concentrated" in analysis["concentration_insight"]
    assert analysis["leader_gap"] is not None
    assert analysis["leader_gap"]["leader"] == "Category_1"
    assert analysis["leader_gap"]["runner_up"] == "Category_2"


def test_analyze_comparison():
    df_h2h = pd.DataFrame({
        "plan_type": ["Standard", "Enterprise"],
        "mrr": [25000.0, 75000.0]
    })
    analysis = analyze_comparison(df_h2h, "Standard vs Enterprise MRR")
    assert "head_to_head" in analysis
    h2h = analysis["head_to_head"]
    assert h2h["higher_performer"] == "Enterprise"
    assert h2h["ratio"] == 3.0
    assert h2h["percentage_change"] == 200.0


def test_analyze_anomaly():
    # Normal data around 100 with one huge spike and one plunge
    vals = [100.0, 102.0, 98.0, 101.0, 99.0, 850.0, 100.0, 97.0, 5.0, 101.0]
    labels = [f"Day_{i}" for i in range(1, 11)]
    df = pd.DataFrame({"day": labels, "value": vals})

    analysis = analyze_anomaly(df, "check anomalies in values")
    assert analysis["anomalies_detected_count"] >= 1
    detected = analysis["detected_anomalies"]
    assert any("Day_6" in a["period_or_entity"] for a in detected)


def test_get_output_token_budget():
    assert get_output_token_budget("aggregate") == 220
    assert get_output_token_budget("time_series") == 550
    assert get_output_token_budget("ranking") == 420
    assert get_output_token_budget("anomaly") == 480


# ============================================================================
# INSIGHT AGENT TESTS
# ============================================================================

def test_insight_agent_empty_result():
    agent = InsightAgent(model_name="test-model")
    assert agent.model_name == "test-model"

    # None DataFrame
    res = agent.generate_insights("total sales?", None)
    assert res == "No data matched your query."

    # Empty DataFrame
    res_empty = agent.generate_insights("total sales?", pd.DataFrame())
    assert res_empty == "No data matched your query."


def test_insight_agent_successful_generation():
    agent = InsightAgent()
    df = pd.DataFrame({
        "category": ["Electronics", "Furniture", "Apparel"],
        "revenue": [120000.0, 85000.0, 45000.0]
    })

    mock_llm_response = (
        "1. Total revenue across categories reached $250,000.\n"
        "2. Electronics dominated performance with $120,000 (48.0% share).\n"
        "3. Furniture followed at $85,000 with a 34.0% share."
    )

    with patch("app.agents.descriptive.get_together_chat_completion", return_value=mock_llm_response) as mock_llm:
        insights = agent.generate_insights(
            user_query="top categories by revenue",
            results_df=df,
            sql_query="SELECT category, revenue FROM sales ORDER BY revenue DESC;"
        )

        assert mock_llm.called
        call_kwargs = mock_llm.call_args[1]
        assert call_kwargs["agent_name"] == "InsightGenerator"
        prompt_content = call_kwargs["messages"][0]["content"]
        assert "User Question: \"top categories by revenue\"" in prompt_content
        assert "Electronics" in prompt_content
        assert "CRITICAL INSTRUCTIONS:" in prompt_content

        assert insights == mock_llm_response


def test_insight_agent_error_handling():
    agent = InsightAgent()
    df = pd.DataFrame({"revenue": [1000.0, 2000.0]})

    with patch("app.agents.descriptive.get_together_chat_completion", side_effect=RuntimeError("Rate limit exceeded")):
        insights = agent.generate_insights(
            user_query="total revenue",
            results_df=df
        )

        assert "Insight generation failed: Rate limit exceeded" in insights
        assert "Please review the raw data." in insights


@pytest.mark.asyncio
async def test_insight_agent_awaitable_compatibility():
    """Verify that InsightAgent.generate_insights can be invoked both synchronously and with await."""
    agent = InsightAgent()
    df = pd.DataFrame({"revenue": [50000.0, 75000.0]})

    mock_response = "Revenue peaked at $75,000, achieving 50.0% period-over-period growth."

    with patch("app.agents.descriptive.get_together_chat_completion", return_value=mock_response):
        # 1. Sync invocation
        sync_res = agent.generate_insights("revenue growth", df)
        assert isinstance(sync_res, str)
        assert sync_res == mock_response

        # 2. Async / await invocation
        async_res = await agent.generate_insights("revenue growth", df)
        assert isinstance(async_res, str)
        assert async_res == mock_response


def test_insight_agent_backward_compatibility_args():
    """Verify backwards-compatibility with (user_query, filtered_columns, filtered_rows, sql=...) signature."""
    agent = InsightAgent()
    cols = ["department", "headcount"]
    rows = [["Engineering", 42], ["Sales", 28]]

    mock_response = "Engineering leads department headcount at 42 employees (60.0% of total)."

    with patch("app.agents.descriptive.get_together_chat_completion", return_value=mock_response) as mock_llm:
        res = agent.generate_insights(
            "headcount by department",
            cols,
            rows,
            sql="SELECT department, headcount FROM depts;"
        )
        assert mock_llm.called
        assert res == mock_response
