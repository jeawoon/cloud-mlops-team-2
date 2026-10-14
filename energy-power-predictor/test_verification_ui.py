"""Streamlit UI -> real local HTTP API -> saved model -> rendered results."""
import json
import os
from pathlib import Path
import threading
import unittest
from http.server import HTTPServer
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from api import Handler

ROOT = Path(__file__).parent


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:'+str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def app(self):
        return AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run()

    def test_formula_and_measured_examples_show_api_response(self):
        with patch.dict(os.environ, {'PREDICTION_API_URL':self.url}):
            app = self.app()
            self.assertFalse(app.exception)
            app.button(key='verification_run').click().run()
            self.assertFalse(app.exception)
            result = app.session_state.verification_result
            self.assertEqual(result['predicted_wh'], 200)
            self.assertTrue(any(m.label=='절대오차 (Wh)' and m.value=='0.000' for m in app.metric))
            fixture = json.loads((ROOT/'models/verification_cases.json').read_text())
            for case in fixture['cases'][1:]:
                app.selectbox(key='verification_case').set_value(case['id']).run()
                app.button(key='verification_run').click().run()
                self.assertFalse(app.exception)
                result = app.session_state.verification_result
                self.assertEqual(result['case_id'], case['id'])
                self.assertAlmostEqual(result['actual_wh'], case['actual_wh'])
                self.assertTrue(result['reproduction_ok'])
                self.assertTrue(any(m.label=='실측 정답 (Wh)' for m in app.metric))

    def test_plan_changes_and_empty_selection_keep_verification_available(self):
        with patch.dict(os.environ, {'PREDICTION_API_URL':self.url}):
            app = self.app()
            app.multiselect(key='plan_devices').set_value(['Appliance4']).run()
            app.number_input(key='plan_power_Appliance4').set_value(100.).run()
            app.number_input(key='plan_duration_Appliance4').set_value(60.).run()
            app.number_input(key='plan_qty_Appliance4').set_value(2).run()
            self.assertFalse(app.exception)
            self.assertTrue(any(m.label=='선택한 가전 예상 추가요금 합계' and m.value=='40.00원' for m in app.metric))
            app.multiselect(key='plan_devices').set_value([]).run()
            self.assertFalse(app.exception)
            app.button(key='verification_run').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state.verification_result['predicted_wh'], 200)


if __name__ == '__main__':
    unittest.main()
