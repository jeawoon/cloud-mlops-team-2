"""Compare short/long history on identical chronological holdouts.

The experimental model requires real historical readings; it must not be
served through the six-reading demo without supplying those extra inputs.
"""
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import r2_score, mean_absolute_error
from train_refit import ROOT, COLUMNS, load, load_uci


def extend(frame, z):
    frame = frame.copy()
    for lag in (6, 12, 18, 36, 72, 144, 288, 432, 1008):
        frame[f'lag_{lag}'] = z.shift(lag)
    for window in (36, 144, 1008):
        # Allow at most 20% missing meter readings; never fill from the future.
        rolling = z.rolling(window, min_periods=int(np.ceil(window*.8)))
        frame[f'mean_{window}'] = rolling.mean()
        frame[f'std_{window}'] = rolling.std(ddof=0)
        frame[f'max_{window}'] = rolling.max()
    frame['daily_change'] = z - z.shift(144)
    return frame


def predict_history(history_wh, typical_wh, minutes=60):
    """Forecast using a timestamp-indexed series of real 10-minute Wh readings."""
    from train_refit import prepare
    if minutes not in (10, 60) or not np.isfinite(typical_wh) or typical_wh <= 0:
        raise ValueError('minutes must be 10 or 60; typical_wh must be positive')
    if not isinstance(history_wh.index, pd.DatetimeIndex):
        raise ValueError('history_wh requires a DatetimeIndex')
    history_wh = history_wh.sort_index().asfreq('10min')
    if len(history_wh) < 1009 or (history_wh.dropna() < 0).any():
        raise ValueError('At least 7 days plus one 10-minute reading are required')
    frame, _, _ = prepare(history_wh)
    z = history_wh / typical_wh
    # Rebuild base features using the exact training scale, not input-window median.
    for i in range(6):
        frame[f'lag_{i}'] = z.shift(i)
    frame['change'] = z-z.shift(1)
    frame['mean'] = z.rolling(6).mean()
    frame['std'] = z.rolling(6).std(ddof=0)
    frame = extend(frame, z)
    bundle = joblib.load(ROOT/'models/long_history_model.joblib')
    latest = frame[bundle['columns']].iloc[[-1]]
    if not np.isfinite(latest.to_numpy()).all():
        raise ValueError('Insufficient valid historical meter readings')
    return float(bundle['models'][str(minutes//10)].predict(latest)[0]*typical_wh)


def main():
    homes = [(p, *load(p)) for p in sorted((ROOT/'data/refit').glob('CLEAN_House*.csv'))]
    p = ROOT/'data/household_power/household_power.zip'
    if p.exists():
        homes.append((p, *load_uci(p)))
    results, models = {}, {}
    for steps in (1, 6):
        sets = [[], [], []]
        for path, frame, z, scale in homes:
            frame = extend(frame, z)
            target = pd.concat([z.shift(-i) for i in range(1, steps+1)], axis=1).mean(axis=1, skipna=False)
            data = frame.assign(target=target)
            a, b = int(len(data)*.6), int(len(data)*.8)
            for idx, part in enumerate((data.iloc[:a-steps], data.iloc[a:b-steps], data.iloc[b:])):
                sets[idx].append(part.dropna())
        train, valid, test = [pd.concat(parts) for parts in sets]
        long_columns = [c for c in train.columns if c != 'target']
        results[str(steps)] = {}
        for name, columns in (('short', COLUMNS), ('long', long_columns)):
            candidates = []
            for leaves in (7, 15, 31):
                model = HistGradientBoostingRegressor(max_iter=200, max_leaf_nodes=leaves, min_samples_leaf=40, l2_regularization=10, learning_rate=.05, early_stopping=False, random_state=42)
                model.fit(train[columns], train.target)
                candidates.append((r2_score(valid.target, model.predict(valid[columns])), leaves, model))
            score, leaves, model = max(candidates, key=lambda item:item[0])
            combined = pd.concat([train, valid])
            model.fit(combined[columns], combined.target)
            pred = model.predict(test[columns])
            metric = {'r2':float(r2_score(test.target, pred)), 'validation_r2':float(score), 'test_rows':len(test), 'selected_leaves':leaves, 'per_house':{}}
            for (path, _, _, scale), part in zip(homes, sets[2]):
                if len(part) < 2:
                    metric['per_house'][path.stem] = {'test_rows':len(part), 'r2':None}
                    continue
                pred_house = model.predict(part[columns])*scale
                metric['per_house'][path.stem] = {'r2':float(r2_score(part.target*scale, pred_house)), 'mae_wh':float(mean_absolute_error(part.target*scale, pred_house)), 'test_rows':len(part)}
            results[str(steps)][name] = metric
            if name == 'long':
                models[str(steps)] = model
            print(steps, name, json.dumps(metric), flush=True)
    out = ROOT/'reports/long_history'
    out.mkdir(parents=True, exist_ok=True)
    (out/'evaluation.json').write_text(json.dumps(results, indent=2))
    joblib.dump({'models':models, 'columns':long_columns, 'metrics':results, 'requires_history':True}, ROOT/'models/long_history_model.joblib')


if __name__ == '__main__':
    main()
