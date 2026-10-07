# 가정 전력 사용량 예측 데모

`energydata_complete.csv`로 학습해 현재 실내외 온도·습도·날씨·시간대에 따른 **다음 1시간 평균** 가전 전력량(Wh/10분)을 예측합니다.

## 실행

```bash
cd energy-power-predictor
python3 -m pip install -r requirements.txt
python3 train.py --data '/path/to/energydata_complete.csv' --output models
python3 api.py --port 8000
```

위 API 서버 터미널은 켜 둔 상태에서 다른 터미널을 열어 같은 폴더에서 `python3 -m streamlit run app.py`를 실행합니다. 웹페이지는 `http://127.0.0.1:8000` API에 JSON으로 예측을 요청합니다. 다른 API 서버를 사용할 때는 `PREDICTION_API_URL` 환경변수를 설정합니다.

## 모델 예측 API

- `GET /api/health`: 모델 로드 상태 확인
- `GET /api/docs`: 입출력 필드 설명
- `POST /api/predict`: 온습도 기반 기본·고급 1~8시간 예측. 응답 `forecast`는 시간별 `[하한, 중앙, 상한]` Wh/10분, `total_kwh`는 누적 kWh입니다.
- `POST /api/recent`: 최근 6개 10분 사용량 기반 10분/1시간 가전 예측
- `POST /api/whole-house`: 최근 6개 사용량과 장기간 중앙값 기반 전체 전력 예측
- `recent_wh`는 최근 값부터 오래된 값 순서입니다. 잘못된 범위·누락 입력은 HTTP 422 JSON 오류를 반환합니다.

```bash
curl -X POST http://54.180.145.65/api/predict \
  -H 'Content-Type: application/json' \
  -d '{"indoor_temp":22,"indoor_humidity":45,"outdoor_temp":10,"outdoor_humidity":70,"hour":18,"weekday":2,"mode":"manual","forecast_hours":1}'
```

AWS에서는 `energy-api`와 `energy-predictor` 서비스가 자동 실행됩니다. Nginx가 외부 `/api/` 요청을 내부 8000 포트로 전달하고, 웹페이지 요청은 내부 API를 사용합니다. 외부 보안 그룹은 기존 HTTP 80번을 유지합니다.

Plegma 확장 학습을 적용하려면 다음처럼 실행합니다.

```bash
python3 train.py --data '/path/to/energydata_complete.csv' --plegma-dir 'data/plegma/extracted' --output models
```

## 처리 방식

- 10분 단위 기록을 시간별 평균으로 집계해 돌발 사용량의 영향을 줄입니다.
- 시간 순서를 보존해 앞 80%로 학습하고 뒤 20%로 성능을 평가합니다.
- 실내 센서 `T1~T9`, `RH_1~RH_9`는 평균으로 통합합니다.
- `rv1`, `rv2`는 무작위 변수이므로 사용하지 않습니다.
- 시간대·요일·월을 순환형 특성으로, 실내외 온도 차와 냉난방 필요도를 추가합니다.
- 기본 모드는 환경·시간 정보만, 고급 모드는 직전 1시간 사용량까지 사용합니다.
- 고급 모드는 직전 1시간, 최근 3시간 평균, 어제 같은 시간 사용량을 함께 사용합니다.
- 고급 모드 중앙 예상값은 제곱오차 회귀로, 기본 모드와 P10·P90 예측 구간은 분위수 회귀로 계산합니다.
- Plegma 확장 학습을 지정하면 그리스 13가구의 사계절 전력·실내외 온습도 데이터를 시간별로 변환해 추가합니다. 원본 UCI 테스트 구간은 학습에 넣지 않아, 기존 데이터 기준 성능을 계속 확인할 수 있습니다.
- Plegma 확장 학습에서는 기본·고급 모드별 테스트 MAE를 비교합니다. 기존 구간 모델과 피크 모델을 보존하고 중앙 예측만 교체하려면 `python3 update_central_model.py --data '/path/to/energydata_complete.csv'`를 실행합니다. 교체 전 모델과 비교 결과는 `reports/central_squared_error/`에 보관됩니다.
- 원본 CSV에는 날씨 범주가 없어서 학습 시 실외 온도·습도에 따른 데모 범주를 생성합니다. 실제 사용 시에는 사용자가 선택한 날씨를 반영합니다.

## 한국 날씨 API

데모의 현재 날씨 버튼은 [Open-Meteo Forecast API](https://open-meteo.com/en/docs)를 사용합니다. API 키가 필요 없으며 `kma_seamless` 모델을 먼저 요청해 한국기상청(KMA) 모델을 사용합니다. 해당 모델의 최신 값이 없을 때에는 자동으로 `best_match` 모델을 사용합니다. 네트워크가 없거나 API가 응답하지 않아도 수동 슬라이더 예측은 계속 사용할 수 있습니다.

과거 날씨 코드가 필요하면 주택의 실제 위치를 알고 있을 때만 `weather_enrichment.py`로 Open-Meteo Archive API 데이터를 받으세요. 원본 파일에 위치 정보가 없으므로, 한국 날씨를 원본 학습 데이터에 임의 결합하면 안 됩니다.

## 해석 주의

## 장기간 공개 전력 데이터 확장

- REFIT Cleaned: `https://zenodo.org/records/5063428`, CC BY 4.0. House 11·House 2를 사용합니다. 기존 웹 모델은 전체 전력만 사용하며, 아래 별도 실험 모델은 가전별 기록도 사용합니다.
- UCI Individual Household Electric Power Consumption: `https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption`, CC BY 4.0. 프랑스 한 가정의 약 4년치 전체 전력을 사용합니다.
- `python3 train_refit.py`로 `data/refit/CLEAN_House*.csv`, `data/household_power/household_power.zip`를 전처리·학습합니다. 결측·문제 기록이 많은 구간은 제외하고, 집별 학습/검증/테스트를 시간순 60/20/20으로 나눕니다. 학습 구간 중앙값으로 정규화하며, 향후 목표가 다음 구간으로 넘어가는 경계 행은 제외합니다.
- 앱의 별도 전체 전력 예측 영역에 최근 6개 10분 구간 사용량과 장기간 중앙값을 입력합니다. 온습도가 없는 자료에 임의 날씨를 붙이지 않습니다. UCI Appliances 가전량과 전체 전력량을 합쳐 성능을 계산하지 않습니다.
- 원본은 `data/`에 보관하며 Git에는 포함하지 않습니다. 출처·원본 MD5는 `models/refit_sources.json`, 검증 결과는 `reports/refit/evaluation.json`에 저장됩니다.
- 기존 최근 패턴 모델은 `python3 train_recent.py --data '/path/to/energydata_complete.csv'`로 학습합니다.

### 긴 과거 기록·가전별 피처 실험

- `python3 train_long_history.py`: 과거 24시간·7일 요약, 전날·지난주 같은 시간 기록을 추가합니다. 동일 샘플 통합 평가에서 다음 1시간 R²는 0.6402 → 0.6746입니다.
- `python3 train_appliance_history.py`: REFIT 가정별 모델에 9개 가전 채널의 소비량·변화·활동 상태를 추가합니다. 가정별 동일 샘플 비교에서 House11의 다음 10분 R²는 0.8646 → 0.8657, 다음 1시간은 0.8648 → 0.8607입니다. House2는 각각 0.4809 → 0.5720, 0.5468 → 0.6060입니다.
- 가전 채널 번호는 집마다 의미가 다르며, 활동 상태는 평균 20W 초과 여부를 이용한 추정입니다. 실제 스위치 상태가 아닙니다.
- 평가 상세: [긴 기록](evaluations/long_history/README.md), [가전별 피처](evaluations/appliance_history/README.md). 이전에 확인한 테스트 기간을 사용했으므로 새로운 미래 구간에서 재검증이 필요합니다. 특정 가정의 R²를 전체 가정 성능으로 해석하지 않습니다.
- 새 모델은 `models/long_history_model.joblib`, `models/appliance_history_model.joblib`에 저장됩니다. 추론 함수는 각 학습 스크립트에 포함됩니다. 실제 7일 이상의 전력·가전 기록이 필요하며, 기존 6개 입력 웹 폼이나 AWS 배포 모델은 교체하지 않았습니다.
- 검사: `python3 -m unittest test_appliance_history -v`.

온습도만으로는 재실 인원, 조리, 세탁 같은 돌발 사용량을 완전히 알 수 없습니다. 따라서 이 결과는 가정의 평균적 사용 패턴을 보여주는 데모 예측이며, 예측 구간도 함께 확인해야 합니다.

전기요금은 한전 주택용 저압·고압 누진 전력량요금을 바탕으로 한 다음 1시간의 **추가 예상요금**입니다. 기본요금, 할인, TV수신료, 청구 단위 반올림은 포함하지 않습니다. 실제 청구액은 [한전 전기요금 계산기](https://home.kepco.co.kr/kepco/front/html/CY/J/A/CYJAPP002.html)로 확인하세요.
