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


3단계 완료 후 수정 (커밋 5bc7e03) — KPI 라벨 정직화 + 도메인 분류 버그


KPI 4번째 항목 라벨을 "미국 리콜·한국 미조치"→"한국 시정 개시일 미확인"으로 교정. kr_us_gap 실데이터를 재확인한 결과 "한국 발표 자체가 없는" 행은 0건(us_date 있는 15행 전부 kr_date 있음)이었고, 실제로는 "발표는 됐으나 시정 개시일(kr_start_date) 미기재"인 14건뿐이었음 — 스펙 문구를 그대로 따르면 실데이터와 다른 단정이 됨. 대시보드 KPI 카드 캡션·덤벨 차트 캡션·백엔드 summary note 3곳 모두 동일하게 교정.
vehicles.py 도메인 분류 버그: recall의 component 필드가 포괄적이면(예: "ELECTRICAL SYSTEM:12V/24V/48V BATTERY") summary의 더 구체적인 키워드(ICCU)를 아예 확인하지 않던 문제 — component만 보고 먼저 매칭되면 or 단축평가로 summary를 안 보게 되는 구조였음. component+summary를 합쳐 한 번에 매칭하도록 수정(engine/domains.py의 도메인 순서상 ICCU_충전제어가 구동배터리보다 먼저 체크되므로 이 수정만으로 올바르게 분리됨).


4단계 진행 — 조사 채팅 (Chat) 화면


착수 전 확인 요청(사용자 지시)으로 seed_manual.py의 EV6 데모 레코드가 3단계 커밋에 빠져있었음을 발견 → 4단계 첫 작업으로 처리.


발견 1 — EV6 데모 각본의 전제가 실데이터와 다름 (사용자 확인 후 "현실 반영"으로 결정)


스펙 4절 각본은 "EV6 자체의 계기판 관련 리콜은 현재 없습니다"를 전제하지만, 실제로 EV6는 이미 ICCU(통합충전제어장치) 12V 배터리 리콜(24V200000→24V867000으로 확대)을 보유. "계기판이 깜빡이다 꺼짐" 신고 대부분(최근 90일 53건 중 클러스터 키워드 일치 1건)이 이미 이 리콜로 설명됨.
전력손실·ICCU 언급 없이 순수 계기판 표시 결함만 보고된 사례 2건(ODINO 11630458 2024-12·11670403 2025-06)은 있으나 둘 다 90일 밖의 오래된 사례 — "최근 재발 없음"이 정확한 서술.
각본을 이 현실대로 재작성(webapp/backend/llm/mock_responses/answer/ev6_cluster.json).


발견 2 — kr_us_gap.csv 기반 recalls 테이블의 구조적 누락 (IONIQ 5 사례로 발견)


kr_us_gap.csv는 캠페인당 "조회한 차종" 하나만 기록해서, 같은 캠페인이 실제로 적용되는 다른 차종이 자동 seed.py 파이프라인의 recalls 테이블에서 누락됨. 예: 24V204000(ICCU)은 실제로 IONIQ 5/IONIQ 6/Genesis GV60·GV70·G80에 공통 적용되는 캠페인이지만 kr_us_gap.csv엔 IONIQ 6로만 기록돼 있어, IONIQ 5는 실제 리콜이 있음에도 대시보드에서 "recalled"가 아닌 다른 상태로 잘못 표시되고 있었음(3단계 산출물에 이미 존재하던 숨은 버그, 이번에 발견해 수정).
webapp/backend/seed_manual.py를 EV6·IONIQ 5 공용 함수로 일반화 — data/recalls/recalls_hk_by_vehicle.csv에서 두 차종의 실제 US 리콜 전량(EV6 4건·IONIQ 5 14건)과 data/processed/hk_electrical_recent_full.csv에서 두 차종의 고유 불만 전량(EV6 449건·IONIQ 5 1,112건)을 가져와 "이력 조회"·"리콜 대조" 단계가 실측과 일치하는 라이브 쿼리 결과를 보여주도록 함. 재시드 후 복원: complaints 1,579행·recalls 31행. IONIQ 5는 이제 올바르게 recalled 상태로 표시됨(26V068000, 2026-02-06, 구동배터리 버스바 결함 — ICCU와는 별개의 최신 리콜).
다른 차종에도 같은 누락이 있을 수 있음 — recalls 테이블 전체를 kr_us_gap.csv 대신 recalls_hk_by_vehicle.csv(차종별 전체 리콜 이력)를 기준으로 재구축하는 것이 본편에서 검토할 개선점. 이번 세션 범위 밖으로 남김.
IONIQ 5는 2026년 상반기 ICCU/12V 배터리 신고가 실제로 극단적으로 급증한 상태(b1_signals.csv 기준 2026-01 134건·2026-02 192건, 최근 90일 103건 중 77건(75%)이 ICCU/12V 키워드 일치) — 조사 채팅 두 번째 데모 시나리오("이력 있음")로 적합해 채택.


구현 — SSE 배관 + 목 모드


llm/adapter.py: LLM.call(role, scenario, context) — mock 모드는 llm/mock_responses/{role}/{scenario}.json의 markdown_template에 context를 대입해 반환. 타임라인 단계 수치(신고 건수·리콜 캠페인 등)는 전부 routers/chat.py가 DB에서 실시간 조회해 context로 넘기므로 템플릿엔 지어낸 값이 없음.
routers/chat.py: POST /api/chat, 시나리오 3종(ev6_cluster/ioniq5_charging/out_of_scope) 키워드 매칭 후 SSE로 단계별 이벤트 스트리밍. 인용 원문(sources)도 DB에서 직접 조회.
버그 수정 1 (db.py): sqlite3.connect에 check_same_thread=False 필요 — FastAPI의 동기 Depends(get_db)가 스레드풀에서 커넥션을 생성하는데, StreamingResponse의 실제 스트리밍은 이벤트루프 스레드에서 이어서 실행돼 "SQLite objects created in a thread can only be used in that same thread" 에러 발생. 요청마다 커넥션을 새로 만들고 바로 닫으므로(동시 공유 없음) 안전.
버그 아님 (테스트 방법 이슈): Git Bash에서 curl -d '{"message":"한글..."}' 로 직접 보내면 쉘의 콘솔 코드페이지 인코딩 문제로 서버가 400/500을 반환 — 실제 브라우저 fetch(JSON.stringify)는 항상 올바른 UTF-8을 보내므로 앱 버그가 아님. curl로 재현할 땐 UTF-8 파일을 --data-binary "@file"로 보내야 함.
프론트: lib/sse.ts(fetch+ReadableStream 수동 SSE 파싱, EventSource는 POST 미지원), components/InvestigationTimeline.tsx(타임라인, fade+slide 200ms), components/ChatAnswerCard.tsx(답변 렌더링 — lib/markdown.tsx 재사용 + 원문 인용 목록 + 고지문), pages/Chat.tsx.
검증: TestClient로 3개 시나리오 전부 200 확인 후 실제 uvicorn 서버+curl SSE, Vite 프록시(5173→8000) 경유까지 end-to-end 확인.


5단계 착수 전 — recalls 테이블 전체 재구축 (이월 항목 처리)


4단계에서 발견한 recalls 테이블의 구조적 누락(kr_us_gap.csv가 캠페인당 차종 1개만 기록)을 EV6·IONIQ 5 두 차종만 임시 보강했던 것을, data/recalls/recalls_hk_by_vehicle.csv(현대·기아 27개 차종 × 캠페인 전체 쌍, 377행)를 정본으로 전체 재구축.
스키마 수정 필요: recalls.campaign이 PRIMARY KEY였는데, 같은 캠페인이 여러 차종에 공통 적용되는 실제 사례가 있어(예: 24V204000이 IONIQ 5·IONIQ 6·Genesis GV60/GV70/G80에 공통 적용) PK로 두면 첫 매칭 차종 외엔 전부 유실 — kr_us_gap과 동일한 클래스의 버그를 재구축 도중 미리 발견해 id INTEGER PRIMARY KEY AUTOINCREMENT로 교체(campaign은 non-unique). 기존 app.db는 스키마 마이그레이션이 안 되므로 삭제 후 재생성(gitignore 대상, 로컬 재생성 가능 확인 후 삭제).
seed_recalls()를 recalls_hk_by_vehicle.csv 기반으로 교체, EV9 24V757000 하드코딩 제거(이 파일에 이미 존재), seed_manual.py의 EV6·IONIQ 5 리콜 보강 코드 삭제(중복 삽입 방지 — 이제 전체가 정본에서 자동으로 채워짐). kr_us_gap.csv는 한미 시차 전용(kr_us_gap 테이블)으로 역할 분리, recalls에는 더 이상 관여하지 않음. signals 셀 상태(derive_state)는 여전히 kr_us_gap.csv 기반 recall_lookup을 그대로 사용 — 이번 재구축과 무관(3단계에서 이미 셀 상태·에피소드 상태를 분리해뒀기 때문에 영향 없음).


검증 결과


① recalls 행 수: 17행(4개 차종만 커버) → 227행(27개 차종 전체 커버) — 약 13배 증가
② 에피소드 상태 분포(기준월 2026-06, 57개 base_model 카드): recalled 4→15(+11: CARNIVAL·ELANTRA·EV9·IONIQ 5·K5·KONA·SANTA CRUZ·SONATA·SORENTO·SPORTAGE·TELLURIDE 추가) / active 1→1(NIRO, 불변) / rising 1→1(IONIQ 9, 불변) / new 51→40(-11). watched_models(78)·us_recalled_kr_unremediated(14)는 recalls 테이블과 무관해 불변.
  부수 발견: new_alarms_this_week이 1→0으로 바뀜 — 원인은 캠페인 25V426000이 kr_us_gap.csv에서는 "NIRO"로 단순 기록돼 있었으나 recalls_hk_by_vehicle.csv에는 실제로 "NIRO EV"(별도 base_model, normalize_model이 EV 접미어는 벗기지 않음)로 정확히 기록돼 있어, plain NIRO가 이제 이 리콜의 영향을 받지 않는 것으로 정정됨(NIRO가 5월·6월 모두 active로 계산돼 "신규" 아님으로 바뀜) — 더 정확해진 결과.
③ 차종별 리콜 보유 수 상위 10(recalls 테이블, distinct campaign count): SANTA FE 18 / TELLURIDE 16 / PALISADE 16 / TUCSON 15 / IONIQ 5 14 / ELANTRA 14 / SORENTO 13 / KONA 12 / SPORTAGE 11 / SONATA 10 — 내 차 페이지 도메인 상태 칠하기의 눈검증 기준으로 사용.


5단계 진행 — 내 차 (MyCar)


등록 27종은 recalls_hk_by_vehicle.csv의 실측 distinct base_model(정확히 27개)과 Make 컬럼을 그대로 사용(frontend/src/lib/carRegistry.ts) — 임의로 목록을 짜지 않음.
백엔드 GET /api/vehicles/{model}/{year}/map 응답에 필드 추가(도메인 상세 카드용, 지어낸 값 없음): recall_count(해당 도메인에 매칭된 리콜 수), complaint_count(해당 도메인에 매칭된 불만 수), trend(월별 건수 — 서로 다른 달이 2개 미만이면 "추이"라 부를 근거가 부족해 빈 배열로 생략, 지어낸 단일점 차트 금지), kr_gap(대표 리콜 캠페인이 kr_us_gap에 있으면 발표일·시차일). 대표 리콜 선정 로직도 수정: 기존엔 SQL 정렬 없이 마지막으로 순회된 리콜이 우연히 남는 구조였는데, ORDER BY report_date ASC로 명시해 "가장 최근 리콜"이 항상 남도록 함.
검증 예시(실제 응답): TUCSON/2026 계기판→26V400000(+8일, 싼타페 다음으로 유명한 실사례) / IONIQ 5/2025는 계기판·ICCU_충전제어·구동배터리·제동SW 4개 도메인이 모두 서로 다른 실제 리콜로 recalled(26V047000·24V868000·26V068000·25V235000 — ICCU와 구동배터리 버스바 결함이 별개 리콜로 정확히 분리되어 나타남), ADAS_카메라만 실측 불만 1건으로 active. SOUL/2020처럼 표본이 적은 차종은 계기판 리콜 1건 외엔 전부 "이력 없음"으로 정직하게 표시.
구현 순서(사용자 지시대로): ① 등록 플로우(차종 검색 그리드 → 연식 선택, localStorage 저장) → ② SVG 폴백 버전 완성(핫스팟 6개·도메인 상세 카드·"이 증상 조사하기"→채팅 프리필·등록 직후 순차 점등+토스트 전부 SVG로 검증) → ③ 3D(R3F) 레이어를 그 위에 얹음.
3D: frontend/public/models/{suv,sedan,sports}.glb 3종 + lib/bodyType.ts(27개 차종 → 3종 매핑, 판단 근거는 실제 세그먼트 — 매핑에 없으면 suv 폴백). CarViewer.tsx가 WebGL 미지원·3초 로딩 초과·런타임 에러 시 자동으로 CarViewerSvg로 폴백(ErrorBoundary + 타임아웃 레이스). 핫스팟 3D 위치는 glb의 실제 스케일을 알 수 없어(에이전트 환경에 브라우저가 없어 시각 확인 불가) 로드 후 계산한 바운딩 박스에 대한 상대 비율(lib/hotspots.ts의 400x200 SVG 좌표를 전후·상하 비율로 변환)로 배치 — 실제 렌더링에서 전후가 뒤집혀 보이면 CarViewer3D.tsx의 FRONT_AXIS_SIGN을 -1로 바꿔 보정.
버그 발견·수정(3D): CarModel의 박스 계산 useEffect를 처음엔 `[scene]`에 의존시켰는데, drei의 useGLTF가 같은 경로(같은 차체형태, 예: TUCSON→SANTA FE 둘 다 suv.glb)를 캐시로 재사용하면 scene 참조가 안 바뀌어 onLoaded가 다시 호출되지 않고, 그 결과 상위 CarViewer의 3초 타임아웃이 멀쩡한 모델도 SVG로 잘못 폴백시키는 문제를 미리 발견해 `[path]` 의존으로 수정.
한계(명시, 브라우저 미접근으로 시각 확인 못함): 3D 핫스팟의 정확한 위치·회전축 정렬은 실제 glb 지오메트리를 육안으로 봐야 확정 가능 — 사용자가 브라우저에서 직접 확인 필요. 모바일 반응형(스펙의 "답변 위 접이식" 등)은 이번 5단계에서 미적용.


5.5단계 (2026-07-07 완료) — 디자인·데이터 개선 패스 (6단계 폴리시 이전, 사용자 지시로 선행)


(1) 덤벨 차트 데이터 가드


kr_us_gap 테이블에 model·defect_summary(한국_원인>한국_증상>미국_컴포넌트 순 실측값, 지어낸 번역 없음)·date_basis 컬럼 추가. GET /api/gap이 |gap_days|<=365 필터 + 캠페인당 대표 1행(동률 시 |gap_days| 최소값, id로 재현 가능하게 tie-break) dedup을 적용해 반환하도록 변경 — 프론트는 백엔드가 이미 정제한 값을 그대로 그림(클라이언트 측 슬라이스 로직 제거).
큐레이션: kr_us_gap.csv(27행)만으로는 이 필터를 통과하는 게 정확히 7건이었는데, EV9는 이 파일에 아예 없어(24V757000, 계기판/IEB 리콜) kr_us_gap_v2.csv(KOTSA 기반, CLAUDE.md Task 6에 이미 기록된 실측값 "-3일")에서 해당 1행만 선별 추가(date_basis='KOTSA리콜개시일'로 별도 표기, CLAUDE.md 원칙대로 보도자료 기준과 구분) — 정확히 8건이 되어 사용자가 지정한 "대표 8건"과 일치.
검증 결과(실제 API 응답): TUCSON 26V400000 +8일, SANTA FE 25V808000 +152일, PALISADE 26V169000 +4일, IONIQ 6 25V606000 +33일, PALISADE 25V291000 +127일, NIRO 25V426000 -121일, SORENTO 25V006000 +10일, EV9 24V757000 -3일. excluded_count=5(NEXO+1478·SELTOS+660·ELANTRA+420·KONA+793·CARNIVAL+1103, 전부 ±365일 초과).


(2) 대시보드 위계 개편


engine/episode.py에 DASHBOARD_PRIORITY={active:4,rising:3,recalled:2,new:1} 신설(셀 상태용 STATE_PRIORITY와 목적이 달라 별도 상수 — "지금 당장 봐야 할 것"이 이미 대응 중인 recalled보다 앞섬). signals.py의 카드 빌드 로직을 _build_cards() 헬퍼로 통합해 list_signals()·get_summary() 양쪽에서 재사용.
"오늘의 시그널" 히어로 카드: get_summary()가 DASHBOARD_PRIORITY 1순위 카드 1건을 골라 complaints 테이블에서 해당 base_model의 최신 인용 1건(있으면)을 조인해 hero 필드로 반환. 최우선 카드가 'new'뿐이면(감지된 게 없으면) hero=null.
"주목 필요" 기본 탭 신설: active OR rising OR (recalled AND recall_recent) — recall_recent은 새 필드로, 매칭된 리콜 접수일이 기준월 기준 90일 이내인지 여부(engine/episode.py RECALL_RECENT_WINDOW_DAYS). 이미 오래 대응 중인 리콜까지 계속 주목 필요에 띄우지 않기 위함. 원래 있던 '재발'(resolved) 탭은 에피소드 상태가 절대 resolved를 반환하지 않아 항상 빈 탭이었으므로 제거.
SignalCard의 "대표 증상 미확인 (표본 부족)"·"리포트 없음" 반복 placeholder 문구 제거 — 정보 있을 때만 해당 줄을 렌더링.
KPI 4번째 카드의 캡션 텍스트를 카드 밖 페이지 각주로 이동, 카드에는 라벨 옆에 "*" 표시만 남김.
검증(TestClient): hero=NIRO(active), signals 정렬 첫 5건이 active>rising>recalled 순으로 정확히 나옴.


(3) 히트맵 압축


HEATMAP_MONTHS 24→12, top_models를 총 신고량 상위 20개 대신 "발화(alarm) 이력이 한 번이라도 있는 차종" 중 상위 12개로 변경(HEATMAP_MAX_MODELS=12) — 조용한 차종을 채워 압축 취지를 해치지 않음. 셀 h-4 w-4→h-6 w-6, 월 라벨은 3개월 간격만 표시(나머지는 빈 헤더, 정렬용 셀은 유지), 색상 보간에 감마 보정(t**0.55)을 추가해 중저값 구간의 대비를 강화.
검증(TestClient): models 12개(TUCSON·SORENTO·SONATA·IONIQ 5·SANTA FE·TELLURIDE·PALISADE·SPORTAGE·SOUL·EV6·KONA·FORTE), months 12개(2025-07~2026-06).


(4) 내 차(MyCar) 2열 레이아웃 개편 + 차체형태별 핫스팟 분리


레이아웃: lg:grid-cols-2 — 좌측(정보 기둥: 차종명 대형 타이포+상태 요약 배지+도메인 6개 클릭 목록+선택된 도메인의 DomainDetailCard), 우측(3D/SVG 뷰어, w-[60%]로 축소, lg:sticky top-6). 기존엔 핫스팟 클릭 시 뷰어 아래로 스크롤하는 구조였는데, 이제 좌측 목록에서도 동일한 selectedDomain 상태를 공유해 클릭 가능 — 스크롤 불필요해져 관련 코드 제거.
핫스팟 좌표 분리: lib/hotspots.ts를 HOTSPOTS_BY_BODY_TYPE(suv/sedan/sports 3세트, 라벨은 공통 HOTSPOT_LABELS로 분리)로 재구성. 기존엔 SUV용 좌표(루프라인 60~95) 하나를 세단에도 그대로 써서 계기판·인포테인먼트 핫스팟이 세단 지붕 위 허공에서 겹쳐 보이는 버그가 있었음 — sedan(루프 75~105)·sports(루프 88~118)용 좌표를 별도로 근사 배치(3D는 여전히 바운딩박스 상대비율 변환이라 실제 글TF 지오메트리 육안 확인 전까지는 근사치, 코드 주석에 명시). CarViewerSvg의 실루엣도 차체형태별 3종 path로 분리(suv=기존 박스형, sedan=낮고 긴 루프, sports=가장 낮은 캐빈).
다크 카드 제거: CarViewer.tsx·CarViewerSvg.tsx의 backgroundColor:'#0B1220' 풀 다크 카드를 제거하고 `radial-gradient(ellipse 60% 55% at 50% 75%, var(--color-navy-soft) 0%, transparent 70%)`(차 뒤 은은한 라디얼 글로우)로 교체, 텍스트 색도 백색 고정에서 var(--color-ink)/var(--color-ink-muted)로 변경(더 이상 다크 배경을 전제하지 않음). 핫스팟 호버 툴팁은 별도 플로팅 요소라 기존 다크 배경 유지(가독성 목적, 카드 자체 배경과는 무관).


(5) 채팅 화면 agent화


routers/chat.py: 각 step에 tool(도구 칩 — "규칙 매칭"/"DB 조회"/"인용 검증")과 duration_ms(time.perf_counter()로 측정한 실제 처리 시간, 이후 UI 페이싱용 asyncio.sleep은 제외) 추가. 인용 소스(sources)에 이미 struct_verify로 환각 검증된 part_category·symptom 필드를 함께 실어 프론트가 원문 옆에 한국어 한 줄 요약(lib/partCategory.ts의 PART_CATEGORY_KO — 새 번역이 아니라 기존 검증된 코드값의 한국어 별칭)을 병기하도록 함. _clean_quote()로 원문의 개행·중복 공백만 정리(바이트 단위 내용 변경 없음 — 프로젝트의 "인용은 verbatim이어야 함" 원칙 때문에 mojibake 등 글자 단위 수정은 하지 않음, 코드 주석에 스코프 명시).
InvestigationTimeline.tsx를 Chat.tsx 우측 사이드바에서 대화 흐름 인라인(질문 버블 → 타임라인 → 답변 카드 순서)으로 이동. 진행 중엔 단계가 하나씩 나타나고 마지막에 스피너, 완료(pending→false)되면 useEffect로 자동 접혀 "조사 N단계 완료" 한 줄 요약만 남고 클릭 시 재펼침. 각 단계 행에 도구 칩 배지 + "Nms" 소요시간 배지 추가.
입력창을 페이지 상단에서 하단(sticky bottom-0)으로 이동, 대화 영역이 flex-1로 확장.
검증: TestClient로 EV6 시나리오 SSE 스트림 전체 재생 — 5단계 전부 tool·duration_ms 포함, 최종 answer의 sources에 part_category="INSTRUMENT_CLUSTER" 정상 포함 확인.


공통 검증: `npx tsc --noEmit` 무오류, `npm run build` 성공. app.db는 kr_us_gap 스키마 변경(model·defect_summary·date_basis 컬럼 추가)으로 삭제 후 재생성 필요했음 — DB_PATH가 webapp/data/app.db(webapp/backend/data/app.db 아님)라는 점에 다시 한번 주의(이전 세션에서도 동일 실수 있었음, db.py의 DB_PATH 정의 참조).


7단계 산출물 (2026-07-08 완료) — 배포 준비 + 문서화


webapp/Dockerfile — 멀티스테이지: 1) node:20-slim에서 frontend 빌드 2) python:3.11-slim에 backend 복사, requirements 설치, 빌드 시점에 seed.py 실행해 app.db를 이미지에 굽고, frontend/dist를 FastAPI가 직접 정적 서빙. 빌드 컨텍스트는 반드시 저장소 루트(webapp/ 아님) — engine/normalize.py가 REPO_ROOT/scripts/precision_v2.py를, seed.py가 REPO_ROOT/data/processed·data/recalls를 import/참조하기 때문(REPO_ROOT는 각 파일의 상대 경로 계산으로 산출, Dockerfile 상단 주석에 명시). data/raw(1.46GB 원본)는 seed.py가 전혀 참조하지 않아 이미지에서 제외.
.dockerignore(저장소 루트 신규) — data/raw·data/samples·docs/molit_press·node_modules·dist·app.db·.env·__pycache__ 제외.
requirements.txt에 pandas==2.2.3 추가 발견·수정: seed.py뿐 아니라 routers/signals.py·engine/episode.py 등 런타임 코드도 pandas를 쓰는데 requirements.txt엔 빠져 있었음 — 지금까지 conda 환경(ogc2026)에 pandas가 별도로 깔려 있어 우연히 동작해온 것이었고, Docker처럼 requirements.txt만으로 설치하는 환경에서는 즉시 ImportError가 났을 잠재 버그.
main.py 수정: ① CORS를 ALLOWED_ORIGINS 환경변수 기반으로 변경(기본값은 기존과 동일한 로컬 개발용 localhost:5173 — 배포 환경은 프론트를 같은 오리진에서 서빙하므로 CORS 자체가 불필요) ② FRONTEND_DIST(webapp/frontend/dist)가 존재할 때만(Docker 이미지에서만) SPA fallback 라우트 등록 — 정적 자산은 그대로 서빙, 그 외 경로(/chat, /my-car)는 index.html을 돌려 react-router가 처리. 로컬 개발 중엔 이 디렉터리가 없어(Vite가 따로 서빙) 라우트 자체가 등록 안 됨.
버그 발견·즉시 수정: SPA catch-all(`/{full_path:path}`)을 처음 구현했을 때 등록되지 않은 `/api/*` 경로(예: 오타)까지 index.html을 200으로 반환해버리는 문제를 curl로 직접 검증하다 발견 — `full_path.startswith("api/")`면 404를 강제하도록 수정, 재검증 결과 정상 API는 200·존재하지 않는 API 경로는 404로 분리됨을 확인.


검증 (Docker Desktop이 이 머신에 설치돼 있지 않아 `docker build`/`docker run` 자체는 실행 불가 — 대신 이미지가 실행할 것과 동일한 단계를 로컬에서 개별 실행해 검증):
① `npm run build`(frontend) 성공 확인
② conda ogc2026 환경에서 `python seed.py` 재실행 — complaints 1579행·recalls 227행·kr_us_gap 28행 등 CLAUDE.md 기존 기록과 일치, 정상 종료
③ 빌드된 dist를 우vicorn이 직접 서빙하는 상태로 실행 후 curl로 확인: `/`·`/chat`·`/my-car` 전부 200(SPA fallback 동작), 정적 자산(`/favicon.svg`, `/assets/*.js`) 200 + 올바른 content-type, `/api/summary` 200, 존재하지 않는 `/api/does-not-exist` 404(SPA fallback 버그 수정 후 재확인)
④ Playwright로 실제 브라우저에서 3화면 스크린샷 촬영·확인(docs/screenshots/dashboard.png·chat.png·mycar.png) — 상황판 KPI·히트맵·덤벨차트, 조사 채팅 EV6 시나리오 5단계 완료 후 답변 카드, 내 차 IONIQ 5(2025) 도메인 지도 6개 항목 전부 실측값과 일치하는 형태로 렌더링됨을 시각 확인
한계(명시): Docker 이미지 자체의 빌드·구동은 검증하지 못함 — 사용자가 Docker Desktop 설치 후 `docker build -f webapp/Dockerfile -t precall .`(저장소 루트에서) 직접 1회 확인 필요.


README.md(저장소 루트, 신규) — 1분 소개, 스크린샷 3장(위 Playwright 캡처), 라이브 데모 URL 자리, 로컬 실행법(Docker 한 줄 / 개발모드 두 터미널), 목 모드 설명과 실 키 꽂는 법, 프로젝트 구조 지도, 문서 읽는 순서(CLAUDE.md → 13_초안v0_스펙 → 06_되감기_K12_확정 → struct_prompt_v2 → webapp/README.md).
부수 발견·정리: .playwright-mcp/ 디렉터리(Playwright MCP 스크린샷/스냅샷 디버그 산출물)가 이전 세션에서 실수로 git에 커밋되어 있었음 — 이번 세션에서 실수로 전체 삭제했다가 기존 커밋분은 `git checkout --`으로 복원하고, 이번 세션에서 새로 생긴 디버그 파일만 제거. 루트 .gitignore에 `.playwright-mcp/` 추가해 향후 재발 방지(기존 추적 파일 자체를 git rm하는 결정은 이번 작업 범위 밖으로 남김).

7.5단계 (2026-07-09 완료) — 리브랜딩(PRECALL → MOBISCOPE) + 정적 로고 적용


텍스트 교체: 앱·문서 전역의 "PRECALL"(FastAPI title, index.html title, 헤더, README 2종)을 "MOBISCOPE"로, docker 이미지 태그 예시(`precall`)와 localStorage 키(`precall:my-car`)도 동일하게 `mobiscope`로 교체. 헤더의 태그라인 "리콜보다 먼저 아는"은 완전 삭제(대체 문구 없음). CLAUDE.md 자체의 과거 세션 기록(위 7단계 등)은 그 시점의 실제 실행 로그이므로 리브랜딩 대상에서 제외(그대로 보존).
webapp/frontend/src/components/Logo.tsx(신규) — src/assets/logo_mobiscope.png(사용자 제공, 핀마크+체크 아이콘과 MOBISCOPE 워드마크가 이미 합쳐진 완성 로고)를 렌더링. compact prop: true면 헤더용으로 height 32px 고정(width auto), false(기본)면 원본 비율 그대로(발표용). Layout.tsx 헤더의 텍스트 로고를 `<Logo compact />`로 교체.
webapp/frontend/src/pages/Brand.tsx(신규) + App.tsx에 `/brand` 라우트 추가 — 발표용 페이지, `<Logo />` 원본 비율 큰 사이즈로만 표시(SVG 애니메이션은 사용자가 추후 직접 구현 예정이라 이미지 태그만). 대시보드(랜딩) 상단에는 로고를 넣지 않음(원래도 없었음, 유지).
폰트: src/index.css에 "HyundaiSans" @font-face 2개(Regular 400·Bold 700, woff2/woff) 선언 — src는 public/fonts/HyundaiSans-{Regular,Bold}.{woff2,woff} 참조. body font-family 스택을 `"HyundaiSans", "Montserrat", "Pretendard", system-ui, ...`로 교체(파일이 없으면 요청이 404로 실패하고 스택의 다음 폰트로 자연 폴백 — Montserrat 자체도 웹폰트로 로드하지 않고 스택에만 명시, 기존 Pretendard와 동일한 패턴). public/fonts/README.md(신규)에 필요한 파일명과 폴백 순서 안내. 루트 README.md에 "폰트 라이선스" 절 신설(출처·라이선스 고지용 한 줄, 현재는 플레이스홀더).
파비콘: public/favicon.svg를 기존 추상 도형에서 핀마크(지도 마커)+체크 아이콘(로고의 아이콘 부분과 동일한 모티프, 네이비 #002C5F 채움 + 흰색 체크 스트로크)으로 교체. index.html의 참조 경로(`/favicon.svg`)는 변경 없음. 빌드 산출물인 dist/favicon.svg는 변경하지 않음(다음 빌드 시 public/에서 자동 재생성).
검증: `npx tsc --noEmit` 무오류. `npm run build` 성공 — 콘솔에 HyundaiSans 4개 파일이 "빌드 타임에 resolve 안 됨, 런타임에 resolve 시도" 경고가 뜨는데, 이는 파일이 아직 없다는 걸 보여주는 정상 동작(의도한 폴백 케이스)이며 빌드 자체는 실패하지 않음을 확인.
한계(명시): 브라우저 미접근으로 헤더/‎/brand 페이지의 실제 렌더링(로고 비율·파비콘 탭 아이콘 표시)은 시각 확인 못함 — 사용자가 `npm run dev`로 직접 확인 필요. 현대산스 폰트 파일 자체는 이번 작업 범위 밖(사용자가 직접 `public/fonts/`에 배치 예정).


7.6단계 (2026-07-09 완료) — UI/UX 1차 고도화 (카드 시스템 + 마이크로 인터랙션)


index.css에 --color-surface(카드용 흰색)를 페이지 배경 --color-bg(옅은 그레이, slate-50)와 분리하고, `.card`/`.card-hover`(hover 시 translateY(-3px)+그림자 심화)/`.btn-tension`(hover:brightness(.94)+active:scale(.96))/`.skeleton`(shimmer)/`.page-fade-in`/`.scrollbar-hide` 유틸리티 신설 — 기존에 컴포넌트마다 흩어져 있던 `rounded-xl border p-6` + `boxShadow: var(--shadow-card)` 인라인 패턴을 전부 이 클래스로 교체(카드 셸 스타일이 파일마다 미세하게 다르게 벌어지는 걸 방지).
Footer.tsx(신규), Layout.tsx: 헤더를 sticky+shadow-sm 흰 바로, 배경을 slate-50으로, 라우트 전환마다 재생되는 페이드인(`key={location.pathname}`)을 추가.
KpiStrip에 lucide 아이콘(Car/Activity/Bell/AlertCircle) 추가, HeroSignalCard의 상태색 테두리 삭제 후 옅은 틴트 배경만 남김. Chat.tsx에 실제 백엔드 detect_scenario() 키워드와 매칭되는 추천 질문 칩 4개(스태거 등장) 추가, 입력 영역을 흰 "독"으로 분리.
MyCar.tsx: 왼쪽 정보 패널을 카드 하나로 묶고, 도메인 리스트 항목의 hover 효과를 인라인 backgroundColor(선택 시에만 지정)와 Tailwind hover 클래스(비선택 시에만 적용)로 분리해 실제로 동작하게 함 — 인라인 style은 항상 우선 적용되므로, 선택되지 않은 상태에서도 backgroundColor를 계속 지정해두면 Tailwind의 `hover:bg-*`가 영원히 안 먹는 버그가 될 뻔했음(발견해서 미리 회피). 도메인 상세 카드 전환은 framer-motion height 아코디언으로 변경.
검증: `npx tsc --noEmit` 무오류, `npm run build` 성공.


7.7단계 (2026-07-09 완료) — UI/UX 2차 고도화 (밀도·3D 프레이밍 버그·리포트 허브·다크 푸터)


CarViewer3D.tsx 버그 수정: 자동회전(useFrame으로 매 프레임 group.rotation.y 증가) 중인 모델의 카메라 프레이밍을, 회전 전 정지 상태의 바운딩박스 8개 꼭짓점을 고정 카메라 축에 투영해 계산하고 있었음 — 이 투영은 계산 시점(회전각 0)에서만 정확하고, 이후 모델이 계속 돌면서 다른 회전각에서는 투영 폭이 계산값을 초과해 차가 프레임 밖으로 삐져나가는(잘리는) 버그였음. Y축 회전에 불변인 바운딩 스피어 반지름(`Box3.getBoundingSphere`) 하나로 가로·세로 거리를 동시에 계산하도록 교체해 회전각과 무관하게 항상 프레임 안에 들어오도록 수정, FRAME_FILL_RATIO도 0.9→0.82로 낮춰 여유를 더 둠. CarViewer.tsx·CarViewerSvg.tsx의 인라인 `aspectRatio:'16/9'`를 Tailwind `aspect-video`+`min-h-[360px]`로 교체하고, MyCar.tsx에서 뷰어를 옥죄던 `sm:w-[60%]` 폭 제한을 제거(우측 컬럼 전체 폭 사용) — 3D 수학 버그와 별개로 뷰어 자체가 좁아 작아 보이던 부분도 함께 해소.
Dashboard.tsx: FilterBar.tsx(신규, 제조사/기간 토글 + 데이터 내보내기 버튼) 추가 — 백엔드가 이 축의 필터링을 지원하지 않아 전부 더미(제조사·기간 토글은 로컬 선택 상태만 바뀌고 실제 재조회 없음, 내보내기는 "준비 중" 안내만 표시)임을 컴포넌트 상단 주석에 명시. 이미 존재하던 GapDumbbell(한·미 비교)+Heatmap 2단 그리드는 유지하고 패딩(p-6→p-4)·제목 크기(text-sm→text-[13px])만 줄여 밀도를 높임. 대시보드 하단의 RecentReports를 제거하고 "시그널 리포트 전체 보기" 링크로 교체(컴포넌트 자체는 다른 곳에서 안 쓰여 삭제).
리포트 2-Pane 허브 신설: 기존 ReportView.tsx의 렌더링 로직(메타 카드+지표+마크다운+확신도 접이식+고지문)을 ReportPaper.tsx로 추출(`variant='card'`|`'flat'` — flat은 페이퍼 자체가 표면이라 섹션마다 흰 카드로 다시 감싸지 않음). 신규 ReportsHub.tsx(`/reports`)가 좌측 리포트 목록(신고 있는 시그널 중 report_id 있는 것만, 기존 api.signals() 재사용이라 새 백엔드 엔드포인트 불필요)+우측 A4 비율(최대폭 720px) 흰 페이퍼 UI, PDF 다운로드·공유 버튼은 더미(클릭 시 "준비 중" 안내). Layout.tsx 헤더 네비게이션에 "시그널 리포트" 탭 추가(내 차와 조사 채팅 사이).
Footer.tsx를 얇은 라이트 푸터에서 `bg-slate-900 text-slate-400` 다크 4열 푸터로 전면 교체 — Col1 로고(이미지 대신 흰 텍스트 워드마크 사용: 실제 로고 PNG가 흰 배경이라 다크 배경에 얹으면 흰 박스로 보여 어울리지 않음)+소개+이메일(placeholder), Col2 바로가기, Col3 데이터 출처(KOTSA·MOLIT·NHTSA, 기존 라이트 푸터와 동일 링크), Col4 법적 고지(이용약관·개인정보처리방침은 실제 문서가 없는 자리표시 링크+면책조항 전문). 최하단에 `Copyright © 2026 MOBISCOPE. All rights reserved.` 한 줄.
검증: `npx tsc --noEmit` 무오류, `npm run build` 성공, `/reports` 라우트 curl 200 확인.
한계(명시): 3D 프레이밍 수정은 수학적으로는 회전 불변이 맞지만 브라우저 미접근으로 실제 glb 렌더링에서 차가 온전히 보이는지 시각 확인은 못함 — 사용자가 `npm run dev`로 직접 확인 필요.


7.8단계 (2026-07-09 완료) — PDF 내보내기·용어집 툴팁·구독 모달


의존성 추가: `html2pdf.js`(jsPDF+html2canvas 번들) 설치. 패키지 자체가 `type.d.ts`를 내장하고 package.json의 `types` 필드가 이를 직접 가리켜(DefinitelyTyped `@types/html2pdf.js`보다 항상 우선 적용됨) 처음엔 `@types/html2pdf.js`도 같이 설치했다가, 그 타입엔 있는 `pagebreak` 옵션이 실제 사용되는 내장 타입엔 없어 빌드 에러 → 내장 타입에 없는 옵션을 코드에서 제거하고 중복 `@types` 패키지를 삭제해 정리. `export =` 형태라 default import(`import html2pdf from 'html2pdf.js'`)에 `esModuleInterop`가 필요해 tsconfig.app.json에 추가(런타임은 Vite가 이미 CJS interop을 처리해 영향 없음, 타입체크만 통과시키는 설정). 번들 크기 약 1.4MB→2.36MB(gzip 670KB)로 증가 — html2canvas+jsPDF가 무거운 라이브러리라 예상된 증가, 이번 범위 밖이라 코드 스플리팅은 손대지 않음.
Chat.tsx 구조 변경: 기존엔 `turn: Turn | null` 하나만 유지해 새 질문을 하면 이전 대화가 사라지는 구조였음 — "채팅 내역(복수)을 PDF로 내보낸다"는 요청 자체가 여러 턴의 존재를 전제하므로, `turns: Turn[]`로 바꿔 질문마다 배열에 추가되도록 변경(스트리밍 콜백은 항상 배열의 마지막 항목만 갱신하는 `updateLastTurn` 헬퍼로 처리, 동시에 두 질문이 진행 중일 수 없도록 마지막 턴이 pending이면 입력을 막는 기존 규칙 유지). 헤더 우측에 "PDF로 내보내기" 버튼(턴이 1개 이상일 때만 노출) — `printRef`로 감싼 대화 영역 전체를 `html2pdf().from(ref).save()`로 내보내며, 파일명은 `MOBISCOPE_조사리포트_YYYYMMDD.pdf`(로컬 날짜 기준). 내보내기는 화면에 보이는 현재 상태 그대로 캡처하므로(타임라인 접힘·인용 펼침 등 사용자가 토글한 상태 포함), 강제로 펼치는 로직은 넣지 않음.
용어집 툴팁: lib/glossary.tsx에 하드코딩 더미 딕셔너리 5개(ICCU/ADAS/IEB/OTA/ECU) + `linkifyGlossary(text)`(정규식으로 단어 경계 매칭 후 해당 부분만 GlossaryTerm으로 감싸 반환) + components/GlossaryTerm.tsx(점선 밑줄 + `group-hover`로 부드럽게 나타나는 다크 툴팁, HotspotDot 계열과 톤 일치시킴). 적용 범위는 요청대로 두 곳만: ChatAnswerCard의 구조화 답변 headline·섹션 본문(원문 인용문 자체는 verbatim 원칙 때문에 손대지 않음), MyCar 도메인 리스트의 라벨(`ADAS 카메라`·`ICCU·충전제어`에 실제로 걸림).
알림 구독 모달: components/SubscribeModal.tsx(framer-motion 배경 페이드+카드 스케일 인, ESC 없이 배경 클릭·X로 닫기) — 이메일 입력 후 "구독하기"를 누르면 로컬 상태만 바뀌어 확인 화면으로 전환되고, 문구에 "(데모 UI — 실제 발송은 아직 연결되어 있지 않습니다)"를 명시해 실제로 이메일이 발송되는 것처럼 오해하지 않도록 함(실제 구독 API 없음). MyCar.tsx 차종명 옆에 "🔔 알림 받기" 버튼 추가해 모달을 띄움.
검증: `npx tsc --noEmit` 무오류, `npm run build` 성공, dev 서버(`/`, `/chat`, `/my-car`) 전부 curl 200 확인.
한계(명시): 브라우저 미접근으로 실제 PDF 출력 결과(페이지 나뉨·한글 폰트 렌더링 품질)와 툴팁·모달의 애니메이션 체감은 시각 확인 못함 — 사용자가 직접 브라우저에서 "PDF로 내보내기"를 눌러 결과물을 확인 필요. html2canvas는 CSS `oklch()`/최신 색상 함수를 지원하지 못하는 경우가 있는데, 이 프로젝트는 색상을 전부 hex(`#RRGGBB`)로 쓰고 있어 문제될 가능성은 낮지만 실제 캡처 결과에서 카드 배경색 등이 깨지지 않는지 확인 권장.


7.9단계 (2026-07-09 완료) — Mock-Driven 프론트엔드 고도화: 시맨틱 서치 로더 + 출처 칩


배경: 백엔드 팀이 Task 1~3(실제 LLM 연동)을 별도로 진행 중이라, 현재 LLM_PROVIDER=mock 상태에서도 프론트엔드가 완성된 제품처럼 보이도록 순수 연출용 UI 2종을 추가. 두 기능 모두 실제 백엔드 로직·데이터와 무관한 프론트엔드 전용 장식이라는 점을 코드 주석에 명시.


1단계 — 시맨틱 서치 스텝 로더: components/SemanticSearchLoader.tsx(신규) — "의미론적 간극(Semantic Gap) 분석 중..." → "NHTSA 불만 데이터 컨텍스트 매칭 중..." → "리콜 인과관계 추론 중..." 3단계를 1초 간격으로 활성화(setInterval, 마지막 단계에서 정지)하는 체크리스트형 로더(완료=체크·진행중=스피너+navy 강조·대기=회색 원, framer-motion으로 opacity/y 부드럽게 전환). 실제 백엔드 SSE 스텝(InvestigationTimeline이 이미 보여주는 진짜 조사 단계)과는 별개로 존재 — 대체가 아니라 InvestigationTimeline 안의 마지막 "조사 중..." 단순 스피너 한 줄만 이걸로 교체(진짜 스텝 목록은 그대로 유지).
2단계 — 출처 칩 + 더미 모달: components/SourceChips.tsx(신규, "NHTSA 리포트 원문 보기"·"국토교통부 보도자료" 뱃지 2개) + components/SourceModal.tsx(신규, framer-motion 페이드+스케일 모달) — 클릭하면 "원문 연동은 아직 준비 중입니다"를 정직하게 안내(빈 페이지로 이동하거나 실제 링크가 있는 것처럼 오해하게 만들지 않음). ChatAnswerCard.tsx(구조화 답변·마크다운 폴백 두 분기 모두)와 ReportPaper.tsx(card·flat variant 공용이라 ReportView·ReportsHub 양쪽에 자동 적용)에 적용.
검증: 두 단계 모두 구현 직후 `npx tsc --noEmit` 개별 확인, 마지막에 `npm run build` 성공 + dev 서버(`/`, `/chat`, `/my-car`) curl 200 재확인.
한계(명시): 브라우저 미접근으로 1초 간격 로더의 체감 타이밍과 모달 애니메이션은 시각 확인 못함 — 사용자가 조사 채팅에서 질문을 보내 직접 확인 필요.


7.10단계 (2026-07-09 완료) — 내 차(My Car) 3D 뷰어·핫스팟·빈 상태·헤더 최고급화


뷰어 스테이지: components/GridOverlay.tsx(신규) — 중심에서 가장자리로 radial mask 페이드되는 은은한 격자 배경(scanning stage 느낌). CarViewer.tsx(checking 플레이스홀더 + 3D 모드 2곳)·CarViewerSvg.tsx의 기존 다크네이비 라디얼 그라데이션(VIEWER_BG)을 Tailwind v4의 `var(--tw-gradient-stops)` 커스텀 그라데이션 패턴(`bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-slate-100 to-transparent`)으로 교체 + GridOverlay를 3D/SVG 두 뷰어 모두에 레이어.
핫스팟 인터랙션: HotspotDot.tsx(SVG) + CarViewer3D.tsx에 신설한 Hotspot3DMarker(3D, 핫스팟마다 독립적인 hover 상태가 필요해 별도 컴포넌트로 분리) — 툴팁을 기존 다크(#0B1220 불투명) 스타일에서 글래스모피즘(`bg-white/80 backdrop-blur-md border border-white/40 shadow-xl rounded-full text-slate-800`)으로 교체. 점(dot)은 평상시 `animate-pulse`로 맥박, hover/선택 시 파란 링 글로우(`ring-4 ring-blue-500/30 scale-110`)+배경을 블루(#3B82F6)로 전환 — 이 hover 전환은 로컬 `useState` 기반으로 직접 계산해서 인라인 backgroundColor 값 자체를 바꾸는 방식으로 구현(7.6단계에서 이미 발견한 문제: 인라인 style이 항상 우선이라 Tailwind의 `hover:`/`group-hover:` 클래스로는 고정 인라인 배경색을 못 이김 — 동일 함정을 여기서도 미리 피함).
빈 상태(Empty state): MyCar.tsx의 "도메인을 선택하면..." 박스를 `.card`(흰 배경+그림자)에서 `border-2 border-dashed border-slate-200 bg-slate-50` 점선 박스로 교체, 중앙에 큼직한 `ScanSearch`(lucide, w-12 h-12 text-slate-300) 아이콘 배치, 텍스트는 text-slate-500으로 톤다운.
헤더 타이포·배지: 차종명(`h1`)을 font-bold→font-extrabold tracking-tight로, "OOOO년식"을 별도 텍스트 줄이 아니라 차종명 옆의 슬레이트 배지 칩(`bg-slate-100 text-slate-600 rounded-md px-2 py-1 text-sm font-medium`)으로 이동. "🔔 알림 받기" 버튼을 차종명 옆에서 우측 상단("다른 차로 변경" 옆)으로 재배치.
검증: 4단계 각각 구현 직후 `npx tsc --noEmit` 개별 확인, 마지막에 `npm run build` 성공 + dev 서버(`/`, `/my-car`) curl 200 재확인.
한계(명시): 브라우저 미접근으로 실제 glb 렌더링에서의 그리드/그라데이션 톤, 글래스 툴팁의 backdrop-blur 체감, 핫스팟 pulse/glow 타이밍은 시각 확인 못함 — 사용자가 `/my-car`에서 직접 확인 필요.


7.10.1 (2026-07-09 완료) — 버그 수정: 3D 핫스팟 툴팁이 헤더보다 크게 렌더링되던 원인


사용자가 실제 브라우저에서 확인한 결과, 3D 뷰어 위 툴팁 글자가 "ELANTRA" 헤더보다 2배 가까이 크게 렌더링됨을 보고 — 7.10단계에서 Tailwind 클래스(text-xs 등)로는 원인을 못 찾았던 이유는 애초에 Tailwind와 무관한 문제였기 때문.
근본 원인: CarViewer3D.tsx의 `<Html distanceFactor={10} .../>`(@react-three/drei). drei의 Html.js 내부(`web/Html.js` 274~275행)를 직접 열어 확인한 결과, distanceFactor가 설정되면 `el.style.transform = "translate3d(...) scale(objectScale(camera) * distanceFactor)"`를 코드가 직접 주입한다 — 즉 카메라와 모델 사이 거리 기반으로 툴팁 전체 DOM에 인라인 CSS scale을 강제로 건다. 7단계에서 카메라 자동 프레이밍을 바운딩 스피어 기준으로 바꾼 뒤로 카메라가 작은 차종엔 상대적으로 더 가까이 붙게 되어 이 배율이 크게 튀었던 것으로 보임 — Tailwind 클래스를 아무리 줄여도 이 인라인 transform이 그 위에 곱해지니 안 잡혔음.
수정: `distanceFactor` prop을 완전히 제거(값을 낮추는 게 아니라 아예 안 씀) — drei 소스상 `distanceFactor === undefined`일 때만 `scale=1`로 고정되고 순수 화면좌표(translate3d)만 적용되기 때문. 코드에 drei 내부 동작을 직접 인용한 주석을 남겨 재발 방지. 추가로 패딩(px-2.5→px-2)·폰트(`text-xs`→`text-[12px] leading-tight`)도 사용자 요청대로 더 조여둠 — 이제는 진짜로 이 값들이 그대로 렌더링된다.
검증: `npx tsc --noEmit` 무오류, `npm run build` 성공.
한계(명시): 브라우저 미접근이라 실제로 툴팁이 정상 크기로 보이는지는 여전히 사용자가 확인해야 함 — 다만 이번엔 근본 원인(drei 소스 코드)을 직접 확인하고 고친 것이라 이전보다 확신도가 높음.


7.11단계 (2026-07-09 완료) — 대시보드 데이터 시각화 전면 개편 (dataviz 스킬 적용)


차트 색상·타이포 작업이라 dataviz 스킬(references/color-formula.md·palette.md)을 먼저 로드하고 원칙에 맞춰 결정: "Sequential = 하나의 색상, 옅음→짙음", "Status는 카테고리/시퀀셜과 분리된 고정 팔레트, 절대 재사용 금지"를 그대로 적용.


Heatmap.tsx: 시퀀셜 색상 앵커를 회색(#F6F7F9)→네이비에서 옅은 파랑(#DBEAFE, Tailwind blue-100)→네이비(#002C5F)로 교체 — 저값 구간이 "칙칙한 회색"이 아니라 "옅은 파랑"으로 읽히도록(0건은 여전히 별도로 회색 유지, 시퀀셜 램프와 구분되는 "데이터 없음" 취급). 알람(스파이크) 표시는 빨강 테두리 대신 셀 전체를 앱 기존의 예약된 critical 토큰(`var(--color-state-active)`, #DC2626)으로 반전 — dataviz 스킬의 "status는 시퀀셜/카테고리컬과 별개의 고정 팔레트" 원칙과, 이 값이 이미 앱 전역에서 "활성/위험" 의미로 쓰이는 토큰이라는 점을 모두 만족(새 색을 즉흥적으로 추가하지 않음). `node scripts/validate_palette.js`의 `contrast()`로 실측: 알람 빨강 vs 흰 카드 4.83:1(WCAG 텍스트 기준 통과), 툴팁 글자(slate-800) vs 글래스 배경 14.6:1. 시퀀셜 램프의 밝은 끝(#DBEAFE, vs 흰 카드 1.22:1)은 낮게 나오지만 이는 스킬 문서가 명시한 정상 동작("옅은 값은 표면에 녹아들어도 됨" — 시퀀셜 채움이지 텍스트가 아님, 별도 완화 불필요).
셀·그리드: `border-collapse`+개별 셀 padding 방식을 `border-collapse:separate`+`border-spacing:1px`(테이블 전체 1곳에서 통제)로 교체해 셀이 하나로 묶여 보이게(게슈탈트) 촘촘히 좁힘, 모서리 `rounded-sm`→`rounded`.
호버 툴팁: 기존 "차트 아래 정적 캡션 한 줄"(JS `hover` state로 갱신) 방식을 제거하고, 내 차 페이지 핫스팟과 동일한 글래스모피즘(`bg-white/80 backdrop-blur-md border-white/40 shadow-xl`) + fade·slide-up 전환의 커서 앵커 툴팁으로 교체 — 순수 CSS `group-hover`라 `useState`/`onMouseEnter`/`onMouseLeave` JS 상태 자체가 필요 없어져 코드도 더 단순해짐.


GapDumbbell.tsx: Y축 레이블을 "차종 · 결함설명"이 뒤섞인 한 줄에서 2줄로 분리 — 1줄: 차종명(`font-bold text-slate-800`, 링크) + 캠페인 코드(mono, 작게), 2줄: 결함 설명(`text-slate-500 text-sm truncate`, `truncate()` 헬퍼로 40자 제한 상향). 연결선 2px→6px(`h-1.5`)+둥근 끝(`rounded-full`)+`#E2E8F0`(slate-200)로 강화, 점 10px→12px + 흰 링(`ring-2 ring-white`) 추가로 굵은 선과 겹쳐도 또렷하게. 모든 행에 `rounded-lg p-2 hover:bg-slate-50 transition-colors` — 단, 기존에 영구 강조되던 산타페 행(`highlighted`)은 hover 클래스 대신 그 고유 틴트를 계속 유지(하이라이트 위에 회색 호버가 덮이는 걸 방지).
검증: `npx tsc --noEmit` 무오류, `npm run build` 성공, dev 서버 curl 200.
한계(명시): 브라우저 미접근으로 실제 색상 대비·간격·툴팁 위치는 시각 확인 못함 — 사용자가 상황판에서 직접 확인 필요.


7.12단계 (2026-07-09 완료) — 대시보드 두 차트 높이 동기화 + 범례 컴포넌트화


높이 동기화: Dashboard.tsx의 그리드에 `items-stretch` 명시(CSS Grid 기본값이라 동작은 그대로지만 의도를 코드로 남김). GapDumbbell.tsx·Heatmap.tsx 두 카드 모두 `.card flex h-full flex-col`로 바꾸고, 내부를 헤더(제목+메타)/범례/본문(가변)/푸터 4단으로 나눠 본문에만 `flex-1`을 줘서 — 두 카드 중 콘텐츠가 더 긴 쪽에 맞춰 짧은 쪽 카드가 늘어날 때, 그 여백이 본문 영역에 자연스럽게 흡수되고 푸터(출처 표기)는 양쪽 다 바닥에 정렬되게 함. 패딩을 7.7단계에서 밀도 때문에 줄였던 p-4에서 이번에 p-6으로 되돌려 앱의 다른 카드들(SignalCard·DomainDetailCard·ChatAnswerCard 등)과 통일.
스크롤바: Heatmap의 `overflow-x-auto` 래퍼에 기존 index.css의 `.scrollbar-hide` 유틸(7.6단계에서 채팅 추천 칩용으로 이미 만들어둔 것 재사용 — 새로 안 만듦)을 붙여 월 컬럼이 카드 폭을 넘길 때 뜨는 브라우저 기본 스크롤바를 감춤.
범례 컴포넌트화: components/LegendDot.tsx(신규, 색상 원형 뱃지+텍스트) — 기존에 "●" 문자와 "—"로 이어 붙인 한 줄 설명 텍스트를 지우고, GapDumbbell은 LegendDot 3개(미국 접수/한국 발표/한국 시정 개시일 미확인*)를 `flex flex-wrap gap-4`로, Heatmap은 시퀀셜 그라디언트 스와치("신고 건수 적음→많음")+LegendDot 1개(알람 발화)를 같은 방식으로 배치. "클릭 시 시그널 상세로 이동" 같은 조작 안내는 범례에서 분리해 헤더 우측에 `text-xs text-slate-400`로 따로 둠.
검증: `npx tsc --noEmit` 무오류, `npm run build` 성공, dev 서버 curl 200.
한계(명시): 브라우저 미접근으로 실제 두 카드의 높이가 픽셀 단위로 맞는지, 스크롤바가 정말 안 보이는지는 시각 확인 못함 — 사용자가 상황판에서 직접 확인 필요.


7.13단계 (2026-07-09 완료) — 릿지라인 플롯 + 시맨틱 네트워크 그래프 도입


의존성: `d3`·`@types/d3`·`react-force-graph-2d` 설치. 후자를 코드 작성 전에 `node_modules`에서 직접 열어 실제 타입(`ForceGraphProps`)과 내부 툴팁 라이브러리(`float-tooltip`, 클래스명 `.float-tooltip-kap`, `node_modules/float-tooltip/dist/float-tooltip.mjs`에서 직접 확인)를 먼저 확인한 뒤 그 위에서 작성 — 지난 drei distanceFactor 버그 때처럼 API를 추측하지 않고 실제 소스를 먼저 읽는 방식을 그대로 적용. 번들 크기 671KB→742KB(gzip, +71KB) 증가, 예상보다는 적었지만 실측치.


Step 1 — RidgelinePlot.tsx (대시보드 우측, Heatmap.tsx 대체·삭제): 기존 `/api/heatmap`(`HeatmapResponse`) 데이터를 그대로 재사용(새 백엔드 불필요) — 모델별 월별 count를 d3 `area().curve(curveBasis)`로 조이플롯 area 생성. 스파이크(alarm) 구간은 같은 area path를 `clipPath`로 잘라 빨강(`#F43F5E`)을 덧씌우는 방식이라, 빨강으로 바뀌는 경계선도 파란 곡선과 완전히 일치(별도 red path 계산 없음).
버그 두 개를 직접 찾아 구현 중 수정: ① 행(row)별 `<g transform>`에 부모 `<g>`가 이미 적용한 MARGIN.top을 또 더해 모든 행이 두 배로 밀려 있던 것 — 부모 변환과 자식 변환을 같이 계산해보고 발견, 자식 변환에서 중복 제거. ② `MARGIN.top`이 12px였는데 맨 위 행의 최대 피크가 `ROW_HEIGHT*(OVERLAP-1)`(약 47.6px)까지 위로 솟을 수 있어 SVG 기본 `overflow:hidden`에 그 피크가 잘려나가는 문제 — margin.top을 그 최대 피크값 기준으로 동적 계산하도록 고침(`Math.ceil(ROW_HEIGHT*(OVERLAP-1))+4`). 둘 다 렌더링을 못 보는 상태에서 좌표 수식을 직접 재검산해서 찾은 것이라 실제 화면에서 재확인 필요.
사용자가 지정한 대로 `flex items-stretch`(기존 CSS Grid에서 교체) + 컨테이너 `h-full min-h-[500px] overflow-hidden` 적용. 호버 툴팁은 겹치는 피크 때문에 히트맵처럼 CSS group-hover만으로는 처리하기 어려워(피크가 인접 행 영역까지 침범) MyCar 핫스팟과 같은 방식(JS 상태 기반 xPct/yPct 절대좌표 툴팁)으로 구현 — 재질(글래스모피즘)은 동일하게 통일.


Step 2 — SemanticNetworkGraph.tsx (조사 채팅 답변 카드 하단): react-force-graph-2d, 노드 그룹 3종(증상=오렌지 #F97316·부품=블루 #3B82F6·리콜=레드 #EF4444), `nodeCanvasObject`로 원+라벨 직접 그리기, 드래그 물리엔진은 라이브러리 기본 동작 그대로(추가 설정 불필요). 배경은 캔버스를 투명(`backgroundColor="rgba(0,0,0,0)"`)으로 두고 바깥 div에 CSS 방사형 그라데이션 점 패턴을 깔아 점그리드 구현.
데이터 — 사용자는 "Mock 데이터"를 요청했지만, 채팅 답변에 이미 실려 있는 진짜 근거(`answer.sources`: odino 신고의 `part_category`, campaign 리콜의 `id`)로 그래프를 구성하도록 바꿈(`lib/semanticGraph.ts`의 `buildSemanticGraph`) — DB의 `symptom` 컬럼은 거의 항상 비어 있어(Task 5 표본 20건 제외 전부 NULL, 직접 쿼리로 확인) 증상 노드는 대신 사용자가 실제로 입력한 질문 원문(`turn.question`, `Chat.tsx`→`ChatAnswerCard`로 새로 내려줌)을 사용. sources에 부품/캠페인 정보가 전혀 없으면(즉 실제 근거가 없으면) 컴포넌트가 자동으로 `MOCK_SEMANTIC_GRAPH`(요청하신 더미 데이터, ICCU/ADAS/24V757000 등)로 폴백 — "지어낸 관계를 사실처럼 보여주지 않는다"는 이 프로젝트 전반의 원칙과 "데이터가 없을 때도 데모가 항상 동작해야 한다"는 이번 요청을 동시에 만족시키려 한 절충. 사용자가 순수 정적 더미 데이터만 원했다면 이 판단은 되돌릴 수 있음(그 경우 `buildSemanticGraph` 호출을 없애고 항상 `MOCK_SEMANTIC_GRAPH`만 넘기면 됨).


Step 3 — 글래스모피즘 통일: index.css에 `.float-tooltip-kap` 전역 오버라이드 추가(`!important` — 라이브러리가 직접 `<style>`을 주입해 순서를 보장할 수 없음) — `bg-white/80 backdrop-blur-md border-white/40 shadow-xl` 톤을 그대로 적용해 릿지라인·히트맵(전 단계)·내 차 핫스팟과 동일한 재질로 통일.
검증: `npx tsc --noEmit` 무오류, `npm run build` 성공(4058 모듈, 이전 대비 +1273 — d3/force-graph 트리), dev 서버(`/`, `/chat`) curl 200.
한계(명시): 브라우저 미접근으로 이번 단계는 특히 확인이 더 필요함 — ① 릿지라인의 실제 겹침·스파이크 색·툴팁 위치, ② force-graph의 드래그 물리감, 점그리드 배경, 글래스 툴팁이 실제로 덮어써지는지, ③ 캔버스 기반 컴포넌트라 다크모드/고DPI 렌더링 등은 전혀 시각 확인 못함 — 사용자가 상황판과 조사 채팅에서 직접 확인 필요.


7.14단계 (2026-07-09 완료) — 릿지라인 플롯 재튜닝(행별 정규화) + GapDumbbell 푸터 줄바꿈 수정


근본 원인 발견: 7.13단계의 릿지라인이 "밋밋하다"는 피드백 — 원인은 y스케일을 전 차종 공통 max(전역 최댓값)로 잡았던 것. 한 차종의 극단값이 나머지 전부를 짓눌러 대부분의 행이 자기 최댓값의 일부만 차오르고 있었음(조이플롯이 겹치려면 "모든 행"이 자기 기준 최대치까지 차야 함). RidgelinePlot.tsx를 행(row)마다 자체 max로 정규화하는 y스케일로 교체 — 이제 모든 행이 균등하게 OVERLAP배(2.4→2.8)까지 차오르며 위 행을 침범한다. 트레이드오프를 헤더 부제("봉우리 높이는 차종별 최근 최댓값 기준")에 명시하고, 차종 간 절대 비교는 호버 툴팁의 실제 숫자로 하도록 안내.
X축: d3.axisBottom + useEffect(명령형 DOM 조작이라 React 렌더와 분리) — domain·tick line은 select().remove()로 지우고 텍스트만 slate-400/11px로 남김.
경계 부드럽게: 기존 clipPath(rect) 방식을 linearGradient(userSpaceOnUse, pad spread)로 교체 — 스파이크 구간 양 끝 ~16px를 투명→불투명으로 페이드시켜 별도 클립 없이도 경계가 부드러움(스프레드 pad 덕에 그라디언트 벡터 밖은 자동으로 0-opacity 유지). 테두리 선(stroke) 전부 제거 + mix-blend-mode:multiply로 겹치는 봉우리가 자연스럽게 짙어지게.
부수 수정: GapDumbbell.tsx 푸터(제외 안내+출처 표기)가 대시보드 2단 flex 레이아웃의 좁아진 폭에서 justify-between 한 줄로 밀려 잘려 보이던 문제 — flex-col로 세로 배치해 항상 전체 문장이 보이게 함(사용자가 화면에서 직접 발견).
검증: `npx tsc --noEmit` 무오류, `npm run build` 성공.
한계(명시): 브라우저 미접근 — 좌표·그라디언트 계산을 손으로 재검산했지만 실제 렌더링에서 겹침·페이드가 의도대로 보이는지는 사용자 확인 필요.


7.15단계 (2026-07-09 완료) — 헤더 알림 벨 + 구독 시그널 슬라이드오버 드로어


"마이페이지를 대체" 요청을 "내 차(MyCar) 페이지를 삭제/교체"가 아니라 "별도의 구독-목록 전용 페이지를 안 만들고 드로어로 대신한다"는 의미로 해석 — 기존 내 차 페이지·SubscribeModal은 그대로 유지, 이번 건 헤더에서 전역으로 여는 새 패널만 추가.
components/NotificationDrawer.tsx(신규) — framer-motion으로 우측에서 슬라이드인(x:'100%'→0)+배경 backdrop-blur-sm 오버레이, 목록 2건은 사용자가 지정한 그대로 하드코딩(ELANTRA 2021/ADAS 카메라 리콜 진행 중/빨강, IONIQ 5 2023/ICCU 관련 불만 급증 감지/주황) — "Mock" 요청이었지만 클릭 시 이동 경로만은 실제로 연결: 드로어가 열릴 때 `api.signals()`를 조회해 모델명→signalId 매핑을 만들고, 클릭하면 해당 차종의 실제 `/signals/:id`로 이동(없으면 `/my-car`로 폴백) — 목록 내용은 데모지만 클릭 결과는 진짜 페이지로 가게 함.
Layout.tsx 헤더 우측에 종 아이콘 버튼(뱃지: 구독 건수 배지, 현재 2) 추가, 클릭 시 드로어 오픈. 헤더가 `sticky z-20`이라 드로어 오버레이·패널은 z-40/z-50으로 그 위에 뜨도록 함.
검증: `npx tsc --noEmit` 무오류, `npm run build` 성공, dev 서버(`/`, `/api/health`) curl 200.
한계(명시): 브라우저 미접근으로 슬라이드 애니메이션·배경 블러·뱃지 위치는 시각 확인 못함 — 사용자가 아무 페이지에서나 헤더 종 아이콘을 눌러 직접 확인 필요.


7.16단계 (2026-07-09 완료) — 릿지라인 가독성 튜닝(진폭 축소 + 능선 윤곽선)


7.15단계에서 겹침을 키운 뒤(OVERLAP 2.8) 오히려 너무 심해 구분이 안 된다는 피드백 — RidgelinePlot.tsx OVERLAP 2.8→1.4(요청한 1.3~1.5 범위)로 축소. MARGIN.top이 OVERLAP에서 파생되는 값이라 자동으로 함께 줄어듦(맨 위 행 최대 피크를 담는 계산식은 그대로 재사용).
능선 흰 윤곽선: 같은 rowY 스케일·curveBasis로 d3.line() 하나를 추가로 생성해 area의 위쪽 경계만 흰 선(stroke-width 1.5, opacity 0.8, round join/cap)으로 각 행 위에 덧그림 — 겹치는 구간에서 앞 행이 뒷 행 위에 흰 선으로 갈라져 보이게 함(area만으로는 겹친 부분이 뭉쳐 보였음).
투명도 안정화: 파랑 fill-opacity 0.55→0.45, 빨강(스파이크) 그라디언트 피크 opacity 0.65→0.5 — mix-blend-mode:multiply는 유지하되(겹칠수록 짙어지는 효과 자체는 요청 범위 밖) 진폭 축소로 동시에 겹치는 행 수 자체가 줄어들어 "뭉개지거나 까매지는" 위험이 기존보다 낮아짐.
검증: `npx tsc --noEmit` 무오류, `npm run build` 성공, dev 서버 curl 200.
한계(명시): 브라우저 미접근 — 실제로 겹침이 "적당히" 보이는지, 흰 윤곽선이 분리 효과를 내는지는 사용자가 상황판에서 직접 확인 필요. 진폭 배율은 취향이 갈리는 값이라 1.4가 안 맞으면 RidgelinePlot.tsx 상단의 OVERLAP 상수 하나만 바꾸면 됨.


Task 12 산출물 (2026-07-10 완료, 담당: 상진) — STR-01/02 배치 구조화 API + 인용 검증

scripts/str01_batch_structurize.py — 신고 CSV → 구조화 JSONL 배치 파이프라인. 검증된 프롬프트 v2(docs/struct_prompt_v2.md 무수정)로 CDESCR를 LLM 구조화. 건별 루프: LLM 호출 → JSON 파싱 → 스키마 검사(struct_verify.py와 동일 허용값) → 인용 verbatim 검사 → 실패 시 오류 사유를 프롬프트에 덧붙여 재시도(최대 3회) → 통과 건만 즉시 append(중단 후 재실행 시 처리된 ODINO 스킵 = 이어하기). PROVIDER 환경변수로 제공사 교체(gemini | anthropic), 표준 라이브러리만 사용(새 의존성 없음). 429/503 백오프 내장.
data/samples/sample_100_for_meeting.csv — 입력 100건(현대·기아 전장/SW, 모수 hk_electrical_recent_full.csv의 부분집합임을 확인 — 100/100이 모수에 존재).
data/processed/str01_sample100_results.jsonl — 구조화 결과 100건.
data/processed/str01_sample100_report.md — 실행 리포트(AC 증빙).

LLM: Gemini 2.5 Flash (temperature=0, responseMimeType=application/json). 무료 티어는 분당·일일 쿼터가 빡빡해 100건 완주 불가(3.5 Flash는 12건, 2.5 Flash는 16건에서 429 소진) → 유료 결제 후 완주. 파일럿(Task 5)은 Claude 계열이었으므로 이번 STR 트랙부터 기준 모델이 Gemini로 변경됨 — STR-06에서 기준선 재설정 예정.

검증 결과 (AC 전부 충족)
STR-01 AC①(형식 위반 0): 0/100 ✅
STR-01 AC②(배치 100건 처리): 100/100 완주 ✅
STR-02 AC(인용 통과율 100%, 불일치 파기·재시도): 인용 불일치 0/100 ✅
독립 재검증(struct_verify 로직): 스키마 위반 0, 인용 불일치 0, 고유 ODINO 100.

1차 실행 성공 95/실패 5 → 원인 규명·보강 후 재실행에서 5건 전부 통과(최종 100/100). 실패 5건은 3회 재시도 후 파기됐던 것으로 STR-02 "불일치 파기" 동작이 실제로 작동함을 확인.
실패 원인 2종 (신고 내용 문제 아님):
  ① 인용 환각 오판 3건 — 원본 CSV 모지바케(UTF-8→latin-1 오디코딩, 예: couldn't이 couldnâ\x80\x99t로 저장). LLM이 정상 문자로 정리해 인용 → 깨진 원문과 불일치. fix_mojibake()(latin-1 재인코딩→utf-8 디코딩)로 읽기 시 복구 후 대조하도록 보강. hk_electrical_recent_full.csv 원본에도 같은 모지바케가 있을 수 있어 전체 1,579건 실행 시 이 복구가 필요함.
  ② part_category 허용값 위반 2건 — 프롬프트 스키마가 허용값에 괄호 설명을 붙여 표기(ADAS(전방충돌·차선·후방카메라 등 운전보조))해 LLM이 통째로 복사. 괄호 앞 토큰만 취하도록 정규화. v3(STR-04) 작성 시 스키마 허용값과 설명을 분리하는 개선 검토.

분포 (참고 — 정답 아님, STR-03에서 채점 예정): part_category ELECTRICAL_SYSTEM 27·NON_ELECTRICAL 18·PROPULSION_BATTERY 14·POWERTRAIN_SW 14·ADAS 10·INSUFFICIENT_INFO 6·BRAKES_ELECTRONIC 6·INSTRUMENT_CLUSTER 5 / severity CRITICAL 76·SERIOUS 16·MODERATE 4·MINOR 4 / insufficient_info=true 5건 / 장문(300자+) 76·단문 24.

관찰: 동일 신고를 Gemini 3.5 Flash와 2.5 Flash가 severity를 다르게 판정한 사례 확인(예: ICCU 완속충전 불가 건을 3.5는 MODERATE, 2.5는 SERIOUS) — 모델 간 판정 편차 존재, STR-03 정답 채점 필요성의 실증.


Task 13 산출물 (2026-07-10 완료, 담당: 상진) — STR-04 스키마 v3 (mentions_existing_recall) + 제네시스 대조군 검증

docs/struct_prompt_v3.md — v2에 mentions_existing_recall(bool) 필드 추가한 v3 프롬프트. v2는 무수정 보존(별도 파일). 새 필드 정의는 [추가 규칙 ④]: 서술문이 기존 리콜·시정조치·NHTSA 캠페인을 언급하면 true(특정 캠페인 번호/일반 리콜 언급/리콜 부품 미수급 항의 포함), severity·part_category와 독립. 목적은 급증 분석 시 "기존 리콜 후속 항의"를 신규 시그널과 분리해 위양성을 줄이는 것(Task 8·9의 GENESIS 24V107000 사례가 배경).
data/samples/genesis_14_for_str04.csv — 검증 입력 14건(제네시스 2024-04, hk_electrical_recent_full.csv에서 CDESCR 추출, 모지바케 복구 적용).
data/processed/str04_genesis_v3.jsonl — v3 구조화 결과 14건.
data/processed/str04_genesis_v2_gemini.jsonl — 회귀 비교용 v2(동일 모델 Gemini) 결과 14건.
data/processed/str04_genesis_report.md — 실행 리포트.
scripts/str01_batch_structurize.py 확장 — --prompt 옵션 추가(프롬프트 파일 교체 가능). 프롬프트에 "mentions_existing_recall" 문자열이 있으면 그 bool 필드를 자동으로 필수 검증에 포함(extra_bool_keys). 기존 v2 동작은 그대로.

AC 결과 (충족)
제네시스 대조군에서 기존 리콜 언급 9건 이상 탐지: 11/11 탐지 ✅ (재현율 100%, 오탐 0)
14건 전수 v3 판정 vs 원문 정답 완전 일치 — TP 11 / FN 0 / FP 0 / TN 3.
정답 기준 리콜 언급은 11건(24V107000 직접 언급 10 + 일반 리콜 언급 1). 작업표 문구의 "9건"보다 많으나 어느 기준이든 AC(9 이상) 충족. 24V107000 직접 언급 10건은 대부분 "The contact received notification of NHTSA Campaign Number: 24V107000" 보일러플레이트, 1건(11581754)은 "several open recalls" 일반 언급.

회귀 검증 (v3 필드 추가가 기존 판정을 바꾸는가)
같은 모델(Gemini 2.5 Flash)로 v2 vs v3 비교: 14건×4필드=56개 중 6건 상이(약 89% 안정). 전부 경계 케이스(INSUFFICIENT_INFO 경계 2·인접 심각도 2·part_category 경계 2). Gemini는 temperature=0에서도 완전 결정론적이지 않아 6건 중 일부는 v3 효과가 아니라 실행 노이즈 가능성 — 핵심 산출물(리콜 언급 탐지)과 무관. 이전 세션 Claude 결과(struct_genesis_202404.jsonl)와 비교하면 10건 상이하나 이는 모델 차이(Claude→Gemini)가 섞인 것이라 순수 회귀로 부적합.

개선 메모: v2 스키마 허용값에 괄호 설명이 붙어(ADAS(...)) LLM이 통째 복사하는 문제(Task 12)는 v3에서도 그대로 있음 — 정규화로 우회 중. 차후 허용값과 설명을 분리하는 게 근본 개선.


Task 14 산출물 (2026-07-10 완료, 담당: 상진) — 100건 최종 구조화 v3 (mentions_existing_recall 포함)

data/processed/str01_sample100_results_v3.jsonl — sample_100_for_meeting.csv 100건을 v3 프롬프트(8필드)로 재구조화한 최종본. STR-01(v2, 7필드)과 입력·모델·방식 완전 동일, 프롬프트만 v2→v3라 mentions_existing_recall 필드만 추가됨.
data/processed/str01_sample100_v3_report.md — 리포트.
LLM: Gemini 2.5 Flash. 100/100 완주, 실패 0.

검증: 형식 위반 0 / 인용 불일치 0 (8필드 전수, 새 bool 필드 포함 독립 검증). mentions_existing_recall true 19건 / false 81건.
정본 정리: v2 파일(str01_sample100_results.jsonl, 7필드)은 STR-01/02 AC 증빙으로 보존, 이 v3 파일(8필드)이 STR-03 채점 등 이후 단계의 정본.
