import copy
import unittest
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from src.device_forecast import COLUMNS,predict_device,training_features


class DeviceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle=joblib.load(Path(__file__).parent/'models/device_forecast_model.joblib')

    def setUp(self):
        self.payload={'device':'fridge','recent_wh':[5.]*6,'hour':12,'minute':30,'weekday':2,'unit_price_krw_per_kwh':200}

    def test_both_models_and_units(self):
        for device in ('fridge','dishwasher'):
            self.payload['device']=device
            result=predict_device(self.bundle,self.payload)
            self.assertTrue(np.isfinite(result['energy_wh']))
            self.assertGreaterEqual(result['energy_wh'],0)
            self.assertAlmostEqual(result['cost_krw'],result['energy_wh']/1000*200)
            self.assertIsNone(result['cycle_scenario_r2'])
            self.assertEqual(result['test_rows'],14933)

    def test_no_future_or_whole_house_features(self):
        series=pd.Series(np.arange(20.),index=pd.date_range('2026-01-01',periods=20,freq='10min'))
        before=training_features(series)
        changed=series.copy();changed.iloc[11:]=999
        pd.testing.assert_frame_equal(before.iloc[:11],training_features(changed).iloc[:11])
        self.assertFalse(any('total' in c or 'Aggregate' in c for c in COLUMNS))

    def test_reject_invalid_inputs(self):
        for key,value in [('device','whole-house'),('recent_wh',[5.]*5),('recent_wh',[float('nan')]*6),('hour',2.5),('minute',60),('unit_price_krw_per_kwh',True)]:
            p=copy.deepcopy(self.payload);p[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):predict_device(self.bundle,p)

    def test_rate_only_changes_cost(self):
        a=predict_device(self.bundle,self.payload)
        self.payload['unit_price_krw_per_kwh']=400
        b=predict_device(self.bundle,self.payload)
        self.assertEqual(a['energy_wh'],b['energy_wh'])
        self.assertAlmostEqual(b['cost_krw'],a['cost_krw']*2)


if __name__=='__main__':unittest.main()
