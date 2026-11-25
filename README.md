# 이커머스 상품·고객 분석

NumPy·Pandas로 혼합 형식의 거래 데이터를 정제하고 상품 이미지·텍스트 피처, 탐색적 분석, RFM 고객 세분화와 실행 가설을 구성한 학습 프로젝트입니다.

**기본 탐색부터 전처리, 피처 생성, 통계·시각화, 고객군, 민감도 분석과 리포트까지 구현했습니다.** 거래와 대표 이미지는 합성 데이터이므로 실제 고객의 이탈이나 마케팅 효과를 입증하는 결과가 아닙니다.

- [전체 분석 노트북](notebooks/analysis_report.ipynb): 단계별 코드·출력·한국어 설명
- [분석 보고서](output/analysis/report.md): 주요 결과·차트·비즈니스 제안
- [전처리 기준](docs/preprocessing_policy.md): 사용자 합의 규칙과 보류 기준

## 데이터·출처·라이선스

- 데이터: [Messy E-Commerce Sales Dataset 2026 — AfaqKhan](https://www.kaggle.com/datasets/afaqkhan091/messy-e-commerce-sales-dataset-2026)
- 제공자 공개 메타데이터 기준 **합성 학습 데이터**, **CC0: Public Domain**. [메타데이터 API](https://www.kaggle.com/api/v1/datasets/view/afaqkhan091/messy-e-commerce-sales-dataset-2026)에서 2026-11-25 확인.
- 원본은 12,180행·13컬럼, 고유 고객 3,374명·상품명 46개입니다. 주문 ID 중복이 있어 행 수와 고유 주문 수를 구분합니다.
- 날짜·카테고리 표기 차이, 결측치, 중복·수량 오류가 의도적으로 포함된 데이터입니다.
- [출처 기록과 원본 SHA-256](docs/data_source.json). 데이터 라이선스와 저장소 소스 코드의 [LICENSE.txt](LICENSE.txt)는 구분합니다.
- 이미지는 내장 이미지 생성 도구의 흑백 대표 스케치 46개입니다. [매핑 CSV](dataset/raw/images/image_mapping.csv)와 [이미지 설명·프롬프트](dataset/raw/images/README.txt)를 제공합니다. 실제 상품 사진·브랜드·모델의 외관이 아닙니다.

| 원본 컬럼 | 의미 |
|---|---|
| `Order_ID`, `Customer_ID` | 주문·고객 식별자 |
| `Order_Date` | 혼합 형식의 주문 날짜 |
| `Product_Category`, `Product_Name` | 상품 카테고리·상품명 |
| `Quantity`, `Unit_Price_USD` | 수량·단가(USD) |
| `Discount_Percent` | 할인율(%) |
| `Payment_Method` | 결제 수단 |
| `Shipping_City`, `Country` | 배송 도시·국가 |
| `Order_Status` | Delivered / Cancelled / Returned / Pending / Shipped |
| `Customer_Rating` | 고객 평점 |

## 실행

검증 환경은 Python 3.14입니다. 패키지 버전은 [requirements.txt](requirements.txt)에 고정했습니다. Matplotlib의 내부 설치 의존성과 별개로 분석 코드에서는 Pillow·OpenCV·ML/NLP·자동 EDA 도구를 직접 사용하지 않습니다.

프로젝트 루트에서 실행합니다. 기존 `.venv`가 있으면 환경 생성은 생략합니다.

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/run_analysis.py
```

**전체 분석 명령은 정상 실행 시 터미널 출력 없이 정제 파일·분석 표·차트·보고서를 갱신합니다.** 오류는 터미널에 표시됩니다. 원본은 변경하지 않습니다.

전처리만 실행하려면:

```bash
.venv/bin/python src/pipeline.py
.venv/bin/python src/pipeline.py --input dataset/raw/csv/ecommerce_retail_transactions_raw.csv --output-dir dataset/processed
```

전처리 CLI만 실행하면 정제 CSV가 피처 생성 이전 상태로 갱신됩니다. 제출용 최종 결과에는 `scripts/run_analysis.py`를 실행하세요. 원본 디렉터리·하위 경로·입력 CSV가 있는 디렉터리를 출력 위치로 지정하거나 입력을 덮어쓰는 경로는 거부합니다.

검증:

```bash
.venv/bin/python scripts/check_pipeline.py
.venv/bin/python scripts/check_analysis.py
```

검증은 전처리 7개 + 분석 5개 테스트로 날짜 경계값·대치·원본 보존·금액 보존·동점 점수·고객군 분할·민감도 집합·이미지 연결 등을 확인합니다. 분석 테스트는 임시 디렉터리에 결과를 저장하여 저장소의 산출물과 분리합니다.

IDE에서 노트북을 열고 `.venv`를 커널로 선택해 위에서부터 실행해도 전체 결과를 생성할 수 있습니다. 원본 탐색 1~9절과 정제 분석 10절 이후의 분모를 구분했습니다.

## 구조와 산출물

```text
src/pipeline.py                    # DataAnalyzer: 전처리·피처·IQR·RFM
src/reporting.py                   # 표·차트·고객군·민감도·보고서
scripts/run_analysis.py            # 전체 실행, 정상 출력 없음
scripts/check_pipeline.py          # 전처리 검증
scripts/check_analysis.py          # 전체 분석 검증
notebooks/analysis_report.ipynb    # 실행 결과와 해석
docs/preprocessing_policy.md      # 처리 기준
docs/data_source.json             # 출처·라이선스·원본 해시
dataset/raw/csv/                  # 원본 CSV
dataset/raw/images/               # PNG 46개·매핑·설명
dataset/processed/                # 정제 거래·확인 목록·요약
output/analysis/                  # 분석 표·RFM·민감도·보고서
output/analysis/figures/          # 필수 6종 + 민감도 차트
```

- [정제 거래](dataset/processed/transactions_cleaned.csv): 원본 컬럼 보존, 정규화·대치·날짜 상태·이미지/텍스트 피처·분석 대상 표시.
- [확인 필요 목록](dataset/processed/review_required.csv): 항목마다 한 행. 원본 레코드 번호·컬럼·원본값·사유·날짜 후보 포함.
- [전처리 요약](dataset/processed/preprocessing_summary.json): 날짜 상태·대치·상태별 포함 수·국가/구분자 패턴.
- [고객별 RFM](output/analysis/rfm_customers.csv), [고객군 요약](output/analysis/rfm_segments.csv), [날짜 민감도](output/analysis/date_sensitivity.csv), [그룹 이동표](output/analysis/segment_transitions.csv).
- [기술 통계](output/analysis/descriptive_statistics.csv), [상관행렬](output/analysis/correlations.csv), [이미지 피처](output/analysis/image_features.csv), [월별 금액](output/analysis/monthly_estimated_amount.csv), [분석 요약](output/analysis/analysis_summary.json).

## 전처리와 피처 기준

- 공백 정리 기준의 완전 중복만 제거하고 식별자는 문자열로 유지합니다.
- 미국 표기 변형을 `USA`, 신용카드를 `CREDIT_Card`로 통일하되 다른 국가·결제 수단은 구분합니다.
- 평점은 결측 유지, 도시 결측은 `Unknown`. 할인율 원본 결측만 상품별 → 카테고리별 → 전체 중앙값으로 대치하고 대치 단계를 기록합니다.
- 오류·무한대·범위 밖 값은 확인 목록에 남깁니다. 수량은 양의 정수, 단가는 양수여야 대상 금액에 사용합니다.
- 유효한 `Delivered` 거래만 공통 매출·RFM 대상으로 사용하고, 다른 상태와 보류 거래는 정제 데이터에 보존합니다.
- 추정 금액은 수량×단가×(1−분석용 할인율/100)입니다. 실제 결제액·환불액이 없어 회계상 확정 매출이나 순매출로 부르지 않습니다.
- 이미지 로드는 허용된 Matplotlib `imread()`, 크기 정규화는 NumPy 인덱싱·흰 패딩(64×64 RGB). **배치 배열의 평균·표준편차는 반복문 없이 NumPy 축 연산**으로 추출합니다. 파일 로드·패딩에는 순회가 있습니다.
- 상품명 길이·단어 수는 Pandas 문자열 연산으로 만듭니다. 합성 이미지 통계로 실제 구매 원인을 주장하지 않습니다.
- IQR 탐지는 함수로 직접 구현했습니다. 분포 비교용 클리핑과 실제 금액·RFM을 분리해 정상 고액 구매를 자동 삭제하지 않습니다.

### 날짜 가정과 확인 필요 항목

명시적 연-월-일·영문 월을 우선 해석합니다. 월·일 모두 유효하고 다를 때만 사용자 승인 가정인 **USA=월/일**, **UK·Canada·Australia·Germany·India·UAE=일/월**을 적용합니다. 국별 유일한 표준이나 출처 검증 사실이 아닙니다.

한쪽만 유효하지만 국가 규칙과 충돌하면 후보 날짜를 보존하되 보류합니다. 제공자는 `YYYY-MM-DD`, `DD/MM/YYYY`, `MM-DD-YYYY` 등의 혼합 형식을 설명하며 국가별 규칙의 근거는 확인되지 않았습니다. 국가와 관계없이 숫자 날짜의 `-`는 월/일만 유효한 1,467행, `/`는 일/월만 유효한 1,447행이 관측됐습니다.

`analysis_eligible`은 공통 분석 대상, `date_needs_review`는 날짜 보류, `row_needs_review`는 어떤 컬럼이든 확인 항목이 있는지를 뜻합니다. `source_csv_row`는 헤더 포함 CSV 레코드 번호로 셀 내부 줄바꿈이 있으면 편집기의 물리적 줄 번호와 다를 수 있습니다. 같은 거래의 여러 사유는 확인 목록에 여러 행으로 기록합니다.

## 주요 결과

| 항목 | 결과 |
|---|---:|
| 원본 → 중복 제거 후 거래 | 12,180 → 12,000행 |
| 확인 필요 거래 / 항목 | 1,653행 / 1,668개 |
| 날짜 규칙 충돌 | 1,482행 |
| 할인율 대치 / 도시 Unknown | 722행 / 494행 |
| 유효 완료 구매 / 고객 | 5,700행 / 2,823명 |
| 대상 추정 할인 후 금액 | 675,801.92 USD |
| IQR 단가 이상치 | 200행 |

날짜 가정으로 도출한 본 분석 기준일은 **2026-12-05**입니다. 모호하지 않은 날짜의 최대일은 **2026-06-30**이며, 7~12월 거래는 국가 가정으로 해석한 날짜에서만 나옵니다. 기준일은 출처 확인일(2026-11-25)보다도 늦습니다. 월별 차트의 주황색 음영은 이 가정에만 의존하는 구간으로, 실제 매출 급감이나 미래 완료 구매의 증거가 아닙니다. Recency 절댓값도 가정 기준일의 영향을 받습니다.

차트는 히스토그램·전후 박스플롯·막대·상관 히트맵·산점도·월별 라인차트 6종과 날짜 민감도 차트입니다. 차트 제목·축은 영어, 노트북 해석은 한국어로 작성했습니다.

## RFM 규칙과 고객군

Recency=기준일−마지막 유효 완료 구매일, Frequency=고유 주문 수, Monetary=추정 금액 합계입니다. R은 역방향 평균 백분위 순위×4의 올림, F는 횟수 1/2/3/4회 이상을 1/2/3/4점, M은 평균 백분위 순위×4의 올림으로 계산합니다. 동점은 같은 점수를 유지하므로 ID 순서에 영향받지 않습니다.

아래 순서로 먼저 만족한 고객군에 배정합니다.

| 그룹 | 규칙 | 고객 수 | 추정 금액 비중 |
|---|---|---:|---:|
| VIP | R≥3, F≥3, M≥3 | 482 | 34.67% |
| Loyal | 위 그룹 외 F≥3 | 339 | 14.93% |
| New | 위 그룹 외 R≥3, 구매 1회 | 354 | 6.14% |
| At_Risk | 위 그룹 외 R≤2, 구매 2회 이상 | 400 | 13.95% |
| Other | 나머지 | 1,248 | 30.31% |

R은 상대 순위이므로 ‘최근’은 최근 30일을 의미하지 않습니다. New는 관측 기간 내 단일 구매 고객이며 가입일이 없어 실제 신규 가입을 확정하지 못합니다. At_Risk도 실제 이탈을 관측한 집단이 아닙니다. 대상에서 빠진 고객은 551명입니다.

## 비즈니스 인사이트와 실행 가설

### 1. VIP 유지 실험

- **근거:** 고객의 17.07%인 VIP 482명이 대상 추정 금액의 34.67%를 차지합니다. [고객군 표](output/analysis/rfm_segments.csv).
- **실행:** VIP에 우선 상담·혜택을 무작위 대조 실험으로 제공해 재구매율 유지·증대를 목표로 합니다.
- **검증:** 상품 원가·혜택 비용·후속 구매가 필요합니다. 대조군 대비 이익 개선이 없으면 제안을 기각합니다.

### 2. 이탈 위험 가설의 재구매 유도

- **근거:** At_Risk 400명(14.17%)의 평균 Recency는 가정 기준일에서 642.6일입니다. 모호하지 않은 최종일보다 연장된 기준일의 영향을 포함하므로 실제 미구매 기간으로 단정하지 않습니다. [고객군 표](output/analysis/rfm_segments.csv).
- **실행:** 해당 그룹에 재입고 안내나 혜택을 무작위 시험해 재구매 반응을 높이는 것을 목표로 합니다.
- **검증:** 날짜 원본·수신 동의·발송 이력·원가가 필요합니다. 날짜 재해석이나 자연 재구매로 설명되면 분류·캠페인 가설을 재검토합니다.

### 3. 단일 구매 고객의 두 번째 구매 실험

- **근거:** New 354명(12.54%)은 완료 구매가 1회이고 평균 추정 금액은 117.19 USD입니다. [고객군 표](output/analysis/rfm_segments.csv).
- **실행:** 구매 상품 관련 안내를 무작위 시험해 두 번째 구매 전환율 증가를 목표로 합니다.
- **검증:** 가입일·과거 기간 구매·상품별 구매 주기·후속 관측이 필요합니다. 실제 신규가 아니거나 재구매 주기가 길다면 대상 선정이 틀릴 수 있습니다.

합성 데이터의 패턴을 바탕으로 구성한 가설이며, 캠페인 효과 크기·인과성·LTV를 추정한 결과가 아닙니다.

## 민감도·한계와 제출

같은 5,700개 거래·같은 금액에 날짜만 바꾸어 비교했습니다. 대안은 모든 모호한 날짜 월/일, 일/월, 구분자별 해석이며 보류 거래는 복구하지 않았습니다. 시나리오 전체 최대 날짜 **2026-12-06**을 공통 기준일로 사용합니다.

- 날짜 해석에 따른 고객군 변경률: 월/일 2.90%, 일/월 0.60%, 구분자별 1.66%.
- Monetary를 할인 전 금액으로 바꾸면 8명(0.28%)의 그룹이 바뀝니다. 이는 할인율 대치 오차 자체의 추정이 아닙니다.
- 월별 절대 금액 변화 합은 매출 손실이 아니며, 낮은 고객군 변경률도 날짜 가정이 옳음을 입증하지 않습니다.
- 보류 거래 복구, 관측 기간 이전 구매, 합성 이미지의 실제 외관 대체, 날짜 가정의 사실 확인은 완료됐다고 주장하지 않습니다.

최종 제출 대상 저장소: [PBK98/Numpy_Pandas](https://github.com/PBK98/Numpy_Pandas). 로컬 분석 산출물은 생성했으며, 이번 작업에서 자동 커밋·푸시는 수행하지 않습니다. 변경 파일과 노트북 출력을 확인한 뒤 저장소에 반영하면 됩니다.
