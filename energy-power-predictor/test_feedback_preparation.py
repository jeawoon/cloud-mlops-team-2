import copy
import json
import unittest
from prepare_feedback_training import prepare


class PreparationTests(unittest.TestCase):
    def sample(self):
        # Synthetic fixture only; never production training data.
        return dict(event_id='test-1', prediction_id='test-record', occurred_at='2026-11-11T01:10:00+00:00',
                    event_type='actual_recorded', status='evaluated', target={'actual_wh':10},
                    inputs={'plans':[dict(device='Appliance1', method='recent_forecast', quantity=1,
                                         settings=dict(recent_wh=[10]*6, hour=10, minute=0, weekday=2))]})

    def review(self):
        return {'test-1':dict(approved=True, measurement_verified=True, scope_verified=True,
                             household_group='test-house', forecast_at='2026-11-11T10:00:00+09:00')}

    def test_operational_logs_are_not_labels(self):
        rows, report=prepare([json.dumps({'message':json.dumps({'record_type':'container_output','message':'status=200'})}), 'bad'])
        self.assertEqual(rows, [])
        self.assertEqual(report['operational_or_other'],1)
        self.assertEqual(report['invalid_or_non_json'],1)

    def test_requires_explicit_quality_review(self):
        rows, report=prepare([json.dumps(self.sample())])
        self.assertEqual(rows, [])
        self.assertEqual(report['quality_review_required'],1)

    def test_deduplicates_and_respects_later_deletion_out_of_order(self):
        value=self.sample()
        deleted=dict(event_id='test-2', prediction_id='test-record', occurred_at='2026-11-11T01:11:00+00:00',event_type='record_deleted',status='deleted')
        rows, report=prepare([json.dumps(v) for v in (deleted,value,value)],self.review())
        self.assertEqual(rows, [])
        self.assertEqual(report['deleted_records'],1)
        self.assertEqual(report['duplicate_events'],1)

    def test_reviewed_single_appliance_only_and_target_not_features(self):
        value=self.sample()
        rows, _=prepare([json.dumps({'message':json.dumps(value)})],self.review())
        self.assertEqual(len(rows),1)
        self.assertNotIn('prediction',rows[0])
        mixed=copy.deepcopy(value);mixed['inputs']['plans']*=2
        rows, report=prepare([json.dumps(mixed)],self.review())
        self.assertEqual(rows,[])
        self.assertEqual(report['unsupported_scope'],1)

    def test_nan_target_rejected(self):
        value=self.sample();value['target']['actual_wh']=float('nan')
        self.assertEqual(prepare([json.dumps(value)],self.review())[0],[])

    def test_malformed_nested_data_is_excluded(self):
        for field in ('target','inputs'):
            value=self.sample();value[field]=None
            self.assertEqual(prepare([json.dumps(value)],self.review())[0],[])


if __name__=='__main__':unittest.main()
