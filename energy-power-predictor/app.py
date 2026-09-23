from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import joblib
import streamlit as st

from src.features import make_demo_row
from src.billing import estimate_incremental_cost

ROOT = Path(__file__).parent
MODEL_PATH = ROOT / "models" / "energy_model.joblib"


@st.cache_resource
def load_bundle():
    return joblib.load(MODEL_PATH)


def korean_weather(code: int) -> str:
    groups = {0: "맑음", 1: "대체로 맑음", 2: "부분적으로 흐림", 3: "흐림", 45: "안개", 48: "안개",
              51: "이슬비", 53: "이슬비", 55: "이슬비", 61: "비", 63: "비", 65: "강한 비",
              71: "눈", 73: "눈", 75: "강한 눈", 80: "소나기", 81: "소나기", 82: "강한 소나기",
              95: "뇌우", 96: "우박을 동반한 뇌우", 99: "우박을 동반한 뇌우"}
    return groups.get(code, "알 수 없음")


def get_korea_weather(city: str) -> dict:
    # Prefer Open-Meteo's KMA seamless model. Fall back to Best Match if the
    # KMA run is temporarily unavailable for the requested time/location.
    locations = {"서울": (37.5665, 126.9780), "부산": (35.1796, 129.0756), "대전": (36.3504, 127.3845), "광주": (35.1595, 126.8526), "제주": (33.4996, 126.5312)}
    lat, lon = locations[city]
    base = {"latitude": lat, "longitude": lon, "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m", "timezone": "Asia/Seoul"}
    current = None
    for model in ("kma_seamless", "best_match"):
        params = urlencode({**base, "models": model})
        with urlopen(f"https://api.open-meteo.com/v1/forecast?{params}", timeout=8) as response:
            candidate = json.load(response)["current"]
        if all(candidate.get(key) is not None for key in ("temperature_2m", "relative_humidity_2m", "weather_code", "wind_speed_10m")):
            current = candidate
            break
    if current is None:
        raise RuntimeError("현재 날씨 데이터가 없습니다")
    return {
        "temperature": current["temperature_2m"],
        "humidity": current["relative_humidity_2m"],
        "wind": current["wind_speed_10m"],
        "label": korean_weather(current["weather_code"]),
        "time": current["time"],
    }


st.set_page_config(page_title="가정 전력 사용량 예측", page_icon="⚡", layout="centered")
st.markdown("""
<style>
/* Temperature and humidity: cool on the left, warm on the right. */
.st-key-indoor_temp [data-baseweb="slider"] > div > div,
.st-key-indoor_humidity [data-baseweb="slider"] > div > div,
.st-key-outdoor_temp [data-baseweb="slider"] > div > div,
.st-key-outdoor_humidity [data-baseweb="slider"] > div > div {
    background: linear-gradient(90deg, #1976d2 0%, #42a5f5 35%, #ffb74d 65%, #e53935 100%) !important;
}
.st-key-indoor_temp [data-baseweb="slider"] [role="slider"],
.st-key-indoor_humidity [data-baseweb="slider"] [role="slider"],
.st-key-outdoor_temp [data-baseweb="slider"] [role="slider"],
.st-key-outdoor_humidity [data-baseweb="slider"] [role="slider"] {
    background: linear-gradient(135deg, #1976d2 0%, #e53935 100%) !important;
    border: 2px solid #ffffff !important;
    box-shadow: 0 1px 5px rgba(0, 0, 0, 0.35) !important;
}
/* Time: bright early hours through darker late hours. */
.st-key-time_slider [data-baseweb="slider"] > div > div {
    background: linear-gradient(90deg, #ffffff 0%, #d7d7d7 45%, #777777 100%) !important;
}
.st-key-time_slider [data-baseweb="slider"] [role="slider"] {
    background: linear-gradient(135deg, #ffffff 0%, #666666 100%) !important;
    border: 2px solid #ffffff !important;
    box-shadow: 0 1px 5px rgba(0, 0, 0, 0.35) !important;
}
</style>
""", unsafe_allow_html=True)
st.title("가정 전력 사용량 예측")
st.caption("현재 조건을 바탕으로 향후 1~8시간의 가전 전력량과 추가 전기요금을 예측합니다.")

if not MODEL_PATH.exists():
    st.error("학습 모델이 없습니다. README의 학습 명령을 먼저 실행하세요.")
    st.stop()
bundle = load_bundle()

with st.sidebar:
    st.header("한국 현재 날씨")
    city = st.selectbox("도시", ["서울", "부산", "대전", "광주", "제주"])
    if st.button("현재 날씨 불러오기"):
        try:
            st.session_state.weather = get_korea_weather(city)
            st.session_state.outdoor_temp = float(st.session_state.weather["temperature"])
            st.session_state.outdoor_humidity = int(st.session_state.weather["humidity"])
            label = st.session_state.weather["label"]
            st.session_state.weather_type = "눈" if "눈" in label else "비" if any(x in label for x in ("비", "소나기", "이슬비")) else "흐림" if any(x in label for x in ("흐림", "안개")) else "맑음"
            weather_time = datetime.fromisoformat(st.session_state.weather["time"])
            st.session_state.time_slider = weather_time.hour
            st.session_state.weekday_selector = weather_time.weekday()
        except Exception as exc:
            st.warning(f"날씨를 불러오지 못했습니다: {exc}")
    current = st.session_state.get("weather")
    if current:
        current_time = current["time"].replace("T", " ")
        st.write(f"{city}: {current['label']}, {current['temperature']}°C, 습도 {current['humidity']}%, {current_time}")

weather_defaults = st.session_state.get("weather", {})
if "outdoor_temp" not in st.session_state:
    st.session_state.outdoor_temp = float(weather_defaults.get("temperature", 10.0))
if "outdoor_humidity" not in st.session_state:
    st.session_state.outdoor_humidity = int(weather_defaults.get("humidity", 70))
if "weather_type" not in st.session_state:
    st.session_state.weather_type = "맑음"
if "time_slider" not in st.session_state:
    st.session_state.time_slider = datetime.now().hour
if "weekday_selector" not in st.session_state:
    st.session_state.weekday_selector = datetime.now().weekday()
col1, col2 = st.columns(2)
with col1:
    indoor_temp = st.slider("실내 온도 (°C)", 10.0, 35.0, 22.0, 0.1, key="indoor_temp")
    indoor_humidity = st.slider("실내 습도 (%)", 20, 80, 45, key="indoor_humidity")
    outdoor_temp = st.slider("실외 온도 (°C)", -15.0, 40.0, step=0.1, key="outdoor_temp")
with col2:
    outdoor_humidity = st.slider("실외 습도 (%)", 10, 100, key="outdoor_humidity")
    weather = st.selectbox("날씨", ["맑음", "흐림", "비", "눈"], key="weather_type")
    hour = st.slider("시간", 0, 23, key="time_slider")
    weekday = st.selectbox("요일", range(7), format_func=lambda x: ["월", "화", "수", "목", "금", "토", "일"][x], key="weekday_selector")

forecast_hours = st.select_slider("예측 기간", options=list(range(1, 9)), value=1, format_func=lambda value: f"{value}시간")

advanced = st.toggle("고급 예측 모드: 최근 사용 패턴 입력", value=False)
previous_hour = None
if advanced:
    st.caption("최근 전력량은 다음 시간의 사용량과 피크 발생 확률을 계산하는 데 사용됩니다.")
    previous_hour = st.number_input("직전 1시간 평균 전력량 (Wh/10분)", min_value=0.0, value=80.0, step=5.0)
    same_hour_yesterday = st.number_input("어제 같은 시간 평균 전력량 (Wh/10분)", min_value=0.0, value=80.0, step=5.0)
    recent_3h_mean = st.number_input("최근 3시간 평균 전력량 (Wh/10분)", min_value=0.0, value=80.0, step=5.0)
mode = "advanced" if advanced else "manual"
models = bundle["models"][mode]
peak_model = bundle.get("peak_models", {}).get(mode)

# The first prediction uses the selected current hour; later hours are forecast
# sequentially, carrying the predicted use forward in advanced mode.
forecast = []
peak_probabilities = []
previous_for_forecast = previous_hour
recent_for_forecast = recent_3h_mean if advanced else None
for step in range(forecast_hours):
    current_hour = (hour + step) % 24
    current_weekday = (weekday + (hour + step) // 24) % 7
    row = make_demo_row(
        indoor_temp, indoor_humidity, outdoor_temp, outdoor_humidity, weather,
        current_hour, current_weekday, datetime.now().month, bundle["defaults"],
        previous_for_forecast, same_hour_yesterday if advanced else None,
        recent_for_forecast,
    )
    lower = max(0, float(models["0.1"].predict(row)[0]))
    middle = max(0, float(models["0.5"].predict(row)[0]))
    upper = max(lower, float(models["0.9"].predict(row)[0]))
    forecast.append((lower, middle, upper))
    if peak_model is not None:
        peak_probabilities.append(float(peak_model.predict_proba(row)[0, 1]))
    if advanced:
        previous_for_forecast = middle
        recent_for_forecast = (recent_for_forecast * 2 + middle) / 3

p10 = sum(item[0] for item in forecast) / forecast_hours
p50 = sum(item[1] for item in forecast) / forecast_hours
p90 = sum(item[2] for item in forecast) / forecast_hours
total_kwh = sum(item[1] for item in forecast) * 6 / 1000
total_low_kwh = sum(item[0] for item in forecast) * 6 / 1000
total_high_kwh = sum(item[2] for item in forecast) * 6 / 1000
personal_avg = st.number_input("개인화 기준: 최근 7일 평균 전력량 (Wh/10분, 선택)", min_value=0.0, value=0.0, step=5.0)
low, high = ((personal_avg * 0.8, personal_avg * 1.2) if personal_avg > 0 else bundle["thresholds"])
level = "낮음" if p50 < low else "보통" if p50 < high else "높음"

st.divider()
a, b, c = st.columns(3)
a.metric(f"향후 {forecast_hours}시간 평균", f"{p50:.0f} Wh/10분")
b.metric("누적 예상 사용량", f"{total_kwh:.2f} kWh")
c.metric("사용 구간", level)
st.caption(f"누적 예상 범위: {total_low_kwh:.2f} ~ {total_high_kwh:.2f} kWh")
if peak_probabilities:
    peak_probability = max(peak_probabilities)
    peak_hour = (hour + peak_probabilities.index(peak_probability)) % 24
    peak_label = "높음" if peak_probability >= 0.60 else "주의" if peak_probability >= 0.30 else "낮음"
    st.subheader("피크 전력 발생 가능성")
    peak_col1, peak_col2 = st.columns(2)
    peak_col1.metric("피크 발생 확률", f"{peak_probability:.0%}", peak_label)
    peak_col2.metric("가장 주의할 시간", f"{peak_hour:02d}:00")
    peak_info = bundle["metrics"].get("peak_prediction", {}).get("definition", "학습 데이터 상위 사용량 구간")
    st.caption(f"피크는 '{peak_info}'으로 정의했습니다. 직전 전력량을 입력한 고급 모드에서 생활 패턴을 더 반영합니다.")
st.subheader(f"향후 {forecast_hours}시간 예상 전기요금")
bill_col1, bill_col2 = st.columns(2)
with bill_col1:
    tariff = st.selectbox("주택용 계약 종류", ["주택용 저압", "주택용 고압"])
with bill_col2:
    monthly_kwh = st.number_input("이번 달 누적 사용량 (kWh)", min_value=0.0, value=150.0, step=1.0)
energy_only, with_tax = estimate_incremental_cost(monthly_kwh, total_kwh, tariff)
st.metric(f"향후 {forecast_hours}시간 추가 예상요금", f"약 {with_tax:.0f}원")
st.caption(f"예상 사용량 {total_kwh:.3f} kWh 기준. 전력량요금은 약 {energy_only:.0f}원이며 부가가치세·전력산업기반기금을 포함한 참고 추정치입니다. 기본요금·할인·TV수신료는 제외됩니다.")
metric = bundle["metrics"][f"{mode}_mode"]
st.caption(f"{('고급' if advanced else '기본')} 모드 검증 성능: MAE {metric['mae_wh']} Wh, R² {metric['r2']}, 80% 목표 예측구간 포함률 {metric['p10_p90_coverage_pct']}%")
selection = bundle["metrics"].get("model_selection", {}).get(mode)
if selection:
    st.caption(f"현재 선택된 학습 모델: {selection}")
data_note = bundle["metrics"].get("data_period", {}).get("note")
if data_note:
    st.info(data_note)
