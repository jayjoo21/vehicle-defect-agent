# STR-01/STR-02 v4 실행 리포트

## 배경 — v4로 바뀐 것

원본 NHTSA 데이터(`hk_electrical_recent_full.csv`, 16,964행)를 다시 들여다본 결과, 같은 신고(ODINO)가 여러 결함 유형을 가질 때 NHTSA가 이미 CMPLID(행) 단위로 분리해뒀다는 걸 발견했다. v4는 이 구조를 그대로 활용해 **처리 단위를 ODINO → CMPLID로 바꾸고**, `COMPDESC`(부품 분류)를 코드가 `compdesc1`(대분류)/`compdesc2`(중분류)로 잘라 LLM에게 "이 앵커에만 집중하라"는 입력으로 준다. `compdesc1`이 `UNKNOWN OR OTHER`일 때만 같은 ODINO의 다른 행(형제) COMPDESC를 조회해 "이미 처리된 부분은 배제하라"는 근거로 추가 제공한다. 자세한 설계는 [docs/struct_prompt_v4.md](../../docs/struct_prompt_v4.md) 참조.

## 표본 — sample_100_v4.csv

`hk_electrical_recent_full.csv`(16,964행, 51개 원본 컬럼 전부)에서 100건 추출([scripts/sample_v4_100.py](../../scripts/sample_v4_100.py)):

| 그룹 | 건수 | 목적 |
|---|---|---|
| A_multi_cmplid | 27행 (11개 ODINO) | 다중 CMPLID 앵커링이 실제로 작동하는지 검증 — ODINO의 행 전부 포함 |
| B_unknown_with_sibling | 13행 | UNKNOWN OR OTHER + 형제 COMPDESC 있음 케이스 검증 |
| C_unknown_no_sibling | 13행 | UNKNOWN OR OTHER + 단독 행 케이스 검증 |
| RANDOM | 47행 | 나머지 전체에서 무작위 |
| **합계** | **100행** | 고유 ODINO 84건, 고유 CMPLID 100건 |

## 실행

- LLM: Gemini 2.5 Flash, temperature=0(운영 기본값), `responseMimeType=application/json`
- 형제 COMPDESC 조회는 표본이 아니라 **원본 전체(`hk_electrical_recent_full.csv`)를 인덱스로 사용** — 표본 밖에 있는 형제 행도 정확히 찾아냄(검증 완료, 아래 참조)
- 실행: `python scripts/str01_batch_structurize.py --input data/samples/sample_100_v4.csv --prompt docs/struct_prompt_v4.md --output data/processed/str01_sample100_v4_results.jsonl --sibling-source data/processed/hk_electrical_recent_full.csv`

### STR-01 결과
- 100/100 완주, 실패 0건, 재시도 발생 0건, 소요 1,075초

## STR-02 — 독립 재검증 ([scripts/struct_verify_v4.py](../../scripts/struct_verify_v4.py))

| 항목 | 결과 |
|---|---|
| 스키마 위반 | 0/100 |
| compdesc1/compdesc2 불일치(코드 필드 자체 검증) | 0/100 |
| 인용 불일치(환각) | 0/100 |
| `insufficient_info=true` + 빈 인용 예외 허용 | 14/100 |

인용 통과율 100%(불일치 0/100) ✅. `insufficient_info=true`인 14건은 전부 `evidence_quote=""`였고, 이는 v4 설계상 정상 동작(형제가 이미 다룬 내용을 제외하고 나니 남는 근거가 없거나, 서술문에 해당 COMPDESC 단서가 전혀 없는 경우)이라 예외로 허용했다 — v2/v3의 `check_quote()`였다면 이 14건 전부 "환각"으로 오탐됐을 것.

`compdesc1`/`compdesc2`는 LLM 출력이 아니라 코드가 원본 COMPDESC를 그대로 파싱해 채우는 필드라, 100건 전부 원본과 정확히 일치하는지도 별도로 재확인했다(불일치 0건 — 당연히 그래야 하는 결정론적 필드이므로 검증이라기보다 회귀 확인 성격).

## 분포 (참고 — 정답 아님, STR-03에서 안정성 진단 예정)

- severity: CRITICAL 58 / SERIOUS 25 / MINOR 14 / MODERATE 3
- driving_context: 주행 중 54 / 불명 29 / 정차·주차 중 15 / 시동 시 2
- compdesc1: UNKNOWN OR OTHER 45 / ELECTRICAL SYSTEM 23 / FORWARD COLLISION AVOIDANCE 15 / VEHICLE SPEED CONTROL 9 / LANE DEPARTURE 5 / BACK OVER PREVENTION 3
- insufficient_info=true: 14건
- symptom 태그: 총 285개(고유 253개)

## 메커니즘 실동작 확인 (파일럿 5건에서 먼저 검증한 내용, 100건에도 동일 반영)

- **다중 CMPLID 앵커링**: ODINO 11486092의 UNKNOWN OR OTHER 행(CMPLID 1843078)이 다른 두 형제(VEHICLE SPEED CONTROL, FORWARD COLLISION AVOIDANCE:ADAPTIVE CRUISE CONTROL)가 이미 다룬 내용(ACC 오작동)뿐이라 남는 게 없다고 판단 → `insufficient_info=true`, `evidence_quote=""` 정상 반환
- **형제 COMPDESC 원본 전체 조회**: CMPLID 2212327(ODINO 11741656)의 형제 행(2212326, BACK OVER PREVENTION:WARNINGS)은 100건 표본엔 없고 원본 16,964행에만 있는데도 코드가 정확히 찾아내 "후방충돌방지 관련 내용은 제외하라"는 지시가 반영됨

## 다음 단계
같은 100건을 temperature=0.4로 3회 독립 실행 → STR-03(자기일관성 진단) 진행.
