"""Versioned reference bill difference; not a live KEPCO invoice service."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from src.device_forecast import numeric

TABLE_VERSION = 'residential-reference-2025-04-01'
TABLE_SOURCE = 'https://data.cmpi.or.kr/program/board/2025.04.01%20%EC%8B%9C%ED%96%89.pdf'
FUND_SOURCE = 'https://whatsnew.moef.go.kr/mec/ots/dif/view.do?comBaseCd=DIFPERCD&difPer1=DIFPER007&difSer=5e897953-86a8-44d6-baac-d6ffd29f5c68&temp=2024&temp2=HALF002'
FUEL_SOURCE = 'https://www.kepco.co.kr/home/media/newsroom/notice/boardView.do?boardMngNo=14&boardNo=2759'
RATES = {'주택용 저압': ([120.,214.6,307.3], [910,1600,7300],736.2),
         '주택용 고압': ([105.,174.,242.3], [730,1260,6060],601.3)}


def _parts(usage, tariff, month, climate, fuel, fund):
    rates, basics, super_rate = RATES[tariff]
    first, second = (300,450) if month in (7,8) else (200,400)
    tier = 0 if usage <= first else 1 if usage <= second else 2
    energy = min(usage,first)*rates[0] + max(0,min(usage,second)-first)*rates[1]
    energy += max(0,min(usage,1000)-second)*rates[2]
    energy += max(0,usage-1000)*(super_rate if month in (1,2,7,8,12) else rates[2])
    subtotal = int(basics[tier] + energy + usage*(climate+fuel))
    vat = int(Decimal(str(subtotal*.1)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    levy = int(subtotal*fund/10)*10
    total = int((subtotal+vat+levy)/10)*10
    return dict(basic_krw=basics[tier], energy_krw=energy, climate_krw=usage*climate,
                fuel_krw=usage*fuel, vat_krw=vat, fund_krw=levy, bill_krw=total)


def reference_increment(current_kwh, added_kwh, options):
    if not isinstance(options,dict):raise ValueError('요금 설정을 확인하세요.')
    current=numeric(current_kwh,'월 누적 사용량',0,10000)
    added=numeric(added_kwh,'추가 사용량',0,10000)
    tariff=options.get('tariff','주택용 저압')
    if not isinstance(tariff,str) or tariff not in RATES:raise ValueError('지원 계약 종류를 선택하세요.')
    try:day=date.fromisoformat(options['billing_date'])
    except (KeyError,TypeError,ValueError):raise ValueError('요금 기준일을 YYYY-MM-DD로 입력하세요.')
    if day < date(2025,7,1):raise ValueError('참고 계산은 2025-07-01 이후 기준일만 지원합니다.')
    climate=numeric(options.get('climate_won_per_kwh',9),'기후환경 단가',0,100)
    fuel=numeric(options.get('fuel_won_per_kwh',5),'연료비 단가',-5,5)
    before=_parts(current,tariff,day.month,climate,fuel,.027)
    after=_parts(current+added,tariff,day.month,climate,fuel,.027)
    return dict(mode='reference_progressive',reference_table_version=TABLE_VERSION,
                before=before,after=after,additional_cost_krw=after['bill_krw']-before['bill_krw'],
                sources=[TABLE_SOURCE,FUND_SOURCE,FUEL_SOURCE],
                note='2025-04-01 공개 참고표 기반입니다. 현재 공식 주택용 표의 최신성은 확인하지 못했습니다. 기후환경 단가는 입력 가정, 연료비 5원은 2026년 4분기 확인값입니다. 날짜·분기별 단가는 고지서로 확인하세요. 할인·최소요금·검침일 일할계산·월 경계·아파트 계약 특례·TV수신료는 미반영입니다. 실제 청구액이 아닙니다.')


def energy_charge(usage_kwh,tariff):
    return _parts(numeric(usage_kwh,'usage_kwh',0,20000),tariff,10,0,0,.027)['energy_krw']


def estimate_incremental_cost(current_kwh,added_kwh,tariff):
    result=reference_increment(current_kwh,added_kwh,dict(tariff=tariff,billing_date='2026-10-20'))
    return result['after']['energy_krw']-result['before']['energy_krw'],result['additional_cost_krw']
