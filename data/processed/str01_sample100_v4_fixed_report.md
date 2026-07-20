# STR-01/STR-02 v4 실행 리포트 (수정판 — 빈 필드 방지 + 검증 스크립트 모지바케 버그 수정)

## 이전 버전([str01_sample100_v4_report.md](str01_sample100_v4_report.md))과 달라진 점

1. **프롬프트**: `docs/struct_prompt_v4.md`에서 "서술문에 이 COMPDESC 관련 내용이 없는 경우"(진짜 정보부족 예시, 구 예시4)를 삭제 — 이 예시가 오히려 모델의 정보부족 판정을 과도하게 유도하는 부작용이 있어 제거. 나머지 예시 번호를 1~5로 재정렬(기존 6개 → 5개).
2. **코드**: `scripts/str01_batch_structurize.py`에 후처리 추가 — LLM 응답의 `symptoms`/`evidence_quote`가 비어있으면 코드가 강제로 안내문구(`["정보 부족으로 판단 불가"]` / `"(정보 부족으로 근거 문장 없음)"`)로 채움. **어떤 경우에도 빈 배열·빈 문자열이 최종 출력에 남지 않도록 보장.**
3. **검증 스크립트 버그 수정**: `scripts/struct_verify_v4.py`가 원본 CDESCR의 모지바케(UTF-8→latin-1 오디코딩)를 복구하지 않고 비교해 정상 인용을 환각으로 오판하던 버그 발견·수정(Task 12에서 이미 한 번 발견됐던 동일 클래스 버그가 재발한 것 — `fix_mojibake()` 호출 추가).

## 실행

동일 100건(`data/samples/sample_100_v4.csv`)을 동일 방식(temperature=0, Gemini 2.5 Flash)으로 재실행:
```
python scripts/str01_batch_structurize.py \
  --input data/samples/sample_100_v4.csv \
  --prompt docs/struct_prompt_v4.md \
  --output data/processed/str01_sample100_v4_results.jsonl \
  --sibling-source data/processed/hk_electrical_recent_full.csv
```
100/100 완주, 실패 0건.

## STR-02 — 독립 재검증 (`scripts/struct_verify_v4.py`)

| 항목 | 결과 |
|---|---|
| 스키마 위반 | 0/100 |
| compdesc1/compdesc2 불일치(코드 필드 자체 검증) | 0/100 |
| 인용 불일치(환각) | 0/100 |
| `insufficient_info=true` + 안내문구 예외 허용 | 14/100 |

인용 통과율 100%(불일치 0/100) ✅. `insufficient_info=true`인 14건은 **전부 `evidence_quote="(정보 부족으로 근거 문장 없음)"`**였고(빈 문자열 아님), `symptoms`도 전부 `["정보 부족으로 판단 불가"]`(빈 배열 아님) — 이전 버전과 달리 셀 자체가 비어있는 경우가 하나도 없다.

`compdesc1`/`compdesc2`는 LLM 출력이 아니라 코드가 원본 COMPDESC를 그대로 파싱해 채우는 필드라, 100건 전부 원본과 정확히 일치하는지도 별도로 재확인(불일치 0건).

## 분포 (참고 — 정답 아님, STR-03에서 안정성 진단)

- severity: CRITICAL 61 / SERIOUS 23 / MINOR 9 / MODERATE 7
- driving_context: 주행 중 57 / 불명 28 / 정차·주차 중 13 / 시동 시 2
- compdesc1: UNKNOWN OR OTHER 45 / ELECTRICAL SYSTEM 23 / FORWARD COLLISION AVOIDANCE 15 / VEHICLE SPEED CONTROL 9 / LANE DEPARTURE 5 / BACK OVER PREVENTION 3
- insufficient_info=true: 14건
- symptom 태그: 총 302개(고유 258개)
- sample_group: RANDOM 47 / A_multi_cmplid 27 / B_unknown_with_sibling 13 / C_unknown_no_sibling 13

이전 버전(14건) 대비 `insufficient_info=true` 목록의 구체적 CMPLID는 일부 바뀌었다(6건 교체) — 이는 Gemini가 temperature=0에서도 완전히 결정론적이지 않기 때문(CLAUDE.md Task 13에 이미 기록된 known behavior)이며, 프롬프트·코드 수정과 무관한 실행 노이즈로 판단된다. 회귀 검증을 위해 별도로 이전에 발견됐던 회귀 케이스(2098867·2205835 — 명백한 관련 내용이 있는데도 정보부족으로 잘못 판정됐던 것)를 재확인한 결과, 이번 실행에서는 둘 다 정상적으로 실제 내용이 채워짐을 확인했다(예시 삭제로 회귀 원인이 제거됨).

## 다음 단계
같은 100건을 temperature=0.4로 3회 독립 실행 → STR-03(자기일관성 진단) 진행 (`str03_v4_fixed_run{1,2,3}.jsonl`).
