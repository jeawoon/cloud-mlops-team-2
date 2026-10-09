"""Sum selected-appliance plans, without restoring a whole-house model."""
from src.device_forecast import numeric,predict_device
from src.laundry import predict_laundry


def calculate_plan(data,catalog,get_bundle):
    if not isinstance(data,dict):raise ValueError('JSON object required')
    plans=data.get('plans')
    if not isinstance(plans,list) or not 1<=len(plans)<=9:raise ValueError('가전을 1~9개 선택하세요')
    rate=numeric(data.get('unit_price_krw_per_kwh',200),'unit_price_krw_per_kwh',0,10000)
    seen=set();rows=[]
    for plan in plans:
        if not isinstance(plan,dict):raise ValueError('가전 계획을 확인하세요')
        key=plan.get('device')
        if key not in catalog['profiles'] or key in seen:raise ValueError('알 수 없거나 중복된 가전입니다')
        seen.add(key)
        qty=numeric(plan.get('quantity',1),'quantity',1,50)
        if int(qty)!=qty:raise ValueError('대수는 정수여야 합니다')
        qty=int(qty)
        start=numeric(plan.get('start_after_minutes',0),'start_after_minutes',0,1440)
        method=plan.get('method','power_time')
        settings=plan.get('settings',{})
        if not isinstance(settings,dict):raise ValueError('설정은 객체여야 합니다')
        if method=='power_time':
            power=numeric(settings.get('power_w'),'power_w',0,20000)
            duration=numeric(settings.get('duration_minutes'),'duration_minutes',0,1440)
            duty=numeric(settings.get('duty_cycle_pct',100),'duty_cycle_pct',0,100)/100
            standby=numeric(settings.get('standby_w',0),'standby_w',0,20000)
            wh=(power*duty+standby*(1-duty))*duration/60
            scope=f'지정 사용 시간 {duration:g}분'
            metrics=None
            note='소비전력·가동률·시간을 가정한 계산이며 이 계획의 R²는 검증되지 않았습니다.'
        elif method=='laundry_cycle' and key=='Appliance2':
            result=predict_laundry(get_bundle('larco_cycle_model.joblib'),dict(settings,unit_price_krw_per_kwh=rate))
            wh=result['energy_wh'];duration=result['estimated_duration_minutes']
            scope='세탁코스 1회 완료'
            metrics=result['measured_cycle_test_metrics'];note=result['note']
        elif method=='recent_forecast' and key in ('Appliance1','Appliance3'):
            device='fridge' if key=='Appliance1' else 'dishwasher'
            result=predict_device(get_bundle('device_forecast_model.joblib'),dict(settings,device=device,unit_price_krw_per_kwh=rate))
            wh=result['energy_wh'];duration=10
            scope='현재부터 다음 10분'
            metrics=result['metrics'];note=result['note']
            if start!=0:raise ValueError('최근 기록 모델은 현재부터 다음 10분만 지원합니다. 미래 시작 계획은 시간·소비전력 계산을 선택하세요')
        else:raise ValueError('이 가전에서 지원하지 않는 계산 방식입니다')
        energy=wh*qty
        rows.append({'device':key,'label':catalog['profiles'][key]['label'],'quantity':qty,'method':method,
                     'start_after_minutes':start,'duration_minutes':duration,'scope':scope,
                     'energy_wh':energy,'energy_kwh':energy/1000,'cost_krw':energy/1000*rate,
                     'metrics':metrics,'note':note})
    total=sum(r['energy_wh'] for r in rows)
    return {'items':rows,'selected_appliances_wh':total,'selected_appliances_kwh':total/1000,
            'selected_appliances_cost_krw':total/1000*rate,'unit_price_krw_per_kwh':rate,'plan_r2':None,
            'note':'선택한 가전의 각 사용 계획 합계입니다. 집 전체 소비전력 또는 같은 10분 구간의 합계가 아닙니다. 시작 지연은 고정 단가 계산의 비용에 영향을 주지 않습니다.'}
