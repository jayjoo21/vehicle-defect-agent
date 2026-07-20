# STR-04 실행 리포트 — 스키마 v3 (mentions_existing_recall) + 제네시스 대조군 검증

## 개요
- **목적**: 구조화 스키마에 `mentions_existing_recall`(bool) 필드 추가 → 신고가 기존 리콜을 언급하는지 판별
- **프롬프트**: `docs/struct_prompt_v3.md` (v2 무수정 보존, v3는 별도 파일)
- **검증 데이터**: 제네시스 2024-04 신고 14건 (`data/samples/genesis_14_for_str04.csv`)
- **출력**: `data/processed/str04_genesis_v3.jsonl`
- **LLM**: Gemini 2.5 Flash (temperature=0)

## 새 필드 정의 (v3 [추가 규칙 ④])
서술문이 기존 리콜·시정조치·NHTSA 캠페인을 언급하면 `true`. 특정 캠페인 번호(예: 24V107000), 일반적 기존 리콜 언급("several open recalls"), 기존 리콜 부품 미수급 항의 포함. severity·part_category 판정에는 영향 없는 독립 필드.

## AC 결과

| AC | 결과 |
|---|---|
| 제네시스 대조군에서 기존 리콜 언급 9건 이상 탐지 | **11/11 탐지** ✅ |

### 상세 (14건 전수, v3 판정 vs 원문 정답)
- 정답(원문에 리콜/캠페인 언급): **11건** (24V107000 직접 언급 10 + 일반 리콜 언급 1)
- v3가 true로 탐지: **11건**
- 제대로 탐지(TP) 11 / 놓침(FN) 0 / 오탐(FP) 0 / 정탐음성(TN) 3
- **재현율 11/11 = 100%, 오탐 0** — 14건 전부 정답과 일치

> 참고: 작업표 AC 문구는 "리콜 언급 9건"이나, 원문 직접 확인 결과 리콜 언급은 11건(24V107000 직접 10 + 일반 1)이었음. 어느 기준이든 AC 문턱(9 이상)을 충족.

## 회귀 검증 (v3 필드 추가가 기존 판정을 바꾸는가)
같은 모델(Gemini 2.5 Flash)로 v2·v3를 각각 돌려 기존 4필드(part_category/severity/driving_context/insufficient_info) 비교:
- 14건 × 4필드 = 56개 비교 중 **6건 상이 (약 89% 안정)**
- 상이 건은 전부 경계 케이스: INSUFFICIENT_INFO 경계 2건("The contact had not experienced a failure" 류 보일러플레이트), 인접 심각도 등급 2건(SERIOUS↔CRITICAL/MODERATE), part_category 경계 2건
- **주의**: Gemini는 temperature=0에서도 완전 결정론적이지 않아, 이 6건 중 일부는 v3 프롬프트 효과가 아니라 실행 노이즈일 수 있음. 핵심 산출물(리콜 언급 탐지)과는 무관.
- (참고) v2를 이전 세션 Claude 결과(struct_genesis_202404.jsonl)와 비교하면 10건 상이하나, 이는 모델 차이(Claude→Gemini)가 섞인 것이라 순수 회귀로 부적합 — 위 같은-모델 비교가 정확.

## 산출물
- `docs/struct_prompt_v3.md` — v3 프롬프트
- `data/samples/genesis_14_for_str04.csv` — 검증 입력 14건
- `data/processed/str04_genesis_v3.jsonl` — v3 구조화 결과
- `data/processed/str04_genesis_v2_gemini.jsonl` — 회귀 비교용 v2(동일 모델) 결과
- 스크립트: `str01_batch_structurize.py`에 `--prompt` 옵션 추가(프롬프트 교체), v3 필드 자동 검증
