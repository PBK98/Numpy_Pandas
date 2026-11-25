"""합의된 기준으로 전처리하고 CSV/집계 JSON을 저장한다.

실행: .venv/bin/python src/pipeline.py
원본 컬럼은 보존하고 정제값은 소문자 파생 컬럼에 기록한다.
"""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = ['Order_ID', 'Customer_ID', 'Order_Date', 'Product_Category',
           'Product_Name', 'Quantity', 'Unit_Price_USD', 'Discount_Percent',
           'Payment_Method', 'Shipping_City', 'Country', 'Order_Status', 'Customer_Rating']
REVIEW_COLUMNS = ['source_csv_row', 'Order_ID', 'column', 'original_value',
                  'reason', 'country_normalized', 'candidate_mdy', 'candidate_dmy']
COUNTRIES = {'usa': 'USA', 'us': 'USA', 'unitedstates': 'USA',
             'uk': 'UK', 'unitedkingdom': 'UK', 'ca': 'Canada', 'canada': 'Canada',
             'au': 'Australia', 'australia': 'Australia', 'de': 'Germany', 'germany': 'Germany',
             'in': 'India', 'india': 'India', 'uae': 'UAE'}
PAYMENTS = {'creditcard': 'CREDIT_Card', 'debitcard': 'DEBIT_CARD',
            'netbanking': 'NET_BANKING', 'paypal': 'PAYPAL',
            'cashondelivery': 'COD', 'cod': 'COD', 'upi': 'UPI'}


def key(series):
    return series.str.lower().str.replace(r'[^a-z0-9]', '', regex=True)


class DataAnalyzer:
    def __init__(self, data_path=ROOT / 'dataset/raw/csv/ecommerce_retail_transactions_raw.csv'):
        self.data_path = Path(data_path)
        self.df = None
        self.raw = None
        self._issues = []
        self.summary = {}

    def load_data(self):
        self.raw = pd.read_csv(self.data_path, dtype='string', skip_blank_lines=False)
        missing = set(COLUMNS) - set(self.raw.columns)
        if missing:
            raise ValueError(f'필수 컬럼 누락: {sorted(missing)}')
        if self.raw.empty:
            raise ValueError('거래 데이터가 비어 있습니다.')
        self.df = self.raw.copy()
        self._issues = []
        self.summary = {'input_rows': len(self.raw)}
        return self.df

    def _record(self, mask, column, reason):
        mask = mask.fillna(False)
        if not mask.any():
            return
        d = self.df
        result = pd.DataFrame(index=d.index[mask])
        for col in ['source_csv_row', 'Order_ID', 'country_normalized', 'candidate_mdy', 'candidate_dmy']:
            result[col] = d.loc[mask, col] if col in d else pd.NA
        result['column'] = column
        result['original_value'] = d.loc[mask, column] if column in d else pd.NA
        result['reason'] = reason
        self._issues.append(result[REVIEW_COLUMNS])

    def normalize(self):
        # 원본 셀 값은 남기고 공백 정리용 복사본으로 중복을 판정한다.
        clean = self.df.apply(lambda s: s.str.strip()).replace('', pd.NA)
        duplicate = clean.duplicated()
        self.summary['duplicates_removed'] = int(duplicate.sum())
        self.df = self.df.loc[~duplicate].copy()
        clean = clean.loc[~duplicate]
        d = self.df
        d['source_csv_row'] = d.index + 2  # 헤더 포함 CSV 레코드 번호
        for original, target in [('Order_ID', 'order_id'), ('Customer_ID', 'customer_id'),
                                 ('Product_Name', 'product_name'), ('Product_Category', 'category')]:
            d[target] = clean[original]
        d['country_normalized'] = key(clean['Country']).map(COUNTRIES).astype('string')
        for original, target in [('Order_ID', 'order_id'), ('Customer_ID', 'customer_id'),
                                 ('Product_Name', 'product_name'), ('Product_Category', 'category')]:
            self._record(d[target].isna(), original, 'missing_identifier_or_product')
        d['payment_normalized'] = key(clean['Payment_Method']).map(PAYMENTS).astype('string')
        d['order_status'] = clean['Order_Status'].str.lower().map(
            {s.lower(): s for s in ['Delivered', 'Cancelled', 'Returned', 'Pending', 'Shipped']}).astype('string')
        for raw, col in [('Country', 'country_normalized'), ('Payment_Method', 'payment_normalized'),
                         ('Order_Status', 'order_status')]:
            self._record(d[col].isna(), raw, 'missing_or_unmapped')
        conflicts = d.groupby('order_id')['customer_id'].transform(lambda s: s.nunique(dropna=False)).gt(1)
        d['order_customer_conflict'] = conflicts.fillna(False)
        self._record(conflicts, 'Order_ID', 'order_customer_conflict')

    def parse_dates(self):
        d = self.df
        s = d['Order_Date'].str.strip().replace('', pd.NA)
        parsed = pd.Series(pd.NaT, index=d.index, dtype='datetime64[ns]')
        status = pd.Series('unsupported_format', index=d.index, dtype='string')
        status.loc[s.isna()] = 'missing_date'
        for pattern, fmt in [(r'\d{4}-\d{1,2}-\d{1,2}', '%Y-%m-%d'),
                             (r'\d{4}/\d{1,2}/\d{1,2}', '%Y/%m/%d'),
                             (r'\d{1,2} [A-Za-z]{3} \d{4}', '%d %b %Y')]:
            mask = s.str.fullmatch(pattern, na=False)
            candidate = pd.to_datetime(s.where(mask), format=fmt, errors='coerce')
            parsed.loc[mask] = candidate.loc[mask]
            status.loc[mask] = 'invalid_date'
            status.loc[mask & candidate.notna()] = 'explicit'
        mdy = pd.Series(pd.NaT, index=d.index, dtype='datetime64[ns]')
        dmy = mdy.copy()
        for sep in ['-', '/']:
            mask = s.str.fullmatch(r'\d{1,2}' + sep + r'\d{1,2}' + sep + r'\d{4}', na=False)
            mdy.loc[mask] = pd.to_datetime(s.where(mask), format=f'%m{sep}%d{sep}%Y', errors='coerce').loc[mask]
            dmy.loc[mask] = pd.to_datetime(s.where(mask), format=f'%d{sep}%m{sep}%Y', errors='coerce').loc[mask]
            status.loc[mask] = 'invalid_date'
        both = mdy.notna() & dmy.notna()
        same = both & mdy.eq(dmy)
        one = mdy.notna() ^ dmy.notna()
        ambiguous = both & ~same
        parsed.loc[same | one] = mdy.fillna(dmy).loc[same | one]
        status.loc[same] = 'same_day_month'
        status.loc[one] = 'unambiguous_numeric'
        us = d['country_normalized'].eq('USA').fillna(False)
        other = d['country_normalized'].isin(set(COUNTRIES.values()) - {'USA'})
        parsed.loc[ambiguous & us] = mdy.loc[ambiguous & us]
        parsed.loc[ambiguous & other] = dmy.loc[ambiguous & other]
        status.loc[ambiguous] = 'ambiguous_country_unmapped'
        assumed = ambiguous & (us | other)
        status.loc[assumed] = 'country_assumed'
        conflict = one & ((us & mdy.isna()) | (other & dmy.isna()))
        status.loc[conflict] = 'country_format_conflict'
        d['order_date_parsed'] = parsed
        d['candidate_mdy'], d['candidate_dmy'] = mdy, dmy
        d['date_parse_status'] = status
        d['date_country_assumption_used'] = assumed
        review_states = ['missing_date', 'invalid_date', 'unsupported_format',
                         'ambiguous_country_unmapped', 'country_format_conflict']
        d['date_needs_review'] = status.isin(review_states)
        numeric_mask = mdy.notna() | dmy.notna()
        patterns = pd.DataFrame({
            'country': d['country_normalized'].fillna('unmapped'),
            'separator': s.str.extract(r'^\d{1,2}([/-])\d{1,2}[/-]\d{4}$', expand=False),
            'interpretation': pd.Series('neither', index=d.index, dtype='string'),
        })
        patterns.loc[both, 'interpretation'] = 'both'
        patterns.loc[mdy.notna() & dmy.isna(), 'interpretation'] = 'mdy_only'
        patterns.loc[dmy.notna() & mdy.isna(), 'interpretation'] = 'dmy_only'
        self.summary['country_separator_date_patterns'] = (
            patterns.loc[numeric_mask].groupby(['country', 'separator', 'interpretation'])
            .size().rename('rows').reset_index().to_dict('records'))
        for reason in review_states:
            self._record(status.eq(reason), 'Order_Date', reason)

    def handle_missing_values(self, strategy='group_median', group_col='product_name'):
        if strategy != 'group_median':
            raise ValueError('합의된 할인율 대치 전략은 group_median입니다.')
        d = self.df
        if group_col not in d:
            raise ValueError(f'대치 그룹 컬럼 없음: {group_col}')
        d['city_was_missing'] = d['Shipping_City'].str.strip().replace('', pd.NA).isna()
        d['shipping_city'] = d['Shipping_City'].str.strip().replace('', pd.NA).fillna('Unknown')
        numeric_map = {'Quantity': 'quantity', 'Unit_Price_USD': 'unit_price_usd',
                       'Discount_Percent': 'discount_percent', 'Customer_Rating': 'customer_rating'}
        for original, col in numeric_map.items():
            text = d[original].str.strip().replace('', pd.NA)
            values = pd.to_numeric(text, errors='coerce').astype('Float64')
            finite = pd.Series(np.isfinite(values.to_numpy(dtype=float, na_value=np.nan)), index=d.index)
            values = values.where(finite)
            d[col] = values
            self._record(text.notna() & ~finite, original, 'non_numeric_or_non_finite')
        for original, col, valid in [
            ('Quantity', 'quantity', d['quantity'].gt(0) & d['quantity'].mod(1).eq(0)),
            ('Unit_Price_USD', 'unit_price_usd', d['unit_price_usd'].gt(0)),
            ('Discount_Percent', 'discount_percent', d['discount_percent'].between(0, 100)),
            ('Customer_Rating', 'customer_rating', d['customer_rating'].between(1, 5)),
        ]:
            self._record(d[col].notna() & ~valid.fillna(False), original, 'out_of_range')
            if col == 'customer_rating':
                d[col] = d[col].where(valid)
        for raw, col in [('Quantity', 'quantity'), ('Unit_Price_USD', 'unit_price_usd')]:
            self._record(d[raw].str.strip().replace('', pd.NA).isna(), raw, 'missing_numeric')
        missing = d['Discount_Percent'].str.strip().replace('', pd.NA).isna()
        d['discount_was_missing'] = missing
        observed = d['discount_percent'].where(d['discount_percent'].between(0, 100))
        filled = observed.copy()
        source = pd.Series('invalid', index=d.index, dtype='string')
        source.loc[observed.notna()] = 'observed'
        for label, estimates in [
            ('product_median', observed.groupby(d[group_col]).transform('median')),
            ('category_median', observed.groupby(d['category']).transform('median')),
            ('global_median', pd.Series(observed.median(), index=d.index, dtype='Float64')),
        ]:
            mask = missing & filled.isna() & estimates.notna()
            filled.loc[mask] = estimates.loc[mask]
            source.loc[mask] = label
        source.loc[missing & filled.isna()] = 'unresolved'
        d['discount_percent_filled'], d['discount_fill_source'] = filled, source
        self._record(missing & filled.isna(), 'Discount_Percent', 'discount_imputation_unresolved')

    def mark_analysis_eligibility(self):
        d = self.df
        valid_amount = (d['quantity'].gt(0) & d['quantity'].mod(1).eq(0)
                        & d['unit_price_usd'].gt(0) & d['discount_percent_filled'].between(0, 100)).fillna(False)
        gross = d['quantity'] * d['unit_price_usd']
        estimated = gross * (1 - d['discount_percent_filled'] / 100)
        finite = pd.Series(np.isfinite(estimated.to_numpy(dtype=float, na_value=np.nan)), index=d.index)
        self._record(valid_amount & ~finite, 'Unit_Price_USD', 'amount_overflow')
        d['amount_valid'] = valid_amount & finite
        d['amount_before_discount_usd'] = gross.where(d['amount_valid'])
        d['amount_estimated_usd'] = estimated.where(d['amount_valid'])
        d['analysis_eligible'] = (d['order_status'].eq('Delivered').fillna(False)
                                 & d['order_id'].notna() & d['customer_id'].notna()
                                 & ~d['order_customer_conflict'] & d['amount_valid']
                                 & d['order_date_parsed'].notna() & ~d['date_needs_review'])
        reasons = pd.Series('', index=d.index, dtype='string')
        for mask, reason in [
            (~d['order_status'].eq('Delivered').fillna(False), 'not_delivered'),
            (d['order_id'].isna() | d['customer_id'].isna(), 'missing_id'),
            (d['order_customer_conflict'], 'order_customer_conflict'),
            (~d['amount_valid'], 'invalid_amount'),
            (d['order_date_parsed'].isna() | d['date_needs_review'], 'date_review_required'),
        ]:
            reasons.loc[mask] += reason + ';'
        d['analysis_exclusion_reasons'] = reasons.str.rstrip(';')
        review = self.review_required
        d['row_needs_review'] = d['source_csv_row'].isin(review['source_csv_row'])

    @property
    def review_required(self):
        return (pd.concat(self._issues, ignore_index=True) if self._issues
                else pd.DataFrame(columns=REVIEW_COLUMNS))

    def detect_outliers(self, column, threshold=1.5, eligible_only=False):
        """IQR 이상치 행만 반환한다. 원본 행을 삭제하지 않는다."""
        if not np.isfinite(threshold) or threshold < 0:
            raise ValueError('threshold는 0 이상의 유한수여야 합니다.')
        values = pd.to_numeric(self.df[column], errors='coerce')
        finite = pd.Series(np.isfinite(values.to_numpy(dtype=float, na_value=np.nan)), index=values.index)
        valid = finite.copy()
        if column in ['quantity', 'Quantity']:
            valid &= values.gt(0) & values.mod(1).eq(0)
        elif column in ['unit_price_usd', 'Unit_Price_USD']:
            valid &= values.gt(0)
        elif column in ['discount_percent', 'discount_percent_filled', 'Discount_Percent']:
            valid &= values.between(0, 100)
        elif column in ['customer_rating', 'Customer_Rating']:
            valid &= values.between(1, 5)
        if eligible_only:
            valid &= self.df['analysis_eligible']
        values = values.where(valid.fillna(False))
        if values.notna().sum() == 0:
            return self.df.iloc[0:0].copy()
        q1, q3 = values.quantile([0.25, 0.75])
        iqr = q3 - q1
        return self.df.loc[values.lt(q1 - threshold * iqr) | values.gt(q3 + threshold * iqr)].copy()

    def calculate_rfm(self, reference_date=None):
        """분석 대상 거래의 R/F/M 원시 지표. 점수·세그먼트는 후속 단계."""
        d = self.df.loc[self.df['analysis_eligible']]
        if d.empty:
            return pd.DataFrame(columns=['customer_id', 'Recency', 'Frequency', 'Monetary'])
        reference = pd.Timestamp(reference_date) if reference_date is not None else d['order_date_parsed'].max()
        if pd.isna(reference) or reference < d['order_date_parsed'].max():
            raise ValueError('기준일은 유효한 최종 거래일 이상이어야 합니다.')
        rfm = d.groupby('customer_id').agg(last_order=('order_date_parsed', 'max'),
            Frequency=('order_id', 'nunique'), Monetary=('amount_estimated_usd', 'sum'))
        rfm['Recency'] = (reference - rfm.pop('last_order')).dt.days
        return rfm.reset_index()[['customer_id', 'Recency', 'Frequency', 'Monetary']]

    def preprocess(self):
        self.load_data()
        self.normalize()
        self.parse_dates()
        self.handle_missing_values()
        self.mark_analysis_eligibility()
        return self.df

    def save_results(self, output_dir=ROOT / 'dataset/processed'):
        if self.df is None or 'analysis_eligible' not in self.df:
            raise RuntimeError('preprocess()를 먼저 실행하세요.')
        out = Path(output_dir).resolve()
        raw_dir = (ROOT / 'dataset/raw').resolve()
        if out == raw_dir or raw_dir in out.parents or out == self.data_path.resolve().parent:
            raise ValueError('원본 디렉터리에 결과를 저장할 수 없습니다.')
        targets = [out / n for n in ['transactions_cleaned.csv', 'review_required.csv', 'preprocessing_summary.json']]
        if any(p.resolve() == self.data_path.resolve() for p in targets):
            raise ValueError('입력 파일을 덮어쓸 수 없습니다.')
        out.mkdir(parents=True, exist_ok=True)
        d = self.df
        self.summary.update({
            'cleaned_rows': len(d), 'review_items': len(self.review_required),
            'review_rows': int(d['row_needs_review'].sum()),
            'analysis_eligible_rows': int(d['analysis_eligible'].sum()),
            'analysis_excluded_rows': int((~d['analysis_eligible']).sum()),
            'analysis_eligible_customers': int(d.loc[d['analysis_eligible'], 'customer_id'].nunique()),
            'date_status_counts': {str(k): int(v) for k, v in d['date_parse_status'].value_counts().items()},
            'discount_fill_counts': {str(k): int(v) for k, v in d['discount_fill_source'].value_counts().items()},
            'city_filled_rows': int(d['city_was_missing'].sum()),
            'eligible_rows_by_order_status': d.groupby(d['order_status'].fillna('unmapped'))['analysis_eligible'].agg(['size','sum']).astype(int).to_dict('index'),
            'count_basis': '중복 제거 후 기준. review_items는 한 거래의 여러 확인 항목을 포함할 수 있음.',
            'date_policy': 'USA=MDY; UK/Canada/Australia/Germany/India/UAE=DMY; conflicts held for review',
        })
        d.to_csv(targets[0], index=False, date_format='%Y-%m-%d')
        self.review_required.to_csv(targets[1], index=False, date_format='%Y-%m-%d')
        targets[2].write_text(json.dumps(self.summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return targets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'dataset/raw/csv/ecommerce_retail_transactions_raw.csv')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dataset/processed')
    args = parser.parse_args()
    analyzer = DataAnalyzer(args.input)
    analyzer.preprocess()
    analyzer.save_results(args.output_dir)


if __name__ == '__main__':
    main()
