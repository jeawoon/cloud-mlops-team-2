"""REFIT per-house ablation: long aggregate history vs appliance-aware history.

Channel numbers are house-specific, never assumed to identify the same device.
Input bins are completed past 10-minute intervals. Targets are future intervals.
"""
import json
import hashlib
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import r2_score, mean_absolute_error
from train_refit import ROOT, prepare
from train_long_history import extend

CHANNELS = [f'Appliance{i}' for i in range(1, 10)]
ON_THRESHOLD_W = 20.0  # Activity proxy, not ground-truth device switch status.


def load_channels(path):
    pieces = []
    columns = ['Aggregate'] + CHANNELS
    for chunk in pd.read_csv(path, usecols=['Time', 'Issues']+columns, chunksize=200000):
        chunk['Time'] = pd.to_datetime(chunk.Time)
        chunk.loc[chunk.Issues != 0, columns] = np.nan
        chunk[columns] = chunk[columns].where(chunk[columns] >= 0)
        grouped = chunk.set_index('Time')[columns].resample('10min').agg(['sum', 'count'])
        pieces.append(grouped)
    bins = pd.concat(pieces).groupby(level=0).sum().asfreq('10min')
    values = {}
    for column in columns:
        count = bins[(column, 'count')]
        values[column] = (bins[(column, 'sum')]/count/6).where(count >= 60)
    return pd.DataFrame(values)


def build_features(readings, scale):
    frame, _, _ = prepare(readings.Aggregate)
    z = readings.Aggregate/scale
    for i in range(6):
        frame[f'lag_{i}'] = z.shift(i)
    frame['change'] = z-z.shift(1)
    frame['mean'] = z.rolling(6).mean()
    frame['std'] = z.rolling(6).std(ddof=0)
    frame = extend(frame, z)
    baseline = list(frame.columns)
    extras = {}
    for channel in CHANNELS:
        wh = readings[channel]
        extras[channel+'_wh'] = wh/scale
        extras[channel+'_previous_wh'] = wh.shift(1)/scale
        extras[channel+'_mean_1h'] = wh.rolling(6).mean()/scale
        extras[channel+'_change'] = wh.diff()/scale
        extras[channel+'_active'] = (wh*6 > ON_THRESHOLD_W).astype(float).where(wh.notna())
    return pd.concat([frame, pd.DataFrame(extras)], axis=1), baseline


def score(model, part, columns, scale):
    prediction = model.predict(part[columns])*scale
    return {'r2':float(r2_score(part.target*scale, prediction)),
            'mae_wh':float(mean_absolute_error(part.target*scale, prediction)),
            'test_rows':len(part)}


def predict_appliance_history(readings, house, minutes=60):
    """Use matching-house Aggregate + Appliance1..9 10-minute Wh history."""
    if minutes not in (10, 60):
        raise ValueError('minutes must be 10 or 60')
    if not isinstance(readings.index, pd.DatetimeIndex) or readings.index.has_duplicates:
        raise ValueError('Unique timestamp index required')
    readings = readings.sort_index().asfreq('10min')
    if len(readings) < 1009 or not set(['Aggregate']+CHANNELS).issubset(readings.columns):
        raise ValueError('Need 7 days plus one reading for Aggregate and Appliance1..9')
    if (readings[['Aggregate']+CHANNELS].dropna() < 0).any().any():
        raise ValueError('Energy readings must be nonnegative')
    bundle = joblib.load(ROOT/'models/appliance_history_model.joblib')
    if house not in bundle['homes']:
        raise ValueError('Unknown house; channel mapping must match the training house')
    entry = bundle['homes'][house]
    frame, _ = build_features(readings, entry['scale'])
    latest = frame[entry['columns']].iloc[[-1]]
    if not np.isfinite(latest.to_numpy()).all():
        raise ValueError('Missing required historical readings')
    return float(entry['models'][str(minutes//10)].predict(latest)[0]*entry['scale'])


def main():
    results, homes = {}, {}
    checksums = {'CLEAN_House11.csv':'5b41bae97ab28871fcfe5167b41c0347',
                 'CLEAN_House2.csv':'13957fd139bf8f6ba8bceea36e85bb3d'}
    for filename, checksum in checksums.items():
        path = ROOT/'data/refit'/filename
        digest = hashlib.md5()
        with path.open('rb') as handle:
            for block in iter(lambda:handle.read(1024*1024), b''):
                digest.update(block)
        if digest.hexdigest() != checksum:
            raise ValueError('Raw REFIT checksum mismatch')
        readings = load_channels(path)
        a, b = int(len(readings)*.6), int(len(readings)*.8)
        scale = float(readings.Aggregate.iloc[:a].median())
        frame, baseline = build_features(readings, scale)
        columns = list(frame.columns)
        results[path.stem] = {}
        homes[path.stem] = {'scale':scale, 'columns':columns, 'models':{}}
        for steps in (1, 6):
            target = pd.concat([readings.Aggregate.shift(-i)/scale for i in range(1, steps+1)], axis=1).mean(axis=1, skipna=False)
            data = frame.assign(target=target)
            train, valid, test = [part.dropna() for part in (data.iloc[:a-steps], data.iloc[a:b-steps], data.iloc[b:])]
            if min(len(train), len(valid), len(test)) < 2:
                raise ValueError('Insufficient complete samples')
            results[path.stem][str(steps)] = {}
            for name, features in (('aggregate_only', baseline), ('with_appliances', columns)):
                candidates = []
                for leaves in (7, 15, 31):
                    model = HistGradientBoostingRegressor(max_iter=200, max_leaf_nodes=leaves, min_samples_leaf=40, l2_regularization=10, learning_rate=.05, early_stopping=False, random_state=42)
                    model.fit(train[features], train.target)
                    candidates.append((r2_score(valid.target, model.predict(valid[features])), leaves, model))
                val, leaves, model = max(candidates, key=lambda item:item[0])
                combined = pd.concat([train, valid])
                model.fit(combined[features], combined.target)
                metrics = score(model, test, features, scale)
                metrics.update(validation_r2=float(val), selected_leaves=leaves,
                               train_rows=len(train), validation_rows=len(valid))
                results[path.stem][str(steps)][name] = metrics
                if name == 'with_appliances':
                    homes[path.stem]['models'][str(steps)] = model
                print(path.stem, steps, name, json.dumps(metrics), flush=True)
    out = ROOT/'reports/appliance_history'
    out.mkdir(parents=True, exist_ok=True)
    (out/'evaluation.json').write_text(json.dumps(results, indent=2))
    joblib.dump({'homes':homes, 'metrics':results, 'active_threshold_w':ON_THRESHOLD_W,
                 'unit':'mean Wh per 10 minutes', 'source':'https://zenodo.org/records/5063428',
                 'license':'CC-BY-4.0'}, ROOT/'models/appliance_history_model.joblib')


if __name__ == '__main__':
    main()
