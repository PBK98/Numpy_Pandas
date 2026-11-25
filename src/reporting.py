"""재현 가능한 분석 표·차트·민감도 결과를 생성한다."""
import os
import logging
logging.getLogger('matplotlib').setLevel(logging.ERROR)
import tempfile
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'ecommerce-matplotlib'))
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from src.pipeline import DataAnalyzer, ROOT

SEGMENTS = ['VIP', 'Loyal', 'New', 'At_Risk', 'Other']


def rfm_for_frame(frame, reference):
    grouped = frame.groupby('customer_id').agg(last_order=('order_date_parsed','max'),
        Frequency=('order_id','nunique'), Monetary=('amount_estimated_usd','sum'))
    grouped['Recency'] = (reference - grouped.pop('last_order')).dt.days
    return DataAnalyzer.score_rfm(grouped.reset_index())


def sensitivity(analyzer, eligible):
    """같은 거래 집합·금액·기준일에서 날짜 해석만 바꾼다. 보류 거래는 복구하지 않는다."""
    frames = {'country_policy': eligible.copy()}
    for label in ['all_mdy', 'all_dmy', 'separator_policy']:
        alt = eligible.copy()
        mask = alt.date_country_assumption_used
        if label == 'all_mdy':
            candidate = alt.candidate_mdy
        elif label == 'all_dmy':
            candidate = alt.candidate_dmy
        else:
            candidate = alt.candidate_mdy.where(alt.Order_Date.str.contains('-', regex=False), alt.candidate_dmy)
        alt.loc[mask, 'order_date_parsed'] = candidate.loc[mask]
        frames[label] = alt
    reference = max(frame.order_date_parsed.max() for frame in frames.values())
    base = rfm_for_frame(frames['country_policy'], reference).set_index('customer_id')
    base_monthly = frames['country_policy'].groupby(frames['country_policy'].order_date_parsed.dt.to_period('M')).amount_estimated_usd.sum()
    results, transitions = [], []
    for label, frame in frames.items():
        scored = rfm_for_frame(frame, reference).set_index('customer_id').reindex(base.index)
        monthly = frame.groupby(frame.order_date_parsed.dt.to_period('M')).amount_estimated_usd.sum()
        delta = monthly.subtract(base_monthly, fill_value=0)
        changed = scored.segment.ne(base.segment)
        results.append({'scenario':label,'shared_reference_date':reference.strftime('%Y-%m-%d'),
            'transactions':len(frame),'customers':len(scored),'segment_changed':int(changed.sum()),
            'segment_changed_pct':float(changed.mean()*100),
            'recency_changed':int(scored.Recency.ne(base.Recency).sum()),
            'monthly_amount_l1_change_usd':float(delta.abs().sum()),
            'total_amount_usd':float(frame.amount_estimated_usd.sum())})
        t = pd.crosstab(base.segment,scored.segment,rownames=['country_segment'],colnames=['alternative_segment']).stack().rename('customers').reset_index()
        t.columns=['country_segment','alternative_segment','customers'];t['scenario']=label
        transitions.append(t)
    return pd.DataFrame(results), pd.concat(transitions,ignore_index=True)


def run_analysis(output_dir=ROOT/'output/analysis', processed_dir=ROOT/'dataset/processed'):
    out = Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    figures=out/'figures';figures.mkdir(exist_ok=True)
    analyzer=DataAnalyzer();analyzer.preprocess()
    image_features=analyzer.engineer_features()
    analyzer.save_results(processed_dir)
    d=analyzer.df
    eligible=d.loc[d.analysis_eligible].copy()
    if eligible.empty:
        raise ValueError('유효한 완료 구매가 없습니다.')
    rfm=analyzer.score_rfm(analyzer.calculate_rfm())
    reference=eligible.order_date_parsed.max()
    unambiguous_latest = d.loc[~d.date_country_assumption_used, 'order_date_parsed'].max()
    assumption_tail_rows = int(eligible.order_date_parsed.gt(unambiguous_latest).sum())
    checked_on = pd.Timestamp(json.loads((ROOT/'docs/data_source.json').read_text())['checked_on'])
    rfm=rfm.merge(eligible.groupby('customer_id').agg(
        imputed_orders=('discount_was_missing','sum'),
        imputed_amount_usd=('amount_estimated_usd',lambda x:x[eligible.loc[x.index,'discount_was_missing']].sum())),
        on='customer_id',validate='one_to_one')
    segment=rfm.groupby('segment').agg(customers=('customer_id','size'),
        recency_mean=('Recency','mean'),frequency_mean=('Frequency','mean'),
        monetary_mean=('Monetary','mean'),amount_usd=('Monetary','sum')).reindex(SEGMENTS).fillna(0)
    segment['customer_pct']=segment.customers/len(rfm)*100
    segment['amount_pct']=segment.amount_usd/segment.amount_usd.sum()*100
    cols=['quantity','unit_price_usd','discount_percent_filled','amount_estimated_usd',
          'product_name_length','image_mean','image_std']
    stats=eligible[cols].describe().T
    corr=eligible[cols].astype(float).corr()
    iqr_outliers=analyzer.detect_outliers('unit_price_usd', eligible_only=True)
    prices=eligible.unit_price_usd.astype(float)
    q1,q3=prices.quantile([.25,.75]);iqr=q3-q1
    clipped=prices.clip(q1-1.5*iqr,q3+1.5*iqr)
    monthly=eligible.groupby(eligible.order_date_parsed.dt.to_period('M')).amount_estimated_usd.sum()
    monthly=monthly.reindex(pd.period_range(monthly.index.min(),monthly.index.max(),freq='M'),fill_value=0)
    monthly.index=monthly.index.astype(str)
    date_sensitivity,transitions=sensitivity(analyzer,eligible)
    gross_frame=eligible.copy();gross_frame['amount_estimated_usd']=gross_frame.amount_before_discount_usd
    gross_rfm=rfm_for_frame(gross_frame,reference).set_index('customer_id')
    primary=rfm.set_index('customer_id')
    monetary_changed=gross_rfm.segment.reindex(primary.index).ne(primary.segment)
    review=analyzer.review_required
    review_counts=review.groupby(['column','reason']).size().rename('items').reset_index()
    # 전후 표의 단위는 각각 명시한다. 제거 전과 제거 후 분모가 다르다.
    before_after=pd.DataFrame([
        ['rows',len(analyzer.raw),len(d)],
        ['missing_discount',int(analyzer.raw.Discount_Percent.isna().sum()),int(d.discount_percent_filled.isna().sum())],
        ['missing_city',int(analyzer.raw.Shipping_City.isna().sum()),int(d.shipping_city.isna().sum())],
        ['missing_rating',int(analyzer.raw.Customer_Rating.isna().sum()),int(d.customer_rating.isna().sum())],
    ],columns=['metric','raw_rows_basis','deduplicated_rows_basis'])
    result={'reference_date':reference.strftime('%Y-%m-%d'),
        'latest_unambiguous_date':unambiguous_latest.strftime('%Y-%m-%d'),
        'reference_extension_days':int((reference-unambiguous_latest).days),
        'assumption_only_tail_rows':assumption_tail_rows,
        'source_checked_on':checked_on.strftime('%Y-%m-%d'),
        'reference_after_source_check':bool(reference > checked_on),
        'eligible_transactions':len(eligible),'customers':len(rfm),
        'estimated_amount_usd':float(eligible.amount_estimated_usd.sum()),
        'iqr_price_outliers':len(iqr_outliers),'iqr_price_lower':float(q1-1.5*iqr),
        'iqr_price_upper':float(q3+1.5*iqr),
        'price_mean_before':float(prices.mean()),'price_mean_clipped':float(clipped.mean()),
        'monetary_definition_segment_changed':int(monetary_changed.sum()),
        'monetary_definition_segment_changed_pct':float(monetary_changed.mean()*100),
        'eligible_discount_imputed':int(eligible.discount_was_missing.sum()),
        'excluded_customers':int(d.customer_id.nunique()-len(rfm)),
        'image_features_complete':bool(d.image_mean.notna().all() and d.image_std.notna().all()),
        'dates_review_held':int(d.date_needs_review.sum()),
        'date_sensitivity_same_transactions':True}
    tables={'image_features':image_features,'rfm_customers':rfm,
        'rfm_segments':segment.reset_index(),'descriptive_statistics':stats.reset_index(names='variable'),
        'correlations':corr.reset_index(names='variable'),'date_sensitivity':date_sensitivity,
        'segment_transitions':transitions,'review_summary':review_counts,'before_after':before_after,
        'monthly_estimated_amount':monthly.rename_axis('month').rename('amount_usd').reset_index()}
    for name,table in tables.items():table.to_csv(out/f'{name}.csv',index=False)
    (out/'analysis_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    sns.set_theme(style='whitegrid')
    def save(name):
        plt.tight_layout();plt.savefig(figures/f'{name}.png',dpi=140);plt.close()
    plt.figure(figsize=(8,4));plt.hist(prices,bins=35,color='#386cb0')
    plt.title('Unit price distribution: eligible purchases');plt.xlabel('Unit price (USD)');plt.ylabel('Transaction rows');save('01_histogram')
    plt.figure(figsize=(8,4));plt.boxplot([prices,clipped],tick_labels=['Original valid prices','IQR-clipped (EDA only)'])
    plt.title('IQR treatment comparison (not used for RFM)');plt.xlabel('Price series');plt.ylabel('Unit price (USD)');save('02_boxplot')
    plt.figure(figsize=(8,4));plt.bar(segment.index,segment.customers,color='#386cb0')
    plt.title('Customers by RFM segment');plt.xlabel('Segment');plt.ylabel('Customers');save('03_bar')
    plt.figure(figsize=(10,7));sns.heatmap(corr,annot=True,fmt='.2f',cmap='vlag',vmin=-1,vmax=1)
    plt.title('Pearson correlations: eligible purchases');plt.xlabel('Variable');plt.ylabel('Variable');save('04_heatmap')
    plt.figure(figsize=(8,4));plt.scatter(rfm.Frequency,rfm.Monetary,alpha=.35,s=14)
    plt.title('Customer purchase frequency and estimated value');plt.xlabel('Unique completed orders');plt.ylabel('Estimated total amount (USD)');save('05_scatter')
    plt.figure(figsize=(10,4));plt.plot(monthly.index,monthly.values,marker='o',markersize=3)
    last_confirmed_month = str(unambiguous_latest.to_period('M'))
    confirmed_position = monthly.index.get_loc(last_confirmed_month)
    if confirmed_position < len(monthly)-1:
        plt.axvspan(confirmed_position+.5,len(monthly)-.5,color='#d95f02',alpha=.15,
                    label='Country-assumed dates only')
        plt.axvline(confirmed_position+.5,color='#d95f02',linestyle='--')
        plt.legend(fontsize=9)
    plt.xticks(rotation=60);plt.title('Monthly estimated completed-purchase amount');plt.xlabel('Month (country date assumption)');plt.ylabel('Estimated amount (USD)');save('06_line')
    plt.figure(figsize=(8,4));plt.bar(date_sensitivity.scenario,date_sensitivity.segment_changed_pct,color='#d95f02')
    plt.title('Date interpretation sensitivity: same transaction cohort');plt.xlabel('Alternative date scenario');plt.ylabel('Customers changing segment (%)');plt.xticks(rotation=15);save('07_sensitivity')
    vip, risk, new = segment.loc['VIP'], segment.loc['At_Risk'], segment.loc['New']
    findings = f"""# 이커머스 상품·고객 분석 결과

## 분석 범위

원본 {len(analyzer.raw):,}행 → 정제 {len(d):,}행 → 유효 완료 구매 {len(eligible):,}행, 고객 {len(rfm):,}명.
대상 추정 금액은 {result['estimated_amount_usd']:,.2f} USD이며, RFM 기준일은 {result['reference_date']}이다.
모호하지 않은 날짜의 최대일은 {result['latest_unambiguous_date']}다. 국가 가정 때문에 기준일이 {result['reference_extension_days']}일 확장됐다.
이 최대일 이후 거래 {assumption_tail_rows}행과 차트 음영 구간은 국가 가정으로 해석한 날짜에서만 나온다. 실제 매출 급감이나 미래 완료 구매의 증거가 아니다.
출처 확인일 {result['source_checked_on']}보다도 기준일이 늦다. Recency 절댓값은 가정한 기준일의 영향을 받으며 실제 미구매 기간으로 단정하지 않는다.
거래는 Kaggle의 합성 학습 데이터(CC0), 이미지는 AI 생성 대표 스케치다.
출처: [Kaggle](https://www.kaggle.com/datasets/afaqkhan091/messy-e-commerce-sales-dataset-2026).
확인 필요 거래 {analyzer.summary['review_rows']:,}행의 항목은 원본을 유지한 채 별도 CSV에 남겼다.

## 통계와 IQR

- 단가 평균 {prices.mean():.2f}, 중앙값 {prices.median():.2f}, 표준편차 {prices.std():.2f} USD.
- 단가 사분위수: Q1 {q1:.2f}, Q3 {q3:.2f} USD. 평균·중앙값과 분포를 함께 보아 고가 관측값의 영향을 검토한다.
- IQR 이상치 {len(iqr_outliers)}행({len(iqr_outliers)/len(eligible)*100:.2f}%). EDA용 클리핑 시 평균 {clipped.mean():.2f} USD.
- 고가의 정상 구매를 삭제하지 않도록 RFM은 원래 유효 금액을 유지한다.
- 단가/금액 Pearson r={corr.loc['unit_price_usd','amount_estimated_usd']:.3f}, 수량/금액 r={corr.loc['quantity','amount_estimated_usd']:.3f}.
  두 관계는 금액 산식에 포함된 변수 간 관계로, 독립적인 인과효과를 뜻하지 않는다.
- 이미지 평균/표준편차 r={corr.loc['image_mean','image_std']:.3f}. 합성 선화의 구조이며 실제 상품 수요의 근거가 아니다.

## RFM과 실행 가설

R은 역방향 평균 백분위 순위×4의 올림, F는 구매횟수 1/2/3/4회 이상, M은 금액 평균 백분위 순위×4의 올림이다.
동점 점수는 같으며 그룹 크기를 강제로 같게 만들지 않는다.
우선순위: VIP(R≥3,F≥3,M≥3) → Loyal(F≥3) → New(R≥3,F=1) → At_Risk(R≤2,F≥2) → Other.
R은 상대 순위이며 실제 최근 30일을 뜻하지 않는다. New는 관측 기간의 단일 구매 고객, At_Risk는 이탈 가설이다.

1. **VIP 유지 실험**
   - 근거: {int(vip.customers)}명({vip.customer_pct:.2f}%)이 추정 금액의 {vip.amount_pct:.2f}%를 차지한다.
   - 실행: VIP에 우선 상담·혜택을 무작위 시험해 재구매율 유지·증대를 목표로 한다.
   - 검증: 원가·혜택 비용·후속 구매 데이터가 필요하다. 대조군 대비 이익 개선이 없으면 제안을 기각한다.
2. **이탈 위험 가설의 재구매 유도**
   - 근거: At_Risk {int(risk.customers)}명({risk.customer_pct:.2f}%)의 평균 Recency는 가정 기준일에서 {risk.recency_mean:.1f}일이다. 기준일 연장 영향을 포함하므로 확정된 미구매 기간이 아니다.
   - 실행: 해당 고객에 재입고 안내·혜택을 무작위 시험해 재구매 반응 증대를 목표로 한다.
   - 검증: 날짜 원본·수신 동의·발송 이력·원가가 필요하다. 날짜 재해석이나 자연 재구매로 설명되면 가설을 재검토한다.
3. **단일 구매 고객의 두 번째 구매 실험**
   - 근거: New {int(new.customers)}명({new.customer_pct:.2f}%)의 완료 주문은 1회, 평균 추정 금액은 {new.monetary_mean:.2f} USD다.
   - 실행: 구매 상품 관련 안내를 시험해 두 번째 구매 전환율 증가를 목표로 한다.
   - 검증: 가입일·과거 기간 구매·구매 주기·후속 관측이 필요하다. 실제 신규가 아니거나 구매 주기가 길면 대상 선정이 틀릴 수 있다.

## 민감도와 한계

같은 거래 집합·같은 금액·공통 기준일 {date_sensitivity.shared_reference_date.iloc[0]}에서 날짜만 바꾸면,
최대 {date_sensitivity.segment_changed_pct.max():.2f}%의 고객이 그룹을 바꾼다.
공통 기준일은 시나리오 전체 최대 날짜로, 본 분석 기준일과 다를 수 있다.
국가 규칙 충돌 {result['dates_review_held']:,}행은 대안에서도 복구하지 않으므로 결과는 포함된 거래 집합에 한정된다.
할인 전 금액으로 정의를 바꾸면 {result['monetary_definition_segment_changed']}명({result['monetary_definition_segment_changed_pct']:.2f}%)의 그룹이 바뀐다.
이는 할인 대치 오차 자체의 추정이 아니라 금액 정의 민감도다.
월별 절대 변화 합은 실제 매출 손실을 뜻하지 않는다. 효과 크기·LTV·실제 이탈·인과성을 입증하지 않는다.

## 차트

![단가 분포](figures/01_histogram.png)
![IQR 비교](figures/02_boxplot.png)
![고객군](figures/03_bar.png)
![상관관계](figures/04_heatmap.png)
![빈도와 금액](figures/05_scatter.png)
![월별 추정 금액](figures/06_line.png)
![날짜 민감도](figures/07_sensitivity.png)
"""
    (out/'report.md').write_text(findings,encoding='utf-8')
    # 소수 고객·거래를 비교하는 참고 예시만 표시한다. 합성 이미지로 매출 원인을 주장하지 않는다.
    return {'analyzer':analyzer,'eligible':eligible,'rfm':rfm,'segment':segment,'stats':stats,
            'corr':corr,'before_after':before_after,'date_sensitivity':date_sensitivity,
            'summary':result,'monthly':monthly,'output_dir':out}
