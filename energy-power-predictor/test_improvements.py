"""2026-10-20 features: no original CSVs or AWS credentials required."""
import copy
from datetime import date
import io
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from api import predict,Handler
from src.billing import reference_increment,_parts
from src.csv_history import parse_history,MAX_BYTES
from src.extended_history import extended_features
from src.history_store import handle
from src.operations import LimitedServer,RateLimiter
from src.uncertainty import metadata,interval

ROOT=Path(__file__).parent


def csv_bytes(values,unit='Wh'):
    times=pd.date_range('2026-01-01',periods=len(values),freq='10min')
    return pd.DataFrame({'timestamp':times.astype(str),'value':values}).to_csv(index=False).encode()


class CsvTests(unittest.TestCase):
    def test_chronology_and_units(self):
        expected=list(range(6))
        for factor,unit in [(1,'Wh'),(.001,'kWh'),(6,'W')]:
            result=parse_history(csv_bytes([v*factor for v in expected]),unit)
            self.assertEqual(result['recent_wh'],expected[::-1])
            self.assertEqual(result['hour'],0)
            self.assertEqual(result['minute'],50)

    def test_bad_csv_is_rejected(self):
        samples=[b'',b'a'*(MAX_BYTES+1),b'timestamp,watts\n1,2',csv_bytes([1]*5),csv_bytes([True]*6),csv_bytes([-1]*6),csv_bytes([np.nan]*6),csv_bytes([9999]*6)]
        good=csv_bytes([1]*6)
        samples += [good.replace(b'00:10:00',b'00:00:00'),good.replace(b'00:10:00',b'00:15:00'),good.replace(b'2026-01-01',b'2099-01-01')]
        for sample in samples:
            with self.subTest(size=len(sample)),self.assertRaises(ValueError):parse_history(sample)

    def test_24_hour_record_and_predicted_units(self):
        result=parse_history(csv_bytes([5.]*144))
        self.assertEqual(len(result['history_wh']),144)
        result.update(device='fridge',model_variant='extended')
        prediction=predict('/api/device-forecast',result)
        self.assertTrue(np.isfinite(prediction['energy_wh']))
        self.assertEqual(prediction['test_rows'],12380)
        self.assertIsNotNone(prediction['energy_interval_wh'])

    def test_past_only_features(self):
        series=pd.Series(np.arange(300.),index=pd.date_range('2026-01-01',periods=300,freq='10min'))
        old=extended_features(series);new=series.copy();new.iloc[200:]=999
        pd.testing.assert_frame_equal(old.iloc[:200],extended_features(new).iloc[:200])

    def test_degraded_dishwasher_variant_is_not_served(self):
        p=dict(device='dishwasher',recent_wh=[5.]*6,history_wh=[5.]*144,hour=12,weekday=1,model_variant='extended')
        with self.assertRaises(ValueError):predict('/api/device-forecast',p)


class BillingTests(unittest.TestCase):
    def options(self,**kw):
        return dict(tariff='주택용 저압',billing_date='2026-10-20',**kw)

    def test_tiers_and_summer(self):
        a=_parts(201,'주택용 저압',10,0,0,.027)
        b=_parts(201,'주택용 저압',7,0,0,.027)
        self.assertAlmostEqual(a['energy_krw'],200*120+214.6)
        self.assertAlmostEqual(b['energy_krw'],201*120)
        self.assertEqual(a['basic_krw'],1600);self.assertEqual(b['basic_krw'],910)

    def test_difference_includes_basic_fee_crossing(self):
        r=reference_increment(200,1,self.options())
        self.assertEqual(r['after']['basic_krw']-r['before']['basic_krw'],690)
        self.assertEqual(r['additional_cost_krw'],r['after']['bill_krw']-r['before']['bill_krw'])
        self.assertEqual(reference_increment(200,0,self.options())['additional_cost_krw'],0)

    def test_super_user_seasonal_rate(self):
        winter=_parts(1001,'주택용 저압',1,0,0,.027)
        spring=_parts(1001,'주택용 저압',3,0,0,.027)
        self.assertAlmostEqual(winter['energy_krw']-spring['energy_krw'],736.2-307.3)

    def test_reject_invalid_billing(self):
        for options in ({},dict(billing_date='2020-01-01'),dict(billing_date='2026-10-20',tariff=[]),dict(billing_date='2026-10-20',fuel_won_per_kwh=True)):
            with self.assertRaises(ValueError):reference_increment(150,1,options)
        with self.assertRaises(ValueError):reference_increment(-1,1,self.options())

    def test_old_fixed_plan_and_optional_reference(self):
        payload=dict(plans=[dict(device='Appliance4',method='power_time',quantity=2,settings=dict(power_w=100,duration_minutes=60))],unit_price_krw_per_kwh=200)
        self.assertEqual(predict('/api/appliance-plan',payload)['selected_appliances_cost_krw'],40)
        payload['billing']=dict(self.options(),current_kwh=150,acknowledge_reference=True)
        r=predict('/api/appliance-plan',payload)
        self.assertEqual(r['selected_appliances_wh'],200)
        self.assertEqual(r['selected_appliances_cost_krw'],r['billing']['additional_cost_krw'])


class IntervalTests(unittest.TestCase):
    def test_calibration_counts_and_containment(self):
        for key in ('fridge','dishwasher','laundry','fridge_extended'):
            r=interval(key,10)
            self.assertLessEqual(r['lower_wh'],10)
            self.assertGreaterEqual(r['upper_wh'],10)
            self.assertGreaterEqual(r['lower_wh'],0)
            self.assertGreater(r['evaluation_rows'],0)
        self.assertEqual(metadata()['calibrations']['fridge']['calibration_rows'],7466)
        self.assertEqual(metadata()['calibrations']['fridge']['evaluation_rows'],7467)

    def test_point_models_unchanged(self):
        cases=json.loads((ROOT/'models/verification_cases.json').read_text())['cases']
        for case in cases:
            self.assertAlmostEqual(predict('/api/appliance-plan',case['payload'])['selected_appliances_wh'],case['reference_prediction_wh'])


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'ENERGY_HISTORY_DB':str(Path(self.directory.name)/'history.sqlite3')});self.env.start()
        self.a='a'*43;self.b='b'*43
        self.payload=dict(plans=[dict(device='Appliance4',method='power_time',settings=dict(power_w=100,duration_minutes=60))])

    def tearDown(self):
        self.env.stop();self.directory.cleanup()

    def save(self):
        return handle('save',dict(owner_token=self.a,consent=True,prediction_payload=self.payload),predict)['id']

    def test_consent_required_and_no_side_effect(self):
        with self.assertRaises(ValueError):handle('save',dict(owner_token=self.a,prediction_payload=self.payload),predict)
        self.assertFalse((Path(self.directory.name)/'history.sqlite3').exists())

    def test_ownership_actual_and_delete(self):
        record=self.save()
        self.assertEqual(handle('list',dict(owner_token=self.b),predict)['records'],[])
        for action in ('actual','delete'):
            with self.assertRaises(ValueError):handle(action,dict(owner_token=self.b,id=record,actual_wh=80,scope_confirmed=True,confirm_delete=True),predict)
        result=handle('actual',dict(owner_token=self.a,id=record,actual_wh=80,scope_confirmed=True),predict)
        self.assertEqual(result['records'][0]['absolute_error_wh'],20)
        self.assertEqual(handle('delete',dict(owner_token=self.a,id=record,confirm_delete=True),predict)['records'],[])

    def test_client_prediction_not_trusted_and_file_private(self):
        self.save()
        rows=handle('list',dict(owner_token=self.a,predicted_wh=99999),predict)['records']
        self.assertEqual(rows[0]['prediction']['selected_appliances_wh'],100)
        path=Path(self.directory.name)/'history.sqlite3'
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertNotIn(self.a.encode(),path.read_bytes())


class OperationsTests(unittest.TestCase):
    def test_throttle(self):
        limiter=RateLimiter(limit=2)
        self.assertTrue(limiter.allow('a'));self.assertTrue(limiter.allow('a'));self.assertFalse(limiter.allow('a'))
        self.assertTrue(limiter.allow('b'))

    def test_auth_and_redacted_logs(self):
        server=LimitedServer(('127.0.0.1',0),Handler,max_workers=2)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        secret='private-service-token-not-for-logs'
        url='http://127.0.0.1:'+str(server.server_port)
        try:
            with patch.dict(os.environ,{'PREDICTION_API_TOKEN':secret}):
                with self.assertRaises(HTTPError) as error:urlopen(url+'/api/docs',timeout=5)
                self.assertEqual(error.exception.code,401)
                self.assertEqual(urlopen(url+'/api/health',timeout=5).status,200)
                with self.assertLogs('energy_api',level='INFO') as captured:
                    request=Request(url+'/api/docs',headers={'Authorization':'Bearer '+secret})
                    with urlopen(request,timeout=5) as response:self.assertEqual(response.status,200)
                self.assertNotIn(secret,' '.join(captured.output))
        finally:server.shutdown();server.server_close();thread.join(timeout=5)


class ImprovementsUiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.server=LimitedServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.env=patch.dict(os.environ,{'ENERGY_HISTORY_DB':str(Path(self.temp.name)/'ui.sqlite3'),
            'PREDICTION_API_URL':'http://127.0.0.1:'+str(self.server.server_port)})
        self.env.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
        self.env.stop();self.temp.cleanup()

    def app(self):return AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()

    def test_ai_mode_csv_and_24h_option(self):
        app=self.app();self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key='plan_method_Appliance2_simple').value,'시간·소비전력 입력')
        app.radio(key='workspace_mode').set_value('AI 예측').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key='plan_method_Appliance2_ai').value,'세탁코스 학습 모델')
        app.multiselect(key='ai_plan_devices').set_value(['Appliance1']).run()
        with patch('src.appliance_plan_ui.st.file_uploader',return_value=io.BytesIO(csv_bytes([5.]*144))):
            app.radio(key='input_source_Appliance1').set_value('CSV 업로드').run()
            self.assertFalse(app.exception)
            app.checkbox(key='use_extended_Appliance1').check().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('0.8119' in c.value for c in app.caption))
            self.assertTrue(any('예상 범위' in m.value for m in app.markdown))

    def test_progressive_record_and_actual_round_trip(self):
        app=self.app()
        app.multiselect(key='plan_devices').set_value(['Appliance4']).run()
        app.number_input(key='plan_power_Appliance4').set_value(100.).run()
        app.number_input(key='plan_duration_Appliance4').set_value(60.).run()
        app.number_input(key='plan_qty_Appliance4').set_value(2).run()
        app.radio(key='billing_mode').set_value('주택용 누진 참고 계산').run()
        app.checkbox(key='bill_ack').check().run()
        self.assertFalse(app.exception)
        app.checkbox(key='record_consent').check().run()
        app.button(key='save_prediction').click().run()
        self.assertFalse(app.exception)
        owner=app.session_state.private_history_token
        records=handle('list',dict(owner_token=owner),predict)['records']
        self.assertEqual(len(records),1)
        record=records[0]['id']
        app.radio(key='workspace_mode').set_value('내 기록').run()
        self.assertFalse(app.exception)
        app.number_input(key='actual_'+record).set_value(240.).run()
        app.checkbox(key='scope_'+record).check().run()
        next(b for b in app.button if b.label=='실측값 저장').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any(m.label=='절대오차 Wh' and m.value=='40.000' for m in app.metric))


if __name__=='__main__':unittest.main()
