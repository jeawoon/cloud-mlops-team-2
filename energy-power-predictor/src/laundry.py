"""Separate complete-cycle estimate with measured LARCO ground truth."""
import pandas as pd
from src.device_forecast import numeric
from train_larco import features


def predict_laundry(bundle,payload):
    if not isinstance(payload,dict):raise ValueError('JSON object required')
    machine=payload.get('machine')
    if machine not in bundle['catalog']:raise ValueError('학습된 제품 모델을 선택하세요')
    catalog=bundle['catalog'][machine]
    program,heat=payload.get('program'),payload.get('heat')
    option=next((o for o in catalog['options'] if o['program']==program and o['heat']==heat),None)
    if option is None:raise ValueError('학습에 포함된 코스·설정 온도를 선택하세요')
    load=numeric(payload.get('load_kg'),'load_kg',option['min_load_kg'],option['max_load_kg'])
    ambient=numeric(payload.get('ambient_temp'),'ambient_temp',catalog['ambient_min'],catalog['ambient_max'])
    price=numeric(payload.get('unit_price_krw_per_kwh',200),'unit_price_krw_per_kwh',0,10000)
    row=features(pd.DataFrame([dict(machine=machine,program_name=program,program_heat=heat,target_load=load,ambient_temp=ambient)]))
    wh=max(0,float(bundle['models']['energy'].predict(row)[0]))
    minutes=max(0,float(bundle['models']['duration'].predict(row)[0]))
    return {'scope':'complete washing cycle only','energy_wh':wh,'energy_kwh':wh/1000,'cost_krw':wh/1000*price,
            'estimated_duration_minutes':minutes,'measured_cycle_test_metrics':bundle['metrics']['reports']['energy']['test'],
            'test_cycles':bundle['metrics']['test_cycles'],'whole_house_scenario_r2':None,
            'note':'LARCO 실험실 세탁코스 1회 전체 사용량입니다. 다음 10분 또는 집 전체 시뮬레이션 정확도가 아닙니다. 다른 제품·실제 가정에서는 추가 검증이 필요합니다.'}
