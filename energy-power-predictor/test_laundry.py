import copy
import unittest
from pathlib import Path
import joblib
import pandas as pd
from train_larco import features
from src.laundry import predict_laundry


class LaundryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle=joblib.load(Path(__file__).parent/'models/larco_cycle_model.joblib')

    def setUp(self):
        m=next(iter(self.bundle['catalog']))
        catalog=self.bundle['catalog'][m]
        o=catalog['options'][0]
        self.payload={'machine':m,'program':o['program'],'heat':o['heat'],'load_kg':o['min_load_kg'],
                      'ambient_temp':catalog['ambient_min'],'unit_price_krw_per_kwh':200}

    def test_units_and_scope(self):
        r=predict_laundry(self.bundle,self.payload)
        self.assertGreaterEqual(r['energy_wh'],0)
        self.assertAlmostEqual(r['energy_wh']/1000,r['energy_kwh'])
        self.assertAlmostEqual(r['energy_kwh']*200,r['cost_krw'])
        self.assertIsNone(r['whole_house_scenario_r2'])
        self.assertEqual(r['test_cycles'],131)

    def test_rate_change_not_energy_change(self):
        a=predict_laundry(self.bundle,self.payload)
        self.payload['unit_price_krw_per_kwh']=400
        b=predict_laundry(self.bundle,self.payload)
        self.assertEqual(a['energy_wh'],b['energy_wh'])
        self.assertAlmostEqual(a['cost_krw']*2,b['cost_krw'])

    def test_invalid_inputs(self):
        for key,value in [('machine','unknown'),('program','unknown'),('heat','unknown'),('load_kg',float('nan')),('ambient_temp',-100),('unit_price_krw_per_kwh',True)]:
            p=copy.deepcopy(self.payload);p[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):predict_laundry(self.bundle,p)

    def test_post_cycle_values_do_not_affect_features(self):
        row=pd.DataFrame([dict(machine='test',program_name='cotton',program_heat='40',ambient_temp=25.,target_load=2.,
                               cycle_duration=120,total_energy_consumed_wh=500,power_mean=200,post_cycle_weight=4.)])
        before=features(row)
        row[['cycle_duration','total_energy_consumed_wh','power_mean','post_cycle_weight']]=99999
        pd.testing.assert_frame_equal(before,features(row))


if __name__=='__main__':unittest.main()
