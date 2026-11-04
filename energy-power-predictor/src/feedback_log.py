"""Opt-in prediction feedback. SQLite is the durable source; JSONL is exportable."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import logging
from logging.handlers import RotatingFileHandler


def event(kind, record_id, payload, prediction, model_version, actual_wh=None, actual_cost=None):
    # Explicit allowlist: no name, owner capability, IP, headers, CSV or unknown fields.
    allowed={'power_time':{'power_w','duration_minutes','duty_cycle_pct','standby_w'},'laundry_cycle':{'machine','program','heat','load_kg','ambient_temp'},'recent_forecast':{'recent_wh','history_wh','hour','weekday','minute','model_variant'}}
    plans=[]
    for p in payload['plans']:
        plans.append({**{k:p[k] for k in ('device','method','quantity','start_after_minutes') if k in p},'settings':{k:v for k,v in p.get('settings',{}).items() if k in allowed.get(p.get('method','power_time'),set())}})
    predicted_wh=prediction['selected_appliances_wh'];predicted_cost=prediction['selected_appliances_cost_krw']
    assessment=None
    if actual_wh is not None:
        energy_error=predicted_wh-actual_wh
        energy_limit=max(5.,abs(actual_wh)*.1)
        cost_error=None if actual_cost is None else predicted_cost-actual_cost
        cost_limit=None if actual_cost is None else max(1.,abs(actual_cost)*.1)
        assessment=dict(energy_signed_error_wh=energy_error,energy_absolute_error_wh=abs(energy_error),energy_tolerance_wh=energy_limit,energy_within_tolerance=abs(energy_error)<=energy_limit,
                        price_signed_error_krw=cost_error,price_absolute_error_krw=None if cost_error is None else abs(cost_error),price_tolerance_krw=cost_limit,price_within_tolerance=None if cost_error is None else abs(cost_error)<=cost_limit,
                        rule='v1: energy max(5Wh,10% actual); price max(1KRW,10% actual)',label_source='user_reported_same_scope')
    return dict(schema_version=1,event_id=secrets.token_hex(16),event_type=kind,prediction_id=record_id,occurred_at=datetime.now(timezone.utc).isoformat(),
                inputs={'plans':plans,'unit_price_krw_per_kwh':prediction['unit_price_krw_per_kwh'],'billing':{k:v for k,v in payload.get('billing',{}).items() if k in ('current_kwh','tariff','billing_date','climate_won_per_kwh','fuel_won_per_kwh')}},
                target={'name':'selected_appliances_energy_and_additional_cost','scopes':[i['scope'] for i in prediction['items']],'actual_wh':actual_wh,'actual_additional_cost_krw':actual_cost},
                prediction={'energy_wh':predicted_wh,'additional_cost_krw':predicted_cost,'methods':[i['method'] for i in prediction['items']]},
                release=os.environ.get('ENERGY_RELEASE','unknown'),model_version=json.loads(model_version),assessment=assessment,status='pending_actual' if actual_wh is None else 'evaluated',has_label=actual_wh is not None,training_eligible=False,quality_review_required=True,
                note='User-reported labels require quality review; power_time is arithmetic. Not automatically approved training data.')


def persist(db, value):
    db.execute('INSERT INTO feedback_events VALUES (?,?,?,?)',(value['event_id'],value['prediction_id'],value['occurred_at'],json.dumps(value,ensure_ascii=False,allow_nan=False)))


def export(value):
    # JSONL is best-effort; committed SQLite events remain recoverable after file failure.
    try:
        from src.history_store import ROOT
        path=Path(os.environ.get('ENERGY_HISTORY_DB',str(ROOT/'work/user_history.sqlite3'))).parent/'feedback'
        path.mkdir(parents=True,exist_ok=True,mode=0o700)
        logger=logging.getLogger('energy_feedback_file')
        if not logger.handlers:
            handler=RotatingFileHandler(path/(socket.gethostname()+'.jsonl'),maxBytes=10*1024*1024,backupCount=10,encoding='utf-8')
            handler.setFormatter(logging.Formatter('%(message)s'));logger.addHandler(handler);logger.setLevel(logging.INFO);logger.propagate=False
        logger.info(json.dumps(value,ensure_ascii=False,allow_nan=False))
    except Exception:
        logging.getLogger('energy_api').error('feedback_jsonl_export_failed; durable SQLite event retained')
