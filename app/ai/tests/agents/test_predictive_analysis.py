import json
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.agents.predictive import (
    PredictiveAnalysis,
    PredictiveAnalysisProcess,
    build_join_graph,
    extract_schema_relationships,
    find_shortest_join_path,
    load_yaml_schema_from_content,
    predictiveanalysis,
    predictiveanalysisprocess,
)
from app.agents.trained_model_manager import (
    clean_model_slug,
    get_best_model_from_file_paths,
    load_and_predict_with_saved_model,
)


def test_aliases():
    assert PredictiveAnalysis is PredictiveAnalysisProcess
    assert predictiveanalysis is PredictiveAnalysisProcess
    assert predictiveanalysisprocess is PredictiveAnalysisProcess


def test_load_yaml_schema_from_content():
    yaml_content = """
    tables:
      - table_name: orders
        description: Order items and totals
        primary_key: order_id
        columns:
          - name: order_id
            type: VARCHAR
          - name: price
            type: FLOAT
            is_measure: true
          - name: freight_value
            type: FLOAT
    """
    schema = load_yaml_schema_from_content(yaml_content)
    assert "orders" in schema
    assert schema["orders"]["description"] == "Order items and totals"
    assert "order_id" in schema["orders"]["primary_key"]
    assert len(schema["orders"]["columns"]) == 3


def test_format_schema_summary():
    schema = {
        "orders": {
            "description": "Order records",
            "primary_key": ["order_id"],
            "foreign_keys": [{"from_column": "customer_id", "to_table": "customers", "to_column": "customer_id"}],
            "columns": [
                {"name": "order_id", "type": "VARCHAR", "description": "Primary ID"},
                {"name": "price", "type": "FLOAT", "description": "Item price", "is_measure": True},
            ],
        }
    }
    pa = PredictiveAnalysisProcess(schema_info=schema)
    summary = pa._format_schema_summary()
    assert "Table 'orders': Order records" in summary
    assert "Primary Key: order_id" in summary
    assert "orders.customer_id -> customers.customer_id" in summary
    assert "orders.price (FLOAT, measure): Item price" in summary


def test_analyze_regression():
    schema = {
        "orders": {
            "columns": [{"name": "price"}, {"name": "freight_value"}]
        }
    }
    pa = PredictiveAnalysisProcess(schema_info=schema)

    mock_json = """```json
    {
        "problem_type": "regression",
        "target_column": "orders.price",
        "feature_columns": ["orders.freight_value"],
        "reasoning": "Predicting numerical price based on freight value."
    }
    ```"""

    with patch("app.agents.predictive.get_together_chat_completion", return_value=mock_json):
        result = pa.analyze("predict price based on freight")
        assert result["problem_type"] == "regression"
        assert result["target_column"] == "orders.price"
        assert result["feature_columns"] == ["orders.freight_value"]
        assert "Linear Regression" in result["models"]
        assert "Random Forest Regression" in result["models"]
        assert "XGBoost Regression" in result["models"]


def test_analyze_classification():
    schema = {
        "customers": {
            "columns": [{"name": "churn"}, {"name": "tenure"}]
        }
    }
    pa = PredictiveAnalysisProcess(schema_info=schema)

    # Test auto table-prefixing when model returns bare column name
    mock_json = """```json
    {
        "problem_type": "classification",
        "target_column": "churn",
        "feature_columns": ["tenure"],
        "reasoning": "Predicting customer churn status."
    }
    ```"""

    with patch("app.agents.predictive.get_together_chat_completion", return_value=mock_json):
        result = pa.analyze("predict customer churn")
        assert result["problem_type"] == "classification"
        assert result["target_column"] == "customers.churn"
        assert result["feature_columns"] == ["customers.tenure"]
        assert "Logistic Regression" in result["models"]
        assert "Random Forest Classification" in result["models"]
        assert "XGBoost Classification" in result["models"]


def test_generate_sql_for_features_single_table():
    schema = {
        "orders": {
            "columns": [{"name": "price"}, {"name": "freight_value"}]
        }
    }
    pa = PredictiveAnalysisProcess(schema_info=schema)
    sql = pa.generate_sql_for_features("orders.price", ["orders.freight_value"])
    assert "SELECT orders.price, orders.freight_value FROM orders" in sql


def test_generate_sql_for_features_multi_table_join():
    schema = {
        "orders": {
            "columns": [{"name": "order_id"}, {"name": "customer_id"}],
            "foreign_keys": [{"from_column": "customer_id", "to_table": "customers", "to_column": "customer_id"}],
            "primary_key": ["order_id"]
        },
        "customers": {
            "columns": [{"name": "customer_id"}, {"name": "state"}],
            "primary_key": ["customer_id"]
        }
    }
    pa = PredictiveAnalysisProcess(schema_info=schema)
    sql = pa.generate_sql_for_features("orders.order_id", ["customers.state"])
    assert "FROM orders" in sql
    assert "JOIN customers ON orders.customer_id = customers.customer_id" in sql
    assert "orders.order_id" in sql
    assert "customers.state" in sql


def test_fetch_predictive_data():
    pa = PredictiveAnalysisProcess()
    fake_df = pd.DataFrame({"orders.price": [10.0, 20.0], "orders.freight": [2.0, 4.0]})
    mock_connector = MagicMock()
    mock_connector.execute_sql.return_value = fake_df

    pa_details = {
        "target_column": "orders.price",
        "feature_columns": ["orders.freight"]
    }
    res = pa.fetch_predictive_data(pa_details, data_connector=mock_connector)
    assert res["status"] == "success"
    assert res["row_count"] == 2
    assert res["df"] is fake_df


def test_run_model_training_and_evaluation_regression():
    pa = PredictiveAnalysisProcess()
    np.random.seed(42)
    n = 60
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    df = pd.DataFrame({
        "order_date": dates,
        "feature_num": np.random.randn(n) * 10,
        "feature_cat": ["A", "B", "C"] * (n // 3),
        "target_price": np.linspace(10, 100, n) + np.random.randn(n) * 2,
    })

    pa_details = {
        "problem_type": "regression",
        "target_column": "target_price",
        "feature_columns": ["order_date", "feature_num", "feature_cat"],
        "selected_models": ["Linear Regression", "Random Forest Regression"]
    }

    eval_info = pa.run_model_training_and_evaluation(df, pa_details)
    assert eval_info["status"] == "success"
    assert eval_info["problem_type"] == "regression"
    assert eval_info["train_count"] > 0
    assert eval_info["test_count"] > 0
    assert eval_info["best_model"] in ["Linear Regression", "Random Forest Regression"]
    assert len(eval_info["model_results"]) == 2

    lin_res = next(m for m in eval_info["model_results"] if m["model_name"] == "Linear Regression")
    assert "r2_score" in lin_res
    assert "rmse" in lin_res
    assert "mae" in lin_res
    assert "accuracy_score" in lin_res

    # Verify unseen predictions
    unseen = eval_info["unseen_predictions"]
    assert "predictions" in unseen
    assert len(unseen["predictions"]) > 0
    pred1 = unseen["predictions"][0]
    assert "predicted_target" in pred1
    assert "features" in pred1


def test_run_model_training_and_evaluation_classification():
    pa = PredictiveAnalysisProcess()
    n = 60
    df = pd.DataFrame({
        "feature_num": np.linspace(1, 100, n),
        "feature_cat": ["Alpha", "Beta"] * (n // 2),
        "target_churn": ["No", "Yes"] * (n // 2),
    })

    pa_details = {
        "problem_type": "classification",
        "target_column": "target_churn",
        "feature_columns": ["feature_num", "feature_cat"],
        "selected_models": ["Logistic Regression", "Random Forest Classification"]
    }

    eval_info = pa.run_model_training_and_evaluation(df, pa_details)
    assert eval_info["status"] == "success"
    assert eval_info["problem_type"] == "classification"
    assert len(eval_info["model_results"]) == 2

    log_res = next(m for m in eval_info["model_results"] if m["model_name"] == "Logistic Regression")
    assert "accuracy_score" in log_res
    assert "precision" in log_res
    assert "recall" in log_res
    assert "f1_score" in log_res
    assert "confusion_matrix" in log_res


def test_unseen_predictions_with_nan_rows():
    pa = PredictiveAnalysisProcess()
    df = pd.DataFrame({
        "feature_x": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0],
        "target_y": [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0, np.nan, np.nan],
    })

    pa_details = {
        "problem_type": "regression",
        "target_column": "target_y",
        "feature_columns": ["feature_x"],
        "selected_models": ["Linear Regression"]
    }

    eval_info = pa.run_model_training_and_evaluation(df, pa_details)
    unseen = eval_info["unseen_predictions"]
    assert "unlabeled/unseen" in unseen["source"]
    assert len(unseen["predictions"]) == 2


def test_format_evaluation_report():
    pa = PredictiveAnalysisProcess()
    pa_details = {
        "problem_type": "regression",
        "target_column": "orders.price",
        "feature_columns": ["freight"],
        "selected_models": ["Linear Regression"],
        "reasoning": "Price prediction test"
    }
    eval_info = {
        "train_count": 80,
        "test_count": 20,
        "total_count": 100,
        "best_model": "Linear Regression",
        "features_used": ["freight"],
        "model_results": [{
            "model_name": "Linear Regression",
            "accuracy_score": 92.5,
            "r2_score": 0.925,
            "rmse": 1.5,
            "mae": 1.2,
            "mse": 2.25
        }],
        "unseen_predictions": {
            "source": "Sample scenario",
            "model_used": "Linear Regression",
            "target_column": "orders.price",
            "feature_columns": ["freight"],
            "predictions": [{
                "sample_id": 1,
                "features": {"freight": "12.5"},
                "predicted_target": "55.00"
            }]
        }
    }

    report = pa.format_evaluation_report(eval_info, pa_details, is_reused=False, row_count=100)
    assert "Predictive Analysis & CrewAI Code Interpreter Execution" in report
    assert "Linear Regression" in report
    assert "92.50%" in report
    assert "Predictions on New / Unseen Data" in report
    assert "55.00" in report


def test_analyze_and_evaluate_end_to_end():
    schema = {"sales": {"columns": [{"name": "revenue"}, {"name": "units"}]}}
    pa = PredictiveAnalysisProcess(schema_info=schema)

    fake_df = pd.DataFrame({"revenue": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0] * 5, "units": [1, 2, 3, 4, 5, 6] * 5})
    mock_connector = MagicMock()
    mock_connector.execute_sql.return_value = fake_df

    mock_json = """```json
    {
        "problem_type": "regression",
        "target_column": "sales.revenue",
        "feature_columns": ["sales.units"],
        "reasoning": "Predicting revenue from units sold."
    }
    ```"""

    with patch("app.agents.predictive.get_together_chat_completion", return_value=mock_json):
        res = pa.analyze_and_evaluate(
            user_query="forecast revenue based on units",
            data_connector=mock_connector
        )
        assert res["initial_routing_decision"] == "predictive_analysis"
        assert res["decision"] == "predictive_analysis"
        assert "revenue" in res["sql"]
        assert isinstance(res["results"], pd.DataFrame)
        assert "Linear Regression" in res["explanation"]
        assert res["predictive_analysis_details"]["problem_type"] == "regression"


def test_trained_model_manager_helpers():
    assert clean_model_slug("Random Forest Regression") == "random_forest_regression"
    assert clean_model_slug("XGBoost-Classifier v1.0") == "xgboost_classifier_v1_0"

    file_paths = [
        {"model_name": "ModelA", "file_path": "path/a.pickle", "accuracy": {"accuracy_score": 85.0}},
        {"model_name": "ModelB", "file_path": "path/b.pickle", "accuracy": {"accuracy_score": 94.2}},
    ]
    best = get_best_model_from_file_paths(file_paths, problem_type="regression")
    assert best["model_name"] == "ModelB"


@pytest.mark.asyncio
async def test_predictive_prepare_structured_response():
    from app.agents import predictive
    from app.query_engine import snapshot_store

    snapshot_store.load_dataset(
        "reviews",
        pd.DataFrame({
            "order_status": ["delivered", "shipped", "delivered", "canceled", "delivered"] * 4,
            "price": [29.9, 45.0, 120.0, 80.0, 15.0] * 4,
            "review_score": [5, 4, 5, 1, 4] * 4,
        }),
    )

    mock_json = """```json
    {
        "problem_type": "classification",
        "target_column": "reviews.review_score",
        "feature_columns": ["reviews.order_status", "reviews.price"],
        "reasoning": "Predicting customer review score based on status and price."
    }
    ```"""

    with patch("app.agents.predictive.get_together_chat_completion", return_value=mock_json):
        prep = await predictive.prepare("Can we predict whether a customer will leave a positive review?")

    assert prep.payload is not None
    assert prep.payload["confidence"] in ["high", "medium"]
    assert "summary" in prep.payload
    assert "metrics" in prep.payload
    assert len(prep.payload["metrics"]) >= 3
    assert "insights" in prep.payload
    assert len(prep.payload["insights"]) >= 1
    # Check that offline_text and insightsText contain clean text, not raw code interpreter header
    assert "Predictive Analysis & CrewAI Code Interpreter Execution" not in prep.offline_text
    assert "review" in prep.offline_text.lower()

