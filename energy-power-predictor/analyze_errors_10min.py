"""Existing 10-minute model holdout diagnostics; no model mutation."""
import argparse
import hashlib
import json
import joblib
import numpy as np
import pandas as pd
from analyze_errors import ROOT, summarize
from train_recent import COLUMNS


def main(data_path):
    raw = pd.read_csv(data_path,parse_dates=['date']).sort_values('date').set_index('date').asfreq('10min')
    X = pd.DataFrame(index=raw.index)
    X['indoor_temp'] = raw[[f'T{i}' for i in range(1,10)]].mean(axis=1)
    X['indoor_humidity'] = raw[[f'RH_{i}' for i in range(1,10)]].mean(axis=1)
    X['outdoor_temp'],X['outdoor_humidity'] = raw.T_out,raw.RH_out
    hour = raw.index.hour+raw.index.minute/60
    X['hour_sin'],X['hour_cos'] = np.sin(2*np.pi*hour/24),np.cos(2*np.pi*hour/24)
    X['weekend'] = (raw.index.weekday>=5).astype(int)
    for i in range(6):
        X[f'lag_{i}'] = raw.Appliances.shift(i)
    X['change'] = X.lag_0-X.lag_1
    X['recent_mean'] = X[[f'lag_{i}' for i in range(6)]].mean(axis=1)
    X['recent_std'] = X[[f'lag_{i}' for i in range(6)]].std(axis=1,ddof=0)
    data = X.assign(target=raw.Appliances.shift(-1)).dropna()
    a,b = int(len(data)*.6),int(len(data)*.8)
    train,test = data.iloc[:a-1],data.iloc[b:]
    path = ROOT/'models/recent_model.joblib'
    bundle = joblib.load(path)
    expected = bundle['metrics']['1']
    if len(test)!=expected['test_rows'] or str(test.index.min())!=expected['test_start']:
        raise ValueError('Holdout does not match saved model evaluation')
    threshold = float(train.target.quantile(.9))
    frame = pd.DataFrame({'actual':test.target,'predicted':bundle['models']['1'].predict(test[COLUMNS]),'previous_wh':test.lag_0})
    frame.index += pd.Timedelta(minutes=10)
    frame['abs_error'] = (frame.predicted-frame.actual).abs()
    frame['peak'] = frame.actual>=threshold
    frame['jump'] = frame.actual-frame.previous_wh>=threshold
    sse = (frame.predicted-frame.actual)**2
    groups = {'전체':summarize(frame),'평상시':summarize(frame[~frame.peak]),'피크':summarize(frame[frame.peak]),'급상승':summarize(frame[frame.jump])}
    worst = frame.nlargest(20,'abs_error').reset_index()
    worst = worst.rename(columns={worst.columns[0]:'target_time'})
    worst.target_time = worst.target_time.astype(str)
    worst[['actual','predicted','abs_error','previous_wh']] = worst[['actual','predicted','abs_error','previous_wh']].round(2)
    report = {'model_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'test_rows':len(test),'peak_threshold_wh':threshold,
              'detail':{'groups':groups,'peak_squared_error_share_pct':round(float(sse[frame.peak].sum()/sse.sum()*100),1),
                        'by_hour':[{'hour':int(h),**summarize(p)} for h,p in frame.groupby(frame.index.hour)],'worst':worst.to_dict('records')}}
    (ROOT/'models/error_analysis_10min.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(groups,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',required=True)
    main(parser.parse_args().data)
