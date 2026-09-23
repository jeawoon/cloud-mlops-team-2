"""Train next-hour energy models for manual and advanced input modes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from src.features import ADVANCED_FEATURE_COLUMNS, MANUAL_FEATURE_COLUMNS, make_hourly_training_data


def fit_models(X: pd.DataFrame, y: pd.Series) -> dict:
    return {str(q): GradientBoostingRegressor(loss="quantile", alpha=q, n_estimators=250, max_depth=2, min_samples_leaf=15, learning_rate=0.03, random_state=42).fit(X, y) for q in (0.1, 0.5, 0.9)}


def evaluate(models: dict, X: pd.DataFrame, y: pd.Series) -> dict:
    pred = models["0.5"].predict(X)
    p10, p90 = models["0.1"].predict(X), models["0.9"].predict(X)
    return {"mae_wh": round(float(mean_absolute_error(y, pred)), 2), "rmse_wh": round(float(mean_squared_error(y, pred) ** 0.5), 2), "r2": round(float(r2_score(y, pred)), 3), "p10_p90_coverage_pct": round(float(((y >= p10) & (y <= p90)).mean() * 100), 1)}


def main(data_path: str, output_dir: str) -> None:
    raw = pd.read_csv(data_path)
    hourly, y = make_hourly_training_data(raw)
    split = int(len(hourly) * 0.8)
    train, test = hourly.iloc[:split], hourly.iloc[split:]
    manual_models = fit_models(train[MANUAL_FEATURE_COLUMNS], y.iloc[:split])
    advanced_models = fit_models(train[ADVANCED_FEATURE_COLUMNS], y.iloc[:split])
    metrics = {
        "source_rows": len(raw), "hourly_rows": len(hourly), "train_rows": len(train), "test_rows": len(test),
        "target": "next-hour average Appliances use", "target_unit": "Wh per 10 minutes (hourly average)",
        "manual_mode": evaluate(manual_models, test[MANUAL_FEATURE_COLUMNS], y.iloc[split:]),
        "advanced_mode": evaluate(advanced_models, test[ADVANCED_FEATURE_COLUMNS], y.iloc[split:]),
        "baselines": {
            "global_median_mae_wh": round(float(mean_absolute_error(y.iloc[split:], [y.iloc[:split].median()] * len(test))), 2),
            "previous_hour_mae_wh": round(float(mean_absolute_error(y.iloc[split:], test["previous_hour_wh"])), 2),
            "same_hour_yesterday_mae_wh": round(float(mean_absolute_error(y.iloc[split:], test["same_hour_yesterday_wh"])), 2),
        },
        "data_period": {"start": str(hourly.index.min()), "end": str(hourly.index.max()), "note": "Training data covers winter to spring only; summer generalization is limited."},
    }
    defaults = raw[["Windspeed", "Visibility", "Press_mm_hg"]].median().to_dict()
    bundle = {"models": {"manual": manual_models, "advanced": advanced_models}, "defaults": defaults, "thresholds": np.quantile(y.iloc[:split], [1 / 3, 2 / 3]).tolist(), "metrics": metrics}
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, output / "energy_model.joblib")
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", default="models")
    args = parser.parse_args()
    main(args.data, args.output)
