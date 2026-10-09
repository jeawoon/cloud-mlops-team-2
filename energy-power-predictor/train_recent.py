"""Temporal validation of short-horizon forecasts with observed recent energy."""
import argparse
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, ExtraTreesRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error

ROOT = Path(__file__).parent
COLUMNS = ['indoor_temp', 'indoor_humidity', 'outdoor_temp', 'outdoor_humidity', 'hour_sin', 'hour_cos', 'weekend'] + [f'lag_{i}' for i in range(6)] + ['change', 'recent_mean', 'recent_std']


def recent_row(indoor_temp, indoor_humidity, outdoor_temp, outdoor_humidity, hour, weekday, recent):
    values = [indoor_temp, indoor_humidity, outdoor_temp, outdoor_humidity,
              np.sin(2*np.pi*hour/24), np.cos(2*np.pi*hour/24), int(weekday >= 5)]
    values += list(recent) + [recent[0]-recent[1], np.mean(recent), np.std(recent)]
    return pd.DataFrame([values], columns=COLUMNS)


def scores(y, pred):
    return {'r2': round(float(r2_score(y, pred)), 4), 'mae_wh': round(float(mean_absolute_error(y, pred)), 2)}


def main(path):
    raw = pd.read_csv(path, parse_dates=['date']).sort_values('date').set_index('date')
    raw = raw.asfreq('10min')
    X = pd.DataFrame(index=raw.index)
    X['indoor_temp'] = raw[[f'T{i}' for i in range(1, 10)]].mean(axis=1)
    X['indoor_humidity'] = raw[[f'RH_{i}' for i in range(1, 10)]].mean(axis=1)
    X['outdoor_temp'], X['outdoor_humidity'] = raw['T_out'], raw['RH_out']
    hour = raw.index.hour + raw.index.minute/60
    X['hour_sin'], X['hour_cos'] = np.sin(2*np.pi*hour/24), np.cos(2*np.pi*hour/24)
    X['weekend'] = (raw.index.weekday >= 5).astype(int)
    for i in range(6):
        X[f'lag_{i}'] = raw.Appliances.shift(i)
    X['change'] = X.lag_0 - X.lag_1
    X['recent_mean'] = X[[f'lag_{i}' for i in range(6)]].mean(axis=1)
    X['recent_std'] = X[[f'lag_{i}' for i in range(6)]].std(axis=1, ddof=0)
    bundle, report = {'models': {}, 'columns': COLUMNS}, {}
    for steps in (1, 6):
        target = pd.concat([raw.Appliances.shift(-i) for i in range(1, steps+1)], axis=1).mean(axis=1, skipna=False)
        frame = X.assign(target=target).dropna()
        a,b = int(len(frame)*.60), int(len(frame)*.80)
        # Embargo rows whose future targets extend into the next partition.
        train, valid, test = frame.iloc[:a-steps], frame.iloc[a:b-steps], frame.iloc[b:]
        candidates = {'ridge': make_pipeline(StandardScaler(), Ridge(alpha=100))}
        for leaves in (7, 15, 31):
            candidates[f'hist_{leaves}'] = HistGradientBoostingRegressor(max_iter=250, max_leaf_nodes=leaves, min_samples_leaf=40, learning_rate=.05, l2_regularization=10, early_stopping=False, random_state=42)
        candidates['extra_trees'] = ExtraTreesRegressor(n_estimators=150, min_samples_leaf=15, max_features=.8, n_jobs=2, random_state=42)
        candidates['random_forest'] = RandomForestRegressor(n_estimators=100, min_samples_leaf=15, max_features=.8, n_jobs=2, random_state=42)
        results = {}
        for name, model in candidates.items():
            model.fit(train[COLUMNS], train.target)
            results[name] = scores(valid.target, model.predict(valid[COLUMNS]))
        choice = max(results, key=lambda name: results[name]['r2'])
        model = candidates[choice]
        model.fit(frame.iloc[:b-steps][COLUMNS], frame.iloc[:b-steps].target)
        result = scores(test.target, model.predict(test[COLUMNS]))
        report[str(steps)] = {'horizon_minutes': steps*10, 'selected': choice, 'validation': results, 'test': result, 'persistence_test': scores(test.target, test.lag_0), 'test_rows': len(test), 'test_start': str(test.index.min())}
        bundle['models'][str(steps)] = model
        print(steps*10, 'minutes', result, flush=True)
    bundle['metrics'] = report
    joblib.dump(bundle, ROOT/'models/recent_model.joblib')
    out = ROOT/'reports/recent_patterns'
    out.mkdir(parents=True, exist_ok=True)
    (out/'comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True)
    main(parser.parse_args().data)
