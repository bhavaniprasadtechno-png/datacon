import os
import re
import json
import pickle
import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def clean_model_slug(model_name: str) -> str:
    """Normalize model name into a safe file slug (e.g. 'Linear Regression' -> 'linear_regression')."""
    slug = str(model_name).lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '_', slug).strip('_')
    return slug or "model"


def get_best_model_from_file_paths(file_path_list: List[Dict[str, Any]], problem_type: str = "regression") -> Optional[Dict[str, Any]]:
    """
    Given a list of model json objects from the file_path column,
    find and return the model object with the highest accuracy.
    """
    if not file_path_list or not isinstance(file_path_list, list):
        return None

    best_entry = None
    best_score = -float('inf')
    prob_lower = str(problem_type).lower()
    is_classification = "classific" in prob_lower

    for entry in file_path_list:
        if not isinstance(entry, dict):
            continue
        accuracy_info = entry.get("accuracy", {})
        if not isinstance(accuracy_info, dict):
            continue

        if is_classification:
            # For classification: use accuracy_score or f1_score
            acc = accuracy_info.get("accuracy_score")
            f1 = accuracy_info.get("f1_score")
            score = float(acc) if acc is not None else (float(f1) * 100.0 if f1 is not None else -1.0)
        else:
            # For regression: use r2_score or accuracy_score, or negative RMSE
            r2 = accuracy_info.get("r2_score")
            acc = accuracy_info.get("accuracy_score")
            rmse = accuracy_info.get("rmse")
            if r2 is not None:
                score = float(r2)
            elif acc is not None:
                score = float(acc) / 100.0
            elif rmse is not None and float(rmse) > 0:
                score = -float(rmse)
            else:
                score = -float('inf')

        if score > best_score or best_entry is None:
            best_score = score
            best_entry = entry

    return best_entry


def save_trained_models(
    user_id: str,
    conversation_id: Any,
    pa_details: Dict[str, Any],
    eval_info: Dict[str, Any],
    user_query: str,
    s3_client,
    s3_bucket: str,
    supabase
) -> Optional[Dict[str, Any]]:
    """
    Pickles all trained models, uploads them to S3 in folder 'trained_ml'
    as '{user_id}_{conversation_id}_{model}.pickle', and saves metadata
    to Supabase table 'trained_predictive_model'.
    """
    try:
        if not user_id or not conversation_id:
            logger.warning(f"[TRAINED ML SAVE] Missing user_id ({user_id}) or conversation_id ({conversation_id}). Skipping save.")
            return None

        fitted_models = eval_info.get("fitted_models", {})
        model_results = eval_info.get("model_results", [])
        if not fitted_models and not model_results:
            logger.warning("[TRAINED ML SAVE] No fitted models or model results found to save.")
            return None

        # Build metrics lookup by model name
        metrics_by_model = {}
        for mr in model_results:
            if isinstance(mr, dict) and "model_name" in mr:
                m_name = mr["model_name"]
                metrics_by_model[m_name] = {k: v for k, v in mr.items() if k != "model_name"}

        file_path_list = []
        for model_name, model_obj in fitted_models.items():
            slug = clean_model_slug(model_name)
            s3_key = f"trained_ml/{user_id}_{conversation_id}_{slug}.pickle"

            # Serialize model to pickle with highest protocol for speed and compactness
            try:
                pickled_bytes = pickle.dumps(model_obj, protocol=pickle.HIGHEST_PROTOCOL)
                size_kb = len(pickled_bytes) / 1024
                logger.info(f"[TRAINED ML SAVE] Uploading model '{model_name}' ({size_kb:.1f} KB) to S3: {s3_key}")
                if s3_client and s3_bucket:
                    s3_client.put_object(
                        Bucket=s3_bucket,
                        Key=s3_key,
                        Body=pickled_bytes,
                        ContentType="application/octet-stream"
                    )
                    logger.info(f"[TRAINED ML SAVE] ✅ Successfully uploaded '{model_name}' ({size_kb:.1f} KB) to S3: {s3_key}")
                else:
                    logger.warning(f"[TRAINED ML SAVE] ⚠️ s3_client or s3_bucket not available. Key path generated: {s3_key}")
            except Exception as s3_err:
                logger.error(f"[TRAINED ML SAVE] ❌ Error uploading model '{model_name}' to S3: {s3_err}")
                continue

            acc_metrics = metrics_by_model.get(model_name, {})
            file_path_list.append({
                "model_name": model_name,
                "file_path": s3_key,
                "accuracy": acc_metrics
            })

        if not file_path_list:
            logger.warning("[TRAINED ML SAVE] No models were successfully uploaded to S3.")
            return None

        # Generate descriptive summary for the trained model record
        target_col = pa_details.get("target_column", "target")
        feature_cols = pa_details.get("feature_columns", [])
        feat_str = ", ".join(feature_cols) if isinstance(feature_cols, list) else str(feature_cols)
        prob_type = pa_details.get("problem_type", "regression")
        best_model_name = eval_info.get("best_model", "Best Model")

        description = (
            f"Predictive model for predicting target '{target_col}' based on features [{feat_str}] "
            f"using {prob_type} algorithms (Top model: {best_model_name}) trained for query: '{user_query}'."
        )

        # Insert record into Supabase table 'trained_predictive_model'
        feat_cols_val = feat_str if feat_str else (json.dumps(feature_cols) if isinstance(feature_cols, list) else str(feature_cols))
        db_payload = {
            "fetaure_columns": feat_cols_val,
            "target_column": target_col,
            "problem_type": prob_type,
            "decsription": description,
            "file_path": file_path_list
        }

        if supabase:
            try:
                res = supabase.table("trained_predictive_model").insert(db_data_with_fallbacks(db_payload)).execute()
                logger.info(f"[TRAINED ML SAVE] ✅ Inserted record into Supabase 'trained_predictive_model': {res.data}")
                return res.data[0] if res.data else None
            except Exception as db_err:
                logger.error(f"[TRAINED ML SAVE] ❌ Supabase insert failed: {db_err}. Retrying fallback keys...")
                try:
                    alt_payload = {
                        "feature_column": feat_cols_val,
                        "target_column": target_col,
                        "problem_type": prob_type,
                        "description": description,
                        "file_path": file_path_list
                    }
                    res = supabase.table("trained_predictive_model").insert(alt_payload).execute()
                    logger.info(f"[TRAINED ML SAVE] ✅ Inserted record with fallback keys: {res.data}")
                    return res.data[0] if res.data else None
                except Exception as db_err2:
                    logger.error(f"[TRAINED ML SAVE] ❌ Final Supabase insert attempt failed: {db_err2}")
                    return None
        else:
            logger.warning("[TRAINED ML SAVE] Supabase client not provided. Skipping table insert.")
            return None

    except Exception as e:
        logger.error(f"[TRAINED ML SAVE] ❌ Exception during save_trained_models: {e}", exc_info=True)
        return None


def db_data_with_fallbacks(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to ensure compatibility with Supabase column naming."""
    return payload


def find_matching_trained_model(
    user_query: str,
    pa_details: Optional[Dict[str, Any]] = None,
    supabase=None,
    vectorizer=None,
    similarity_threshold: float = 0.75
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], float]:
    """
    Searches Supabase 'trained_predictive_model' table for an existing trained model
    matching the user query / task.

    Returns:
        (matched_db_record, best_model_entry_from_file_path, similarity_score)
        or (None, None, 0.0) if no match found.
    """
    if not supabase or not user_query:
        return None, None, 0.0

    try:
        res = supabase.table("trained_predictive_model").select("*").order("id", desc=True).limit(50).execute()
        records = res.data or []
        if not records:
            return None, None, 0.0

        query_vec = None
        if vectorizer and hasattr(vectorizer, 'vectorize'):
            try:
                query_vec = vectorizer.vectorize(user_query)
            except Exception as vec_err:
                logger.warning(f"[TRAINED ML MATCH] Error vectorizing user query: {vec_err}")

        best_record = None
        best_model_entry = None
        highest_sim = 0.0

        curr_target = str(pa_details.get("target_column", "")).lower() if pa_details else ""
        curr_prob_type = str(pa_details.get("problem_type", "")).lower() if pa_details else ""

        for rec in records:
            rec_desc = rec.get("decsription") or rec.get("description") or ""
            rec_target = str(rec.get("target_column") or "").lower()
            rec_prob = str(rec.get("problem_type") or "").lower()
            file_paths = rec.get("file_path", [])

            if not file_paths or not isinstance(file_paths, list):
                continue

            similarity = 0.0
            # 1. Cosine similarity via embeddings
            if query_vec is not None and rec_desc:
                try:
                    rec_vec = vectorizer.vectorize(rec_desc)
                    q_norm = np.linalg.norm(query_vec)
                    r_norm = np.linalg.norm(rec_vec)
                    if q_norm > 0 and r_norm > 0:
                        similarity = float(np.dot(query_vec, rec_vec) / (q_norm * r_norm))
                except Exception:
                    similarity = 0.0

            # 2. Check target and problem match boosts
            target_match = bool(curr_target and rec_target and (curr_target in rec_target or rec_target in curr_target))
            prob_match = bool(curr_prob_type and rec_prob and (curr_prob_type in rec_prob or rec_prob in curr_prob_type))

            effective_score = similarity
            if target_match and prob_match:
                effective_score = max(effective_score, 0.85)
            elif target_match:
                effective_score = max(effective_score, 0.78)

            if effective_score >= similarity_threshold and effective_score > highest_sim:
                best_model = get_best_model_from_file_paths(file_paths, problem_type=rec_prob)
                if best_model and best_model.get("file_path"):
                    highest_sim = effective_score
                    best_record = rec
                    best_model_entry = best_model

        if best_record and best_model_entry:
            logger.info(
                f"[TRAINED ML MATCH] 🎯 Found matching trained model (id={best_record.get('id')}, "
                f"similarity={highest_sim:.4f}, best_model={best_model_entry.get('model_name')}, "
                f"file_path={best_model_entry.get('file_path')})"
            )
            return best_record, best_model_entry, highest_sim

        return None, None, 0.0

    except Exception as e:
        logger.error(f"[TRAINED ML MATCH] ❌ Error checking trained models: {e}")
        return None, None, 0.0


def load_and_predict_with_saved_model(
    matched_record: Dict[str, Any],
    best_model_entry: Dict[str, Any],
    pa_details: Dict[str, Any],
    results_df: pd.DataFrame,
    s3_client,
    s3_bucket: str
) -> Optional[Dict[str, Any]]:
    """
    Downloads the pre-trained model pickle from S3, executes predictions on the given dataset/features,
    and formats evaluation & prediction metrics.
    """
    try:
        s3_key = best_model_entry.get("file_path")
        model_name = best_model_entry.get("model_name", "Pre-Trained Model")
        accuracy_info = best_model_entry.get("accuracy", {})

        if not s3_key or not s3_client or not s3_bucket:
            logger.warning(f"[TRAINED ML LOAD] S3 key ({s3_key}), client, or bucket ({s3_bucket}) missing.")
            return None

        # Download from S3
        logger.info(f"[TRAINED ML LOAD] 🌐 Downloading model '{model_name}' from S3: {s3_key}")
        obj = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
        model_obj = pickle.loads(obj["Body"].read())
        logger.info(f"[TRAINED ML LOAD] ✅ Successfully loaded pre-trained model '{model_name}' from S3.")

        target_col_raw = matched_record.get("target_column") or pa_details.get("target_column", "target")
        prob_type = str(matched_record.get("problem_type") or pa_details.get("problem_type", "regression")).lower()

        # Determine feature columns
        feat_raw = (
            matched_record.get("fetaure_columns")
            or matched_record.get("feature_column")
            or matched_record.get("feature_columns")
            or pa_details.get("feature_columns", [])
        )
        if isinstance(feat_raw, str):
            try:
                feature_cols_raw = json.loads(feat_raw)
                if not isinstance(feature_cols_raw, list):
                    feature_cols_raw = [f.strip() for f in feat_raw.split(",") if f.strip()]
            except Exception:
                feature_cols_raw = [f.strip() for f in feat_raw.split(",") if f.strip()]
        else:
            feature_cols_raw = feat_raw or []

        df_cols = list(results_df.columns) if results_df is not None else []

        def resolve_col(c, cols):
            if c in cols:
                return c
            base = c.split(".")[-1] if "." in c else c
            for col in cols:
                if col == base or col.endswith("." + base):
                    return col
            return None

        target_col = resolve_col(target_col_raw, df_cols) or target_col_raw
        feature_cols = [resolve_col(fc, df_cols) for fc in feature_cols_raw]
        feature_cols = [fc for fc in feature_cols if fc is not None and fc != target_col]

        if not feature_cols and results_df is not None:
            feature_cols = [c for c in df_cols if c != target_col]

        # Prepare unseen records for prediction
        df_clean = (
            results_df.copy().dropna(subset=[target_col])
            if (results_df is not None and target_col in df_cols)
            else (results_df.copy() if results_df is not None else pd.DataFrame())
        )

        unseen_raw = (
            results_df[results_df[target_col].isna()].copy()
            if (results_df is not None and target_col in df_cols)
            else pd.DataFrame()
        )
        source_desc = "Extracted unlabeled/unseen records from database for prediction"

        if unseen_raw.empty or len(unseen_raw) == 0:
            source_desc = "Prepared new/unseen scenario feature samples based on dataset distributions"
            sample_count = min(5, len(df_clean)) if len(df_clean) > 0 else 5
            synthetic_rows = []
            for i in range(sample_count):
                row_data = {}
                for col in feature_cols:
                    series = results_df[col] if (results_df is not None and col in results_df.columns) else pd.Series([0])
                    if pd.api.types.is_datetime64_any_dtype(series) or "timestamp" in col.lower() or "date" in col.lower():
                        try:
                            dt_series = pd.to_datetime(series, errors='coerce').dropna()
                            max_dt = dt_series.max() if not dt_series.empty else pd.Timestamp("2024-01-01")
                            future_dt = max_dt + pd.Timedelta(days=(i + 1) * 3)
                            row_data[col] = str(future_dt)
                        except Exception:
                            row_data[col] = "2024-01-01 12:00:00"
                    elif pd.api.types.is_numeric_dtype(series):
                        clean_s = series.dropna()
                        if not clean_s.empty:
                            std_val = float(clean_s.std()) if len(clean_s) > 1 and pd.notnull(clean_s.std()) else 1.0
                            val = float(clean_s.median() + (i - 2) * std_val * 0.2)
                        else:
                            val = float(10.0 * (i + 1))
                        row_data[col] = round(val, 2)
                    else:
                        clean_s = series.dropna()
                        cats = clean_s.unique()
                        if len(cats) > 0:
                            row_data[col] = str(cats[i % len(cats)])
                        else:
                            row_data[col] = f"Sample_{col}_{i+1}"
                synthetic_rows.append(row_data)
            unseen_raw = pd.DataFrame(synthetic_rows)

        # Preprocess features into numerical representation matching model inputs
        X_unseen = pd.DataFrame(index=unseen_raw.index)
        for col in feature_cols:
            if col not in unseen_raw.columns:
                continue
            series = unseen_raw[col]
            if pd.api.types.is_datetime64_any_dtype(series) or "timestamp" in col.lower() or "date" in col.lower():
                try:
                    dt_series = pd.to_datetime(series, errors='coerce')
                    X_unseen[f"{col}_year"] = dt_series.dt.year.fillna(2024)
                    X_unseen[f"{col}_month"] = dt_series.dt.month.fillna(1)
                    X_unseen[f"{col}_day"] = dt_series.dt.day.fillna(1)
                    X_unseen[f"{col}_dayofweek"] = dt_series.dt.dayofweek.fillna(0)
                    X_unseen[f"{col}_hour"] = dt_series.dt.hour.fillna(12)
                    continue
                except Exception:
                    pass
            if pd.api.types.is_numeric_dtype(series):
                med_val = series.median() if not series.empty and pd.notnull(series.median()) else 0
                X_unseen[col] = pd.to_numeric(series, errors='coerce').fillna(med_val)
            else:
                encoded_vals, _ = pd.factorize(series.astype(str))
                X_unseen[col] = encoded_vals

        X_unseen = X_unseen.fillna(0)

        # Align columns with model expectation if feature_names_in_ is present
        if hasattr(model_obj, "feature_names_in_"):
            expected_cols = list(model_obj.feature_names_in_)
            X_unseen = X_unseen.reindex(columns=expected_cols, fill_value=0).fillna(0)

        raw_preds = model_obj.predict(X_unseen)
        formatted_preds = []
        for idx in range(len(unseen_raw)):
            pred_val = raw_preds[idx]
            pred_val_str = f"{float(pred_val):.2f}" if "regression" in prob_type else str(pred_val)
            row_feat_dict = {}
            for fc in feature_cols:
                if fc in unseen_raw.columns:
                    val_raw = unseen_raw.iloc[idx][fc]
                    row_feat_dict[fc] = str(val_raw)
            formatted_preds.append({
                "sample_id": idx + 1,
                "features": row_feat_dict,
                "predicted_target": pred_val_str
            })

        unseen_predictions_info = {
            "source": source_desc,
            "model_used": f"{model_name} (Reused from S3)",
            "predictions": formatted_preds,
            "target_column": target_col,
            "feature_columns": feature_cols
        }

        # Build model_results list using the stored metrics
        model_results = [{
            "model_name": model_name,
            **accuracy_info
        }]

        return {
            "status": "success",
            "is_reused_model": True,
            "reused_s3_key": s3_key,
            "reused_db_id": matched_record.get("id"),
            "train_count": "Pre-trained",
            "test_count": "Pre-trained",
            "total_count": len(results_df) if results_df is not None else 0,
            "target_column": target_col,
            "features_used": list(X_unseen.columns),
            "problem_type": prob_type,
            "best_model": model_name,
            "model_results": model_results,
            "unseen_predictions": unseen_predictions_info,
            "accuracy_info": accuracy_info
        }

    except Exception as e:
        logger.error(f"[TRAINED ML LOAD] ❌ Error executing prediction with saved model: {e}", exc_info=True)
        return None
