"""Retrospectively calibrated intervals, version-bound to frozen models."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def metadata():
    path=ROOT/'models/calibration_metrics.json'
    if not path.exists():return None
    data=json.loads(path.read_text())
    for name,digest in data['models_sha256'].items():
        if Path(name).name!=name or not name.endswith('.joblib'):raise RuntimeError('Invalid calibration model path')
        if hashlib.sha256((ROOT/'models'/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('예측 구간과 모델 버전이 다릅니다. 보정 자료를 다시 생성하세요.')
    return data


def interval(key,wh):
    data=metadata()
    if data is None or key not in data['calibrations']:return None
    m=data['calibrations'][key]
    return dict(lower_wh=max(0,wh-m['radius_wh']),upper_wh=wh+m['radius_wh'],
                nominal_coverage=m['nominal_coverage'],observed_coverage=m['observed_coverage'],
                evaluation_rows=m['evaluation_rows'],note=m['note'])
