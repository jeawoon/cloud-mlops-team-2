import json
import threading
import unittest
from http.server import HTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from api import Handler


class ApiTests(unittest.TestCase):
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

    def call(self, path, payload=None, raw=None):
        body = raw if raw is not None else json.dumps(payload).encode() if payload is not None else None
        request = Request(self.url+path, data=body, headers={'Content-Type':'application/json'})
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_health_catalog_and_docs(self):
        for path in ('/api/health', '/api/docs', '/api/laundry-cycle/catalog', '/api/device-forecast/catalog', '/api/verification-cases'):
            with self.subTest(path=path):
                status, body = self.call(path)
                self.assertEqual(status, 200)
                self.assertIsInstance(body, dict)

    def test_verification_live_route(self):
        status, body = self.call('/api/verification', {'case_id':'formula-tv'})
        self.assertEqual(status, 200)
        self.assertEqual(body['predicted_wh'], 200)
        self.assertEqual(body['predicted_cost_krw'], 40)

    def test_invalid_types_are_422_not_server_errors(self):
        for path, payload in [('/api/appliance-plan', {'plans':[{'device':[]}]}),
                              ('/api/device-forecast', {'device':{}}),
                              ('/api/laundry-cycle', {'machine':[]}),
                              ('/api/verification', {'case_id':{}}),
                              ('/api/appliance-plan', {'plans':[]})]:
            with self.subTest(path=path):
                self.assertEqual(self.call(path, payload)[0], 422)

    def test_malformed_and_oversized_json(self):
        self.assertEqual(self.call('/api/appliance-plan', raw=b'{broken')[0], 422)
        self.assertEqual(self.call('/api/appliance-plan', raw=b' '*16385)[0], 422)

    def test_retired_and_unknown_routes(self):
        for path in ('/api/whole-house', '/api/simulate', '/api/simulator/catalog'):
            self.assertEqual(self.call(path)[0], 410)
            self.assertEqual(self.call(path, {})[0], 410)
        self.assertEqual(self.call('/api/predict', {})[0], 404)


if __name__ == '__main__':
    unittest.main()
