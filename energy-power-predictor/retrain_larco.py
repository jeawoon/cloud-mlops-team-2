"""Reproduce retrospective public-cycle retraining; never synthesize operating labels.

Writes candidates to --out only. Deployment and interval/fixture version updates
are separate reviewed steps. Original test cycles were inspected previously.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor, GradientBoostingRegressor, HistGradientBoostingRegressor
from sklearn.svm import SVR
from sklearn.kernel_ridge import KernelRidge
from train_larco import INPUTS, CATEGORICAL, NUMERIC, features, score

SOURCE_SHA='23f8a0b79fb0719dd8d2f94fd592cab83c4085364a80ffe7d33f79803fadcc37'


def split_cycles(raw):
    data=raw[(raw.environment=='laboratory') & (raw.type=='wm')].copy()
    data['timestamp']=pd.to_datetime(data.timestamp,utc=True,errors='coerce')
    for c in ['ambient_temp','target_load','total_energy_consumed_wh','cycle_duration']:
        data[c]=pd.to_numeric(data[c],errors='coerce')
    data=data.drop_duplicates('file_path').dropna(subset=INPUTS+['timestamp','total_energy_consumed_wh','cycle_duration'])
    data=data[(data.total_energy_consumed_wh>0)&(data.cycle_duration>0)&data.target_load.between(0,20)&data.ambient_temp.between(0,50)]
    parts=[[],[],[]]
    for _,g in data.groupby('machine'):
        g=g.sort_values(['timestamp','file_path'])
        if len(g)<30:continue
        a,b=int(len(g)*.6),int(len(g)*.8)
        for part,values in zip(parts,(g.iloc[:a],g.iloc[a:b],g.iloc[b:])):part.append(values)
    if not all(parts):raise ValueError('Insufficient complete cycles')
    frames=[pd.concat(p) for p in parts]
    ids=[set(p.file_path) for p in frames]
    if any(ids[i]&ids[j] for i,j in ((0,1),(0,2),(1,2))):raise ValueError('Cycle leakage')
    return frames


def pipeline(model):
    transform=ColumnTransformer([('cat',OneHotEncoder(handle_unknown='ignore',sparse_output=False),CATEGORICAL),('num',StandardScaler(),NUMERIC)])
    return make_pipeline(transform,model)


def candidates(existing):
    result={'existing_spec':clone(existing)}
    for leaf in (1,2,4):
        for name,kind in (('extra',ExtraTreesRegressor),('forest',RandomForestRegressor)):
            result[f'{name}_leaf{leaf}']=pipeline(kind(n_estimators=300,min_samples_leaf=leaf,random_state=42,n_jobs=2))
    for depth in (2,3,4):
        for count in (400,800):
            result[f'gradient_d{depth}_{count}']=pipeline(GradientBoostingRegressor(n_estimators=count,max_depth=depth,min_samples_leaf=3,learning_rate=.03,random_state=42))
    for gamma in (.01,.05,.2):
        for cost in (100,1000,5000):
            result[f'svr_g{gamma}_C{cost}']=pipeline(SVR(C=cost,gamma=gamma,epsilon=10))
        for alpha in (.01,.1,1):
            result[f'kernel_g{gamma}_a{alpha}']=pipeline(KernelRidge(alpha=alpha,kernel='rbf',gamma=gamma))
    for leaves in (7,15,31):
        result[f'hist_{leaves}']=pipeline(HistGradientBoostingRegressor(max_iter=400,max_leaf_nodes=leaves,min_samples_leaf=10,learning_rate=.05,l2_regularization=10,early_stopping=False,random_state=42))
    return result


def select_candidate(models,train,valid):
    reports={}
    for name,model in models.items():
        model.fit(features(train),train.total_energy_consumed_wh)
        reports[name]=score(valid.total_energy_consumed_wh,np.maximum(model.predict(features(valid)),0))
    selected=min(reports,key=lambda name:reports[name]['mae'])
    return selected,reports


def main(args):
    source_digest=hashlib.sha256(args.csv.read_bytes()).hexdigest()
    if source_digest!=SOURCE_SHA:raise ValueError('Unexpected source checksum')
    old=joblib.load(args.baseline)
    train,valid,test=split_cycles(pd.read_csv(args.csv))
    if test.file_path.tolist()!=old['metrics']['test_cycle_ids']:raise ValueError('Test population changed')
    models=candidates(old['models']['energy'])
    name,validation=select_candidate(models,train,valid)
    model=models[name]
    both=pd.concat([train,valid])
    model.fit(features(both),both.total_energy_consumed_wh)
    actual=test.total_energy_consumed_wh
    before=np.maximum(old['models']['energy'].predict(features(test)),0)
    after=np.maximum(model.predict(features(test)),0)
    a,b=score(actual,before),score(actual,after)
    report=dict(source=old['metrics']['source'],license=old['metrics']['license'],source_sha256=source_digest,
                baseline_sha256=hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
                selected=name,candidate_count=len(models),selection='minimum validation MAE; test only compares the validation-selected finalist',
                validation=validation,before=a,after=b,mae_reduction_pct=(a['mae']-b['mae'])/a['mae']*100,
                r2_delta=b['r2']-a['r2'],train_cycles=len(train),validation_cycles=len(valid),test_cycles=len(test),
                promotion_eligible=b['mae']<a['mae'] and b['r2']>=a['r2'],
                operating_feedback_labels_used=0,scope='Previously inspected LARCO laboratory cycle test; retrospective experiment, not fresh independent evaluation or operating-log retraining',
                targets_unchanged=True,duration_model_changed=False,
                split_ids={key:frame.file_path.tolist() for key,frame in zip(('train','validation','test'),(train,valid,test))},
                per_machine={key:dict(rows=len(g),before=score(g.total_energy_consumed_wh,before[test.machine.to_numpy()==key]),after=score(g.total_energy_consumed_wh,after[test.machine.to_numpy()==key])) for key,g in test.groupby('machine')})
    bundle=copy.deepcopy(old)
    bundle['models']['energy']=model
    metric=bundle['metrics']['reports']['energy']
    metric.update(selected=name,validation=validation,test=b)
    metric['examples']=[dict(machine=str(r.machine),program=str(r.program_name),heat=str(r.program_heat),load_kg=float(r.target_load),actual=float(r.total_energy_consumed_wh),predicted=float(p)) for (_,r),p in list(zip(test.iterrows(),after))[:10]]
    bundle['metrics']['retraining']=report
    args.out.mkdir(parents=True,exist_ok=True)
    joblib.dump(bundle,args.out/'larco_cycle_model.joblib')
    (args.out/'larco_cycle_metrics.json').write_text(json.dumps(bundle['metrics'],ensure_ascii=False,indent=2,allow_nan=False))
    (args.out/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    test[['file_path','machine','total_energy_consumed_wh']].assign(before_wh=before,after_wh=after).to_csv(args.out/'paired_predictions.csv',index=False)
    print(json.dumps({k:report[k] for k in ('selected','candidate_count','before','after','mae_reduction_pct','r2_delta','promotion_eligible')},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv',required=True,type=Path)
    parser.add_argument('--baseline',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    main(parser.parse_args())
