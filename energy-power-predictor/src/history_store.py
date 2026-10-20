"""Opt-in local SQLite records, scoped by unguessable per-browser capability.

No account identity, IP, uploaded CSV, or plaintext capability is persisted.
Do not expose records without TLS when deployed. This is not account authentication.
"""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
from contextlib import contextmanager
from src.device_forecast import numeric

ROOT=Path(__file__).resolve().parents[1]


def owner_hash(token):
    if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',token):
        raise ValueError('이 브라우저의 기록 접근 키를 확인하세요')
    return hashlib.sha256(token.encode()).hexdigest()


@contextmanager
def connect():
    path=Path(os.environ.get('ENERGY_HISTORY_DB',str(ROOT/'work/user_history.sqlite3')))
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor=os.open(str(path),os.O_CREAT|os.O_RDWR,0o600);os.close(descriptor)
    os.chmod(path,0o600)
    db=sqlite3.connect(str(path),timeout=5)
    db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, owner TEXT NOT NULL, created TEXT NOT NULL, label TEXT NOT NULL, payload TEXT NOT NULL, result TEXT NOT NULL, model_version TEXT NOT NULL, actual_wh REAL)')
    db.execute('CREATE INDEX IF NOT EXISTS record_owner ON records(owner,created)')
    db.commit()
    try:
        with db:yield db
    finally:db.close()


def _rows(db,owner):
    rows=db.execute('SELECT id,created,label,payload,result,model_version,actual_wh FROM records WHERE owner=? ORDER BY created DESC LIMIT 100',(owner,)).fetchall()
    result=[]
    for row in rows:
        r=dict(row);r['payload']=json.loads(r['payload']);r['prediction']=json.loads(r.pop('result'))
        r['absolute_error_wh']=None if r['actual_wh'] is None else abs(r['actual_wh']-r['prediction']['selected_appliances_wh'])
        result.append(r)
    return result


def handle(action,data,predictor):
    if not isinstance(data,dict):raise ValueError('JSON 객체가 필요합니다')
    owner=owner_hash(data.get('owner_token'))
    if action=='save':
        if data.get('consent') is not True:raise ValueError('저장할 때마다 명시적인 동의가 필요합니다')
        payload=data.get('prediction_payload')
        if not isinstance(payload,dict):raise ValueError('예측 입력을 확인하세요')
        label=data.get('label','선택 가전 계획')
        if not isinstance(label,str) or not 1<=len(label)<=80:raise ValueError('기록 이름은 1~80자입니다')
        result=predictor('/api/appliance-plan',payload)
        files=('device_forecast_model.joblib','larco_cycle_model.joblib','device_extended_model.joblib')
        hashes={name:hashlib.sha256((ROOT/'models'/name).read_bytes()).hexdigest() for name in files if (ROOT/'models'/name).exists()}
        record_id=secrets.token_hex(16)
        with connect() as db:
            if db.execute('SELECT COUNT(*) FROM records WHERE owner=?',(owner,)).fetchone()[0]>=1000:
                raise ValueError('브라우저별 기록은 1000개까지 저장할 수 있습니다. 내보낸 후 필요 없는 기록을 삭제하세요.')
            db.execute('INSERT INTO records VALUES (?,?,?,?,?,?,?,NULL)',(record_id,owner,datetime.now(timezone.utc).isoformat(),label,json.dumps(payload,allow_nan=False),json.dumps(result,allow_nan=False),json.dumps(hashes)))
        return {'id':record_id,'saved':True,'note':'해당 서버 디스크에 저장했습니다. 브라우저 접근 키를 잃으면 조회할 수 없습니다. 파일은 암호화되지 않으며 OS 접근권한으로 제한됩니다.'}
    if action not in ('list','actual','delete'):raise ValueError('지원하지 않는 기록 작업')
    with connect() as db:
        if action in ('actual','delete'):
            record_id=data.get('id')
            if not isinstance(record_id,str) or not db.execute('SELECT id FROM records WHERE owner=? AND id=?',(owner,record_id)).fetchone():
                raise ValueError('이 브라우저의 기록을 찾을 수 없습니다')
            if action=='actual':
                if data.get('scope_confirmed') is not True:raise ValueError('같은 가전·대수·예측 기간의 실측임을 확인하세요')
                actual=numeric(data.get('actual_wh'),'실제 사용량 Wh',0,10000000)
                db.execute('UPDATE records SET actual_wh=? WHERE owner=? AND id=?',(actual,owner,record_id))
            else:
                if data.get('confirm_delete') is not True:raise ValueError('삭제 확인이 필요합니다')
                db.execute('DELETE FROM records WHERE owner=? AND id=?',(owner,record_id))
        rows=_rows(db,owner)
    return {'records':rows,'note':'최근 100개만 표시합니다. 임의 계획과 가전별 모델·예측 기간이 섞인 기록으로 전체 R²를 계산하지 않습니다.'}
