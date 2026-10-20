"""Strict completed ten-minute appliance CSV import; never guess units."""
import io
import numpy as np
import pandas as pd

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 10000


def parse_history(content, unit='Wh'):
    if not isinstance(content, bytes) or not 0 < len(content) <= MAX_BYTES:
        raise ValueError('CSV는 비어 있지 않은 2MB 이하 파일이어야 합니다.')
    if unit not in ('Wh', 'kWh', 'W'):
        raise ValueError('단위는 Wh, kWh 또는 10분 평균 W를 선택하세요.')
    try:
        frame = pd.read_csv(io.BytesIO(content), encoding='utf-8-sig', nrows=MAX_ROWS+1)
    except Exception as error:
        raise ValueError('UTF-8 CSV 파일을 확인하세요.') from error
    if list(frame.columns) != ['timestamp', 'value']:
        raise ValueError('CSV 열은 timestamp,value 두 개만 사용하세요.')
    if not 6 <= len(frame) <= MAX_ROWS:
        raise ValueError('CSV는 완료된 10분 구간 6~10,000행이어야 합니다.')
    try:
        stamp = pd.to_datetime(frame.timestamp, errors='raise')
        if not pd.api.types.is_datetime64_any_dtype(stamp):raise ValueError('mixed timezone')
        if stamp.isna().any() or stamp.duplicated().any():raise ValueError('missing/duplicate time')
        if not stamp.is_monotonic_increasing:raise ValueError('time order')
        if not stamp.diff().iloc[1:].eq(pd.Timedelta(minutes=10)).all():raise ValueError('gap')
        if pd.api.types.is_bool_dtype(frame.value):raise ValueError('Boolean measurement')
        energy = pd.to_numeric(frame.value, errors='raise').astype(float)
    except Exception as error:
        raise ValueError('시각은 오래된 순으로 중복·누락 없이 10분 간격, 값은 숫자여야 합니다.') from error
    energy = energy * {'Wh':1, 'kWh':1000, 'W':1/6}[unit]
    if not np.isfinite(energy).all() or not energy.between(0, 4000/6).all():
        raise ValueError('10분 사용량은 0~666.6667Wh 범위의 유한한 숫자여야 합니다.')
    moment = stamp.iloc[-1]
    now=pd.Timestamp.now(tz=moment.tzinfo) if moment.tzinfo else pd.Timestamp.now(tz='Asia/Seoul').tz_localize(None)
    if moment>now:raise ValueError('아직 끝나지 않은 미래 구간은 입력할 수 없습니다.')
    if moment.minute % 10 or moment.second or moment.microsecond:
        raise ValueError('구간 종료 시각은 00/10/20/30/40/50분이어야 합니다.')
    return dict(recent_wh=energy.iloc[-6:][::-1].tolist(), history_wh=energy.iloc[-144:].tolist(),
                hour=int(moment.hour), minute=int(moment.minute), weekday=int(moment.weekday()),
                forecast_at=moment.isoformat(), rows=len(frame), input_unit=unit,
                note='timestamp는 끝난 10분 구간의 종료 시각입니다. 해당 가전만의 기록을 입력하세요.')
