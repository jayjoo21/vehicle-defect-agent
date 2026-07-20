# 100건 최종 구조화 (v3) 리포트 — mentions_existing_recall 포함

## 개요
- **목적**: STR-04에서 추가한 `mentions_existing_recall` 필드를 포함한 **최종 100건 구조화 JSON** 생성
- **입력**: `data/samples/sample_100_for_meeting.csv` (100건, STR-01과 동일)
- **프롬프트**: `docs/struct_prompt_v3.md` (8필드)
- **출력**: `data/processed/str01_sample100_results_v3.jsonl`
- **LLM**: Gemini 2.5 Flash (temperature=0)
- **방식**: STR-01과 완전 동일 (배치·검증·재시도·이어하기). 프롬프트만 v2→v3, 출력 필드만 7→8.

## 결과
- 100/100 완주, 실패 0 (재시도 1건)
- 독립 검증: **형식 위반 0 / 인용 불일치 0** (8필드 전수, 새 필드 bool 검증 포함)
- `mentions_existing_recall`: true 19건 / false 81건
  - true = 서술문이 기존 리콜·NHTSA 캠페인을 언급한 신고 (급증 분석 시 "리콜 후속 항의"로 분리 대상)

## v2 100건(str01_sample100_results.jsonl)과의 관계
- v2 결과는 7필드, 이 v3 결과는 8필드(mentions_existing_recall 추가)
- 나머지 필드 생성 방식·모델·입력 동일. STR-03 채점은 이 v3 최종본을 대상으로 하면 됨(8필드 전체).
- v2 파일은 STR-01/02 AC 증빙으로 이력 보존, v3 파일이 이후 단계의 정본(canonical).
