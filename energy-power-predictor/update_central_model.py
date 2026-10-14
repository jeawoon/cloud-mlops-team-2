"""Replace central forecasts; retain existing interval and peak models."""
import argparse
import json
import shutil
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

from src.features import MANUAL_FEATURE_COLUMNS, ADVANCED_FEATURE_COLUMNS, make_hourly_training_data
from train import evaluate


def main(data_path):
    root = Path(__file__).parent
    path = root / 'models/energy_model.joblib'
    bundle = joblib.load(path)
    hourly, y = make_hourly_training_data(pd.read_csv(data_path))
    split = int(len(hourly) * 0.8)
    backup = root / 'reports/central_squared_error'
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup / 'previous_model.joblib')
    result = {}
    for mode, columns in [('advanced', ADVANCED_FEATURE_COLUMNS)]:
        models = bundle['models'][mode]
        before = evaluate(models, hourly.iloc[split:][columns], y.iloc[split:])
        models['0.5'] = GradientBoostingRegressor(
            loss='squared_error', n_estimators=250, max_depth=2,
            min_samples_leaf=15, learning_rate=0.03, random_state=42,
        ).fit(hourly.iloc[:split][columns], y.iloc[:split])
        after = evaluate(models, hourly.iloc[split:][columns], y.iloc[split:])
        bundle['metrics'][mode + '_mode'] = after
        bundle['metrics']['model_selection'][mode] = 'Central: UCI squared-error; intervals: existing model'
        result[mode] = {'before': before, 'after': after}
    bundle['metrics']['central_model'] = 'advanced: squared-error regression trained on UCI first 80%; manual: existing quantile regression'
    bundle['metrics']['data_period']['note'] = '고급 모드 중앙 예측은 UCI 제곱오차 회귀 모델을 사용합니다. 고급 모드의 예측 구간은 기존 Plegma 확장 모델을 유지합니다.'
    joblib.dump(bundle, path)
    (root / 'models/metrics.json').write_text(json.dumps(bundle['metrics'], ensure_ascii=False, indent=2), encoding='utf-8')
    (backup / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True)
    main(parser.parse_args().data)
