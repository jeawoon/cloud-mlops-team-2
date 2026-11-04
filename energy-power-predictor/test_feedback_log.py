import json,os,tempfile,unittest
from unittest.mock import patch
from src.history_store import handle,connect
from api import predict
class FeedbackTests(unittest.TestCase):
    def test_pending_actual_price_and_delete(self):
        from src.verification import load_cases
        payload=next(c['payload'] for c in load_cases()['cases'] if c['id']=='formula-tv')
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'ENERGY_HISTORY_DB':tmp+'/history.sqlite3'}),patch('src.feedback_log.export'):
            auth={'owner_token':'a'*40}
            record=handle('save',dict(auth,consent=True,prediction_payload=payload,label='private label'),predict)['id']
            with connect() as db:saved=json.loads(db.execute('SELECT event_json FROM feedback_events').fetchone()[0])
            self.assertEqual(saved['status'],'pending_actual');self.assertIsNone(saved['assessment'])
            self.assertNotIn('private label',json.dumps(saved));self.assertNotIn('a'*40,json.dumps(saved))
            handle('actual',dict(auth,id=record,actual_wh=200,actual_cost_krw=40,scope_confirmed=True),predict)
            rows=handle('list',auth,predict)['records']
            self.assertTrue(rows[0]['evaluation']['price_within_tolerance']);self.assertTrue(rows[0]['evaluation']['energy_within_tolerance'])
            handle('actual',dict(auth,id=record,actual_wh=400,actual_cost_krw=80,scope_confirmed=True),predict)
            self.assertFalse(handle('list',auth,predict)['records'][0]['evaluation']['price_within_tolerance'])
            handle('delete',dict(auth,id=record,confirm_delete=True),predict)
            with connect() as db:events=[json.loads(x[0]) for x in db.execute('SELECT event_json FROM feedback_events ORDER BY rowid')]
            self.assertEqual(events[-1]['status'],'deleted');self.assertEqual(len(events),4)
            self.assertTrue(all(e['prediction_id']==record for e in events))
