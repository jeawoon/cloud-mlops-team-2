"""Fridge/dishwasher appliance-only forecasts, selected on temporal validation."""
import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor,ExtraTreesRegressor
from sklearn.metrics import r2_score,mean_absolute_error
from src.device_forecast import DEVICES,COLUMNS,training_features

ROOT=Path(__file__).parent


def load(path):
    cols=[c for c,_ in DEVICES.values()]
    pieces=[]
    for chunk in pd.read_csv(path,usecols=['Time','Issues']+cols,chunksize=200000):
        chunk['Time']=pd.to_datetime(chunk.Time)
        chunk.loc[chunk.Issues!=0,cols]=np.nan
        for c in cols:chunk[c]=chunk[c].where(chunk[c].between(0,4000))
        # label=right denotes the end of a completed bin, available at forecast time.
        pieces.append(chunk.set_index('Time')[cols].resample('10min',closed='left',label='right').agg(['sum','count']))
    bins=pd.concat(pieces).groupby(level=0).sum().asfreq('10min')
    return pd.DataFrame({c:(bins[(c,'sum')]/bins[(c,'count')]/6).where(bins[(c,'count')]>=60) for c in cols})


def score(y,p):
    return {'r2':float(r2_score(y,p)),'mae_wh':float(mean_absolute_error(y,p)),
            'rmse_wh':float(np.sqrt(np.mean((np.asarray(y)-p)**2)))}


def main():
    path=ROOT/'data/refit/CLEAN_House2.csv'
    digest=hashlib.md5()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):digest.update(block)
    if digest.hexdigest()!='13957fd139bf8f6ba8bceea36e85bb3d':raise ValueError('Source checksum mismatch')
    readings=load(path)
    models,reports={},{}
    for key,(channel,label) in DEVICES.items():
        series=readings[channel]
        data=training_features(series).assign(target=series.shift(-1))
        a,b=int(len(data)*.6),int(len(data)*.8)
        train,valid,test=[p.dropna() for p in (data.iloc[:a-1],data.iloc[a:b-1],data.iloc[b:])]
        candidates={f'hist_{leaf}':HistGradientBoostingRegressor(max_iter=250,max_leaf_nodes=leaf,min_samples_leaf=40,l2_regularization=10,learning_rate=.05,early_stopping=False,random_state=42) for leaf in (7,15,31)}
        candidates['extra_trees']=ExtraTreesRegressor(n_estimators=150,min_samples_leaf=15,max_features=.8,n_jobs=2,random_state=42)
        validation={}
        for name,model in candidates.items():
            model.fit(train[COLUMNS],train.target)
            validation[name]=score(valid.target,np.maximum(model.predict(valid[COLUMNS]),0))
        selected=max(validation,key=lambda n:validation[n]['r2'])
        model=candidates[selected]
        both=pd.concat([train,valid])
        model.fit(both[COLUMNS],both.target)
        pred=np.maximum(model.predict(test[COLUMNS]),0)
        reports[key]={'label':label,'source':'https://zenodo.org/records/5063428','license':'CC-BY-4.0','house':'House2','channel':channel,
                      'target':'next completed 10-minute appliance Wh','selected':selected,'validation':validation,
                      'test':score(test.target,pred),'persistence_test':score(test.target,test.lag_0.to_numpy()),
                      'train_rows':len(train),'validation_rows':len(valid),'test_rows':len(test),
                      'test_start':str(test.index.min()),'test_end':str(test.index.max()),
                      'note':'Only this appliance historical energy and calendar features. No whole-house features. Not a planned complete-cycle scenario test; previously inspected time period needs independent future confirmation.'}
        models[key]=model
        print(key,json.dumps(reports[key]['test']),'rows',len(test),selected,flush=True)
    joblib.dump({'models':models,'columns':COLUMNS,'metrics':reports},ROOT/'models/device_forecast_model.joblib')
    (ROOT/'models/device_forecast_metrics.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':main()
