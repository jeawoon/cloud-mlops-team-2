import copy
import json
import unittest
from pathlib import Path
import joblib
from src.appliance_plan import calculate_plan

ROOT=Path(__file__).parent


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.catalog=json.loads((ROOT/'models/appliance_power_catalog.json').read_text())
        self.payload={'unit_price_krw_per_kwh':200,'plans':[
            {'device':'Appliance4','quantity':2,'method':'power_time','settings':{'power_w':100,'duration_minutes':60}},
            {'device':'Appliance1','method':'power_time','settings':{'power_w':100,'duration_minutes':60,'duty_cycle_pct':50,'standby_w':2}}]}

    def test_multiple_appliances_quantity_and_duty(self):
        r=calculate_plan(self.payload,self.catalog,None)
        self.assertAlmostEqual(r['selected_appliances_wh'],251)
        self.assertAlmostEqual(r['selected_appliances_cost_krw'],50.2)
        self.assertIsNone(r['plan_r2'])
        self.assertTrue(all(p['metrics'] is None for p in r['items']))

    def test_future_start_does_not_change_fixed_rate_total(self):
        a=calculate_plan(self.payload,self.catalog,None)
        self.payload['plans'][0]['start_after_minutes']=120
        b=calculate_plan(self.payload,self.catalog,None)
        self.assertEqual(a['selected_appliances_wh'],b['selected_appliances_wh'])

    def test_invalid_plan(self):
        bad=[]
        p=copy.deepcopy(self.payload);p['plans']*=2;bad.append(p)
        p=copy.deepcopy(self.payload);p['plans'][0]['quantity']=True;bad.append(p)
        p=copy.deepcopy(self.payload);p['plans'][0]['settings']['duration_minutes']=-1;bad.append(p)
        p=copy.deepcopy(self.payload);p['plans'][0]['settings']['power_w']=float('nan');bad.append(p)
        p=copy.deepcopy(self.payload);p['plans'][0]['method']='laundry_cycle';bad.append(p)
        for p in bad:
            with self.assertRaises(ValueError):calculate_plan(p,self.catalog,None)

    def test_zero_duration(self):
        p=copy.deepcopy(self.payload);p['plans']=p['plans'][:1];p['plans'][0]['settings']['duration_minutes']=0
        self.assertEqual(calculate_plan(p,self.catalog,None)['selected_appliances_wh'],0)

    def test_model_modes(self):
        def load(name):return joblib.load(ROOT/'models'/name)
        b=load('larco_cycle_model.joblib');m=next(iter(b['catalog']));e=b['catalog'][m];o=e['options'][0]
        plans=[dict(device='Appliance2',method='laundry_cycle',settings=dict(machine=m,program=o['program'],heat=o['heat'],load_kg=o['min_load_kg'],ambient_temp=e['ambient_min'])),
               dict(device='Appliance3',method='recent_forecast',settings=dict(recent_wh=[5.]*6,hour=12,minute=30,weekday=2))]
        r=calculate_plan(dict(plans=plans),self.catalog,load)
        self.assertEqual(len(r['items']),2)
        self.assertTrue(all(item['metrics'] is not None for item in r['items']))
        self.assertAlmostEqual(r['selected_appliances_wh'],sum(item['energy_wh'] for item in r['items']))


if __name__=='__main__':unittest.main()
