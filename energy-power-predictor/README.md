# 가전별 예상 사용량·요금
기존 집 전체 모델·화면·API는 제거했습니다. 원본 데이터는 보존하고 제거 모델과 이전 코드는 `work/removed-wholehouse-cGCHNA/`에 복구 가능하게 보관합니다. 이 폴더는 Git 제외입니다. 기존 UCI 가전 모델도 오프라인 연구 자료로 보존하지만 현재 앱/API에서는 사용하지 않습니다.

## 현재 기능
- 기본 화면은 9종 가전을 여러 개 선택하는 사용 계획 화면입니다. 시간·소비전력·가동률·대수·시작 지연을 입력하면 가전별 Wh/kWh·요금과 선택 계획의 합계를 표시합니다. 기본 W는 보존한 REFIT 가전 통계 숫자만 사용하며 집 전체 모델은 복원하지 않습니다. 냉장고 가동률 기본 50% 등은 예시 가정이며 실제 내 제품의 값이 아닙니다.
- 각 가전의 계산 방식에서 시간·소비전력 계산 또는 지원되는 학습 모델을 고릅니다. 시간·소비전력 계산은 평균 W × 시간 × 대수이고 이 방식의 R²는 미검증입니다. 세탁코스와 10분 예측이 섞이면 합계는 각 선택 계획의 에너지 합이지 집 전체 또는 공통 10분 구간 예측이 아닙니다. 고정 단가에서는 시작 지연이 요금을 바꾸지 않습니다.
- 세탁기: LARCO 실측 운전 조건으로 **코스 1회 전체** 에너지와 소요시간 예측.
- 냉장·냉동고 / 식기세척기: REFIT House2 해당 가전 최근 완료 구간 6개와 시각·요일로 **다음 10분** 에너지 예측. 집 전체나 다른 가전 피처는 사용하지 않습니다.
- 예상 kWh × 입력 단가(원/kWh)로 요금을 계산합니다. 기본 200원은 예시이고 공식 요율이 아닙니다. 누진·기본요금·세금·할인은 별도 계산하지 않습니다.

## 실측 테스트 결과
| 대상 | 예측 범위 | 테스트 | R² | MAE |
|---|---|---:|---:|---:|
| 세탁기 | 코스 1회 완료 | 131회 | 0.8835 | 98.63Wh |
| 냉장·냉동고 | 다음 10분 | 14,933건 | 0.7897 | 1.73Wh |
| 식기세척기 | 다음 10분 | 14,933건 | 0.9303 | 2.40Wh |

세탁기와 두 가전의 데이터·예측 대상·기간이 달라 점수를 직접 비교하거나 합쳐서는 안 됩니다. 냉장고·식기세척기의 임의 켜짐 계획, 설정 온도, 코스 1회 결과에 대한 R²는 검증되지 않았습니다. 실제 최근 측정값 대신 데모값을 입력한 성능도 보장하지 않습니다.

## 데이터·평가
[LARCO 공식 데이터](https://zenodo.org/records/18657997), CC BY 4.0: 실험실 세탁기 유효 코스 642회, 제품별 획득 시각순 60/20/20(383/128/131회). 실제 소비전력이 정답이며 모델·프로그램·설정 온도·주변 온도·목표 무게만 입력합니다. 실제 종료시간·소비전력 통계·작동 후 온도·KPI는 입력하지 않습니다. 원본 요약 약 1.3MB는 `data/larco/`에 보존합니다. 새로운 제품·한국 가정 성능은 검증되지 않았습니다.

[REFIT 공식 데이터](https://zenodo.org/records/5063428), CC BY 4.0: House2의 Appliance1(냉장·냉동고), Appliance3(식기세척기). MD5 검증 후 센서 문제 행·범위 초과·10분 내 유효 60개 미만 측정은 제외합니다. 완료 시각으로 10분 구간을 라벨링합니다. 가전별 앞 60% 학습, 다음 20% 검증, 뒤 20% 테스트로 나누고 미래 목표가 경계를 넘는 행을 제외합니다. 검증 R²로 모델 선택 후 학습+검증 재학습합니다. 테스트는 이전에도 본 기간이므로 독립적인 새 미래 데이터 확인이 필요합니다.

## 실행
같은 폴더에서 첫 터미널:
```bash
python3 api.py --port 8000
```
두 번째 터미널:
```bash
python3 -m streamlit run app.py
```
웹 주소: http://127.0.0.1:8501
다른 API 주소는 `PREDICTION_API_URL`로 설정합니다.

## 재학습
```bash
python3 fetch_larco.py
python3 train_larco.py
python3 train_device_forecasts.py
```
REFIT House2 원본은 `data/refit/CLEAN_House2.csv`가 필요합니다. 다운로드·학습 자료는 Git에 포함하지 않습니다. 기존 원본은 삭제하지 않았습니다.

## API
- POST /api/appliance-plan: plans(device=Appliance1..9, quantity, method, start_after_minutes, settings), 선택적 unit_price_krw_per_kwh. method는 power_time/laundry_cycle/recent_forecast이며 가전별 지원 범위가 다릅니다. 개별 검증 지표는 학습 모드에만 표시하고 전체 plan_r2는 null입니다.
- GET /api/health, /api/docs
- GET /api/laundry-cycle/catalog
- POST /api/laundry-cycle: machine, program, heat, load_kg, ambient_temp, 선택적 unit_price_krw_per_kwh
- GET /api/device-forecast/catalog
- POST /api/device-forecast: device(fridge/dishwasher), recent_wh(해당 가전 최신순 6개), hour, weekday, 선택적 minute·unit_price_krw_per_kwh
- 기존 /api/simulate, /api/whole-house, /api/simulator/catalog는 HTTP 410으로 제거 안내를 반환합니다. 기타 이전 예측 엔드포인트는 현재 API에서 제공하지 않습니다.

## 검사·평가 파일
`python3 -m unittest test_appliance_plan test_laundry test_device_forecast -v`
- `models/larco_cycle_metrics.json`
- `models/device_forecast_metrics.json`
