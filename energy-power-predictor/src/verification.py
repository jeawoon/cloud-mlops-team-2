"""Compare fixed holdout labels with live predictions, never feed labels to a model."""
import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def load_cases():
    fixture = json.loads((ROOT / 'models/verification_cases.json').read_text())
    for name, expected in fixture['model_sha256'].items():
        if name not in ('larco_cycle_model.joblib', 'device_forecast_model.joblib'):
            raise RuntimeError('Unexpected verification model')
        digest = hashlib.sha256((ROOT / 'models' / name).read_bytes()).hexdigest()
        if digest != expected:
            raise RuntimeError('검증 예제와 모델 버전이 다릅니다. 예제를 다시 생성하세요.')
    return fixture


def run_case(payload, predictor):
    if not isinstance(payload, dict) or not isinstance(payload.get('case_id'), str):
        raise ValueError('case_id 문자열을 입력하세요')
    case = next((c for c in load_cases()['cases'] if c['id'] == payload['case_id']), None)
    if case is None:
        raise ValueError('알 수 없는 검증 예제입니다')
    # Only the recorded pre-forecast payload crosses the prediction boundary.
    result = predictor('/api/appliance-plan', copy.deepcopy(case['payload']))
    predicted = result['selected_appliances_wh']
    actual = case['actual_wh']
    price = case['payload']['unit_price_krw_per_kwh']
    error = predicted - actual
    return dict(case_id=case['id'], label=case['label'], kind=case['kind'], scope=case['scope'],
                source=case['source'], selection_rule=case['selection_rule'],
                prediction_payload=case['payload'], actual_wh=actual, predicted_wh=predicted,
                signed_error_wh=error, absolute_error_wh=abs(error),
                relative_error_pct=None if actual == 0 else abs(error) / actual * 100,
                actual_energy_equivalent_cost_krw=actual / 1000 * price,
                predicted_cost_krw=result['selected_appliances_cost_krw'],
                reproduction_ok=abs(predicted-case['reference_prediction_wh']) <= 1e-6,
                record=case.get('source_record', case.get('forecast_at', 'fixed arithmetic')),
                forecast_at=case.get('forecast_at'), target_end=case.get('target_end'),
                note='재현 여부는 저장된 모델 출력과의 일치 검사이며 실제값 적중 판정이 아닙니다. 요금은 예시 단가 200원/kWh의 에너지 환산이며 실제 청구액이 아닙니다.')
