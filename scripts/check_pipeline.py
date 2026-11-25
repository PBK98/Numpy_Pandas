"""실행: .venv/bin/python scripts/check_pipeline.py"""
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.pipeline import DataAnalyzer, COLUMNS, ROOT


class PipelineChecks(unittest.TestCase):
    def run_fixture(self, overrides):
        base = dict(zip(COLUMNS, ['O1','C1','2024-06-30','Books','Book','2','10','10',
                                 'Credit_Card','London','UK','Delivered','5']))
        records = [dict(base, **item) for item in overrides]
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / 'raw.csv'
        pd.DataFrame(records).to_csv(path, index=False)
        analyzer = DataAnalyzer(path)
        analyzer.preprocess()
        return analyzer, Path(temp.name)

    def test_dates_and_conflict_hold(self):
        values = [('11-09-2024','USA'), ('11-09-2024','UK'),
                  ('19/08/2025','USA'), ('05-05-2024','UK'),
                  ('2024-02-30','UK'), ('06/07/2024','unknown'),
                  ('17 Jun 2024','unknown'), ('not-a-date','UK')]
        a,_ = self.run_fixture([{'Order_ID':f'O{i}', 'Order_Date':date, 'Country':country}
                                for i,(date,country) in enumerate(values)])
        d=a.df
        self.assertEqual(d.date_parse_status.tolist(), ['country_assumed','country_assumed',
            'country_format_conflict','same_day_month','invalid_date',
            'ambiguous_country_unmapped','explicit','unsupported_format'])
        self.assertEqual(d.order_date_parsed.iloc[0],pd.Timestamp('2024-11-09'))
        self.assertEqual(d.order_date_parsed.iloc[1],pd.Timestamp('2024-09-11'))
        self.assertFalse(d.analysis_eligible.iloc[2])
        self.assertTrue(d.analysis_eligible.iloc[6])  # 날짜가 명확하면 국가 미등록이어도 날짜 분석 가능

    def test_missing_fallbacks_and_invalid_values(self):
        a,_ = self.run_fixture([
            {'Order_ID':'O0', 'Discount_Percent':'20'},
            {'Order_ID':'O1', 'Discount_Percent':'', 'Customer_Rating':'', 'Shipping_City':''},
            {'Order_ID':'O2', 'Product_Name':'Other', 'Discount_Percent':''},
            {'Order_ID':'O3', 'Product_Name':'New', 'Product_Category':'New', 'Discount_Percent':''},
            {'Order_ID':'O4', 'Discount_Percent':'150'},
            {'Order_ID':'O5', 'Quantity':'-1'},
            {'Order_ID':'O6', 'Unit_Price_USD':'inf'},
            {'Order_ID':'O7', 'Order_Status':'Cancelled'},
        ])
        d=a.df
        self.assertEqual(d.discount_fill_source.iloc[1:4].tolist(),
                         ['product_median','category_median','global_median'])
        self.assertTrue(pd.isna(d.customer_rating.iloc[1]))
        self.assertEqual(d.shipping_city.iloc[1],'Unknown')
        self.assertEqual(d.amount_estimated_usd.iloc[1],18)
        self.assertFalse(d.analysis_eligible.iloc[4:].any())

    def test_duplicate_rfm_save_and_repeated_run(self):
        a,folder=self.run_fixture([{}, {}, {'Order_ID':'O2','Order_Date':'2024-06-29'}])
        self.assertEqual(len(a.df),2)
        rfm=a.calculate_rfm()
        self.assertEqual(rfm.Frequency.iloc[0],2)
        self.assertEqual(rfm.Recency.iloc[0],0)
        self.assertEqual(rfm.Monetary.iloc[0],36)
        a.save_results(folder/'out')
        saved=pd.read_csv(folder/'out/transactions_cleaned.csv')
        self.assertEqual(saved.source_csv_row.tolist(),[2,4])
        self.assertTrue((folder/'out/review_required.csv').is_file())
        a.preprocess()
        self.assertEqual(len(a.df),2)
        with self.assertRaises(ValueError):a.save_results(folder)

    def test_empty_and_no_discount_evidence(self):
        a,_=self.run_fixture([{'Discount_Percent':''}])
        self.assertEqual(a.df.discount_fill_source.iloc[0],'unresolved')
        self.assertFalse(a.df.analysis_eligible.iloc[0])
        self.assertTrue(a.calculate_rfm().empty)
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'empty.csv'
            pd.DataFrame(columns=COLUMNS).to_csv(p,index=False)
            with self.assertRaises(ValueError):DataAnalyzer(p).preprocess()

    def test_review_export_and_summary(self):
        a,folder=self.run_fixture([
            {'Order_ID':'O0', 'Order_Date':'19/08/2025', 'Country':'USA'},
            {'Order_ID':'O1', 'Order_Date':'   '},
            {'Order_ID':'O2', 'Country':'unknown', 'Payment_Method':'unknown'},
            {'Order_ID':'O3', 'Customer_ID':'C1'},
            {'Order_ID':'O3', 'Customer_ID':''},
            {'Order_ID':'O4', 'Order_Status':'Unknown'},
        ])
        self.assertTrue(a.df.analysis_eligible.iloc[2])
        self.assertTrue(a.df.order_customer_conflict.iloc[3:5].all())
        self.assertFalse(a.df.analysis_eligible.iloc[3:5].any())
        self.assertEqual(a.df.date_parse_status.iloc[1],'missing_date')
        a.save_results(folder/'output')
        r=pd.read_csv(folder/'output/review_required.csv')
        conflict=r[r.reason.eq('country_format_conflict')].iloc[0]
        self.assertEqual(conflict.candidate_dmy,'2025-08-19')
        self.assertTrue(pd.isna(conflict.candidate_mdy))
        self.assertTrue(r.loc[r.reason.eq('missing_identifier_or_product'),'country_normalized'].notna().all())
        counts=a.summary['eligible_rows_by_order_status']
        self.assertEqual(sum(v['size'] for v in counts.values()),len(a.df))
        self.assertIn('unmapped',counts)
        self.assertEqual(a.summary['date_status_counts']['missing_date'],1)

    def test_iqr_finite_values_and_cli(self):
        a,folder=self.run_fixture([{'Order_ID':f'O{i}', 'Unit_Price_USD':v}
                                   for i,v in enumerate(['10','10','10','10','1000','inf','-2'])])
        self.assertEqual(a.detect_outliers('Unit_Price_USD').unit_price_usd.tolist(),[1000])
        a.df['empty_numeric']=float('inf')
        self.assertTrue(a.detect_outliers('empty_numeric').empty)
        import subprocess
        result=subprocess.run([sys.executable,str(ROOT/'src/pipeline.py'),
            '--input',str(a.data_path),'--output-dir',str(folder/'cli')],
            capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue((folder/'cli/transactions_cleaned.csv').is_file())

    def test_real_data_invariants(self):
        path=ROOT/'dataset/raw/csv/ecommerce_retail_transactions_raw.csv'
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        a=DataAnalyzer(path);d=a.preprocess()
        self.assertEqual(len(d)+a.summary['duplicates_removed'],len(a.raw))
        self.assertFalse(d.loc[d.date_needs_review,'analysis_eligible'].any())
        self.assertTrue(d.loc[d.analysis_eligible,'order_status'].eq('Delivered').all())
        self.assertTrue(d.loc[d.analysis_eligible,'amount_estimated_usd'].notna().all())
        self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertTrue(set(a.review_required.source_csv_row).issubset(set(d.source_csv_row)))


if __name__=='__main__':unittest.main()
