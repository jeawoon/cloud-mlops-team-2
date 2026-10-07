"""JSON prediction API. Run with: python api.py --port 8000."""
import argparse
import json
import math
from datetime import datetime
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import joblib
from src.features import make_demo_row
from src.billing import estimate_incremental_cost

ROOT = Path(__file__).parent


@lru_cache(maxsize=3)
def bundle(name):
    return joblib.load(ROOT / 'models' / name)


def number(data, name, low, high, default=None, integer=False):
    value = data.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name}: numeric value between {low} and {high} required')
    if integer and int(value) != value:
        raise ValueError(f'{name}: integer required')
    return int(value) if integer else float(value)


def predict(path, data):
    if not isinstance(data, dict):
        raise ValueError('JSON object required')
    hour = number(data, 'hour', 0, 23, integer=True)
    weekday = number(data, 'weekday', 0, 6, integer=True)
    if path == '/api/predict':
        b = bundle('energy_model.joblib')
        mode = data.get('mode', 'manual')
        if mode not in ('manual', 'advanced'):
            raise ValueError('mode must be manual or advanced')
        weather = data.get('weather', '맑음')
        if weather not in ('맑음', '흐림', '비', '눈'):
            raise ValueError('invalid weather')
        conditions = [number(data,'indoor_temp',10,35),number(data,'indoor_humidity',20,80),number(data,'outdoor_temp',-15,40),number(data,'outdoor_humidity',10,100)]
        month = number(data,'month',1,12,datetime.now().month,integer=True)
        hours = number(data,'forecast_hours',1,8,1,integer=True)
        previous = yesterday = recent = None
        if mode == 'advanced':
            previous,yesterday,recent = [number(data,key,0,100000) for key in ('previous_hour_wh','same_hour_yesterday_wh','recent_3h_mean_wh')]
        forecast, peaks = [], []
        for step in range(hours):
            row = make_demo_row(*conditions,weather,(hour+step)%24,(weekday+(hour+step)//24)%7,month,b['defaults'],previous,yesterday,recent)
            models = b['models'][mode]
            center=max(0,float(models['0.5'].predict(row)[0]))
            lower=min(center,max(0,float(models['0.1'].predict(row)[0])))
            upper=max(center,float(models['0.9'].predict(row)[0]))
            forecast.append([lower,center,upper])
            peak = b.get('peak_models',{}).get(mode)
            if peak is not None:peaks.append(float(peak.predict_proba(row)[0,1]))
            if mode == 'advanced':previous,recent=center,(recent*2+center)/3
        return {'forecast':forecast,'peak_probabilities':peaks,'total_kwh':sum(f[1] for f in forecast)*6/1000,'unit':'Wh per 10 minutes','metrics':b['metrics'][mode+'_mode']}
    if path not in ('/api/recent','/api/whole-house'):
        raise KeyError('Unknown endpoint')
    recent = data.get('recent_wh')
    if not isinstance(recent,list) or len(recent)!=6:
        raise ValueError('recent_wh must contain 6 values, newest first')
    recent = [number({'value':v},'value',0,100000) for v in recent]
    minutes=number(data,'minutes',10,60,10,integer=True)
    if minutes not in (10,60):raise ValueError('minutes must be 10 or 60')
    key=str(minutes//10)
    if path=='/api/recent':
        from train_recent import recent_row
        b=bundle('recent_model.joblib')
        values=[number(data,'indoor_temp',10,35),number(data,'indoor_humidity',20,80),number(data,'outdoor_temp',-15,40),number(data,'outdoor_humidity',10,100)]
        row=recent_row(*values,hour,weekday,recent)
        scale=1
        metrics=b['metrics'][key]['test']
    else:
        from train_refit import row as refit_row
        b=bundle('refit_model.joblib')
        scale=number(data,'typical_wh',1,100000)
        row=refit_row(recent,scale,hour,weekday)
        metrics=b['metrics'][key]
    wh=max(0,float(b['models'][key].predict(row)[0])*scale)
    kwh=wh*minutes/10/1000
    tariff=data.get('tariff','주택용 저압')
    if tariff not in ('주택용 저압','주택용 고압'):raise ValueError('invalid tariff')
    monthly=number(data,'monthly_kwh',0,100000,150)
    _,cost=estimate_incremental_cost(monthly,kwh,tariff)
    return {'average_wh_per_10min':wh,'total_kwh':kwh,'estimated_cost_krw':cost,'metrics':metrics,'minutes':minutes}


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def respond(self, status, data):
        body=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path=='/api/health':
            try:
                bundle('energy_model.joblib')
                self.respond(200,{'status':'ok'})
            except Exception:self.respond(503,{'error':'model unavailable'})
        elif self.path=='/api/docs':
            self.respond(200,{'method':'POST','content_type':'application/json','endpoints':{
                '/api/predict':{'required':['indoor_temp','indoor_humidity','outdoor_temp','outdoor_humidity','hour','weekday'],'optional':['weather','month','mode','forecast_hours'],'advanced_required':['previous_hour_wh','same_hour_yesterday_wh','recent_3h_mean_wh'],'output':['forecast [lower,center,upper] Wh/10min','peak_probabilities','total_kwh','metrics']},
                '/api/recent':{'required':['indoor_temp','indoor_humidity','outdoor_temp','outdoor_humidity','hour','weekday','recent_wh'],'optional':['minutes (10 or 60)','monthly_kwh','tariff']},
                '/api/whole-house':{'required':['hour','weekday','recent_wh','typical_wh'],'optional':['minutes (10 or 60)','monthly_kwh','tariff']}}})
        else:self.respond(404,{'error':'not found'})

    def do_POST(self):
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=16384:raise ValueError('body must be 1–16384 bytes')
            data=json.loads(self.rfile.read(length))
            self.respond(200,predict(self.path,data))
        except (ValueError,UnicodeError) as error:self.respond(422,{'error':str(error)})
        except KeyError:self.respond(404,{'error':'not found'})
        except Exception:self.respond(503,{'error':'prediction service unavailable'})


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    HTTPServer((args.host,args.port),Handler).serve_forever()
