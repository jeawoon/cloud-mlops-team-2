"""Past-only optional 24-hour features. No future observation is used."""
import numpy as np
import pandas as pd
from src.device_forecast import training_features


def extended_features(series):
    frame=training_features(series)
    for lag in (6,12,36,72,143):frame[f'long_lag_{lag}']=series.shift(lag)
    for window in (12,36,144):
        rolling=series.rolling(window,min_periods=window)
        for name in ('mean','std','min','max'):
            frame[f'last_{window}_{name}']=getattr(rolling,name)()
    return frame


def inference_row(values,hour,minute,weekday):
    # Input is oldest first. Synthetic dates only build past lags; calendar is replaced.
    series=pd.Series(values,index=pd.date_range('2020-01-01',periods=len(values),freq='10min'))
    row=extended_features(series).iloc[[-1]].copy()
    h=hour+minute/60
    row['hour_sin']=np.sin(2*np.pi*h/24);row['hour_cos']=np.cos(2*np.pi*h/24)
    row['weekend']=int(weekday>=5)
    return row
