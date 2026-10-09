"""Read-only holdout diagnostics for the current deployed-family model."""
import argparse
import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from src.features import make_hourly_training_data, MANUAL_FEATURE_COLUMNS, ADVANCED_FEATURE_COLUMNS

ROOT = Path(__file__).parent


def summarize(frame):
    if frame.empty:
        return {'count':0, 'mae_wh':None, 'rmse_wh':None, 'bias_wh':None}
    error = frame.predicted-frame.actual
    return {'count':len(frame), 'mae_wh':round(float(error.abs().mean()),2),
            'rmse_wh':round(float(np.sqrt((error**2).mean())),2),
            'bias_wh':round(float(error.mean()),2)}


def main(data_path):
    path = ROOT/'models/energy_model.joblib'
    bundle = joblib.load(path)
    hourly, y = make_hourly_training_data(pd.read_csv(data_path))
    expected = bundle['metrics']
    if len(hourly) != expected['hourly_rows']:
        raise ValueError('Data does not match the model evaluation population')
    split = expected['train_rows']
    test = hourly.iloc[split:]
    if len(test) != expected['test_rows']:
        raise ValueError('Holdout size mismatch')
    threshold = float(y.iloc[:split].quantile(.9))
    report = {'model_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
              'unit':'Wh per 10 minutes (hourly average)', 'test_rows':len(test),
              'peak_threshold_wh':threshold, 'modes':{}}
    for mode, columns in [('manual',MANUAL_FEATURE_COLUMNS),('advanced',ADVANCED_FEATURE_COLUMNS)]:
        frame = pd.DataFrame({'actual':y.iloc[split:], 'predicted':bundle['models'][mode]['0.5'].predict(test[columns])})
        # Index denotes observed input hour; target is the NEXT hour.
        frame.index = frame.index+pd.Timedelta(hours=1)
        frame['abs_error'] = (frame.predicted-frame.actual).abs()
        frame['peak'] = frame.actual>=threshold
        frame['previous_wh'] = test.previous_hour_wh.to_numpy()
        frame['jump'] = frame.actual-frame.previous_wh>=threshold
        denominator = float(((frame.actual-frame.predicted)**2).sum())
        peak_sse = float(((frame.loc[frame.peak,'actual']-frame.loc[frame.peak,'predicted'])**2).sum())
        groups = {'전체':summarize(frame),'평상시':summarize(frame[~frame.peak]),
                  '피크':summarize(frame[frame.peak]),'급상승':summarize(frame[frame.jump])}
        by_hour = [{'hour':int(hour),**summarize(part)} for hour,part in frame.groupby(frame.index.hour)]
        worst = frame.nlargest(20,'abs_error').reset_index().rename(columns={'date':'target_time'})
        worst = worst.rename(columns={worst.columns[0]:'target_time'})
        worst['target_time'] = worst.target_time.astype(str)
        worst[['actual','predicted','abs_error','previous_wh']] = worst[['actual','predicted','abs_error','previous_wh']].round(2)
        report['modes'][mode] = {'groups':groups,'by_hour':by_hour,'worst':worst.to_dict('records'),
                                 'peak_squared_error_share_pct':round(100*peak_sse/denominator,1) if denominator else 0}
        print(mode,json.dumps({'groups':groups,'peak_squared_error_share_pct':report['modes'][mode]['peak_squared_error_share_pct']},ensure_ascii=False),flush=True)
    (ROOT/'models/error_analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data',required=True)
    main(parser.parse_args().data)
