"""전체 분석 실행과 분류·집계·민감도·피처 연결을 검증한다."""
import sys
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.pipeline import DataAnalyzer
from src.reporting import run_analysis


class AnalysisChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.report=run_analysis(Path(cls.temp.name)/'analysis', processed_dir=Path(cls.temp.name)/'processed')

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_segment_partition_and_score_ties(self):
        r=self.report['rfm']
        self.assertGreaterEqual(r.segment.nunique(),4)
        self.assertEqual(int(self.report['segment'].customers.sum()),len(r))
        self.assertTrue(r[['R_score','F_score','M_score']].ge(1).all().all())
        self.assertTrue(r[['R_score','F_score','M_score']].le(4).all().all())
        toy=pd.DataFrame({'customer_id':['a','b','c'],'Recency':[5,5,30],
                          'Frequency':[1,1,4],'Monetary':[10.,10.,100.]})
        one=DataAnalyzer.score_rfm(toy).set_index('customer_id').sort_index()
        two=DataAnalyzer.score_rfm(toy.iloc[::-1]).set_index('customer_id').sort_index()
        pd.testing.assert_frame_equal(one,two)
        self.assertEqual(one.loc['a','R_score'],one.loc['b','R_score'])
        self.assertEqual(one.loc['a','M_score'],one.loc['b','M_score'])

    def test_amount_conservation(self):
        r=self.report
        self.assertAlmostEqual(float(r['rfm'].Monetary.sum()),float(r['eligible'].amount_estimated_usd.sum()),places=6)
        self.assertAlmostEqual(float(r['monthly'].sum()),float(r['rfm'].Monetary.sum()),places=6)
        self.assertAlmostEqual(float(r['segment'].customer_pct.sum()),100.)

    def test_sensitivity_same_cohort_and_baseline(self):
        s=self.report['date_sensitivity']
        self.assertEqual(s.transactions.nunique(),1)
        summary=self.report['summary']
        self.assertEqual(summary['latest_unambiguous_date'],'2026-06-30')
        self.assertGreater(summary['reference_extension_days'],0)
        self.assertEqual(s.customers.nunique(),1)
        self.assertEqual(s.shared_reference_date.nunique(),1)
        self.assertTrue(np.allclose(s.total_amount_usd,s.total_amount_usd.iloc[0]))
        base=s[s.scenario.eq('country_policy')].iloc[0]
        self.assertEqual(base.segment_changed,0)
        self.assertEqual(base.monthly_amount_l1_change_usd,0)

    def test_image_text_features_complete_and_shared(self):
        d=self.report['analyzer'].df
        self.assertTrue(d[['image_mean','image_std','product_name_length','product_word_count']].notna().all().all())
        self.assertTrue(d.image_mean.between(0,1).all())
        self.assertTrue(d.image_std.between(0,.5).all())
        self.assertTrue(d.groupby('product_name').image_mean.nunique().eq(1).all())
        self.assertTrue(d.product_name_length.eq(d.product_name.str.len()).all())

    def test_artifacts_and_original_values_kept(self):
        out=self.report['output_dir']
        self.assertEqual(len(list((out/'figures').glob('*.png'))),7)
        for name in ['report.md','rfm_customers.csv','rfm_segments.csv','date_sensitivity.csv']:
            self.assertTrue((out/name).is_file(),name)
        a=self.report['analyzer']
        pd.testing.assert_frame_equal(a.df[a.raw.columns],a.raw.loc[a.df.index],check_dtype=True)


if __name__=='__main__':unittest.main()
