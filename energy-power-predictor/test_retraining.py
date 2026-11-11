import unittest
import pandas as pd
from sklearn.dummy import DummyRegressor
from retrain_larco import split_cycles, select_candidate


class RetrainingTests(unittest.TestCase):
    def rows(self):
        return pd.DataFrame([dict(environment='laboratory',type='wm',machine='fixture-machine',
                                 file_path=f'fixture-{i}',timestamp=f'2026-01-{i//24+1:02d}T{i%24:02d}:00:00Z',
                                 program_name='cold',program_heat='0',ambient_temp=25,target_load=2,
                                 total_energy_consumed_wh=10,cycle_duration=60) for i in range(40)])

    def test_complete_cycles_temporal_disjoint_and_invalid_labels_excluded(self):
        raw=self.rows();raw.loc[0,'total_energy_consumed_wh']=0
        train,valid,test=split_cycles(pd.concat([raw,raw.iloc[[5]]]))
        self.assertEqual(sum(map(len,(train,valid,test))),39)
        self.assertFalse(set(train.file_path)&set(test.file_path))
        self.assertFalse(set(valid.file_path)&set(test.file_path))
        self.assertLess(train.timestamp.max(),valid.timestamp.min())
        self.assertLess(valid.timestamp.max(),test.timestamp.min())

    def test_selection_only_accepts_train_and_validation(self):
        train=self.rows().iloc[:24];valid=self.rows().iloc[24:32]
        models={'correct':DummyRegressor(strategy='constant',constant=10),
                'wrong':DummyRegressor(strategy='constant',constant=100)}
        chosen,reports=select_candidate(models,train,valid)
        self.assertEqual(chosen,'correct')
        self.assertEqual(reports[chosen]['mae'],0)


if __name__=='__main__':unittest.main()
