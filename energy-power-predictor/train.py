"""Train next-hour energy models for manual and advanced input modes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.metrics import average_precision_score, mean_absolute_error, mean_squared_error, r2_score, roc_auc_score

from src.features import ADVANCED_FEATURE_COLUMNS, MANUAL_FEATURE_COLUMNS, make_hourly_training_data
from src.plegma import load_plegma_training_data


def fit_models(X: pd.DataFrame, y: pd.Series, sample_weight: pd.Series | None = None) -> dict:
    return {
        str(q): GradientBoostingRegressor(
            loss="quantile", alpha=q, n_estimators=250, max_depth=2,
            min_samples_leaf=15, learning_rate=0.03, random_state=42,
        ).fit(X, y, sample_weight=sample_weight)
        for q in (0.1, 0.5, 0.9)
    }


def evaluate(models: dict, X: pd.DataFrame, y: pd.Series) -> dict:
    pred = models["0.5"].predict(X)
    p10, p90 = models["0.1"].predict(X), models["0.9"].predict(X)
    return {"mae_wh": round(float(mean_absolute_error(y, pred)), 2), "rmse_wh": round(float(mean_squared_error(y, pred) ** 0.5), 2), "r2": round(float(r2_score(y, pred)), 3), "p10_p90_coverage_pct": round(float(((y >= p10) & (y <= p90)).mean() * 100), 1)}


def fit_peak_model(X: pd.DataFrame, y: pd.Series, threshold: float) -> GradientBoostingClassifier:
    """Estimate whether the next hour will be in the high-use (top 10%) band."""
    return GradientBoostingClassifier(
        n_estimators=250, max_depth=2, min_samples_leaf=15,
        learning_rate=0.03, random_state=42,
    ).fit(X, y >= threshold)


def evaluate_peak_model(model: GradientBoostingClassifier, X: pd.DataFrame, y: pd.Series, threshold: float) -> dict:
    actual = y >= threshold
    probability = model.predict_proba(X)[:, 1]
    return {
        "threshold_wh": round(float(threshold), 2),
        "positive_rate_pct": round(float(actual.mean() * 100), 1),
        "roc_auc": round(float(roc_auc_score(actual, probability)), 3),
        "average_precision": round(float(average_precision_score(actual, probability)), 3),
    }


def main(data_path: str, output_dir: str, plegma_dir: str | None = None, plegma_weight: float = 0.03) -> None:
    raw = pd.read_csv(data_path)
    hourly, y = make_hourly_training_data(raw)
    split = int(len(hourly) * 0.8)
    train, test = hourly.iloc[:split], hourly.iloc[split:]
    train_y = y.iloc[:split]
    base_manual = fit_models(train[MANUAL_FEATURE_COLUMNS], train_y)
    base_advanced = fit_models(train[ADVANCED_FEATURE_COLUMNS], train_y)
    peak_threshold = float(train_y.quantile(0.90))
    peak_models = {
        "manual": fit_peak_model(train[MANUAL_FEATURE_COLUMNS], train_y, peak_threshold),
        "advanced": fit_peak_model(train[ADVANCED_FEATURE_COLUMNS], train_y, peak_threshold),
    }
    base_manual_metrics = evaluate(base_manual, test[MANUAL_FEATURE_COLUMNS], y.iloc[split:])
    base_advanced_metrics = evaluate(base_advanced, test[ADVANCED_FEATURE_COLUMNS], y.iloc[split:])
    manual_models, advanced_models = base_manual, base_advanced
    manual_metrics, advanced_metrics = base_manual_metrics, base_advanced_metrics
    selection = {"manual": "UCI only", "advanced": "UCI only"}
    external_rows = 0
    if plegma_dir:
        defaults = raw[["Windspeed", "Visibility", "Press_mm_hg"]].median().to_dict()
        plegma, plegma_y = load_plegma_training_data(plegma_dir, defaults, float(train_y.median()))
        external_rows = len(plegma)
        # Plegma is an external household population. Keep its contribution
        # deliberately small so UCI remains the target population being tested.
        expanded_manual = pd.concat([train[MANUAL_FEATURE_COLUMNS], plegma[MANUAL_FEATURE_COLUMNS]], ignore_index=True)
        expanded_advanced = pd.concat([train[ADVANCED_FEATURE_COLUMNS], plegma[ADVANCED_FEATURE_COLUMNS]], ignore_index=True)
        expanded_y = pd.concat([train_y.reset_index(drop=True), plegma_y.reset_index(drop=True)], ignore_index=True)
        weights = pd.Series([1.0] * len(train) + [plegma_weight] * external_rows)
        expanded_manual_models = fit_models(expanded_manual, expanded_y, weights)
        expanded_advanced_models = fit_models(expanded_advanced, expanded_y, weights)
        expanded_manual_metrics = evaluate(expanded_manual_models, test[MANUAL_FEATURE_COLUMNS], y.iloc[split:])
        expanded_advanced_metrics = evaluate(expanded_advanced_models, test[ADVANCED_FEATURE_COLUMNS], y.iloc[split:])
        if expanded_manual_metrics["mae_wh"] < base_manual_metrics["mae_wh"]:
            manual_models, manual_metrics = expanded_manual_models, expanded_manual_metrics
            selection["manual"] = "UCI + Plegma"
        if expanded_advanced_metrics["mae_wh"] < base_advanced_metrics["mae_wh"]:
            advanced_models, advanced_metrics = expanded_advanced_models, expanded_advanced_metrics
            selection["advanced"] = "UCI + Plegma"
    metrics = {
        "source_rows": len(raw), "hourly_rows": len(hourly), "train_rows": len(train), "test_rows": len(test),
        "external_plegma_rows": external_rows,
        "target": "next-hour average Appliances use", "target_unit": "Wh per 10 minutes (hourly average)",
        "manual_mode": manual_metrics,
        "advanced_mode": advanced_metrics,
        "peak_prediction": {
            "definition": "next-hour usage at or above the training-period 90th percentile",
            "manual_mode": evaluate_peak_model(peak_models["manual"], test[MANUAL_FEATURE_COLUMNS], y.iloc[split:], peak_threshold),
            "advanced_mode": evaluate_peak_model(peak_models["advanced"], test[ADVANCED_FEATURE_COLUMNS], y.iloc[split:], peak_threshold),
        },
        "model_selection": selection,
        "baselines": {
            "global_median_mae_wh": round(float(mean_absolute_error(y.iloc[split:], [y.iloc[:split].median()] * len(test))), 2),
            "previous_hour_mae_wh": round(float(mean_absolute_error(y.iloc[split:], test["previous_hour_wh"])), 2),
            "same_hour_yesterday_mae_wh": round(float(mean_absolute_error(y.iloc[split:], test["same_hour_yesterday_wh"])), 2),
        },
        "data_period": {"start": str(hourly.index.min()), "end": str(hourly.index.max()), "note": "The UCI holdout is evaluated separately; Plegma adds all-season household patterns from 13 Greek homes." if external_rows else "Training data covers winter to spring only; summer generalization is limited."},
    }
    defaults = raw[["Windspeed", "Visibility", "Press_mm_hg"]].median().to_dict()
    bundle = {"models": {"manual": manual_models, "advanced": advanced_models}, "peak_models": peak_models, "defaults": defaults, "thresholds": np.quantile(y.iloc[:split], [1 / 3, 2 / 3]).tolist(), "metrics": metrics}
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, output / "energy_model.joblib")
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", default="models")
    parser.add_argument("--plegma-dir", help="Directory containing Clean_Dataset from PlegmaDataset_Clean.7z")
    parser.add_argument("--plegma-weight", type=float, default=0.03, help="Relative weight for Plegma rows (default: 0.03)")
    args = parser.parse_args()
    main(args.data, args.output, args.plegma_dir, args.plegma_weight)
