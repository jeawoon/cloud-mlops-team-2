import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from api import predict
from src.verification import load_cases, run_case


class VerificationTests(unittest.TestCase):
    def test_all_fixtures_reproduce_saved_predictions(self):
        fixture = load_cases()
        self.assertEqual(len(fixture['cases']), 7)
        for case in fixture['cases']:
            with self.subTest(case=case['id']):
                result = run_case({'case_id': case['id']}, predict)
                self.assertTrue(result['reproduction_ok'])
                self.assertAlmostEqual(result['absolute_error_wh'], abs(result['predicted_wh']-result['actual_wh']))
                self.assertAlmostEqual(result['predicted_cost_krw'], result['predicted_wh']/1000*200)

    def test_formula_has_independent_exact_answer(self):
        result = run_case({'case_id': 'formula-tv'}, predict)
        self.assertEqual(result['kind'], 'formula')
        self.assertEqual(result['predicted_wh'], 200)
        self.assertEqual(result['absolute_error_wh'], 0)
        self.assertEqual(result['predicted_cost_krw'], 40)

    def test_actual_and_reference_never_cross_prediction_boundary(self):
        for case in load_cases()['cases']:
            calls = []
            def observer(endpoint, payload):
                calls.append((endpoint, copy.deepcopy(payload)))
                return predict(endpoint, payload)
            run_case({'case_id': case['id'], 'actual_wh': 999999}, observer)
            self.assertEqual(calls, [('/api/appliance-plan', case['payload'])])
            forbidden = {'actual_wh', 'reference_prediction_wh', 'target', 'total_energy_consumed_wh'}
            def inspect(obj):
                if isinstance(obj, dict):
                    self.assertFalse(forbidden.intersection(obj))
                    for value in obj.values(): inspect(value)
                elif isinstance(obj, list):
                    for value in obj: inspect(value)
            inspect(calls[0][1])

    def test_invalid_case_ids(self):
        for payload in (None, [], {}, {'case_id': []}, {'case_id': 'missing'}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                run_case(payload, predict)

    def test_distinct_measured_examples_and_test_membership(self):
        fixture = load_cases()
        payloads = [json.dumps(c['payload'], sort_keys=True) for c in fixture['cases']]
        self.assertEqual(len(payloads), len(set(payloads)))
        root = Path(__file__).parent
        laundry = json.loads((root/'models/larco_cycle_metrics.json').read_text())
        devices = json.loads((root/'models/device_forecast_metrics.json').read_text())
        for case in fixture['cases']:
            if 'source_record' in case:
                self.assertIn(case['source_record'], laundry['test_cycle_ids'])
            if 'forecast_at' in case:
                device = 'fridge' if case['id'].startswith('fridge') else 'dishwasher'
                self.assertGreaterEqual(case['forecast_at'], devices[device]['test_start'])
                self.assertLessEqual(case['forecast_at'], devices[device]['test_end'])
        for device in devices:
            recheck = fixture['full_refit_recheck'][device]
            self.assertEqual(recheck['test_rows'], devices[device]['test_rows'])
            self.assertAlmostEqual(recheck['r2'], devices[device]['test']['r2'])
            self.assertAlmostEqual(recheck['mae_wh'], devices[device]['test']['mae_wh'])

    def test_predictor_cannot_mutate_shared_fixture(self):
        before = copy.deepcopy(load_cases())
        def mutate(endpoint, payload):
            result = predict(endpoint, payload)
            payload['plans'].clear()
            return result
        run_case({'case_id': 'formula-tv'}, mutate)
        self.assertEqual(load_cases(), before)

    def test_wrong_model_fails_instead_of_showing_stale_reference(self):
        load_cases.cache_clear()
        try:
            with patch.object(Path, 'read_bytes', return_value=b'wrong model'), self.assertRaises(RuntimeError):
                load_cases()
        finally:
            load_cases.cache_clear()


if __name__ == '__main__':
    unittest.main()
