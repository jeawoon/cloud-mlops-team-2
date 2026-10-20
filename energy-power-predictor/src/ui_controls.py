from datetime import date
import streamlit as st
from src.billing import TABLE_SOURCE,FUND_SOURCE,FUEL_SOURCE


def billing_controls():
    choice=st.radio('요금 계산 방식',['고정 단가','주택용 누진 참고 계산'],horizontal=True,key='billing_mode')
    if choice=='고정 단가':return None
    st.warning('2025-04-01 공개 참고표이며 최신 공식 주택용 요율이라고 보장하지 않습니다. 실제 청구액 계산기가 아닙니다.')
    tariff=st.selectbox('계약 종류',['주택용 저압','주택용 고압'],key='bill_tariff')
    current=st.number_input('이번 달 누적 사용량 (kWh)',0.,10000.,150.,key='bill_current')
    day=st.date_input('요금 기준일',value=date.today(),min_value=date(2025,7,1),key='bill_date')
    climate=st.number_input('기후환경 단가 (원/kWh, 고지서로 확인)',0.,100.,9.,key='bill_climate')
    fuel=st.number_input('연료비 단가 (원/kWh, 고지서로 확인)',-5.,5.,5.,key='bill_fuel')
    st.caption('기후환경 9원은 입력 가정입니다. 연료비 5원은 2026년 4분기 확인값이므로 다른 분기에는 고지서로 수정하세요. 할인·최소요금·일할계산·월 경계·아파트 특례는 제외합니다.')
    st.markdown(f'[참고 요금표]({TABLE_SOURCE}) · [기금 요율 출처]({FUND_SOURCE}) · [연료비 출처]({FUEL_SOURCE})')
    if not st.checkbox('요금표 버전·단가 가정·제외 항목을 확인했습니다',key='bill_ack'):
        st.info('참고표 적용에 동의하거나 고정 단가를 선택하세요.');return False
    return dict(tariff=tariff,current_kwh=current,billing_date=day.isoformat(),
                climate_won_per_kwh=climate,fuel_won_per_kwh=fuel,acknowledge_reference=True)
