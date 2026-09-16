# energydata_train.csv

## 설명
전처리가 완료된 전체 데이터(`energydata_preprocessed.csv`)를 시간순으로 정렬한 뒤, 앞쪽 **80%**를 잘라낸 **학습용(train) 데이터셋**입니다.
총 **15,788행, 32개 컬럼**이며, `2016-01-11 17:00`부터 `2016-04-30 08:10`까지의 기간에 해당합니다.

## 분할 방식
- 시계열 데이터이므로 무작위(random) 분할이 아닌 **시간순 분할**을 적용했습니다.
- 이는 미래 데이터가 과거 예측에 섞여 들어가는 **데이터 누수(leakage)**를 방지하기 위함입니다.

## 컬럼 구성
`energydata_preprocessed.csv`와 동일합니다 (원본 센서값 + 파생 피처 `hour`, `dayofweek`, `is_weekend`, `Appliances_log`, `T_avg_indoor` 포함).

## 용도
예측 모델(회귀 모델)을 **학습**시키는 데 사용합니다.
