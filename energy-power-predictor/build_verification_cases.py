"""Read original public datasets; print deterministic holdout fixtures as JSON.

Does not fit a model, alter data, or choose examples by prediction error.
"""
import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score

from src.device_forecast import COLUMNS, DEVICES, training_features
from src.laundry import predict_laundry
from train_device_forecasts import load

ROOT = Path(__file__).parent


def digest(path, algorithm='sha256'):
    result = hashlib.new(algorithm)
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def build(larco_path, refit_path):
    if digest(larco_path) != '23f8a0b79fb0719dd8d2f94fd592cab83c4085364a80ffe7d33f79803fadcc37':
        raise ValueError('Unexpected LARCO source checksum')
    if digest(refit_path, 'md5') != '13957fd139bf8f6ba8bceea36e85bb3d':
        raise ValueError('Unexpected REFIT source checksum')
    laundry = joblib.load(ROOT / 'models/larco_cycle_model.joblib')
    devices = joblib.load(ROOT / 'models/device_forecast_model.joblib')
    cases = [dict(
        id='formula-tv', label='TV 100W · 60분 · 2대: 산식 확인',
        kind='formula', scope='60분 사용 계획', source='산술 검증, 실측 데이터 아님',
        selection_rule='고정된 독립 산식: 100 × 60/60 × 2 = 200Wh',
        actual_wh=200.0, reference_prediction_wh=200.0,
        payload=dict(unit_price_krw_per_kwh=200, plans=[dict(
            device='Appliance4', method='power_time', quantity=2,
            settings=dict(power_w=100, duration_minutes=60, duty_cycle_pct=100, standby_w=0))]))]
    raw = pd.read_csv(larco_path)
    selected_machines = set()
    for identifier in laundry['metrics']['test_cycle_ids']:
        row = raw.loc[raw.file_path == identifier].iloc[0]
        if row.machine in selected_machines or 'flt' in row.machine:
            continue
        settings = dict(machine=str(row.machine), program=str(row.program_name),
                        heat=str(row.program_heat), load_kg=float(row.target_load),
                        ambient_temp=float(row.ambient_temp))
        try:
            prediction = predict_laundry(laundry, settings)
        except ValueError:
            continue  # Only examples supported by the deployed input catalog.
        selected_machines.add(row.machine)
        cases.append(dict(
            id='laundry-'+str(len(selected_machines)), label=f'세탁코스 실측 예제 {len(selected_machines)}',
            kind='measured', scope='세탁코스 1회 전체',
            source=laundry['metrics']['source'], license='CC-BY-4.0',
            source_record=identifier, selection_rule='테스트 ID 순서상 제품별 첫 API 지원 예제, 고장 제품 제외',
            actual_wh=float(row.total_energy_consumed_wh),
            reference_prediction_wh=prediction['energy_wh'],
            payload=dict(unit_price_krw_per_kwh=200, plans=[dict(
                device='Appliance2', method='laundry_cycle', settings=settings)])))
        if len(selected_machines) == 2:
            break
    readings = load(Path(refit_path))
    evaluations = {}
    for device, (channel, label) in DEVICES.items():
        series = readings[channel]
        data = training_features(series).assign(target=series.shift(-1))
        test = data.iloc[int(len(data) * .8):].dropna()
        predictions = np.maximum(devices['models'][device].predict(test[COLUMNS]), 0)
        actual = test.target.to_numpy()
        evaluations[device] = dict(test_rows=len(test), r2=float(r2_score(actual, predictions)),
                                   mae_wh=float(mean_absolute_error(actual, predictions)))
        first_low = next(i for i, value in enumerate(actual) if value < 1.0)
        for tag, i in [('first', 0), ('low', first_low)]:
            row = test.iloc[i]
            moment = test.index[i]
            settings = dict(recent_wh=[float(row[f'lag_{j}']) for j in range(6)],
                            hour=int(moment.hour), minute=int(moment.minute), weekday=int(moment.weekday()))
            cases.append(dict(
                id=device+'-'+tag, label=label+(' · 테스트 첫 구간' if tag == 'first' else ' · 낮은 사용량 구간'),
                kind='measured', scope='다음 10분', source=devices['metrics'][device]['source'],
                license='CC-BY-4.0', house='House2', forecast_at=str(moment),
                target_end=str(moment + pd.Timedelta(minutes=10)),
                selection_rule='테스트 첫 유효 구간' if tag == 'first' else '정답 1Wh 미만인 첫 테스트 구간(오차 기준 선택 아님)',
                actual_wh=float(actual[i]), reference_prediction_wh=float(predictions[i]),
                payload=dict(unit_price_krw_per_kwh=200, plans=[dict(
                    device=channel, method='recent_forecast', settings=settings)])))
    return dict(schema_version=1, model_sha256={
        name: digest(ROOT / 'models' / name) for name in
        ['larco_cycle_model.joblib', 'device_forecast_model.joblib']},
        full_refit_recheck=evaluations, cases=cases,
        note='기존 테스트 기간의 재현 확인입니다. 예제만으로 전체 R²를 계산하지 않으며 새로운 독립 테스트가 아닙니다.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--larco-csv', required=True)
    parser.add_argument('--refit-csv', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.larco_csv, args.refit_csv), ensure_ascii=False, indent=2, allow_nan=False))
