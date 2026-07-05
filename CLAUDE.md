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
