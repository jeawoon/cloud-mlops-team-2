"""Appliance-only future ten-minute forecasts; never whole-house output."""
import math
import numpy as np
import pandas as pd

DEVICES={'fridge':('Appliance1','냉장·냉동고'),'dishwasher':('Appliance3','식기세척기')}
COLUMNS=[f'lag_{i}' for i in range(6)]+['change','mean','std','hour_sin','hour_cos','weekend']


def numeric(value,name,low,high):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError(f'{name}: {low}~{high} 범위의 숫자를 입력하세요')
    return float(value)


def training_features(series):
    frame=pd.DataFrame({f'lag_{i}':series.shift(i) for i in range(6)})
    frame['change']=series.diff()
    frame['mean']=series.rolling(6).mean()
    frame['std']=series.rolling(6).std(ddof=0)
    h=series.index.hour+series.index.minute/60
    frame['hour_sin'],frame['hour_cos']=np.sin(2*np.pi*h/24),np.cos(2*np.pi*h/24)
    frame['weekend']=(series.index.weekday>=5).astype(int)
    return frame[COLUMNS]


def predict_device(bundle,payload):
    if not isinstance(payload,dict):raise ValueError('JSON object required')
    device=payload.get('device')
    if device not in DEVICES:raise ValueError('냉장·냉동고 또는 식기세척기를 선택하세요')
    recent=payload.get('recent_wh')
    if not isinstance(recent,list) or len(recent)!=6:raise ValueError('해당 가전의 최근 완료된 구간 6개가 필요합니다')
    recent=[numeric(v,'recent_wh',0,4000/6) for v in recent]
    hour=numeric(payload.get('hour'),'hour',0,23)
    minute=numeric(payload.get('minute',0),'minute',0,59)
    weekday=numeric(payload.get('weekday'),'weekday',0,6)
    if any(int(v)!=v for v in (hour,minute,weekday)):raise ValueError('시각과 요일은 정수여야 합니다')
    price=numeric(payload.get('unit_price_krw_per_kwh',200),'unit_price_krw_per_kwh',0,10000)
    h=hour+minute/60
    values=recent+[recent[0]-recent[1],float(np.mean(recent)),float(np.std(recent)),float(np.sin(2*np.pi*h/24)),float(np.cos(2*np.pi*h/24)),int(weekday>=5)]
    row=pd.DataFrame([values],columns=COLUMNS)
    wh=max(0,float(bundle['models'][device].predict(row)[0]))
    return {'device':device,'label':DEVICES[device][1],'horizon_minutes':10,'energy_wh':wh,'energy_kwh':wh/1000,
            'cost_krw':wh/1000*price,'metrics':bundle['metrics'][device]['test'],
            'test_rows':bundle['metrics'][device]['test_rows'],'cycle_scenario_r2':None,
            'note':'이 점수는 REFIT House2 가전의 최근 실측 기록으로 예측한 다음 10분 사용량 기준입니다. 임의 켜짐 계획·식기세척 코스 1회·다른 가정의 성능은 검증되지 않았습니다.'}
