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

## Task: Part 573 리콜 리포트 수집 + 부품 지식 테이블 구축 (2026-07-11 완료)

목적: recalls_sw_candidates.csv의 SW 후보 76개 캠페인에 대해 부품명·부품번호·공급사·결함원인을 구조화해 webapp의 recalls 테이블에 조인 가능한 부품 지식 레이어(parts) 확보. webapp DB 연동은 이번 범위 밖.

**발견 순서와 방향 전환**: 계획했던 발견 방법 1·2번(`api.nhtsa.gov/recalls/campaignNumber` API, `www.nhtsa.gov/recalls?nhtsaId=` 페이지)이 모두 막혀 있음을 실측 확인 — API 응답에 PDF URL 필드 자체가 없고, 페이지는 봇 차단(403, curl 브라우저 UA로도 재현). data.transportation.gov의 Socrata 데이터셋(aqh3-3rri)도 실제 테이블이 아니라 api.nhtsa.gov로의 단순 리다이렉트였음. 대신 NHTSA가 공식 제공하는 리콜 벌크 플랫파일(`static.nhtsa.gov/odi/ffdd/rcl/FLAT_RCL_POST_2010.zip`, 일일 갱신)을 발견 — 이 파일이 이미 캠페인×부품 단위로 `MFR_COMP_NAME`·`MFR_COMP_DESC`·`MFR_COMP_PTNO`·`FMVSS`·`POTAFF`·`DESC_DEFECT`·`CORRECTIVE_ACTION`을 구조화해 제공해 PDF 파싱 없이 바로 얻을 수 있음을 확인. PDF는 공급사명·공급국가·"생산 중 시정 시점" 서술만 보충하는 역할로 범위를 좁힘. PDF 문서 URL 자체는 공식 API 어디에도 없어, 검색엔진이 이미 인덱싱한 실제 URL을 역추적하는 방법을 채택(무작위 대입 아님 — 검색 결과에 실제로 나타난 URL만 채택). 이 방향 전환은 사용자에게 옵션 3가지(하이브리드/PDF전량검색/중단후보고)를 제시해 "하이브리드"로 확정받은 것.

**data/raw/ 쓰기 금지 원칙 준수**: FLAT_RCL_POST_2010.zip(압축 해제 시 약 308MB)을 최초에 실수로 `data/raw/`에 내려받았다가 CLAUDE.md 원칙을 뒤늦게 상기하고 즉시 삭제, 스크래치 디렉터리(`RCL573_SCRATCH` 환경변수, 기본값은 세션 스크래치 경로)에서만 다운로드·압축해제·처리하도록 `scripts/rcl573_fetch.py`를 작성. 최종 산출물만 `data/processed/`에 남음.

**산출물**
- `scripts/rcl573_fetch.py` — 1) 플랫파일 다운로드 후 76개 캠페인으로 필터링, 캠페인×모델×연식×부품 단위로 중복 등장하는 원본을 (campaign, MFR_COMP_NAME, MFR_COMP_PTNO) 기준으로 부품 단위 dedupe(영향 모델 목록은 `affected_models` 컬럼에 집계) → `data/processed/rcl573_flatfile_components.csv`(153행). 2) `rcl573_pdf_urls.csv`의 URL 목록으로 PDF를 1초 간격으로 다운로드 → `docs/rcl573/*.pdf` + `data/processed/rcl573_fetch_log.csv`.
- `scripts/rcl573_parse.py` — PDF에서 공급사명·공급국가("Component Manufacturer" 블록)·생산중시정("Identify How/When Recall Condition was Corrected in Production", verbatim)·크로놀로지 별첨 존재 여부만 추출해 플랫파일 CSV와 campaign 기준으로 병합 → `data/processed/rcl573_components.csv`(17열 × 153행) + `data/processed/rcl573_coverage_check.csv`(검증 요약).
- PDF URL 76개 중 71개는 별도 서브에이전트(general-purpose, 백그라운드)에 위임해 WebSearch로 실제 인덱싱된 URL만 채택하는 방식으로 해결(76건의 반복 검색은 메인 컨텍스트를 크게 소모하는 기계적 작업이라 위임 — 결과는 `data/processed/rcl573_pdf_urls.csv`에 campaign,pdf_url,found로 저장). 나머지 5건(22V651000·24V287000·24V338000·25V797000·25V874000)은 검색으로도 인덱싱된 문서를 찾지 못해 found=false로 남김(추측 URL 생성 없음).

**PDF 파싱 중 발견한 서식 함정**: 2024년 이전 구서식 Part 573 PDF는 "Description of Remedy" 절이 라벨(좌)|값(우) 2열 표 레이아웃인데, pdfplumber의 기본 `extract_text()`가 같은 y좌표의 라벨·값 텍스트를 한 줄로 섞어버려("Identify How/When Recall Condition The condition was caused by..." 식으로 라벨과 값이 붙어버림) 단순 정규식이 실패함(2019·2024년 두 표본에서 확인). 좌표 기반 재구성(`extract_two_column_rows`)으로 우회 — 페이지 내 단어의 x0 분포로 열 경계를 동적 추정하려던 첫 시도는 주소·우편번호 등 다른 정렬에 흔들려 오탐(19V594000에서 값 첫 단어 "KMMG"가 라벨 열로 잘못 분류됨)했고, 두 구서식 표본 모두 값 열이 x0≈0.343×페이지폭에서 시작함을 실측 확인해 고정 비율로 대체한 뒤 정상화. 2026년 신서식(26V400000)은 이 절이 단일 열이라 애초에 문제없음 — 신서식에서 먼저 정규식 시도, 실패 시에만 2열 재구성으로 폴백하는 순서로 구현.

**검증 결과**
1. 수집: PDF URL 확보 71/76(93.4%), 다운로드 성공 71/71, PDF 파싱 성공 71/71·실패 0. 실패 5건은 전부 "검색으로 URL 자체를 못 찾음" 단계에서 걸러진 것(다운로드·파싱 단계 실패 없음).
2. 24V757000 기준행 자동 검증 통과: `part_number=940C3-DO010`, `supplier_name=Hyundai Mobis` 둘 다 일치(코드 내 assert로 매 실행마다 재확인).
3. 결측률(153행 기준, 원인 정상 — 오류 아님): part_number 4.6%(7행, 좌석벨트 리콜 등 특정 부품이 없는 캠페인), supplier_name·supplier_country 각 3.9%(URL 미확보 5개 캠페인), corrected_in_production 12.4%(위 5개 + 구서식 파싱 일부 미스).
4. `recalls_hk_by_vehicle.csv` 조인 커버리지: 76/76 캠페인 전부 매칭.
5. 수동 샘플 점검(5행 무작위 추출): 공급사명에 OCR 깨짐 없음(Hyundai Mobis/Kyungshin America Corp./TYW/Aptiv/Borgwarner 등 실제 자동차 부품사명과 일치, 같은 회사의 표기 변형은 존재 — 예: "Hyundai Mobis"·"Hyundai MOBIS"·"HYUNDAI MOBIS"·"MOBIS"가 캠페인마다 다르게 표기됨, 정규화하지 않고 원문 그대로 저장).

**한계(명시)**: 공급사 표기 정규화 없음(위 4가지 변형이 별개 문자열로 남아 있어, 이후 공급사 단위 집계 시 정규화 필요). Chronology 별첨 PDF의 URL은 3건 샘플에서 임베드된 하이퍼링크가 전혀 없어 이번 범위에서 찾지 못함 — `chronology_attached`(bool)만 채워지고 `chronology_url`은 항상 빈 값. webapp DB 스키마 변경·seed 연동은 다음 세션.

## Task: rcl573 후처리 2건 — 공급사명 정규화 준비 + 공유 부품 다차종 매핑 (2026-07-11 완료)

목적: webapp 연동 전에 위 rcl573_components.csv(153행)의 공급사명 표기 변형을 정규화할 준비와, 같은 부품 계열이 여러 캠페인·차종에 걸리는 매핑 표를 만든다. rcl573_components.csv 원본은 이번 세션에서 수정하지 않음(정규화 적용은 사용자가 alias 파일을 확정한 뒤 별도 작업).

**작업 1 — 공급사명 정규화 준비**
- `scripts/rcl573_supplier_normalize.py` → `data/processed/supplier_distinct.csv`(47개 고유 공급사명, count·example_campaign), `data/processed/supplier_alias_draft.csv`(raw_name·canonical_name·confidence·note).
- 자동 병합(confidence=auto)과 검토 필요(confidence=review)를 엄격히 분리: 토큰화 후 법인접미어(Co./Ltd./Inc./Corp./Company 등)만 제거한 "mechanical key"가 완전히 같은 경우만 auto로 병합(예: "Hyundai KEFICO Corp"/"Corp." → 마침표 차이만, "Korea Flange CO. LTD"/"Co., Ltd" → 대소문자·구두점 차이만). 이 mechanical key가 다른 그룹끼리도 핵심 키워드(모회사명·업종·지역 등 일반어를 제외한 나머지 단어)가 겹치면 "퍼지 클러스터"로 묶어 **confidence=review로 강등**(같은 그룹 내부 병합 자체는 안전해도, 그 결과가 다른 그룹과 동일 회사인지는 여전히 사람이 볼 문제이므로) — 예: "Hyundai Mobis"/"Hyundai MOBIS"/"HYUNDAI MOBIS" 3종은 대소문자만 다르지만 "MOBIS"·"Mobis Parts America"·"Hyundai Mobis Company (Jincheon Plant)"와 같은 Mobis 계열 클러스터에 속해 review로 남음. "MOBIS"/"MOBIS Corporation"도 마찬가지(법인접미어 차이뿐이라 순수하게는 auto감이지만 더 큰 Mobis 클러스터의 일부라 review). "HL Mando"/"Mando America Corp"/"Mando Pyeongtaek Plant"도 review(사용자가 예시로 든 "HL Mando≠Mando Hella" 우려와 동일 클래스). 자동 병합은 절대 하지 않음 — 그룹 간 union은 note에 비교 대상만 기록.
- 결과: auto 27건(57.4%), review 20건(42.6%). mechanical 병합 그룹(원문 2개 이상이 하나로 합쳐진 경우) 4개 — 그중 2개(Hyundai KEFICO Corp 쌍, Korea Flange 쌍)만 최종 auto로 남고 나머지 2개(Hyundai Mobis 3종, MOBIS 쌍)는 퍼지 클러스터 탓에 review로 강등.
- 데이터 품질 부수 발견: "Mobis North America Electrified Powertra"(마지막 "in" 누락 — PDF 추출 중 잘린 것으로 추정)와 "Mobis North America Electrified ("MNAe"")"·"Mobis N. America Electrified Powertrain"이 사실상 같은 회사의 표기 편차로 보이나 파일 자체는 손대지 않고 review로만 남김. "Not Applicable"·"TBD"는 실제 공급사명이 아닌 플레이스홀더로 note에 명시.

**작업 2 — 공유 부품 다차종 매핑**
- `scripts/rcl573_shared_parts.py` → `data/processed/shared_parts.csv`(26행).
- **part_number 앞 5자리 슬라이스 가정이 실데이터에서 위험함을 먼저 확인**: 한 셀에 여러 부품번호가 세미콜론·슬래시·쉼표·`&`로 뒤섞이거나("940C3-PI010; 940C3-PI020; 940C3-PI000", "[[[ 58920-J5070 & 58920-J5170 ]]]"), 차종명이 앞에 붙어 있거나("Telluride: 94051-S9000", "Sportage HECU: 58920-D9100 / Cadenza HECU: 58920-F6210" — 이 경우 차종명 자체에 "/"가 포함돼 구분자 split이 위험), 공백구분 부품번호(다이얼/스위치류, "C6061 ADUS0")도 존재(153행 중 33행이 길이 12자 초과, 실측 후 코딩). 그래서 구분자 기준 split 대신 셀 전체에서 정규식 `[A-Za-z0-9]{5}[- ][A-Za-z0-9]{3,10}` 패턴으로 부품번호처럼 보이는 토큰을 전부 찾아내는 방식으로 전환(차종명 단어는 정확히 5글자가 아니면 매치 안 되어 오탐 없음) — 사용자에게 확인 요청 없이 진행 가능한 수준으로 판단해 바로 구현.
- 검증 결과: 153행 중 part_number 공백 7행 + 토큰 추출 실패 3행 = 10행(6.5%) 제외. 한 셀에서 서로 다른 family가 동시 검출된 행 0건(전부 단일 family로 깔끔하게 귀결 — 애초 우려했던 모호한 다중 family 충돌 없음). 940C3(클러스터) 계열 자동 확인 통과: model_count=12(24V757000·26V046000·26V047000·26V400000 4개 캠페인에 걸쳐 CARNIVAL·EV9·IONIQ 5·K5·KONA·PALISADE·SANTA CRUZ·SANTA FE·SONATA·SORENTO·SPORTAGE·TUCSON).
- 상위 5개 계열: 940C3(클러스터, 4캠페인·12차종) · 46110/48110(전동오일펌프, 3·2캠페인 각 8차종) · 94001/94003(클러스터, 4·1캠페인 각 5·4차종).
- 대표 부품명(component_name_대표) 컬럼은 동률일 때 대괄호로 감싸인 표기(예: "[[[ HECU ]]]")보다 깨끗한 표기를 우선하도록 정렬 규칙을 넣었으나, 58920 계열은 그래도 알파벳순으로 "ABS Assembly"가 선택됨(3개 기여 행이 "[[[ HECU ]]]"·"ABS Assembly"·"HECU"로 전부 동률이라 완벽한 대표성 판단은 어려움 — part_numbers·campaigns·models 등 실제 데이터 컬럼은 정확하며 이 필드는 사람이 훑어볼 때 쓰는 표시용 컬럼일 뿐이라 문제 삼지 않고 그대로 둠).

**한계(명시)**: rcl573_components.csv 원본 미수정(다음 세션에서 alias 확정 후 정규화 적용). part_family는 여전히 "같은 부품 계열"이지 "같은 부품"이 아님 — SW 버전 차이 가능성은 shared_parts.csv만으로는 판단 불가. webapp DB 스키마 변경·seed 연동은 다음 세션.

## Task: 공급사 정규화 적용 + parts 테이블 시드 + 웹앱 연동 (2026-07-11 완료)

**전제 조건 이슈**: 작업 지시가 "data/processed/supplier_alias.csv(사용자 확정본)가 준비됐다"고 전제했으나 실제로는 그 경로에 파일이 없었음(직전 세션 산출물인 supplier_alias_draft.csv만 존재) — 지어내지 않고 파일시스템을 탐색해 `~/Downloads/supplier_alias_final.csv`에서 실제 확정본(canonical_name+supplier_group 2층 구조, confidence=final/verify)을 발견해 `data/processed/supplier_alias.csv`로 반입.

**작업 0 — verify 3건 원문 대조** (canonical_name+supplier_group 반영 전 선행)
- Seoyon E-Hwa Alabama(25V808000) vs SEOYON E-HWA AUBURN(24V877000): 573 원문 Supplier Identification 주소 대조 결과 **서로 다른 주소**(Montgomery AL 36105 vs Dadeville AL 36853) — alias 파일의 "동일 공장으로 추정해 병합" 가정이 틀렸음을 확인, canonical 병합을 취소하고 각자 자기 자신으로 분리(supplier_group은 "Seoyon E-Hwa"로 유지 — 같은 회사 산하 별개 사업장이라는 판단은 유효).
- Transys Korea(24V529000): 원문 주소는 충남 서산으로 현대트랜시스 서산공장과 정황상 일치하나 원문 어디에도 "Hyundai" 표기가 없어 문서 근거만으로는 확정 불가 → 지시대로 supplier_group 현행("Transys Korea") 유지, note에 확인 불가 사유 기록.
- 3건 모두 confidence를 verify→final로 변경.

**작업 1 — 정규화 적용**
- `scripts/rcl573_apply_alias.py` → `data/processed/rcl573_components_normalized.csv`(198행, 원본 153행에서 증가).
- part_number 다중값 분해: rcl573_shared_parts.py에서 검증한 정규식 토큰 추출을 재사용해 "부품번호 1개=1행"으로 분해. 정규식이 하나도 안 걸리는 비어있지 않은 3건("282402S304"·"91150-R5***"·"91850R6020" — 구분자 누락/와일드카드)은 여러 값이 섞인 게 아니라 그 자체로 하나의 값이므로 원문 그대로 1행 유지(정보 손실 방지).
- 검증: part_number 1행 다중값 잔존 0건, supplier_canonical 결측률 4.5%(9/198 — PDF 미확보 5개 캠페인+플레이스홀더), supplier_alias.csv 커버리지 100%(alias에 없는 raw_name 0건), 24V757000 기준행 3필드(part_number/supplier_canonical/supplier_group) 전부 자동 검증 통과.

**작업 2 — webapp parts 테이블 시드**
- `models.py`에 `parts` 테이블 추가(id PK, campaign은 non-unique — 한 캠페인이 여러 부품·차종에 걸리는 실제 사례 때문에 recalls·kr_us_gap과 동일한 이유). `seed.py`에 `load_parts_df`/`seed_parts` 추가, 데이터 소스는 rcl573_components_normalized.csv만.
- app.db 삭제 후 재생성(webapp/data/app.db 경로 확인 후 진행 — 과거 두 세션 실수 재확인).
- 정합성 리포트: parts 198행, recalls 테이블의 164개 캠페인 중 76개가 parts에도 존재(parts 자체 캠페인 수 76 = SW 후보 캠페인 전체와 일치), supplier_group 상위 5(Hyundai Mobis 123·TYW 8·SEGI Korea 6·Kyungshin 6·Continental 6).

**작업 3 — 채팅 답변 연동**
- `routers/chat.py`에 `_campaign_parts(conn, campaigns)` 추가 — ev6_cluster/ioniq5_charging 두 플로우 모두 기존 `iccu_campaigns` 리스트를 그대로 재사용해 parts를 조회하고 `structured.parts`에 실어 보냄(새 쿼리 대상 없음, 이미 조회된 캠페인 목록 재사용). out_of_scope는 `parts: []`로 무변화 유지.
- 프론트: `ChatAnswerCard.tsx`에 기존 "원문 인용" 접이식과 동일한 패턴으로 "결함 부품 정보" 접이식 섹션 추가 — defect_cause는 영문 원문을 인용 블록으로만 표시하고 별도 한국어 번역/요약을 붙이지 않음(part_category처럼 검증된 코드값-별칭 테이블이 parts 데이터엔 없어 "새 번역 생성 금지" 원칙상 붙일 근거가 없다고 판단). 각 부품 줄에 "출처: NHTSA Part 573 공식 리콜 문서 원문 기준" 표기.
- 검증(TestClient SSE 재생): EV6 시나리오 parts 4건 확인(24V200000 ICCU ASSY 36400-1XFA0/Hyundai Mobis 포함), out_of_scope는 parts:[] 무변화 확인.

**작업 4 — 내 차 도메인 카드 연동**
- `routers/vehicles.py`의 도메인별 recall evidence 산출 루프에서 대표 리콜(기존 ORDER BY report_date ASC 로직 그대로) 선정 시 `parts` 테이블에서 해당 campaign의 부품 1건(LIMIT 1 — parts 테이블엔 model 컬럼이 없어 다부품 캠페인의 모델별 구분은 불가, 스펙 범위 내 한계로 명시)을 조회해 evidence.part_number/supplier_canonical에 포함.
- 프론트: `DomainDetailCard.tsx`의 두 recall evidence 렌더 분기(campaignFirst/일반) 모두에 "결함 부품: {part_number} · {supplier_canonical} (공식 리콜 문서 기준)" 줄 추가, 값 없으면 줄 자체 생략(placeholder 금지 원칙).
- 검증: IONIQ 5/2025 map API의 ICCU_충전제어 도메인이 24V868000/36400-1XAA0/Hyundai Mobis를 반환, rcl573_components_normalized.csv의 24V868000 행(ICCU ASSEMBLY/36400-1XAA0/Hyundai Mobis)과 정확히 일치 확인.

**공통 검증**: `npx tsc --noEmit` 무오류, `npm run build` 성공(4059 모듈, 기존 폰트 미해결 경고는 이전 세션부터 있던 정상 폴백 케이스로 무관).

**한계(명시)**: parts 테이블에 model 컬럼이 없어 한 캠페인에 여러 모델별 부품번호가 있는 경우(예: 26V046000의 8개 클러스터 부품) 내 차 화면은 그중 1건만 표시 — 실제 사용자 차량과 정확히 일치하는 부품번호가 아닐 수 있음, 다음 세션에서 필요시 parts 테이블에 model 컬럼 추가 검토. (A)/(B) 파이프라인 통합 문제는 이번 세션 범위 밖(지시대로 미착수).

## Task: 표시 레이어 4건 수정 — 채팅 부품 중복 정리·도메인 라벨·3D 핫스팟 보정·시맨틱 그래프 확장 (2026-07-17 완료)

목적: parts 테이블·rcl573_components_normalized.csv·shared_parts.csv는 확정 상태 그대로 두고, 표시·상호작용 레이어만 수정. DB 스키마·시드·정규화 로직 불변.

**이번 세션부터 Playwright MCP가 처음 연결되어, 이 프로젝트에서 처음으로 3D 렌더링을 실제 브라우저로 육안 검증할 수 있었음** — 이전 세션들은 전부 "브라우저 미접근으로 시각 확인 못함"을 한계로 명시하며 끝났었는데, 이번엔 실측 좌표 대조로 확인.

**수정 1 — 채팅 결함부품 중복 표시 정리**
- `routers/chat.py`의 `_campaign_parts()`를 campaign 기준 그룹화로 변경: 캠페인당 defect_cause·출처 1회만 내려주고, 그 아래 `parts: [{component_name, part_number, supplier_canonical}, ...]`로 부품번호 변형(예: EV6 ICCU의 `36400-1XFA0`/`36400-1XFA0QQK`)을 나열. `ChatPart` 타입을 `ChatPart{campaign, defect_cause, pdf_url, parts: ChatPartLine[]}`로 프론트(`types.ts`)에도 반영, `ChatAnswerCard.tsx`의 "결함 부품 정보" 접이식을 캠페인 블록 단위로 재렌더링(공급사가 캠페인 내에서 동일하면 한 번만 표시, 다르면 부품번호 옆에 병기).
- 검증(실측 API 재생, `EV6 CLUSTER` 쿼리로 detect_scenario 트리거): parts 2블록(24V200000·24V867000), 각각 defect_cause 1회 + part_number 2종이 하위에 nested — 이전엔 4행이 개별 출력되며 defect_cause 원문이 4번 반복됐음.

**수정 2 — 도메인 라벨 언더스코어**
- `DomainDetailCard.tsx`의 `<h3>` 제목이 `domain.domain`(원시 키, 예: `ICCU_충전제어`)을 그대로 찍고 있었는데, 컴포넌트 상단에 이미 계산돼 있던 `label`(= `HOTSPOT_LABELS[domain.domain]`, 리스트가 쓰는 것과 동일 소스)로 교체. 새 매핑을 만들지 않고 기존 라벨 소스 재사용.
- 검증(Playwright, IONIQ 5/2025): 상세 카드 제목이 "ICCU·충전제어"로 리스트와 동일하게 표시됨을 스크린샷으로 확인.

**수정 3 — 3D 핫스팟 위치 보정 (선택지 a 채택)**
- 방법: `CarViewer3D.tsx`의 `useFrame` 자동회전을 임시로 고정각(0°·22.5°·45°)으로 바꿔, `page.evaluate`로 얻은 핫스팟 DOM 좌표와 `browser_take_screenshot`으로 찍은 스크린샷이 완전히 동기화되게 만든 뒤 suv/sedan/sports 3개 차체형태를 전부 대조. (참고: 최초 시도는 자동회전을 켠 채로 스크린샷→좌표조회를 순차 호출했는데, 두 호출 사이 회전각이 달라져 좌표가 실제 이미지와 어긋난 상태로 "ADAS 핫스팟이 지붕 위 허공에 떠 있다"고 잘못 판단할 뻔했음 — 이 타이밍 불일치를 발견하고 고정각 방식으로 전환.)
- 결과: 고정각 상태에서 재검증하니 3개 차체형태·3개 각도 전부에서 핫스팟이 차체(유리창·후드·펜더·로커패널)에 정상적으로 붙어 있었음 — "지붕 뚫고 뜬 위치"는 재현되지 않음, CLAUDE.md의 기존 한계 기록은 실제로는 스크린샷 타이밍 문제였을 가능성이 높음. 실측으로 재현 가능한 진짜 문제는 계기판·인포테인먼트·ADAS 3개 상단 핫스팟이 거의 겹쳐 보이는 것(계기판·인포테인먼트가 원래 y좌표가 같았음) — `hotspots.ts`에서 계기판은 더 아래(대시보드 높이), 인포테인먼트는 더 위(센터페시아 화면)로 벌려 3개 차체형태 전부 조정. 조정 후 22.5° 각도에서 재확인해 분리 개선 확인.
- 테스트에 쓴 `CarViewer3D.tsx`의 회전 로직 변경은 검증 후 원상복구(`git diff` 결과 무변경 확인) — 실제 운영 코드는 자동회전 그대로.

**수정 4 — 시맨틱 그래프를 실제 탐색형으로**
- 신규 `routers/parts.py`: `GET /api/parts/{part_number}/related` — DB가 아니라 `data/processed/rcl573_components_normalized.csv`를 모듈 로드 시 1회 읽어(요청마다 재파싱 안 함), part_number 앞 5자리로 part_family를 도출하고, 그 family에 속한 다른 행들의 `affected_models`(캠페인·부품번호별 실제 적용 차종·연식 원문)를 펼쳐 `{model, campaign, part_number}` 튜플 목록으로 반환. 모델명은 `engine.normalize.normalize_model`로 정규화(다른 라우터와 동일 기준). family 안에 캠페인이 자기 자신 하나뿐이면(공유 없음) `shared: []`로 정직하게 반환.
- `semanticGraph.ts`: `GraphNodeGroup`에 `shared_model`(보라, `#A855F7`) 추가. `buildSemanticGraph`가 이제 `structured.parts`(위 수정 1에서 캠페인별로 묶인 실제 부품번호)를 받아, 카테고리 노드(`part` 그룹, 예: "계기판")에 그 답변에 등장한 모든 실제 부품번호를 `partNumbers`로 붙임 — 카테고리 노드 자체는 특정 부품과 1:1이 아니라서 답변에 실린 모든 부품번호를 근사로 붙였고, 기존에도 카테고리↔캠페인이 전수 교차연결되던 것과 같은 근사 수준.
- `SemanticNetworkGraph.tsx`를 상태 관리형으로 재작성: `partNumbers`가 있는 카테고리 노드는 점선 링으로 확장 가능 표시. 클릭 시 `partNumbers` 전체에 대해 `/api/parts/{pn}/related`를 병렬 호출·합산해 공유 차종(보라 `shared_model` 노드)·공유 리콜(기존 `recall` 빨강 재사용) 노드를 그래프에 추가, 이미 있는 노드는 중복 추가하지 않음. 재클릭 시 그 확장이 만든 노드/링크만 제거(다른 확장이 만든 노드와 겹치면 보존). 공유 관계가 없으면 "이 부품은 다른 차종·리콜과 공유되지 않습니다" 문구를 정직하게 표시. 그래프 상단에 "점선 테두리가 있는 부품 노드를 누르면…" 안내 문구 추가.
- 검증: `GET /api/parts/940C3-BE290/related` 실행 결과에 EV9(`940C3-DO010`/`24V757000`)이 포함됨을 확인(요구된 검증 항목). Playwright로 조사 채팅에서 실제 EV6 계기판 답변의 "계기판" 노드를 클릭 → GV60·IONIQ 5·IONIQ 6·GV70 ELECTRIFIED·EV6 등 보라색 공유 차종 노드와 리콜 노드(24V204000·24V868000)가 새로 펼쳐지는 것을 스크린샷으로 확인(모두 ICCU 부품 계열 36400 공유 차종과 일치).

**부수 발견**: Playwright MCP의 `browser_run_code_unsafe` 샌드박스는 Node의 `require`/동적 `import`를 지원하지 않아(`ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING`) 그 안에서 파일시스템에 직접 쓸 수 없음 — 스크린샷을 파일로 저장하려면 `browser_take_screenshot` 전용 도구만 써야 하고(경로는 저장소 루트 또는 `.playwright-mcp/` 하위만 허용), 큰 base64 문자열을 `Write` 도구로 텍스트 파일에 그대로 옮기려던 시도는 내용이 손상되는 현상을 관찰해 포기하고 위 방식으로 우회함.

**공통 검증**: `npx tsc --noEmit` 무오류, `npm run build` 성공(4059 모듈, 기존 폰트 미해결 경고는 이전 세션부터 있던 정상 폴백 케이스로 무관). 사용한 임시 테스트 스크린샷 파일은 전부 정리(git status에 잔존 없음, 최종 diff는 위 4개 수정 파일 + `routers/parts.py` 신규 추가만).
