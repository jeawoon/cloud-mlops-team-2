"""Refresh version-bound laundry intervals and fixed example outputs after review.

Does not change labels, example IDs, device models, or model selection. Calibration
uses the same previously inspected retrospective test partition as the old release.
"""
import argparse
import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from train_larco import features
from prepare_calibration import interval_report
from retrain_larco import SOURCE_SHA


def main(csv,baseline_calibration):
    if hashlib.sha256(csv.read_bytes()).hexdigest()!=SOURCE_SHA:raise ValueError('Unexpected source checksum')
    root=Path(__file__).parent/'models'
    model_path=root/'larco_cycle_model.joblib'
    model=joblib.load(model_path)
    raw=pd.read_csv(csv)
    held=raw.set_index('file_path').loc[model['metrics']['test_cycle_ids']].reset_index()
    cal,evaluation=[],[]
    for _,group in held.groupby('machine',sort=True):
        group=group.sort_values('timestamp')
        n=len(group)//2;cal.append(group.iloc[:n]);evaluation.append(group.iloc[n:])
    cal=pd.concat(cal);evaluation=pd.concat(evaluation);combined=pd.concat([cal,evaluation])
    p=np.maximum(model['models']['energy'].predict(features(combined)),0)
    path=root/'calibration_metrics.json';data=json.loads(path.read_text())
    interval=interval_report(combined.total_energy_consumed_wh.to_numpy(),p,len(cal))
    prior=json.loads(baseline_calibration.read_text())['calibrations']['laundry']['radius_wh']
    interval['new_calibration_radius_wh']=interval['radius_wh']
    interval['radius_wh']=max(prior,interval['radius_wh'])
    interval['radius_rule']='Do not narrow below the previous release radius without fresh calibration labels'
    interval['observed_coverage']=float(np.mean(np.abs(combined.total_energy_consumed_wh.to_numpy()[len(cal):]-p[len(cal):])<=interval['radius_wh']))
    interval['note']+=' 새 모델 구간은 이전 배포 구간 폭보다 축소하지 않았습니다.'
    data['calibrations']['laundry']=interval
    digest=hashlib.sha256(model_path.read_bytes()).hexdigest()
    data['models_sha256']['larco_cycle_model.joblib']=digest
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False))
    fixture_path=root/'verification_cases.json';fixture=json.loads(fixture_path.read_text())
    for case in fixture['cases']:
        if not case['id'].startswith('laundry-'):continue
        settings=case['payload']['plans'][0]['settings']
        row=pd.DataFrame([dict(machine=settings['machine'],program_name=settings['program'],program_heat=settings['heat'],target_load=settings['load_kg'],ambient_temp=settings['ambient_temp'])])
        case['reference_prediction_wh']=max(0,float(model['models']['energy'].predict(features(row))[0]))
    fixture['model_sha256']['larco_cycle_model.joblib']=digest
    fixture_path.write_text(json.dumps(fixture,ensure_ascii=False,indent=2,allow_nan=False))
    print(json.dumps(data['calibrations']['laundry'],ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv',required=True,type=Path)
    parser.add_argument('--baseline-calibration',required=True,type=Path)
    args=parser.parse_args()
    main(args.csv,args.baseline_calibration)
