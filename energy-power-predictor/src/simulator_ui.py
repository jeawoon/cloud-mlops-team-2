"""Measured washing-cycle simulator only; whole-house views removed."""
from pathlib import Path
import joblib
import pandas as pd
import streamlit as st
from datetime import datetime

ROOT=Path(__file__).resolve().parents[1]


@st.cache_resource
def load_laundry():
    return joblib.load(ROOT/'models/larco_cycle_model.joblib')


def render_laundry(request_prediction,rate):
    with st.expander('실측 정답 기반 — 세탁코스 1회 사용량·요금',expanded=True):
        b=load_laundry()
        st.info('이 기능은 LARCO 실험실에서 실제로 수행한 세탁코스의 소비전력으로 학습했습니다. 집 전체 또는 다음 10분 결과에 합산하지 않는 별도 모델입니다.')
        machine=st.selectbox('실험에서 측정한 세탁기 모델',sorted(b['catalog']),key='larco_machine')
        if 'flt' in machine:
            st.warning('고장 상태 실험 제품입니다. 정상 제품과 구분해서 해석하세요.')
        catalog=b['catalog'][machine]
        labels=[f"{o['program']} / 설정 {o['heat']}°C" for o in catalog['options']]
        choice=st.selectbox('세탁 프로그램·설정 온도',range(len(labels)),format_func=lambda i:labels[i],key='larco_program_'+machine)
        option=catalog['options'][choice]
        a,c=st.columns(2)
        with a:
            low,high=option['min_load_kg'],option['max_load_kg']
            if low==high:
                weight=low
                st.write(f'이 설정의 측정 세탁물 무게: {weight:g}kg')
            else:
                weight=st.number_input('세탁물 무게 (kg)',min_value=low,max_value=high,value=(low+high)/2,step=.5,key=f'larco_load_{machine}_{choice}')
        with c:
            temp=st.number_input('시작 전 주변 온도 (°C)',min_value=catalog['ambient_min'],max_value=catalog['ambient_max'],value=25.0 if catalog['ambient_min']<=25<=catalog['ambient_max'] else catalog['ambient_min'],step=1.0,key='larco_temp_'+machine)
        result=request_prediction('/api/laundry-cycle',dict(machine=machine,program=option['program'],heat=option['heat'],load_kg=weight,ambient_temp=temp,unit_price_krw_per_kwh=rate))
        a,c,d=st.columns(3)
        a.metric('세탁코스 1회 예상 사용량',f"{result['energy_wh']:.1f} Wh")
        c.metric('세탁코스 1회 예상 추가요금',f"{result['cost_krw']:.2f}원")
        d.metric('코스 예상 소요시간',f"{result['estimated_duration_minutes']:.0f}분")
        metrics=result['measured_cycle_test_metrics']
        st.caption(f"실측 코스 정답 테스트 {result['test_cycles']}회: R² {metrics['r2']:.4f}, MAE {metrics['mae']:.2f}Wh. 입력 단가 {rate:g}원/kWh 적용. 분 단위 중간 종료가 아니라 코스 완료까지의 사용량입니다.")
        st.warning(result['note'])
        st.caption('가전별로 기록 시각순 60/20/20 분할했으며 같은 코스의 초 단위 기록을 학습·테스트에 나누지 않았습니다. 실제 종료시간·소비전력 통계·작동 후 온도는 입력에서 제외했습니다. 새로운 제품이나 한국 가정의 성능은 검증되지 않았습니다.')
        with st.expander('실제 정답과 예측 비교 — 테스트 첫 10회'):
            examples=pd.DataFrame(b['metrics']['reports']['energy']['examples'])
            examples['absolute_error_wh']=(examples.predicted-examples.actual).abs()
            st.caption('과거 테스트의 첫 10회입니다. 현재 입력에 대한 실제 결과가 아니며, 오차가 작은 사례만 골라낸 표가 아닙니다.')
            st.dataframe(examples.rename(columns={'machine':'제품','program':'코스','heat':'설정 °C','load_kg':'세탁물 kg','actual':'실측 Wh','predicted':'예측 Wh','absolute_error_wh':'절대오차 Wh'}),hide_index=True)
        st.markdown('[LARCO 원 데이터 — CC BY 4.0](https://zenodo.org/records/18657997)')


@st.cache_resource
def load_devices():
    return joblib.load(ROOT/'models/device_forecast_model.joblib')


def render_device(request_prediction,rate,device):
    b=load_devices()
    report=b['metrics'][device]
    st.subheader(report['label']+' — 다음 10분 사용량·요금')
    st.info('REFIT House2의 해당 가전 실측 기록으로 학습했습니다. 집 전체 전력이나 다른 가전의 기록은 입력하지 않습니다. 코스·설정 온도 등 운전 조건의 정답 자료는 없어 해당 조건을 바꾸는 시뮬레이션의 R²는 계산하지 않습니다.')
    recent=[]
    columns=st.columns(3)
    for i in range(6):
        with columns[i%3]:
            recent.append(st.number_input(f'{i*10}~{(i+1)*10}분 전 해당 가전 사용량 (Wh)',min_value=0.0,max_value=4000/6,value=5.0,step=1.0,key=f'device_{device}_{i}'))
    st.caption('최근에 완료된 구간부터 입력하세요. 기본값은 데모이며 실제 센서 측정값이 아닙니다.')
    now=datetime.now()
    a,c,d=st.columns(3)
    with a:hour=st.number_input('마지막 구간 종료 시각 — 시',min_value=0,max_value=23,value=now.hour,key='device_hour_'+device)
    with c:minute=st.selectbox('분',[0,10,20,30,40,50],index=now.minute//10,key='device_minute_'+device)
    with d:weekday=st.selectbox('요일',range(7),format_func=lambda i:['월','화','수','목','금','토','일'][i],index=now.weekday(),key='device_weekday_'+device)
    result=request_prediction('/api/device-forecast',dict(device=device,recent_wh=recent,hour=int(hour),minute=int(minute),weekday=int(weekday),unit_price_krw_per_kwh=rate))
    a,c=st.columns(2)
    a.metric('다음 10분 해당 가전 예상 사용량',f"{result['energy_wh']:.2f} Wh")
    c.metric('다음 10분 해당 가전 예상 추가요금',f"{result['cost_krw']:.2f}원")
    m=result['metrics']
    st.caption(f"실측 정답 테스트 {result['test_rows']:,}건: R² {m['r2']:.4f}, MAE {m['mae_wh']:.2f}Wh, RMSE {m['rmse_wh']:.2f}Wh.")
    baseline=report['persistence_test']
    st.caption(f"직전 사용량 그대로 예측하는 기준: R² {baseline['r2']:.4f}. 시간순 60/20/20, 검증에서 모델 선택 후 재학습. 이미 확인한 테스트 기간이므로 새 미래 데이터에서 재검증이 필요합니다.")
    st.warning(result['note'])
    st.markdown('[REFIT 실측 자료 — CC BY 4.0](https://zenodo.org/records/5063428)')
