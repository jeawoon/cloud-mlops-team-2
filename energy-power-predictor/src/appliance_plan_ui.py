"""Multi-select appliance planner with explicit formula/model distinctions."""
import json
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from src.simulator_ui import load_laundry

ROOT=Path(__file__).resolve().parents[1]


def render_plan(request_prediction):
    catalog=json.loads((ROOT/'models/appliance_power_catalog.json').read_text())
    profiles=catalog['profiles']
    st.title('가전 선택·예상 전력량·전기료')
    st.caption('가전을 여러 개 선택하고 사용 계획을 입력하세요. 집 전체 예측 모델 없이 선택한 가전만 계산합니다.')
    selected=st.multiselect('사용할 가전 선택 — 여러 개 선택 가능',list(profiles),default=['Appliance2'],format_func=lambda k:profiles[k]['label'],key='plan_devices')
    rate=st.number_input('적용 단가 (원/kWh)',min_value=0.0,max_value=10000.0,value=200.0,step=10.0,key='plan_rate')
    st.caption('200원은 예시입니다. 실제 적용할 단가를 입력하세요. 예상 kWh × 단가로 계산하며 누진·기본요금·세금·할인은 별도 반영하지 않습니다.')
    if not selected:
        st.info('위 목록에서 가전을 선택하면 입력칸과 예상 결과가 표시됩니다.')
        return
    plans=[]
    for key in selected:
        profile=profiles[key]
        with st.expander(profile['label']+' 사용 계획',expanded=True):
            choices=['시간·소비전력 입력']
            if key=='Appliance2':choices.append('세탁코스 학습 모델')
            if key in ('Appliance1','Appliance3'):choices.append('최근 기록 학습 모델 — 다음 10분')
            method_label=st.selectbox('계산 방식',choices,key='plan_method_'+key)
            qty=st.number_input('사용 대수',min_value=1,max_value=50,value=1,key='plan_qty_'+key)
            settings={}
            if method_label=='시간·소비전력 입력':
                method='power_time'
                a,b,c=st.columns(3)
                with a:duration=st.number_input('사용 시간 (분)',min_value=0.0,max_value=1440.0,value=10.0,step=5.0,key='plan_duration_'+key)
                with b:power=st.number_input('가동 소비전력 (W)',min_value=0.0,max_value=20000.0,value=float(profile['active_w']),step=10.0,key='plan_power_'+key)
                with c:duty=st.slider('시간 중 가동 비율 (%)',0,100,50 if key=='Appliance1' else 100,key='plan_duty_'+key)
                start=st.number_input('몇 분 후 사용할 예정인가요?',min_value=0.0,max_value=1440.0,value=0.0,step=5.0,key='plan_start_'+key)
                settings=dict(power_w=power,duration_minutes=duration,duty_cycle_pct=duty,standby_w=profile['standby_w'])
                st.caption(f"기본 가동 W는 REFIT House2의 가전 실측 평균({profile['active_w']:.2f}W)입니다. 내 제품의 값을 입력하면 더 알맞게 계산할 수 있습니다. 가동 비율 기본값은 예시 가정이며, 이 계획 계산의 R²는 검증되지 않았습니다.")
            elif method_label=='세탁코스 학습 모델':
                method='laundry_cycle'
                laundry=load_laundry()
                machine=st.selectbox('세탁기 제품 모델',sorted(laundry['catalog']),key='plan_machine')
                if 'flt' in machine:st.warning('고장 상태 실험 제품입니다.')
                entry=laundry['catalog'][machine]
                option_idx=st.selectbox('프로그램·설정 온도',range(len(entry['options'])),format_func=lambda i:f"{entry['options'][i]['program']} / {entry['options'][i]['heat']}°C",key='plan_program_'+machine)
                option=entry['options'][option_idx]
                lo,hi=option['min_load_kg'],option['max_load_kg']
                if lo==hi:
                    weight=lo;st.write(f'측정 조건의 세탁물 무게: {weight:g}kg')
                else:weight=st.number_input('세탁물 무게 (kg)',min_value=lo,max_value=hi,value=(lo+hi)/2,step=.5,key=f'plan_weight_{machine}_{option_idx}')
                temp=st.number_input('시작 전 주변 온도 (°C)',min_value=entry['ambient_min'],max_value=entry['ambient_max'],value=25.,step=1.,key='plan_temp_'+machine)
                start=st.number_input('몇 분 후 시작하나요?',min_value=0.0,max_value=1440.0,value=0.0,step=5.0,key='plan_laundry_start')
                settings=dict(machine=machine,program=option['program'],heat=option['heat'],load_kg=weight,ambient_temp=temp)
                st.caption('실측 세탁코스 1회 완료까지 예측합니다. 실제 시간은 모델이 추정하며 중간에 끄는 시나리오는 지원하지 않습니다. 검증 R² 0.8835는 이 범위에만 해당합니다.')
            else:
                method='recent_forecast';start=0
                recent=[]
                cols=st.columns(3)
                for i in range(6):
                    with cols[i%3]:recent.append(st.number_input(f'{i*10}~{(i+1)*10}분 전 해당 가전 Wh',min_value=0.0,max_value=4000/6,value=5.0,step=1.,key=f'plan_recent_{key}_{i}'))
                now=datetime.now()
                a,b,c=st.columns(3)
                with a:hour=st.number_input('마지막 구간 종료 — 시',min_value=0,max_value=23,value=now.hour,key='plan_hour_'+key)
                with b:minute=st.selectbox('분',[0,10,20,30,40,50],index=now.minute//10,key='plan_minute_'+key)
                with c:weekday=st.selectbox('요일',range(7),format_func=lambda i:['월','화','수','목','금','토','일'][i],index=now.weekday(),key='plan_weekday_'+key)
                settings=dict(recent_wh=recent,hour=int(hour),minute=int(minute),weekday=int(weekday))
                st.caption('현재부터 다음 10분만 지원합니다. 이 점수는 실제 최근 기록 기준이며 사용 시간·코스를 바꾼 계획의 정확도가 아닙니다. 기본 기록은 데모입니다.')
            plans.append(dict(device=key,method=method,quantity=int(qty),start_after_minutes=start,settings=settings))
    result=request_prediction('/api/appliance-plan',dict(plans=plans,unit_price_krw_per_kwh=rate))
    st.divider()
    a,b=st.columns(2)
    a.metric('선택한 가전 예상 사용량 합계',f"{result['selected_appliances_kwh']:.4f} kWh")
    b.metric('선택한 가전 예상 추가요금 합계',f"{result['selected_appliances_cost_krw']:.2f}원")
    table=pd.DataFrame(result['items'])[['label','quantity','scope','start_after_minutes','duration_minutes','energy_wh','cost_krw']]
    st.dataframe(table.rename(columns={'label':'가전','quantity':'대수','scope':'예측·계산 범위','start_after_minutes':'시작까지 분','duration_minutes':'사용·예상 분','energy_wh':'예상 Wh','cost_krw':'예상 원'}),hide_index=True)
    st.info(result['note'])
    for row in result['items']:
        if row['metrics'] is not None:
            st.caption(f"{row['label']} — 해당 학습 모델의 실측 테스트 R² {row['metrics']['r2']:.4f}. 시간·소비전력 입력 방식에는 적용되지 않습니다.")
    st.caption('같은 유형의 여러 대는 같은 소비전력·운전 조건이라고 가정합니다. 냉장고·세탁기·식기세척기는 운전 단계나 자동 정지에 따라 실제 사용량이 달라질 수 있습니다.')
    st.markdown('[가전 기본 소비전력 출처: REFIT](https://zenodo.org/records/5063428) · [세탁코스 실측 출처: LARCO](https://zenodo.org/records/18657997)')
