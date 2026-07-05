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
