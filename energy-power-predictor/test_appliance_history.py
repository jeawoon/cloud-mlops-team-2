"""Feature timing and saved-model inference smoke tests."""
import unittest
import numpy as np
import pandas as pd
from train_appliance_history import CHANNELS, build_features, predict_appliance_history


class ApplianceHistoryTests(unittest.TestCase):
    def setUp(self):
        idx = pd.date_range('2026-01-01', periods=1100, freq='10min')
        self.data = pd.DataFrame({c:np.full(1100, 5.) for c in ['Aggregate']+CHANNELS}, index=idx)

    def test_no_future_features(self):
        frame, baseline = build_features(self.data, 5)
        changed = self.data.copy()
        changed.iloc[1051:] = 999
        modified, _ = build_features(changed, 5)
        pd.testing.assert_frame_equal(frame.iloc[:1051], modified.iloc[:1051])
        self.assertEqual(len(baseline), 31)
        self.assertEqual(len(frame.columns), 76)

    def test_missing_not_off(self):
        self.data.loc[self.data.index[-1], 'Appliance1'] = np.nan
        frame, _ = build_features(self.data, 5)
        self.assertTrue(np.isnan(frame.iloc[-1].Appliance1_active))

    def test_activity_boundary(self):
        self.data['Appliance1'] = 20/6
        self.data['Appliance2'] = 21/6
        frame, _ = build_features(self.data, 5)
        self.assertEqual(frame.iloc[-1].Appliance1_active, 0)
        self.assertEqual(frame.iloc[-1].Appliance2_active, 1)

    def test_inference(self):
        for house in ('CLEAN_House11', 'CLEAN_House2'):
            for minutes in (10, 60):
                self.assertTrue(np.isfinite(predict_appliance_history(self.data, house, minutes)))

    def test_short_history_rejected(self):
        with self.assertRaises(ValueError):
            predict_appliance_history(self.data.iloc[-6:], 'CLEAN_House11')


if __name__ == '__main__':
    unittest.main()
