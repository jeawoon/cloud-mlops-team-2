"""LARCO real laboratory cycle energy labels; pre-operation settings only."""
import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder,StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import Ridge
from sklearn.ensemble import ExtraTreesRegressor,GradientBoostingRegressor
from sklearn.metrics import r2_score,mean_absolute_error

ROOT=Path(__file__).parent
INPUTS=['machine','program_name','program_heat','ambient_temp','target_load']
CATEGORICAL=['machine','program_name','program_heat']
NUMERIC=['ambient_temp','target_load','nominal_heat','heating_load_proxy']


def features(data):
    frame=data[INPUTS].copy()
    for c in CATEGORICAL:frame[c]=frame[c].astype(str)
    frame['nominal_heat']=frame.program_heat.map(lambda s:np.mean([float(v) for v in s.split('-')]))
    frame['heating_load_proxy']=frame.target_load*(frame.nominal_heat-frame.ambient_temp).clip(lower=0)
    return frame[CATEGORICAL+NUMERIC]


def score(y,p):
    return {'r2':float(r2_score(y,p)),'mae':float(mean_absolute_error(y,p)),
            'rmse':float(np.sqrt(np.mean((np.asarray(y)-p)**2)))}


def fit_selected(train,valid,target):
    models={'ridge':Ridge(alpha=1),
            'gradient_depth2':GradientBoostingRegressor(n_estimators=200,max_depth=2,min_samples_leaf=3,learning_rate=.03,random_state=42),
            'gradient_depth3':GradientBoostingRegressor(n_estimators=200,max_depth=3,min_samples_leaf=3,learning_rate=.03,random_state=42),
            'extra_trees':ExtraTreesRegressor(n_estimators=200,min_samples_leaf=2,random_state=42,n_jobs=2)}
    trials,pipelines={},{}
    for name,m in models.items():
        transform=ColumnTransformer([('cat',OneHotEncoder(handle_unknown='ignore',sparse_output=False),CATEGORICAL),('num',StandardScaler(),NUMERIC)])
        pipe=make_pipeline(transform,m)
        pipe.fit(features(train),train[target])
        trials[name]=score(valid[target],np.maximum(pipe.predict(features(valid)),0))
        pipelines[name]=pipe
    selected=max(trials,key=lambda n:trials[n]['r2'])
    pipe=pipelines[selected]
    all_train=pd.concat([train,valid])
    pipe.fit(features(all_train),all_train[target])
    return pipe,selected,trials


def main():
    folder=ROOT/'data/larco'
    path=folder/'aggregated_data.csv'
    manifest=json.loads((folder/'manifest.json').read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['sha256']:raise ValueError('Source checksum mismatch')
    raw=pd.read_csv(path)
    data=raw[(raw.environment=='laboratory')&(raw.type=='wm')].copy()
    data['timestamp']=pd.to_datetime(data.timestamp,utc=True,errors='coerce')
    for c in ['ambient_temp','target_load','total_energy_consumed_wh','cycle_duration']:
        data[c]=pd.to_numeric(data[c],errors='coerce')
    data=data.drop_duplicates('file_path').dropna(subset=INPUTS+['timestamp','total_energy_consumed_wh','cycle_duration'])
    data=data[(data.total_energy_consumed_wh>0)&(data.cycle_duration>0)&data.target_load.between(0,20)&data.ambient_temp.between(0,50)]
    parts=[[],[],[]]
    for machine,g in data.groupby('machine'):
        g=g.sort_values(['timestamp','file_path'])
        if len(g)<30:continue
        a,b=int(len(g)*.6),int(len(g)*.8)
        for i,part in enumerate((g.iloc[:a],g.iloc[a:b],g.iloc[b:])):parts[i].append(part)
    train,valid,test=[pd.concat(p) for p in parts]
    if set(train.file_path)&set(test.file_path) or set(valid.file_path)&set(test.file_path):raise ValueError('Cycle leakage')
    models,reports={},{}
    for key,target,unit in [('energy','total_energy_consumed_wh','Wh per complete washing cycle'),('duration','cycle_duration','minutes per complete washing cycle')]:
        model,selected,trials=fit_selected(train,valid,target)
        pred=np.maximum(model.predict(features(test)),0)
        models[key]=model
        baseline=pd.concat([train,valid]).groupby('machine')[target].mean()
        reports[key]={'unit':unit,'selected':selected,'validation':trials,'test':score(test[target],pred),
                      'machine_mean_baseline':score(test[target],test.machine.map(baseline).to_numpy()),
                      'examples':[{'machine':str(r.machine),'program':str(r.program_name),'heat':str(r.program_heat),'load_kg':float(r.target_load),'actual':float(r[target]),'predicted':float(p)} for (_,r),p in list(zip(test.iterrows(),pred))[:10]]}
        print(key,json.dumps(reports[key]['test']),selected,flush=True)
    calibration=pd.concat([train,valid])
    catalog={}
    for machine,g in calibration.groupby('machine'):
        options=[]
        for (program,heat),group in g.groupby(['program_name','program_heat']):
            options.append({'program':str(program),'heat':str(heat),'min_load_kg':float(group.target_load.min()),'max_load_kg':float(group.target_load.max()),'observations':len(group)})
        catalog[machine]={'options':options,'ambient_min':float(g.ambient_temp.min()),'ambient_max':float(g.ambient_temp.max())}
    report={'source':manifest['source'],'license':manifest['license'],'population':'laboratory washing machines only; not household schedules',
            'input_fields':INPUTS,'excluded_inputs':['actual cycle_duration','actual energy','power statistics','post-cycle weights','cycle-average observed temperatures','KPIs'],
            'rows':len(data),'train_cycles':len(train),'validation_cycles':len(valid),'test_cycles':len(test),
            'split':'Within each machine, complete cycles ordered by acquisition timestamp: first 60% train, next 20% validation, last 20% test. No one-second row splitting.',
            'test_cycle_ids':test.file_path.tolist(),'reports':reports,'whole_house_scenario_r2':None,
            'note':'Measured complete-cycle energy labels. Not next-10-minute labels or arbitrary household counterfactual outcomes. Does not establish performance on unseen appliance models or Korean homes.'}
    joblib.dump({'models':models,'catalog':catalog,'metrics':report},ROOT/'models/larco_cycle_model.joblib')
    (ROOT/'models/larco_cycle_metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    print('Cycles',len(train),len(valid),len(test),flush=True)


if __name__=='__main__':main()
