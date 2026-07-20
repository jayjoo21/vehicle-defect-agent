# STR-01 / STR-02 실행 리포트 — 100건 배치 구조화 + 인용 검증

## 개요
- **입력**: `data/samples/sample_100_for_meeting.csv` (현대·기아 전장/SW 신고 100건)
- **출력**: `data/processed/str01_sample100_results.jsonl` (100건)
- **스크립트**: `scripts/str01_batch_structurize.py`
- **프롬프트**: `docs/struct_prompt_v2.md` (무수정)
- **LLM**: Gemini 2.5 Flash (`temperature=0`, `responseMimeType=application/json`)

## Acceptance Criteria 결과

| 티켓 | AC | 결과 |
|---|---|---|
| STR-01 | ① 형식 위반 0 | **0건 / 100건** ✅ |
| STR-01 | ② 배치 100건 처리 가능 | **100/100 완주** ✅ |
| STR-02 | 인용 검사 통과율 100%, 불일치 건 파기·재시도 | **인용 불일치 0/100** ✅ |

독립 검증(struct_verify 로직 재적용): 스키마 위반 0, 인용 불일치 0, 고유 ODINO 100.

## 실행 통계
- 1차 실행: 성공 95 / 실패 5
- 실패 5건은 3회 재시도 후에도 검증 미통과로 파기(STR-02 "불일치 건 파기" 동작 확인)
- 실패 원인 규명 후 스크립트 보강 → 재실행에서 5건 전부 통과 → 최종 100/100

### 실패 원인 2종 (신고 내용 문제 아님, 기술적 이슈)
1. **인용 환각 오판 3건** — 원본 CSV의 모지바케(UTF-8→latin-1 오디코딩, 예: `couldn'​t`가 `couldnâ\x80\x99t`로 저장). LLM이 정상 문자로 정리해 인용하면 깨진 원문과 불일치. → 읽기 시 `fix_mojibake()`로 복구 후 대조하도록 보강.
2. **part_category 허용값 위반 2건** — 프롬프트 스키마가 허용값에 괄호 설명을 붙여 표기(`ADAS(전방충돌·차선·후방카메라 등 운전보조)`)해 LLM이 통째로 복사. → 괄호 앞 토큰만 취하도록 정규화.

## 분포 (참고, 정답 아님 — STR-03에서 채점 예정)
- part_category: ELECTRICAL_SYSTEM 27 / NON_ELECTRICAL 18 / PROPULSION_BATTERY 14 / POWERTRAIN_SW 14 / ADAS 10 / INSUFFICIENT_INFO 6 / BRAKES_ELECTRONIC 6 / INSTRUMENT_CLUSTER 5
- severity: CRITICAL 76 / SERIOUS 16 / MODERATE 4 / MINOR 4
- insufficient_info=true: 5건
- 장문(300자+) 76건 / 단문(300자 미만) 24건 → STR-03 장문/단문 분리 채점 대비

## 비고
- provider 교체 가능 구조(`PROVIDER` 환경변수: gemini | anthropic). 동일 스크립트로 전체 1,579건 실행 가능.
- 관찰: 동일 신고를 Gemini 3.5 Flash와 2.5 Flash가 severity를 다르게 판정한 사례 확인 → 모델 간 판정 편차 존재, STR-03 채점 필요성의 실증.
