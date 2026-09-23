# 가정 전력 사용량 예측 데모

`energydata_complete.csv`로 학습해 현재 실내외 온도·습도·날씨·시간대에 따른 **다음 1시간 평균** 가전 전력량(Wh/10분)을 예측합니다.

## 실행

```bash
cd energy-power-predictor
python3 -m pip install -r requirements.txt
python3 train.py --data '/path/to/energydata_complete.csv' --output models
streamlit run app.py
```

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
- 각 모드의 P10·P50·P90 분위수 회귀 모델이 예상값과 예측 구간을 만듭니다.
- Plegma 확장 학습을 지정하면 그리스 13가구의 사계절 전력·실내외 온습도 데이터를 시간별로 변환해 추가합니다. 원본 UCI 테스트 구간은 학습에 넣지 않아, 기존 데이터 기준 성능을 계속 확인할 수 있습니다.
- 학습 후에는 기본·고급 모드별 UCI 테스트 MAE를 비교해 더 낮은 오차의 모델만 선택합니다. 현재 배포 모델은 기본 모드에 UCI 원본 모델(MAE 33.39Wh), 고급 모드에 Plegma 확장 모델(MAE 27.09Wh)을 사용합니다.
- 원본 CSV에는 날씨 범주가 없어서 학습 시 실외 온도·습도에 따른 데모 범주를 생성합니다. 실제 사용 시에는 사용자가 선택한 날씨를 반영합니다.

## 한국 날씨 API

데모의 현재 날씨 버튼은 [Open-Meteo Forecast API](https://open-meteo.com/en/docs)를 사용합니다. API 키가 필요 없으며 `kma_seamless` 모델을 먼저 요청해 한국기상청(KMA) 모델을 사용합니다. 해당 모델의 최신 값이 없을 때에는 자동으로 `best_match` 모델을 사용합니다. 네트워크가 없거나 API가 응답하지 않아도 수동 슬라이더 예측은 계속 사용할 수 있습니다.

과거 날씨 코드가 필요하면 주택의 실제 위치를 알고 있을 때만 `weather_enrichment.py`로 Open-Meteo Archive API 데이터를 받으세요. 원본 파일에 위치 정보가 없으므로, 한국 날씨를 원본 학습 데이터에 임의 결합하면 안 됩니다.

## 해석 주의

온습도만으로는 재실 인원, 조리, 세탁 같은 돌발 사용량을 완전히 알 수 없습니다. 따라서 이 결과는 가정의 평균적 사용 패턴을 보여주는 데모 예측이며, 예측 구간도 함께 확인해야 합니다.

전기요금은 한전 주택용 저압·고압 누진 전력량요금을 바탕으로 한 다음 1시간의 **추가 예상요금**입니다. 기본요금, 할인, TV수신료, 청구 단위 반올림은 포함하지 않습니다. 실제 청구액은 [한전 전기요금 계산기](https://home.kepco.co.kr/kepco/front/html/CY/J/A/CYJAPP002.html)로 확인하세요.
