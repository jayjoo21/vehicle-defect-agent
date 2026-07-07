CLAUDE.md — 차량 결함 조사 Agent 프로젝트

프로젝트 개요

NHTSA(미국 도로교통안전국) 소비자 불만 텍스트에서 소프트웨어/전장 결함 시그널을 조기 탐지하는 LLM Agent.
현재 단계: 데이터 수집·검증 (파이프라인 구현 전). 대상 범위: 현대(HYUNDAI)·기아(KIA) × 전장/SW × 최근 데이터.

디렉토리 구조


data/raw/ — 원본 데이터. 절대 수정·삭제 금지. 이 폴더엔 쓰기 금지.

FLAT_CMPL.txt (1.46GB): NHTSA 불만 전체. 탭 구분, 헤더 없음, latin-1 인코딩



data/recalls/ — NHTSA 리콜 API 수집 결과 (되감기 검증의 정답지)
data/processed/ — 필터링·정제 산출물 (스크립트가 생성)
data/samples/ — 회의 공유·LLM 테스트용 소량 샘플
docs/molit_press/ — 국토부 리콜 보도자료 원문 (한국 쪽 정답지, 파일당 1건)
scripts/ — 수집·정제 스크립트


데이터 소스와 스키마

1. FLAT_CMPL.txt (불만 — 분석 입력)


49개 필드 예상. 공식 스펙: https://static.nhtsa.gov/odi/ffdd/cmpl/Import_Instructions_Excel_All.pdf
핵심 컬럼: ODINO(불만 고유번호), MAKETXT, MODELTXT, YEARTXT, COMPDESC(부품 라벨), CDESCR(소비자 서술 원문 ★), LDATE(접수일), CRASH, FIRE, INJURED, DEATHS
읽기 필수 옵션: sep="\t", header=None, dtype=str, encoding="latin-1", quoting=csv.QUOTE_NONE, on_bad_lines="skip", chunksize=200_000
실측 필드 수: 51개 (PDF 스펙 49개 + UNKNOWN_50·UNKNOWN_51 미문서 컬럼 2개, 현재까지 전부 빈값 — COLS 리스트는 scripts/nhtsa_data_prep.py 참조)

latin-1 아니면 중간에 죽음 / QUOTE_NONE 아니면 서술문 속 따옴표로 행 뭉개짐 / 1.46GB라 통짜 로드 금지(청크 필수)



날짜 형식: YYYYMMDD (예: 19950103)
COMPDESC는 쉼표 구분 복수값 가능, 구형 레코드는 전체 대문자


2. 리콜 API (정답지)


https://api.nhtsa.gov/recalls/recallsByVehicle?make={}&model={}&modelYear={} — 키 불필요
핵심 필드: NHTSACampaignNumber, ReportReceivedDate(★되감기 컷오프 날짜), Component, Summary, Consequence, Remedy, overTheAirUpdate
날짜 형식: DD/MM/YYYY (예: "24/06/2026"). 파싱 시 pd.to_datetime(..., dayfirst=True) 필수. 불만 데이터(YYYYMMDD)와 형식이 다름 — 반드시 ISO(YYYY-MM-DD)로 통일 후 비교
같은 캠페인이 여러 차종·연식에 중복 등장 → 캠페인 수 셀 때는 NHTSACampaignNumber로 dedupe
모델명은 미국 판매명. 레이(Ray) 등 미국 미판매 차종은 조회 불가 → "한국 단독 리콜"로 분류


3. 국토부 보도자료 (docs/molit_press/ — 한국 쪽 정답지)


한국어 텍스트. 양식: ①(제조사) 차종 등 N개 차종 M대는 [원인]으로 [증상] 가능성으로 [날짜]부터 시정조치
한·미 시차 탐지: 미국 캠페인의 ReportReceivedDate vs 한국 보도자료 발표일 비교
확인된 실사례: 미국 26V400000 (투싼 계기판 SW, 접수 2026-06-24) ↔ 국토부 7/2 발표 (투싼 등 2개 차종 54,792대) = 시차 약 8일


도메인 지식 (판단에 반영할 것)


부품 라벨(COMPDESC)은 부정확할 수 있음. 심각한 결함이 "UNKNOWN OR OTHER"로 라벨된 사례 실확인 → 필터링 시 UNKNOWN OR OTHER를 배제하지 말 것
불만은 미검증 소비자 신고 (NHTSA 명시). 산출물에 "결함 확정"이라는 표현 금지
VIN은 출력물에 노출하지 않음


작업 원칙 (반드시 준수)


코딩 전에 계획 먼저: 무엇을 왜 하는지 짧게 설명 후 구현
단순함 우선: 요구한 것만 구현. 과잉 추상화·불필요한 클래스·미래 대비 코드 금지
수술적 수정: 기존 스크립트 수정 시 필요한 부분만 변경. 전면 재작성 금지
결과 검증 필수: 데이터 작업 후 행 수·컬럼 수·날짜 범위·널 비율을 출력해서 보고
대용량 파일(raw/)은 청크 처리. 메모리에 전체 로드 금지
산출물 CSV는 encoding="utf-8-sig" (한글 엑셀 호환)
외부 라이브러리는 pandas, requests, prophet 범위 내에서. 새 의존성 추가 전 확인 요청
LLM 파이프라인 관련 코드는 아직 작성하지 말 것 (현재는 데이터 단계)


현재 작업 목표 (순서대로)


[완료] FLAT_CMPL 스캔·필터링 → data/processed/hk_electrical_recent_full.csv, data/samples/
[완료] 리콜 전량 수집 → data/recalls/recalls_hk_by_vehicle.csv, recalls_hk_campaigns.csv, recalls_sw_candidates.csv
[완료] 불만·리콜 날짜 정규화 → data/processed/lookback_candidates.csv (SW 리콜 캠페인별 발표 전 불만 건수 추이)
[완료] 국토부 보도자료 구조화 + 한·미 시차 표 초안 → 아래 산출물 참조


Task 4 산출물 (2026-07-05 완료)


scripts/molit_extract.py — pdfplumber로 19개 PDF → data/processed/molit_txt/*.txt (19/19 성공)
scripts/molit_parse.py — txt 파싱 → data/processed/molit_recalls.csv (79행, 발표일 2024-12-18~2026-07-02)
scripts/molit_match.py — 한·미 매칭 → data/processed/kr_us_gap.csv (27행)


kr_us_gap.csv 요약 (현대·기아 × NHTSA SW 후보)


미국선행 14건 (NHTSA 접수 후 한국 발표, 중앙값 ~33일)
한국선행 1건 (니로 NIRO, 한국 2월 vs 미국 6월, -121일)
한국단독 8건 (포터·봉고·레이 등 미국 미판매 차종)
매칭불가 4건 (K7·쏠라티·일렉시티·K3 — SW 후보 DB 미등재)
검증 완료: 투싼 26V400000 +8일 미국선행 ✓ / 레이 한국단독 ✓


파싱 주의사항


COMPDESC 불정확 원칙과 동일: 보도자료 ①② 기호가 리콜 항목이 아닌 개선사항 불릿으로 쓰이는 경우 있음 (260324 사례)
□ 단락 형식(원 번호 없음) 리콜은 molit_parse.py의 parse_preamble_recalls()가 처리
장기 시차(1000일↑) 매칭은 recalls_sw_candidates.csv의 SW 후보 커버리지 한계로 최신 매칭 없을 때 구형 캠페인과 연결된 것 — 해석 주의


Task 5 산출물 (2026-07-05 완료) — LLM 구조화 미니 테스트


scripts/struct_verify.py — 스키마+환각 자동 검증
data/processed/llm_struct_test_results.jsonl — 20건 구조화 결과
data/samples/grading_sheet.csv — 수동 채점용 시트


검증 결과: 스키마 위반 0/20, 인용 불일치(환각) 0/20
insufficient_info=true: 3건 (ODINO: 11478093·11729316·11505201)


UNKNOWN OR OTHER 7건 재분류 결과 (LLM이 서술문만으로 판단)


11568390 SORENTO → ELECTRICAL_SYSTEM (화재+동력상실)
11723787 TELLURIDE → POWERTRAIN_SW (변속충격+RPM불안정)
11554308 SORENTO → ELECTRICAL_SYSTEM (도어잠금오류, 탑승자 갇힘)
11541676 IONIQ 5 → NON_ELECTRICAL (서스펜션 — SW 관련성 낮음)
11635055 SOUL → NON_ELECTRICAL (오일 소모)
11505201 PALISADE → NON_ELECTRICAL (견인장치 리콜 — insufficient_info=true)
11478093 SPORTAGE → INSUFFICIENT_INFO (체크엔진 원인 불명)


part_category 분포: ADAS 10건, ELECTRICAL_SYSTEM 4건, NON_ELECTRICAL 3건, POWERTRAIN_SW 2건, INSUFFICIENT_INFO 1건
severity 분포: CRITICAL 11건, SERIOUS 5건, MODERATE 2건, MINOR 2건
채점 기준: data/samples/grading_sheet.csv (부품_정오·심각도_정오·증상_정오·환각_여부·오류유형·메모 컬럼 빈칸)


Task 6 산출물 (2026-07-05 완료) — KOTSA 리콜대수 데이터 전처리 + 한미 시차 v2


data/raw/한국교통안전공단_차종별 리콜대수_20251231.csv — 원본 (cp949, 13,560행)
scripts/kotsa_prep.py — 현대·기아 필터 + 차명 정규화 + SW 플래그
data/processed/kotsa_recalls_hk.csv — 680행 × 13열 (현대·기아, 2012-03~2025-12)
scripts/kotsa_gap_v2.py — KOTSA 기반 한미 매칭 + 캠페인 대응표
data/processed/kr_us_gap_v2.csv — 103행 (보도자료 27 + KOTSA 76)
data/processed/campaign_kotsa_check.csv — 76건 캠페인 × KOTSA 대응 여부


KOTSA 데이터 특성


날짜: 리콜개시일 (KOTSA 공식 시정 시작일) — 보도자료 발표일과 수일~수주 차이 있을 수 있음
SW 관련: 680건 중 219건 (32.2%)
date_basis 컬럼으로 "보도자료" 기반 행과 "KOTSA리콜개시일" 기반 행을 반드시 구분할 것


KOTSA 기반 매칭 결과 (76건, ±730일 윈도우)


미국선행: 31건 / 한국선행: 38건 / 매칭불가: 7건
매칭불가 대부분: KIA TELLURIDE (미국 전용 모델, 한국 미판매) + KIA RIO
매칭 주의: KOTSA 데이터가 2025-12-31 종료 → 2026년 이후 NHTSA 캠페인은 KOTSA 날짜가 한국 선행으로 보이는 오매칭 위험


주목 캠페인 5건 결과 (23V531000·24V204000·24V757000·25V006000·25V115000)


23V531000 SELTOS 2023-07-31 → KR 2023-08-30 (미국선행 +30일, SW 플래그 없음)
24V204000 IONIQ 6 2024-03-15 → KR 2024-03-18 (미국선행 +3일, SW=O)
24V757000 EV9 2024-10-10 → KR 2024-10-07 (한국선행 -3일, SW=O)
25V006000 SORENTO 2025-01-13 → KR 2025-01-24 (미국선행 +11일, SW=O)
25V115000 EV9 2025-02-24 → KR 2025-01-22 (한국선행 -33일, SW 플래그 없음)


KOTSA 모델명 매핑 미등록 (수동 검토 필요): 벨로스터, 베라크루즈, 그랜드스타렉스, 마이티, 파비스, EQ900, 엑시언트 등


Task 7 산출물 (2026-07-06 완료) — B1 감지 baseline + K12 되감기 평가


scripts/b1_detect.py — 차종(MODELTXT)×월(LDATE) 집계, 스파이크 규칙(당월≥직전6개월평균×2 AND 당월≥10건)으로 시그널 발화
data/processed/b1_signals.csv — 2022-07~2026-06, 78개 차종 × 48개월 = 3,744행
docs/k12_list.csv — 되감기 평가용 캠페인 12건 목록 (campaign, type: A=스파이크형 5건·B=만성형 4건·C=조기급증형 3건)
scripts/b1_eval_k12.py — 캠페인별 컷오프(report_date_iso) 이전 12개월 내 B1 시그널 발화 여부 채점 (멀티 차종은 하나라도 발화 시 포착)
data/processed/b1_eval_k12.csv — 캠페인 12건 × 채점 결과 (포착 여부·최초발화월·선행일·윈도우 내 추이)


경보 피로 (전 기간 기준)


총 발화 횟수: 67회 (2022-07~2026-06, 48개월 × 78개 차종 = 3,744 차종-월 중 67건 발화, 1.8%)
월평균 발화 건수: 1.4건/월 (전 차종 합산)
포착률만 보면 좋아 보여도 이 baseline은 항상 어느 정도 울리는 편이라, 포착 여부는 반드시 이 오경보율과 함께 해석할 것


K12 되감기 채점 결과


포착 10/12 (유형별: A=4/5, B=3/4, C=3/3)
평균 선행일 (포착 10건 기준): 215.7일 — 단, 스파이크형은 짧은 선행(10~30일)과 긴 선행(300일대)이 혼재해 평균의 대표성 낮음
캠페인별: 24V757000(EV9) +10일 / 25V235000(IONIQ 5) +70일 / 26V068000(IONIQ 5) +343일 / 23V531000(SPORTAGE) +334일 / 26V316000(TUCSON) +170일 / 26V400000(TUCSON) +206일 / 26V047000(IONIQ 5) +361일 / 25V006000(SORENTO) +166일 / 24V204000(IONIQ 5) +350일 / 25V115000(EV9) +147일
놓친 캠페인 2건 — 둘 다 "만성적으로 이미 높은 월별 건수" 때문에 배율(2배) 조건을 못 넘김:
  25V649000 (SORENTO, 유형A로 분류했으나 실제론 만성형): 컷오프 전 12개월 월별 건수 14~30건, 그런데 직전6개월 평균(baseline_avg6)도 이미 20~41건대라 절대건수는 높아도 배율 조건 미달
  24V879000 (ELANTRA·SANTA FE, 유형B): 월별 건수 10~43건대에서 등락하지만 baseline도 함께 17~30건대로 따라 올라가 있어 스파이크로 안 잡힘
시사점: 배율 기반 규칙은 "완만하게 이미 높아진" 만성 결함(유형B)을 놓치기 쉬움 — 절대 레벨 자체가 임계치를 넘는 규칙(수준 기반) 또는 더 긴 기준선(예: 12개월) 병행이 개선 후보


B1 평가 검증 3종 (2026-07-06 완료)


scripts/b1_eval_validation.py → data/processed/b1_eval_validation.csv


(1) 우연 포착 대조: 실제 컷오프 대신 2023-07~2026-06 전 구간(36개월)을 가상 컷오프로 돌려 "직전 12개월 내 발화 존재" 비율 계산
  캠페인별 우연 포착 확률 0.19~1.00으로 편차 큼 (모델 자체의 발화 빈도에 좌우됨)
  평균 우연 포착 확률: 0.590 — 실제 포착률 10/12=0.833보다는 높지만, 차이가 크지 않아 baseline의 "포착"이 순전히 운으로도 상당 부분 설명됨
  특히 26V047000(7개 차종 묶음)은 우연 포착 확률이 1.0 — 차종 수가 많은 캠페인일수록 "어느 하나라도 발화"라는 채점 방식 자체가 포착을 거의 자동으로 보장하므로, 다차종 캠페인의 포착 결과는 신뢰도 낮게 해석할 것
(2) 정밀도: 발화 67건 중 42건(62.7%)이 발화월 이후 12개월 내 해당 차종 리콜 접수로 이어짐 (recalls_hk_by_vehicle.csv, 차종-캠페인 전체 227쌍 기준으로 재계산 — 최초 recalls_hk_campaigns.csv 164건 기준 52.2%보다 높음. 그 파일은 캠페인당 차종 1개만 보존해 다차종 캠페인의 다른 차종이 누락됐던 것으로 확인)
(3) 민감도 (포착 창 12개월 → 6개월): K12 포착 10/12 → 8/12로 감소
  6개월 창에서 새로 놓친 2건: 26V400000(TUCSON), 24V204000(IONIQ 5/6) — 원래 12개월 창에서는 각각 206일·350일 선행으로 포착됐던 건이라, 그 선행 신호가 6개월보다 더 이전에 발생했다는 뜻
  기존 미포착 2건(25V649000·24V879000)은 6개월 창에서도 그대로 미포착


종합 해석: 포착률 10/12는 액면가보다 약하다 — 평균 우연 포착 확률(0.590)과의 격차가 크지 않고, 정밀도도 62.7% 수준이라 발화 3건 중 1건 이상은 리콜로 이어지지 않음. 배율 기반 baseline은 개선이 필요한 1차 버전으로 취급할 것


Task 8 산출물 (2026-07-06 완료) — 최소 완결 파이프라인 1회전 (진짜 급증 vs 가짜 급증 대조)


data/processed/struct_ev9_202409.jsonl — EV9 2024-09 불만 29건(고유 ODINO 기준) 구조화 (스키마위반 0, 인용불일치 0)
data/processed/report_24V757000.md — EV9 계기판 블랙아웃 시그널 리포트 (진짜 급증 사례)
data/processed/struct_genesis_202404.jsonl — GENESIS 2024-04 불만 14건 구조화 (스키마위반 0, 인용불일치 0)
data/processed/report_false_alarm.md — 대조군 리포트 (가짜 급증 사례)
scripts/struct_verify_generic.py — 임의 jsonl에 대한 스키마·환각 검증 + 분포 집계 (범용화)
scripts/verify_report_quotes.py — 두 리포트의 대표 인용 6건 verbatim 검증 (전체 통과)


EV9 24V757000 (진짜 급증) 결과


B1 발화 2024-09: 고유 29건, 직전6개월평균 2.0건 (실제 리콜 접수보다 10일 선행)
part_category: INSTRUMENT_CLUSTER 28/29(96.6%) — "주행 중 계기판 블랙아웃으로 속도계·방향지시등 표시 상실"이 사실상 동일 문구로 반복
severity: CRITICAL 24/29(82.8%)
결론: 실제 리콜 컴포넌트(INSTRUMENT CLUSTER/PANEL)와 정확히 일치 — 확신도 높음


GENESIS 2024-04 (대조군: 12개월 내 리콜로 안 이어진 발화) 결과


B1 발화: 고유 14건, 직전6개월평균 3.33건 (4.2배 스파이크, 12개월 내 해당 차종 리콜 없음)
part_category: ELECTRICAL_SYSTEM 8/14(57.1%) / INSUFFICIENT_INFO 6/14(42.9%) — 최빈 비율이 EV9(96.6%)보다 크게 낮음
핵심 발견: 이 스파이크는 무작위 노이즈가 아니라 **기존 리콜(24V107000, 전장) 부품 수급 지연에 대한 재확산성 항의**였음(14건 중 9건이 24V107000을 직접 언급) — B1 baseline이 놓치는 위양성은 최소 2종: ①순수 노이즈 ②기존 리콜의 후속 여파를 신규 시그널로 오인
결론: "일관된 새로운 결함 시그널 없음"으로 정직하게 보고 — 억지로 결함을 만들어내지 않음


시사점: part_category 최빈 비율(집중도)이 진짜 급증(96.6%)과 가짜 급증(57.1%) 사이에 약 40%p 차이 — 배율 규칙에 "증상 집중도" 2차 필터를 추가하면 위양성 억제 가능성 있으나, 표본 2건만으로는 임계치 확정 근거 부족


데이터 품질 메모 (발견)


data/processed/hk_electrical_recent_full.csv는 동일 ODINO가 COMPDESC별로 여러 행을 갖는 구조 — b1_signals.csv의 count는 이 원본 행수 기준이라 실제 고유 불만 수보다 다소 부풀려져 있음(예: EV9 2024-09 원본52행 vs 고유29건). 스파이크 배율 자체는 과장되나 임계치 초과 여부의 결론은 대체로 바뀌지 않음(고유건수 기준 재계산해도 14.5배로 여전히 초과) — 다음 baseline 개선 시 고유 ODINO count로 전환 검토할 것


Task 9 산출물 (2026-07-06 완료) — 집중도(part_category 최빈비율) 2차 필터 가설 검증


scripts/concentration_sample.py — b1_signals.csv 발화 67건을 "12개월 내 리콜 연계(42건)"/"비연계(25건)"로 나누고 각 그룹 5건 추출(seed=42, EV9 2024-09·GENESIS 2024-04 강제 포함·재사용)
data/processed/concentration_sample.csv — 표본 10건 목록
data/processed/struct_concentration_new8.jsonl — 신규 8개 발화 × 최대 15건(초과 시 seed=42 무작위) = 100건 구조화 (스키마위반 0/100, 인용불일치 0/100 — struct_verify_generic.py 검증)
scripts/concentration_aggregate.py — 표본 10건(신규8+기존2 재사용)의 part_category 최빈비율·최빈증상비율·mentions_existing_recall 집계
data/processed/concentration_test.csv — 최종 10행 결과


검증 결과 — 표본 10건의 집중도(top_part_ratio) 및 리콜연계 여부


| 차종·월 | 그룹 | 최빈 part_category | 집중도 |
|---|---|---|---|
| CARNIVAL 2024-08 | 비리콜 | PROPULSION_BATTERY(기생방전) | **1.000** |
| EV9 2024-09 | 리콜연계 | INSTRUMENT_CLUSTER | 0.966 |
| IONIQ5 2025-03 | 리콜연계 | PROPULSION_BATTERY(ICCU) | 0.867 |
| IONIQ5 2023-05 | 리콜연계 | PROPULSION_BATTERY(ICCU) | 0.733 |
| TUCSON HYBRID 2025-05 | 비리콜 | ADAS(FCA 오작동+주의카메라) | 0.700 |
| GENESIS 2024-04 | 비리콜 | ELECTRICAL_SYSTEM | 0.571 |
| TUCSON HYBRID 2025-07 | 비리콜 | INSTRUMENT_CLUSTER | 0.533 |
| K4 2026-02 | 비리콜 | ADAS | 0.500 |
| KONA 2025-08 | 리콜연계 | ELECTRICAL_SYSTEM | 0.357 |
| PALISADE 2022-08 | 리콜연계 | POWERTRAIN_SW | **0.300** |

리콜연계 그룹 평균 0.645(중앙값 0.733) vs 비리콜 그룹 평균 0.661(중앙값 0.571) — **두 그룹의 집중도 분포가 사실상 구분되지 않음(비리콜 그룹 평균이 오히려 근소하게 높음)**


핵심 발견: 표본 양 극단에서 가설과 정반대 결과


- 표본 전체에서 **집중도 1위(CARNIVAL, 100%, 기생 배터리 방전)는 리콜 비연계**, **집중도 최하위 2건(PALISADE 30.0%, KONA 35.7%)은 둘 다 리콜연계** — "집중도가 높을수록 리콜로 이어진다"는 report_false_alarm.md의 가설(임계치 80%↑ 제안)과 정반대 방향
- 임계값 후보 적용 시(이 10건 표본 기준, 원래 정밀도 5/10=50%): ≥0.80 적용 시 통과 3건(EV9·IONIQ5 2025-03·CARNIVAL) 중 2건만 실제 리콜 → 정밀도 66.7%로 개선되나, 실제 리콜연계 5건 중 3건(IONIQ5 2023-05·KONA·PALISADE)을 걸러내 재현율이 5/5→2/5로 급락. ≥0.50 적용 시엔 오히려 정밀도가 37.5%(3/8)로 **기준선보다 악화**(KONA·PALISADE라는 저집중도 실제 리콜 2건을 미리 제외해버리는 대신 CARNIVAL 등 고집중 비리콜 다수를 통과시키기 때문)
- 결론: **표본 10건 규모에서도 방향성이 뚜렷하여, "집중도 ≥80%" 2차 필터 가설(Task 8에서 n=2로 제안)은 기각**. 집중도는 이 차원만으로는 신뢰할 수 있는 리콜연계 판별 변수가 아님


mentions_existing_recall (기존 리콜/캠페인 언급 여부) 예비 조사


- 리콜연계 그룹: 7/83건(8.4%) 언급 (IONIQ5 2025-03이 5건으로 대부분 기여 — ICCU 리콜이 이미 잘 알려져 소비자가 인지하고 언급)
- 비리콜 그룹: 11/60건(18.3%) 언급 — 그러나 GENESIS 단독 9건이 대부분을 차지(기존 리콜 24V107000 부품지연 항의라는 특수 사례). GENESIS 제외 시 2/46건(4.3%)으로 오히려 리콜연계 그룹보다 낮음
- 이 지표도 특정 사례(GENESIS) 의존도가 높아 일반화된 2차 필터로 쓰기엔 표본 부족


데이터 품질 발견 (부수적, 해석 주의)


- **TUCSON HYBRID ≠ TUCSON 모델명 불일치**: recalls_hk_by_vehicle.csv에는 "TUCSON HYBRID"가 없고 "TUCSON"만 존재. TUCSON HYBRID 2025-07 발화(INSTRUMENT_CLUSTER 53.3%, 계기판/HUD 블랙아웃 문구가 실제 26V400000 투싼 계기판 SW 리콜·접수 2026-06-24와 매우 유사)가 모델명 불일치로 "비리콜(미스)"로 분류됐을 가능성 — 이는 baseline 실패가 아니라 **차종 매칭 단위의 데이터 정합성 문제**로 별도 처리 필요
- **K4 2026-02 우측 절단(right-censoring) 위험**: 정밀도 체크의 12개월 관측 창이 2026년 초 발화 건에서는 데이터 수집 종료 시점에 가깝게 걸쳐 있어, "리콜 없음"이 진짜 미스인지 아직 관측 기간이 다 안 찬 것인지 구분 불가


Task 10 산출물 (2026-07-06 완료) — 라벨 정제 후 정밀도·집중도 재계산


scripts/precision_v2.py — ① 차종명 정규화(HYBRID/PLUG-IN HYBRID/PLUG-IN/PHEV/ELECTRIC 접미어 제거 → base_model 통일) 후 발화 67건 리콜연계·정밀도 재계산, ② 발화월 >= 2025-07(데이터 종료 2026-06 기준 12개월 관측 미충족)을 "관측기간 부족"으로 분리
data/processed/precision_v2.csv — 발화 67건 × (model, base_model, hit_raw_v1, hit_base_observed, hit_base_full_window, censored)
scripts/concentration_regroup_v2.py — 집중도 표본 10건에 base_model 재분류 반영, 그룹 이동 확인 및 임계값 효과 재계산
data/processed/concentration_test_v2.csv — 재분류 결과


① 차종명 정규화 결과


CARNIVAL HYBRID→CARNIVAL, ELANTRA HYBRID→ELANTRA, IONIQ ELECTRIC/HYBRID/PLUG-IN HYBRID→IONIQ, KONA ELECTRIC→KONA, NIRO PHEV→NIRO, OPTIMA HYBRID/PHEV→OPTIMA, PALISADE HYBRID→PALISADE, SANTA FE HYBRID/PLUG-IN HYBRID→SANTA FE, SONATA HYBRID/PLUG-IN HYBRID→SONATA, SORENTO HYBRID/PHEV→SORENTO, SPORTAGE HYBRID/PHEV→SPORTAGE, TELLURIDE HYBRID→TELLURIDE, **TUCSON HYBRID/PLUG-IN HYBRID→TUCSON**
정밀도: v1(원 모델명) 42/67=62.7% → v2(base_model, 관측가능분 반영) **50/67=74.6%**. base_model 정규화만으로 8건이 miss→hit로 뒤집힘(SANTA FE HYBRID 2025-08, SONATA HYBRID 2023-10, TUCSON HYBRID 2024-09·2025-05·2025-06·2025-07·2025-08·2026-05) — 대부분 "차종명 문자열 불일치로 인한 가짜 미스"였음, Task 9에서 발견한 TUCSON HYBRID 사례가 일반적인 패턴이었음을 확인


② 우측 절단 분리 결과 (발화월 >= 2025-07, 26건)


관측기간 충족(41건): hit=33 → 정밀도 **80.5%**
관측기간 부족(26건, 정밀도 분모에서 제외): 그중 17건은 이미 관측된 조기 리콜연계 확인(예: IONIQ 5 2025-12~2026-02, KONA 2025-07·08, PALISADE 2025-07·09 등) — 나머지 9건(EV6 3개월·FORTE·K4·NIRO 등)은 현재까지 리콜 미관측이나 관측기간이 안 찼으므로 "미스 확정"이 아님


③ 집중도 표본 10건 재분류 — 그룹 이동 2건


TUCSON HYBRID 2025-05(비리콜→**리콜연계**, 집중도 0.700), TUCSON HYBRID 2025-07(비리콜→**리콜연계**, 집중도 0.533, 단 censored=True — 26V400000 리콜(2026-06-24)이 관측가능 구간 내 이미 확인되어 조기 hit으로 처리)
재분류 후 그룹 구성: 리콜연계 7건 / 비리콜 3건(GENESIS·K4·CARNIVAL만 남음) — 원래 5:5였던 표본이 사실 7:3에 가까웠음(TUCSON HYBRID 2건이 모델명 매칭 버그로 잘못 비리콜에 배정돼 있었음)
재계산된 집중도: 리콜연계(n=7) 평균 0.637·중앙값 0.700 [0.300, 0.357, 0.533, 0.700, 0.733, 0.867, 0.966] vs 비리콜(n=3) 평균 0.690·중앙값 0.571 [0.500, 0.571, **1.000**] — **재분류 후에도 비리콜 그룹 평균이 여전히 근소하게 높음**, CARNIVAL(100%, 확정 비censored 미스)이 핵심 반례로 남음
임계값 효과 재계산(기준선 7/10=0.700): ≥0.50 → 5/8=0.625(악화, 실제 리콜 2건 누락), ≥0.70 → 4/5=0.800(개선되나 실제 리콜 7건 중 3건 누락하고 CARNIVAL은 여전히 통과), ≥0.80 → 2/3=0.667(악화). **라벨 정제 후에도 "집중도 단일 임계값" 결론은 바뀌지 않음** — 어떤 임계값도 정밀도를 안정적으로 개선하면서 재현율을 유지하지 못함


④ 정밀도 해석상 한계 (명시)


**"비리콜" 라벨은 NHTSA 리콜 DB(recalls_hk_by_vehicle.csv) 기준이며, 서비스 캠페인·TSB(기술서비스회보)로 처리되고 정식 리콜로 등록되지 않은 결함 대응 건을 포착하지 못한다 — 따라서 위 정밀도(74.6%/80.5%)는 실제 "결함 대응으로 이어진" 비율의 하한 추정치다.**


Task 11 산출물 (2026-07-06 완료) — v2 프롬프트 회귀 검증 (sample_20 중 18건)


scripts/struct_v1v2_regression.py — v1(llm_struct_test_results.jsonl, 20건) vs v2(llm_struct_v2_18cases.jsonl, 18건, 경계 2건 11551510·11729316 제외) 필드별 diff
data/processed/llm_struct_test_v2_regression.csv — 18건 × (part_category/severity/driving_context/insufficient_info/symptoms 각각 v1·v2·변화여부) + 적용된 v2 규칙 메모
검증 결과: **18/18건 무변화** (기대와 일치) — part_category·severity·driving_context·insufficient_info·symptoms 전부 v1=v2
18건 각각에 v2 규칙(①결함-결과분리 ②통제가능성 ③오작동>미작동)을 개별 재적용해 독립 재검증 완료. 예: AEB/FCA 허위제동 4건(11547006·11698291·11700995 등)은 Rule③(오작동)+Rule②(제동=대체불가)로 CRITICAL 유지, 후방카메라 단독 미작동(11617279)·ADAS 미작동(11627029·11737278)은 Rule②(대체가능 편의기능)로 SERIOUS 상한 유지, 도어락(11554308)은 탑승자 갇힘에도 Rule② CRITICAL 허용 목록 외라 SERIOUS 유지 — v1 프롬프트가 이미 이 규칙들과 암묵적으로 일치된 판정을 하고 있었음을 재확인
참고: 이 18건 재구조화 자체는 이전 세션에서 최초 수행됨(commit b233ae6) — 이번 작업은 v2 규칙을 18건에 독립적으로 재적용해 결과를 검증하고, CSV 형태의 diff 리포트로 재정리 + CLAUDE.md에 최초로 기록한 것


webapp/ — 웹 서비스 초안 v0 (docs/13_초안v0_스펙.md 기준, 2026-07-07 진행 중)


11절 구현 순서: 1.스캐폴드 → 2.seed+DB+GET 엔드포인트 → 3.상황판(Dashboard) → 4.조사채팅(Chat) → 5.내차(MyCar) → 6.폴리시 → 7.README. 단계별 실행 가능 상태로 커밋 + 완료 보고 후 다음 단계 진행.
1단계(85a303a)·2단계(af0b97f) 완료. seed는 스펙 9절대로 data/processed/의 b1_signals.csv·report_24V757000.md·kr_us_gap.csv·llm_struct_test_results.jsonl 4종에서만 변환(지어낸 값 없음). 3단계(상황판) 진행 중 — 착수 조건으로 상태 시맨틱을 아래와 같이 수정.


셀 상태(cell state) vs 에피소드 상태(episode state) 분리 — 3단계 착수 조건


signals 테이블(3,744행 = 78개 차종×48개월)의 state 컬럼은 그대로 유지: 모델×월 한 칸의 관측치(리콜 매칭 시 recalled/resolved, b1 스파이크 발화 시 active, count>baseline이면 rising, 그 외 new) — CLAUDE.md에 기록된 baseline(총 발화 67건 등)과 정확히 일치해야 하므로 변경 금지.
반면 대시보드 카드·KPI(활성 시그널 수 등)는 "지금 이 결함이 진행 중인 에피소드인가"를 보여줘야 해서 셀 상태를 그대로 쓰면 안 됨 — 별도 규칙으로 매 요청마다 파생(저장하지 않음): webapp/backend/engine/episode.py
  1) recalled — 매칭된 US 리콜 report_date가 기준월 이전 AND 기준월이 그 접수일로부터 12개월(365일) 이내
  2) active — (1)에 해당하지 않고, 최근 3개월(기준월 포함) 중 하나라도 b1 스파이크 규칙(당월count≥직전6개월평균×2 AND count≥10건, scripts/b1_detect.py와 동일) 발화
  3) rising — 최근 2개월 연속 count≥baseline×1.5 AND count≥5건
  4) new — 그 외(이력 없음, 회색)
"해당 결함 리콜 없음"은 "지금 12개월 이내 리콜 진행 중이 아님"으로 해석(우선순위 1번에서 이미 걸러짐) — 아주 오래 전 리콜 이력이 있다는 이유만으로 이후의 완전히 새로운 급증까지 영구히 active에서 배제하지 않음. 이 규칙은 v0 잠정안이며, 본편 상태추적 모듈이 대체할 예정(코드 상단 docstring에도 명시).
검증 결과(기준월 2026-06, base_model 57개 카드): new 51 / recalled 4(IONIQ 6·PALISADE·SANTA FE·TUCSON) / active 1(NIRO) / rising 1(IONIQ 9). KPI: active_signals=1, new_alarms_this_week=1, watched_models=78(원본 모델명 기준, 불변), us_recalled_kr_unremediated=14(불변).
해석: active+rising 합계 2건은 착수 전 예상(대략 3~10건)보다 적지만, 이미 기록된 baseline 발화 빈도(월평균 1.4건/78모델, 전체 차종-월의 1.8%)와 정확히 같은 자릿수 — 이번 달이 조용한 게 오히려 정상 상태. 최근 대형 급증은 대부분 이미 실제 리콜로 이어져 recalled로 분류되고(TUCSON 등), 리콜 없는 모델의 마지막 발화는 대개 2026-02(IONIQ 5·K4)로 3개월 관측창보다 앞서 있어 active에서 빠짐 — 데이터가 2026-06에서 끝나는 우측 절단(Task 10 ④ 한계)의 연장선.
한계(명시): 원인 결함 단위로 리콜을 구분하지 않아 같은 모델에 여러 다른 결함이 있어도 리콜 하나로 뭉뚱그림. 파워트레인 변형(TUCSON/TUCSON HYBRID 등)은 base_model 기준 count·baseline을 단순 합산.
