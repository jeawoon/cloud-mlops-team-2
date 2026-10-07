"""REFIT whole-house forecast; separate from UCI appliance forecasts."""
import json
import hashlib
import zipfile
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

ROOT = Path(__file__).parent
COLUMNS = [f'lag_{i}' for i in range(6)] + ['change', 'mean', 'std', 'hour_sin', 'hour_cos', 'weekend']


def row(recent, typical_wh, hour, weekday):
    recent = np.asarray(recent)/typical_wh
    values = list(recent)+[recent[0]-recent[1], recent.mean(), recent.std(), np.sin(2*np.pi*hour/24), np.cos(2*np.pi*hour/24), int(weekday>=5)]
    return pd.DataFrame([values], columns=COLUMNS)


def load(path):
    pieces = []
    for chunk in pd.read_csv(path, usecols=['Time','Aggregate','Issues'], chunksize=200000):
        chunk['Time'] = pd.to_datetime(chunk['Time'])
        chunk.loc[chunk.Issues != 0, 'Aggregate'] = np.nan
        chunk = chunk.set_index('Time').Aggregate
        grouped = chunk.resample('10min').agg(['sum','count'])
        pieces.append(grouped)
    sums = pd.concat(pieces).groupby(level=0).sum().asfreq('10min')
    # A 10-minute bin normally contains about 75 eight-second readings.
    series = (sums['sum']/sums['count']/6).where(sums['count']>=60)
    return prepare(series)


def load_uci(path):
    with zipfile.ZipFile(path) as archive:
        with archive.open('household_power_consumption.txt') as handle:
            data = pd.read_csv(handle, sep=';', usecols=['Date','Time','Global_active_power'], na_values=['?'])
    dates = pd.to_datetime(data.Date+' '+data.Time, format='%d/%m/%Y %H:%M:%S')
    power = pd.Series(data.Global_active_power.to_numpy()*1000, index=dates)
    bins = power.resample('10min').agg(['mean','count'])
    series = (bins['mean']/6).where(bins['count']>=8)
    return prepare(series)


def prepare(series):
    split = int(len(series)*.60)
    scale = float(series.iloc[:split].median())
    z = series/scale
    frame = pd.DataFrame({f'lag_{i}':z.shift(i) for i in range(6)})
    frame['change'] = z-z.shift(1)
    frame['mean'] = z.rolling(6).mean()
    frame['std'] = z.rolling(6).std(ddof=0)
    hour = frame.index.hour+frame.index.minute/60
    frame['hour_sin'],frame['hour_cos'] = np.sin(2*np.pi*hour/24),np.cos(2*np.pi*hour/24)
    frame['weekend'] = (frame.index.weekday>=5).astype(int)
    return frame, z, scale


def main():
    for filename,expected in {'CLEAN_House11.csv':'5b41bae97ab28871fcfe5167b41c0347','CLEAN_House2.csv':'13957fd139bf8f6ba8bceea36e85bb3d'}.items():
        path=ROOT/'data/refit'/filename
        if not path.exists():continue
        digest=hashlib.md5()
        with path.open('rb') as handle:
            for block in iter(lambda:handle.read(1024*1024),b''):digest.update(block)
        if digest.hexdigest()!=expected:
            raise ValueError(f'Incomplete or corrupted REFIT download: {filename}')
    homes = [(p,*load(p)) for p in sorted((ROOT/'data/refit').glob('CLEAN_House*.csv'))]
    uci_path = ROOT/'data/household_power/household_power.zip'
    if uci_path.exists():
        homes.append((uci_path,*load_uci(uci_path)))
    models, metrics = {}, {}
    for steps in (1,6):
        sets = [[],[],[]]
        scales=[]
        for path, frame,z,scale in homes:
            target = pd.concat([z.shift(-i) for i in range(1,steps+1)],axis=1).mean(axis=1,skipna=False)
            data = frame.assign(target=target)
            a,b=int(len(data)*.6),int(len(data)*.8)
            for idx, part in enumerate([data.iloc[:a-steps],data.iloc[a:b-steps],data.iloc[b:]]):
                sets[idx].append(part.dropna())
            scales.append(scale)
        train,valid,test = [pd.concat(items) for items in sets]
        candidates={}
        for leaves in (7,15,31):
            model=HistGradientBoostingRegressor(max_iter=200,max_leaf_nodes=leaves,min_samples_leaf=40,l2_regularization=10,learning_rate=.05,early_stopping=False,random_state=42)
            model.fit(train[COLUMNS],train.target)
            candidates[leaves]=(r2_score(valid.target,model.predict(valid[COLUMNS])),model)
        best=max(candidates,key=lambda k:candidates[k][0])
        model=candidates[best][1]
        all_train=pd.concat([train,valid])
        model.fit(all_train[COLUMNS],all_train.target)
        pred=model.predict(test[COLUMNS])
        metrics[str(steps)]={'r2':round(float(r2_score(test.target,pred)),4),'mae_normalized':round(float(mean_absolute_error(test.target,pred)),4),'test_rows':len(test),'validation_r2':round(float(candidates[best][0]),4),'selected_leaves':best,'per_house':{}}
        for (path,_,_,scale), part in zip(homes,sets[2]):
            estimate=model.predict(part[COLUMNS])*scale
            metrics[str(steps)]['per_house'][path.stem]={'r2':round(float(r2_score(part.target*scale,estimate)),4),'mae_wh':round(float(mean_absolute_error(part.target*scale,estimate)),2),'persistence_r2':round(float(r2_score(part.target,part.lag_0)),4)}
        models[str(steps)]=model
        print(steps,metrics[str(steps)],flush=True)
    bundle={'models':models,'metrics':metrics,'columns':COLUMNS,'target':'whole-house electricity Wh per 10 minutes','source':'https://zenodo.org/records/5063428','additional_source':'https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption','license':'CC-BY-4.0'}
    joblib.dump(bundle,ROOT/'models/refit_model.joblib')
    out=ROOT/'reports/refit';out.mkdir(parents=True,exist_ok=True)
    (out/'evaluation.json').write_text(json.dumps(metrics,indent=2))
    manifest={'source':bundle['source'],'additional_source':bundle['additional_source'],'license':bundle['license'],'files':[]}
    for path,_,_,scale in homes:
        digest=hashlib.md5()
        with path.open('rb') as handle:
            for block in iter(lambda:handle.read(1024*1024),b''):digest.update(block)
        manifest['files'].append({'file':path.name,'md5':digest.hexdigest(),'training_median_wh':scale})
    (ROOT/'models/refit_sources.json').write_text(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
