"""Keep deployed central models unchanged; compare optional 24h candidates.

Intervals use first half of OLD test for calibration, second half for coverage.
This is retrospective, serial, previously inspected data, not a new independent test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingRegressor
from src.device_forecast import COLUMNS,DEVICES,training_features
from src.extended_history import extended_features
from train_device_forecasts import load,score
from train_larco import features

ROOT=Path(__file__).parent


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def interval_report(y,p,n):
    residual=np.abs(np.asarray(y[:n])-np.asarray(p[:n]))
    q=float(np.quantile(residual,min(1,np.ceil((n+1)*.9)/n),method='higher'))
    actual=np.asarray(y[n:]);pred=np.asarray(p[n:])
    return dict(radius_wh=q,nominal_coverage=.9,calibration_rows=n,evaluation_rows=len(actual),
                observed_coverage=float(np.mean((actual>=np.maximum(0,pred-q))&(actual<=pred+q))),
                note='기존 테스트 전반부 잔차로 보정하고 후반부에서 포함률 확인. 시계열 의존·분포 변화가 있어 90% 포함을 보장하지 않습니다. 새 독립 테스트가 아닙니다.')


def main(args):
    model_path=ROOT/'models/device_forecast_model.joblib'
    old=joblib.load(model_path)
    raw_md5=hashlib.md5()
    with Path(args.refit_csv).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):raw_md5.update(block)
    if raw_md5.hexdigest()!='13957fd139bf8f6ba8bceea36e85bb3d':raise ValueError('Unexpected REFIT file')
    readings=load(Path(args.refit_csv))
    calibrations={};models={};reports={}
    for device,(channel,_) in DEVICES.items():
        series=readings[channel]
        data=training_features(series).assign(target=series.shift(-1))
        b=int(len(data)*.8);test=data.iloc[b:].dropna()
        pred=np.maximum(old['models'][device].predict(test[COLUMNS]),0)
        calibrations[device]=interval_report(test.target.to_numpy(),pred,len(test)//2)
        frame=extended_features(series).assign(target=series.shift(-1))
        columns=[c for c in frame if c!='target']
        a=int(len(frame)*.6)
        train,valid,held=[p.dropna() for p in (frame.iloc[:a-1],frame.iloc[a:b-1],frame.iloc[b:])]
        candidates={'six_bin_baseline':(clone(old['models'][device]),COLUMNS),
                    '24h_hist_15':(HistGradientBoostingRegressor(max_iter=250,max_leaf_nodes=15,min_samples_leaf=40,l2_regularization=10,learning_rate=.05,early_stopping=False,random_state=42),columns),
                    '24h_hist_31':(HistGradientBoostingRegressor(max_iter=250,max_leaf_nodes=31,min_samples_leaf=40,l2_regularization=10,learning_rate=.05,early_stopping=False,random_state=42),columns)}
        validation={}
        for name,(m,cols) in candidates.items():
            m.fit(train[cols],train.target)
            validation[name]=score(valid.target,np.maximum(m.predict(valid[cols]),0))
        chosen=max(validation,key=lambda n:validation[n]['r2'])
        evaluation={}
        for name,(m,cols) in candidates.items():
            m.fit(pd.concat([train,valid])[cols],pd.concat([train,valid]).target)
            p=np.maximum(m.predict(held[cols]),0)
            evaluation[name]=score(held.target,p)
            if name==chosen:
                models[device]=dict(model=m,columns=cols)
                calibrations[device+'_extended']=interval_report(held.target.to_numpy(),p,len(held)//2)
        frozen=np.maximum(old['models'][device].predict(held[COLUMNS]),0)
        reports[device]=dict(selected_on_validation=chosen,validation=validation,test=evaluation,
                             deployed_model_same_test=score(held.target,frozen),
                             train_rows=len(train),validation_rows=len(valid),test_rows=len(held),
                             note='두 피처 방식은 동일 샘플·동일 시각 경계에서 비교. 선택은 검증 R²만 사용. 기본 배포 모델은 변경하지 않음. 24시간 옵션도 House2 실험으로 다른 집 일반화는 미검증.')
        print(device,json.dumps(reports[device]),flush=True)
    joblib.dump({'models':models,'metrics':reports},ROOT/'models/device_extended_model.joblib')
    if sha(args.larco_csv)!='23f8a0b79fb0719dd8d2f94fd592cab83c4085364a80ffe7d33f79803fadcc37':raise ValueError('Unexpected LARCO file')
    laundry=joblib.load(ROOT/'models/larco_cycle_model.joblib')
    raw=pd.read_csv(args.larco_csv)
    selected=raw.set_index('file_path').loc[laundry['metrics']['test_cycle_ids']].reset_index()
    cal=[];evaluation=[]
    for _,g in selected.groupby('machine',sort=True):
        g=g.sort_values('timestamp');n=len(g)//2;cal.append(g.iloc[:n]);evaluation.append(g.iloc[n:])
    cal=pd.concat(cal);evaluation=pd.concat(evaluation);combined=pd.concat([cal,evaluation])
    p=np.maximum(laundry['models']['energy'].predict(features(combined)),0)
    calibrations['laundry']=interval_report(combined.total_energy_consumed_wh.to_numpy(),p,len(cal))
    result=dict(models_sha256={name:sha(ROOT/'models'/name) for name in ('device_forecast_model.joblib','device_extended_model.joblib','larco_cycle_model.joblib')},
                calibrations=calibrations,experiments=reports,
                scope='retrospective existing test splits only; no unseen homes or new independent future labels')
    (ROOT/'models/calibration_metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    print('calibration',json.dumps(calibrations,ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--refit-csv',required=True);p.add_argument('--larco-csv',required=True)
    main(p.parse_args())
