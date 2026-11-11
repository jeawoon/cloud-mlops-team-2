# 11월 11일 실습: 로그 분석과 재학습 가능성 확인

## 실제 분석 결과

CloudShell의 기존 로그인 권한으로 `/energy-predictor/api`를 조회해 JSONL로 내려받았다.
EC2 역할은 쓰기 권한만 있어 `FilterLogEvents`가 거부됐으며 IAM 권한은 확대하지 않았다.

| 항목 | 건수 |
|---|---:|
| CloudWatch 원본 이벤트 | 628 |
| 컨테이너 운영 로그 | 627 |
| JSON 외 연결 확인 메시지 | 1 |
| 실측 정답이 있는 예측 피드백 | 0 |
| 검토 후 학습 가능한 표본 | 0 |

원본 SHA-256: `26275e6ae31506f4f3a283d80d998eb3fdf1c30dee5062e75a7286dd4078bcce`

**운영 로그를 이용한 재학습은 미실행: 실측 정답이 0건이다.** HTTP 200은 서비스 정상 여부이며 예측 적중 여부가 아니다.
운영 로그의 예측값을 정답으로 복사하거나 테스트 예제를 운영 실측으로 등록하지 않았다.
따라서 운영 로그에서 새로운 R²·MAE를 계산할 수 없다. 아래 별도 실험은 기존 공개 LARCO 실측 데이터로 진행했다.
이 과제는 현재 지도학습 회귀이며 보상·행동·환경이 정의된 강화학습 문제가 아니다.

## 전처리 재현

AWS 읽기 권한이 있는 CloudShell에서 다음을 실행한다. `boto3`는 CloudShell에 기본 제공된다.

```bash
python deploy/download-cloudwatch.py --out /tmp/cloudwatch-api.jsonl
```

파일을 다운로드한 후 프로젝트 폴더에서 실행한다.

```bash
python prepare_feedback_training.py /path/to/cloudwatch-api.jsonl --out reports/feedback
python -m unittest test_feedback_preparation -v
```

CloudWatch 외부 래퍼 제거 → JSON 검증 → 피드백/운영 로그 분리 → event_id 중복 제거 → 예측별 최신 수정/삭제 반영 → 정답·범위·피처 검증 → 사람의 품질 검토를 거친 기록만 별도 JSONL로 내보낸다.
집계 보고서와 빈 학습 파일도 정상 결과다. 스크립트는 학습 또는 모델 교체를 수행하지 않는다.
복수 가전 합계, 산술 계산, 세탁코스 정답을 냉장고 다음 10분 모델의 정답으로 섞지 않는다.
현재 지원하는 학습 후보 내보내기 범위는 단일 냉장고/식기세척기 standard 모델이다.

원본·전처리 데이터는 개인별 사용 패턴일 수 있으므로 `reports/` 또는 저장소 밖에 보관한다.
Git에는 집계·코드·실행 절차만 남긴다. 원본 이벤트·서버 토큰·키 파일은 올리지 않는다.

## 정답을 수집한 뒤 할 일

1. 실제 가전별 계측값으로 예측하고 동의 후 저장한다.
2. 동일 가전·대수·예측 기간의 사용이 끝난 후 실제 Wh를 `내 기록`에 입력한다. 청구액을 확인하지 못했으면 실제 가격은 비워 둔다.
3. 검토자가 계측 출처, 예측 시각·시간대, 동일 가정/기기 식별 그룹, 예측 기간 일치를 확인한다. 기존 기록에는 이 정보가 충분하지 않으므로 자동 승인하지 않는다.
4. `--review review.json`에 event_id별 `approved`, `measurement_verified`, `scope_verified`를 모두 JSON true로, `household_group`, 시간대 포함 `forecast_at`을 제공한다. 실명/주소는 쓰지 않는다.
5. 중복·겹치는 구간과 동일 코스가 평가/학습에 동시에 들어가지 않도록 분리하고, 가정별 시간순 학습/검증/최종 테스트를 고정한다. 10분 타깃이 경계를 넘는 표본을 제거한다.
6. 고정 테스트의 기존 모델/후보 모델 MAE·RMSE·R²를 같은 표본에서 비교한다. 후보 선택은 검증 구간만 사용한다. 실측 건수 부족·정답 분산 0이면 R²를 보고하지 않는다.
7. 개선된 후보만 모델, 해시로 묶인 예측 구간, 검증 예제, 모델 카드까지 함께 갱신하고 테스트 후 PR 리뷰와 배포를 진행한다. 가격은 요금 계산식이므로 에너지 오차와 구분한다.

운영 로그 수집과 공개 실측 데이터 재학습의 출처를 구분한다. 공개 실측 재학습 결과는 아래에 별도로 기록한다.


## 추가 완료: 공개 실측 데이터로 재학습·전후 평가

사용자가 4·5번 진행을 요청해 기존에 확보한 LARCO 실험실 세탁코스 요약을 사용했다.
이 데이터는 CloudWatch 운영 정답 로그가 아니다. 냉장고·식기세척기 모델과 세탁 시간 모델은 변경하지 않았다.

- 출처: https://zenodo.org/records/18657997 · CC-BY-4.0
- 원본 CSV SHA-256: `23f8a0b79fb0719dd8d2f94fd592cab83c4085364a80ffe7d33f79803fadcc37`
- 기존과 같은 전처리 후 642코스. 제품별 시간순 학습 383 / 검증 128 / 평가 131코스.
- 예측 시점에 아는 제품·프로그램·설정 온도·주변 온도·세탁물 무게만 사용한다. 실제 사용 전력·종료시간·사후 통계는 피처로 쓰지 않는다.
- 트리 계열 초기 실험 후보는 평가 성능이 악화되어 배포하지 않았다. 커널 계열을 포함한 재현 가능한 34개 후보 중 검증 MAE가 가장 낮은 SVR(C=5000, gamma=0.01, epsilon=10)을 선택하고 학습+검증 511코스로 재학습했다.
- 이전에도 확인한 평가 구간을 다시 보는 탐색적 비교다. 후보 선택에는 검증 구간을 사용했지만 새 독립 테스트나 실제 사용자 가정의 일반화 성능을 입증하지 않는다.

| 세탁코스 1회 전력량 · 같은 131코스 | 기존 모델 | 재학습 모델 |
|---|---:|---:|
| R² | 0.883463 | 0.898124 |
| MAE (Wh) | 98.626652 | 87.325172 |
| RMSE (Wh) | 126.916208 | 118.664589 |
| 예시 200원/kWh로 환산한 MAE (원) | 19.725330 | 17.465034 |

**MAE 11.46% 감소**, R² +0.014661이다. 예시 단가 환산은 실제 고지서 오차가 아니다.
제품별로 7개 중 6개는 MAE가 줄고 `becken_BWM5381IX`는 107.626→118.386Wh로 증가했다.
평가에는 기존 프로토콜과 동일하게 고장 표시 제품도 포함되어 있다. 전체 개선이 모든 제품의 개선을 뜻하지 않는다.
새 모델의 예측 구간은 새 잔차 기반 폭만 사용하면 좁아지므로 이전 반폭 264.95Wh보다 축소하지 않았다.
같은 기존 후반 평가 67코스에서 포함률 95.52%를 관측했다. 기존 포함률과 같으며 새로운 포함 보장을 의미하지 않는다.
기존 7개 검증 예제의 입력과 실제 정답은 유지하고 새 모델 출력·모델 해시만 갱신했다.

### 재현 명령

기존 모델은 교체 전에 별도 폴더에 보존한다. 아래 경로는 사용자가 보관한 공개 CSV와 기존 모델 경로로 바꾼다.
후보 생성은 운영 모델을 덮어쓰지 않는다.

```bash
python retrain_larco.py --csv /path/to/aggregated_data.csv --baseline /path/to/old/larco_cycle_model.joblib --out reports/retrained
```

`comparison.json`의 동일 평가 표본, 제품별 수치와 `promotion_eligible`를 확인한다.
검토한 후보 번들과 지표를 `models/`에 복사한 후, 이전 `calibration_metrics.json`을 별도로 보존한 상태에서 다음을 실행한다.

```bash
python refresh_laundry_artifacts.py --csv /path/to/aggregated_data.csv --baseline-calibration /path/to/old/calibration_metrics.json
python -m unittest test_retraining test_feedback_preparation test_host_operations test_feedback_log test_appliance_plan test_laundry test_device_forecast test_verification test_api test_verification_ui test_improvements
```

배포는 같은 Blue/Green 스크립트를 사용해 새 컨테이너의 테스트·헬스 체크 후 전환한다.
실습 4·5번의 공개 데이터 대체 실험이며, 운영 로그를 통한 재학습은 실제 정답 수집 후 별도로 수행해야 한다.
