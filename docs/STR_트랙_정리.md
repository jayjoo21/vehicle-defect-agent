# STR 트랙 정리 (담당: 상진)

> 신고 구조화(STR) 트랙 전체 작업 정리 문서. **계속 갱신하는 살아있는 문서**다.
> 각 티켓 절에 그 단계에서 만든 파일·한 일·시행착오·의미를 함께 적는다. 티켓 완료/수정 시 해당 절과 "진행 현황"을 같이 업데이트할 것.
> 최종 갱신: 2026-07-19 (v4로 전면 재설계 — 기존 v2/v3 기록은 삭제하고 v4 기준으로 재작성)

---

## 0. 트랙 개요

NHTSA 소비자 신고(자유 텍스트)를 LLM으로 정형 데이터(JSON)로 바꾸는 것이 STR 트랙이다.

- **입력**: 원본 NHTSA 데이터(`hk_electrical_recent_full.csv`, 16,964행, 51개 컬럼). 핵심 발견 — 같은 신고(ODINO)가 CMPLID(행) 단위로 여러 개로 나뉘고, 이때 COMPDESC(부품 분류)만 다를 뿐 CDESCR(서술문)은 완전히 동일하게 복제돼 있다. 즉 하나의 신고에 여러 결함이 섞여 있으면 NHTSA가 이미 행 단위로 분리해뒀다는 뜻.
- **출력**: CMPLID 단위 구조화 JSON, 9필드(아래 표).
- **LLM**: Gemini 2.5 Flash (`temperature=0`, JSON 강제 출력). `PROVIDER` 환경변수로 제공사 교체 가능(gemini|anthropic).
- **프롬프트**: `docs/struct_prompt_v4.md` — CMPLID 단위·COMPDESC 앵커링 방식으로 v2/v3(ODINO 단위·part_category 재분류 방식)를 전면 대체.
- **9필드 스키마 (v4)**:

| # | 필드 | 채우는 방식 |
|---|---|---|
| 1 | `cmplid` | 원본 CMPLID 그대로 복사(코드) |
| 2 | `odino` | 원본 ODINO 그대로 복사(코드) |
| 3 | `compdesc1` | 원본 COMPDESC를 `:`로 분리한 첫 조각(대분류, 코드) |
| 4 | `compdesc2` | COMPDESC의 두 번째 조각(중분류, 코드. 없으면 `"no"`) |
| 5 | `symptoms` | LLM 판단, 이 COMPDESC 측면에 한정한 증상(최대 5개) |
| 6 | `severity` | LLM 판단, `CRITICAL`\|`SERIOUS`\|`MODERATE`\|`MINOR` |
| 7 | `driving_context` | LLM 판단, `주행 중`\|`정차·주차 중`\|`시동 시`\|`불명` |
| 8 | `evidence_quote` | LLM 판단, 원문 그대로(verbatim) 발췌 |
| 9 | `insufficient_info` | LLM 판단, 이 COMPDESC 측면 정보부족 여부(bool) |

`compdesc1`/`compdesc2`는 출력이 아니라 LLM에게 주는 **입력**(앵커) — "이번 호출은 이 부품 측면만 다뤄라"는 지시로 쓰인다. `part_category`(8종 재분류)·`mentions_existing_recall`은 v4에 없음(전자는 compdesc1/2로 대체, 후자는 이번 스키마에서 제외).

- **브랜치/커밋 규칙**: `feature/신고구조화(STR)` 브랜치, 커밋 메시지 끝에 "(상진)".

---

## 1. 진행 현황 (한눈에)

| 티켓 | 내용 | 상태 |
|---|---|---|
| v4 설계 | CMPLID 단위·COMPDESC 앵커링 재설계 | ✅ 완료·푸시 |
| STR-01 (v4) | 100건 배치 구조화 | ✅ 완료·푸시 |
| STR-02 (v4) | 인용(환각) 자동 검사 | ✅ 완료·푸시 |
| STR-03 (v4) | 자기일관성(temperature) 진단 | ✅ 완료·푸시 |
| 빈 필드 방지 수정 | symptoms/evidence_quote 빈 값 방지 + 검증 버그 수정 | ✅ 완료·푸시 |
| STR-05 | 사용자 입력 구조화 (차종·증상 추출) | ✅ 완료·푸시 (아래 2절, 내용 변경 없음) |

---

## 2. v4 설계 배경 — 왜 전면 재설계했나

**문제**: 원래(v2/v3) 방식은 ODINO 단위로 CDESCR 전체를 한 번에 구조화했다. 그런데 신고 하나에 결함이 여러 개 섞여 있으면(예: 계기판+라디오+창문+ADAS가 한 서술문에 다 나옴) 하나의 `part_category`·`severity`로 뭉뚱그려야 해서 정보 손실이 컸다.

**발견**: 원본 `hk_electrical_recent_full.csv`를 다시 보니, 같은 ODINO가 CMPLID/COMPDESC 조합으로 이미 여러 행으로 나뉘어 있고(16,964행, 고유 ODINO 13,974개 — 복수 행 ODINO 2,536개), 각 행의 CDESCR은 완전히 동일하게 복제돼 있었다. 즉 "이 신고에서 어느 부분이 어느 결함인지" 나누는 작업을 NHTSA가 이미 대략 해뒀다는 뜻 — 이 구조를 그대로 활용하면 다중결함 문제를 상당 부분 해결할 수 있다.

**설계**: 처리 단위를 ODINO → **CMPLID**로 바꾸고, COMPDESC를 코드가 `compdesc1`/`compdesc2`로 잘라 "이 앵커가 가리키는 결함 측면만 다뤄라"는 입력으로 LLM에 준다. `compdesc1`이 `UNKNOWN OR OTHER`(전체의 33.7%)일 때만 같은 ODINO의 다른 행(형제) COMPDESC를 조회해 "형제가 이미 다룬 내용은 배제하고 남는 게 있으면 그것만 다뤄라"는 근거로 추가 제공한다.

---

## 3. 만든 파일

- `scripts/sample_v4_100.py` — `hk_electrical_recent_full.csv`에서 100건 샘플링. 무작위 50건 + 검증용 50건(다중 CMPLID 앵커링 검증용 27행/11개 ODINO, UNKNOWN OR OTHER+형제있음 13건, UNKNOWN OR OTHER+형제없음 13건).
- `data/samples/sample_100_v4.csv` — 위 샘플링 결과(51개 원본 컬럼 + `sample_group`).
- `docs/struct_prompt_v4.md` — v4 구조화 프롬프트. COMPDESC 앵커링 규칙, 필드별 판단 기준 5개, few-shot 예시 5개.
- `scripts/str01_batch_structurize.py` (v4 지원 추가, 기존 v2/v3 배치 기능은 그대로 유지) — 프롬프트 본문에 `compdesc1`이 있으면 v4 모드로 자동 전환. CMPLID 단위 루프, COMPDESC 파싱, 형제 COMPDESC 조회(항상 원본 전체 16,964행을 인덱스로 사용 — 부분 표본을 처리해도 형제 유무가 정확하도록), `symptoms`/`evidence_quote`가 비면 코드가 안내문구로 강제 채우는 후처리.
- `scripts/struct_verify_v4.py` — v4 독립 재검증(스키마·인용·compdesc1/2 코드필드 일치 여부).
- `scripts/str03_consistency_analyze_v4.py` — STR-03 자기일관성 분석(CMPLID 매칭, 3개 정형필드 비교).
- `scripts/grading_sheet_v4.py` / `data/samples/grading_sheet_v4.csv` — 수동 채점표(자동 검증이 답하지 못하는 "판단이 실제로 맞았는가"를 사람이 확인하기 위함).
- `data/processed/str01_sample100_v4_results.jsonl` — 100건 구조화 결과(운영값 temperature=0).
- `data/processed/str01_sample100_v4_fixed_report.md` — STR-01/02 최종 실행 리포트.
- `data/processed/str03_v4_fixed_run1.jsonl` / `run2.jsonl` / `run3.jsonl` — temperature=0.4 3회 독립 실행 결과.
- `data/processed/str03_consistency_v4_fixed_report.md` / `_detail.csv` — STR-03 분석 리포트·상세.

---

## 4. STR-01/STR-02 (v4) — 배치 구조화 + 인용 검증 ✅

**한 일**: 100건을 CMPLID 단위로 구조화. 건별 흐름은 v2/v3와 동일(`LLM 호출 → JSON 파싱 → 스키마 검사 → 인용 검사 → 실패 시 재시도(최대 3회) → 통과 건만 저장`)하되, COMPDESC 앵커링·형제 조회 로직이 추가됐다.

**검증 결과 (최종본)**:
- 스키마 위반 0/100, compdesc1/compdesc2 코드필드 불일치 0/100, 인용 불일치(환각) 0/100
- `insufficient_info=true` 14/100 — 전부 `["정보 부족으로 판단 불가"]` / `"(정보 부족으로 근거 문장 없음)"`로 채워짐(빈 배열·빈 문자열 없음)
- severity: CRITICAL 61·SERIOUS 23·MINOR 9·MODERATE 7 / compdesc1: UNKNOWN OR OTHER 45·ELECTRICAL SYSTEM 23·FORWARD COLLISION AVOIDANCE 15·VEHICLE SPEED CONTROL 9·LANE DEPARTURE 5·BACK OVER PREVENTION 3

**시행착오 (팀장님이 알아야 할 것)**

1. **"빈 텍스트가 있으면 안 된다"는 요구사항이 프롬프트만으로는 100% 보장 안 됨.** 처음엔 few-shot 예시로 "형제가 다뤄도 성급히 포기하지 말고 다시 찾아봐라"는 지시를 추가했더니, 오히려 **구체적 COMPDESC 앵커(예: BACK OVER PREVENTION)에서 완전히 무관한 다른 부품(사각지대감지 BSD) 내용을 잘못 끌어오는 회귀**가 생겼다. 예시 하나 추가만으로도 모델이 "일단 뭐라도 찾아내자"는 쪽으로 전반적으로 더 공격적으로 바뀐 것 — COMPDESC 앵커링 원칙 자체를 침범하는 부작용이었다. → **프롬프트로 "절대 비우지 마라"를 강제하는 접근을 포기**하고, 대신 **코드 후처리**로 전환: LLM 응답을 받은 뒤 `symptoms`/`evidence_quote`가 비어있으면 코드가 고정 안내문구(`["정보 부족으로 판단 불가"]` / `"(정보 부족으로 근거 문장 없음)"`)로 채운다. `insufficient_info` 플래그로 "지어낸 게 아니라 정보부족 표시"임을 구분한다. 이 방식은 100% 결정론적이라 회귀 위험이 없다.
2. **진짜 정보부족 예시(few-shot)가 오히려 정보부족 판정을 과도하게 유도**했다. 원래 있던 "서술문에 이 COMPDESC 관련 내용이 전혀 없는 경우" 예시를 삭제 — 실제로 관련 내용이 있는데도 이 예시 패턴에 이끌려 정보부족으로 잘못 판정하는 경향이 있었다.
3. **독립 검증 스크립트(`struct_verify_v4.py`)에 모지바케 복구 누락 버그**가 있었다 — 원본 CDESCR의 인코딩 깨짐(`couldnâ\x80\x99t`)을 복구하지 않고 비교해서, LLM이 정상적으로 인용한 문장을 "환각"으로 오판했다. Task 12에서 이미 한 번 발견해 고쳤던 것과 같은 클래스의 버그가 새 검증 스크립트에 재발한 것 — `fix_mojibake()` 호출을 추가해 해결.
4. **Gemini는 temperature=0에서도 완전히 결정론적이지 않다.** 같은 프롬프트로 재실행해도 `insufficient_info=true` 목록의 구체적 CMPLID가 일부 바뀐다(수 건 단위). 프롬프트·코드 수정과 무관한 실행 노이즈로 판단.

---

## 5. STR-03 (v4) — 자기일관성(Self-Consistency) 진단 ✅

**방법론은 v2/v3와 동일**: 정답 라벨 없이, 같은 모델(Gemini)로 같은 100건을 temperature=0.4에서 3회 독립 반복 실행해 "모델 스스로 얼마나 일관되게 판단하는지" 측정한다. 다른 LLM·사람 라벨과 비교하는 게 아니라서 순환 논리 문제가 없다.

**v4에서 바뀐 점**: 비교 대상 정형필드가 5개(v3: part_category/severity/driving_context/insufficient_info/mentions_existing_recall) → **3개**(severity/driving_context/insufficient_info)로 줄었다. `part_category`는 v4에 없고(compdesc1/2로 대체, 코드가 채우는 결정론적 필드라 "흔들리는지" 측정 대상 아님), `mentions_existing_recall`도 v4 스키마 자체에 없다.

**결과**: 안정 68건 / 부분 흔들림 20건 / 불안정 12건. 필드별 3회 일치율 — severity 77%, driving_context 82%, insufficient_info 90%. 표본 그룹별 불안정 비율도 추가로 집계했으나(A_multi_cmplid 25.9%, B_unknown_with_sibling 53.8%, C_unknown_no_sibling 15.4%, RANDOM 34.0%), 각 그룹 13~27건의 작은 표본이라 확정적 결론이 아닌 참고 가설로만 취급한다.

**temperature 해석 시 반드시 짚을 것 (v2/v3와 동일한 원칙)**: 이 결과는 temperature=0.4로 일부러 흔든 것이라, "Gemini 운영(temperature=0) 판정이 이 정도로 불안정하다"고 읽으면 안 된다. 절대 수치가 아니라 "100건 중 어디를 사람이 먼저 봐야 하는가"라는 **상대적 우선순위**로만 쓴다.

---

## 6. STR-05 — 사용자 입력 구조화 (차종·증상 추출) ✅

이 티켓은 v4 재설계와 무관(CDESCR 구조화 파이프라인이 아니라 사용자 채팅 입력에서 차종·증상을 추출하는 별도 모듈)하므로 내용 변경 없음.

**한 일**: 한국어 사용자 입력에서 **차종·증상 2개만** 추출하는 모듈. 차종은 carRegistry 27종 영문 표기로 정규화, 증상은 STR-01 `symptoms` 형식(짧은 한국어 명사구). 둘 중 하나라도 없으면 그것만 콕 집어 되물어 둘 다 찰 때까지 반복(슬롯 기반 방식, 완료 시 순수 데이터 3필드만 반환).

**만든 파일**: `docs/str05_query_prompt.md`, `scripts/str05_query_understanding.py`(`extract_slots()`/`run_dialog()`), `data/processed/str05_test_results.json`(테스트 14케이스).

**AC 결과**: 차종 미인식 시 되물음 ✅ · 추출 결과 확인 문장 제공 ✅.

**웹앱 연동 지점**: `scripts/cht01_chat_pipeline.py`의 `parse_question` 자리에 `extract_slots()`를 꽂으면 된다.
