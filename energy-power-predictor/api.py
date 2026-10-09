"""Appliance-only API. Whole-house endpoints intentionally retired."""
import argparse
import json
from functools import lru_cache
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
import joblib

ROOT=Path(__file__).parent
RETIRED=('/api/simulate','/api/whole-house','/api/simulator/catalog')

@lru_cache(maxsize=2)
def bundle(name):
    return joblib.load(ROOT/'models'/name)

@lru_cache(maxsize=1)
def power_catalog():
    return json.loads((ROOT/'models/appliance_power_catalog.json').read_text())

def predict(path,data):
    if not isinstance(data,dict):raise ValueError('JSON object required')
    if path=='/api/appliance-plan':
        from src.appliance_plan import calculate_plan
        return calculate_plan(data,power_catalog(),bundle)
    if path=='/api/laundry-cycle':
        from src.laundry import predict_laundry
        return predict_laundry(bundle('larco_cycle_model.joblib'),data)
    if path=='/api/device-forecast':
        from src.device_forecast import predict_device
        return predict_device(bundle('device_forecast_model.joblib'),data)
    raise KeyError('Unknown endpoint')

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def respond(self,status,data):
        body=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in RETIRED:
            self.respond(410,{'error':'집 전체 예측 모델은 제거되었습니다.'})
        elif self.path=='/api/docs':
            self.respond(200,{'method':'POST','endpoints':{
                '/api/appliance-plan':{'required':['plans (device Appliance1..9, method, quantity, settings)'],'optional':['unit_price_krw_per_kwh'],'methods':['power_time: power_w, duration_minutes, duty_cycle_pct, standby_w','laundry_cycle: same fields as laundry-cycle endpoint; Appliance2 only','recent_forecast: same fields as device-forecast; Appliance1 or Appliance3 only'],'scope':'Sum selected appliance plans; NOT whole-house or a single common 10-minute horizon. plan_r2 remains null.'},
                '/api/laundry-cycle':{'required':['machine','program','heat (string)','load_kg','ambient_temp'],'optional':['unit_price_krw_per_kwh'],'scope':'complete measured washing cycle'},
                '/api/device-forecast':{'required':['device (fridge or dishwasher)','recent_wh (6 appliance-only completed bins, newest first)','hour','weekday'],'optional':['minute','unit_price_krw_per_kwh'],'scope':'next 10-minute energy of one appliance; not a user-plan complete-cycle simulation'}}})
        elif self.path=='/api/health':
            try:
                bundle('larco_cycle_model.joblib')
                bundle('device_forecast_model.joblib')
                power_catalog()
                self.respond(200,{'status':'ok','scope':'appliances only'})
            except Exception:self.respond(503,{'error':'model unavailable'})
        elif self.path=='/api/laundry-cycle/catalog':
            try:
                b=bundle('larco_cycle_model.joblib')
                self.respond(200,{'catalog':b['catalog'],'measured_cycle_test_metrics':b['metrics']['reports']['energy']['test'],'test_cycles':b['metrics']['test_cycles']})
            except Exception:self.respond(503,{'error':'model unavailable'})
        elif self.path=='/api/device-forecast/catalog':
            try:
                b=bundle('device_forecast_model.joblib')
                self.respond(200,{'devices':b['metrics']})
            except Exception:self.respond(503,{'error':'model unavailable'})
        else:self.respond(404,{'error':'not found'})

    def do_POST(self):
        if self.path in RETIRED:
            self.respond(410,{'error':'집 전체 예측 모델은 제거되었습니다.'})
            return
        if self.path not in ('/api/laundry-cycle','/api/device-forecast','/api/appliance-plan'):
            self.respond(404,{'error':'not found'})
            return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=16384:raise ValueError('body must be 1–16384 bytes')
            self.respond(200,predict(self.path,json.loads(self.rfile.read(length))))
        except (ValueError,UnicodeError) as error:self.respond(422,{'error':str(error)})
        except Exception:self.respond(503,{'error':'prediction service unavailable'})

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    HTTPServer((args.host,args.port),Handler).serve_forever()
