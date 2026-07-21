# MOBISCOPE 보고서 수치 대장 (Fact Sheet)

작성: 사전 작업 단계(report_instructions.md). 모든 수치는 저장소 실측(재계산 또는 기존 리포트 대조)으로 검증. `[확인 필요]`는 저장소에서 근거를 찾지 못한 항목.

## 0. 참고 문서 존재 여부 (중요 — 먼저 확인)

report_instructions.md는 "05·06·08·09·10·11 문서"를 근거로 지목하지만, 저장소 `docs/`에는 **06(`06_되감기_K12_확정.md`)만 실재**한다. 05·08·09·10·11번 문서, 그리고 "노션 3장/4장"·"10_실험로그.md"는 저장소 전체(파일명·grep) 검색 결과 **어디에도 없음** — 아마 노션에만 있고 아직 export되지 않은 것으로 추정. 이 문서들에 의존하는 항목(2장 "좋은 Agent 6기준", 서론의 "미국 23%/한국 42~52%/자체 46%" 삼각검증, 5.2절 "20건 strict 90%")은 전부 `[확인 필요]`로 표시함.

## 1. 서론

| 수치 | 값 | 출처 |
|---|---|---|
| 미국 SW결함 비율 23% / 한국 42~52% / 자체 삼각검증 46% | **[확인 필요 → 재조사 후에도 미확인, 본문 제외 권장]** | code/data/docs 전체 재검색(scripts/, docs/*.md, CLAUDE.md, README.md) 결과 report_instructions.md 자체 문장 외 근거 0건. docs/notion/은 수치 근거로 채택 금지 대상이라 대조하지 않음 |
| NHTSA 불만 원본 전체 | **2,221,663행**("약 222만 건"과 부합) | 재검증 완료 — `wc -l data/raw/FLAT_CMPL.txt` |
| UNKNOWN OR OTHER 비율 | **33.7%** (5,711/16,964행) 또는 ODINO 기준 **40.9%**(5,711/13,974) | 실측 재계산, `data/processed/hk_electrical_recent_full.csv` |
| UNKNOWN OR OTHER 1,702건 | **여전히 불일치 → 본문 제외 권장** — 재검색해도 저장소 어디에도 1,702라는 숫자 근거 없음(FLAT_CMPL.txt·hk_electrical_recent_full.csv 재확인). 실측 UNKNOWN 행수는 5,711(33.7%) | 재조사 완료, 근거 없음 확정 |

## 2. 배경 (좋은 Agent 6기준)

**재조사 후에도 미확인 → 본문 처리 방침 확정**: "6기준" 자체는 수치가 아니라 강의 프레임워크(노션 3·4장 전용, 저장소 code/data에 대응 산출물 없음)라 code/data로는 애초에 검증 불가능한 항목. 지시서의 "docs/notion/은 서술 흐름·용어 참고용"이라는 우선순위 규칙에 따라 **기준의 이름·정의는 노션 자료의 표현을 그대로 참고해 서술**하되, "본 프로젝트가 이 기준을 충족한다"는 대응표의 각 셀은 반드시 fact_sheet의 다른 절(5장 실험 등) 수치로 뒷받침되는 것만 채운다. "UNKNOWN OR OTHER 34%" 부분만 위 1번 표로 대체 가능(33.7%로 근사 일치).

## 3. 데이터

| 수치 | 값 | 출처 |
|---|---|---|
| NHTSA 불만 원본 | **2,221,663행**("약 222만 건") | 재검증 완료 — `wc -l data/raw/FLAT_CMPL.txt` |
| 필터 후 (현대·기아·전장·2022+) | **16,964행** (고유 ODINO 13,974 / 고유 CMPLID 16,964) | `data/processed/hk_electrical_recent_full.csv` 실측 |
| MAKETXT 분포 | HYUNDAI 9,506 / KIA 7,458 | 실측 재계산, 위 파일 |
| 미국 리콜(현대·기아 차종×캠페인 쌍) | 377행, 고유 캠페인 **164개** | `data/recalls/recalls_hk_by_vehicle.csv` 실측 |
| SW 후보 캠페인 | **76개** | `data/recalls/recalls_sw_candidates.csv` 실측 |
| 되감기 후보 풀(12개월 추이 확보) | 76건 중 **46건**(insufficient_data=False 46 / True 30) | `data/processed/lookback_candidates.csv` 실측, `docs/06_되감기_K12_확정.md`와 일치 |
| K12 확정 목록 | A유형 5 / B유형 4 / C유형 3 = 12건 | `docs/06_되감기_K12_확정.md`, `docs/k12_list.csv` |
| 한국 보도자료 매칭(kr_us_gap) | **27행** | `data/processed/kr_us_gap.csv` 실측 |
| KOTSA 기반 매칭(kr_us_gap_v2) | 103행(보도자료 27 + KOTSA 76) | `data/processed/kr_us_gap_v2.csv` 실측 |
| 덤벨 차트 대표 8건 | TUCSON +8일 / SANTA FE +152일 / PALISADE +4일 / IONIQ6 +33일 / PALISADE +127일 / NIRO −121일 / SORENTO +10일 / EV9 −3일 | CLAUDE.md 5.5단계 기록(webapp GET /api/gap 실측 응답으로 검증됨) |
| 데이터 함정: 49 vs 51 필드 | 실측 51개(PDF 스펙 49 + UNKNOWN_50·51 미문서 컬럼) | CLAUDE.md 프로젝트 개요 |

## 4. 시스템 설계

파이프라인 6단계(감지→구조화→조사→판정→검수→리포트)는 CLAUDE.md 전체 세션 기록과 정확히 대응:
- 감지(B1): `scripts/b1_detect.py` (Task 7)
- 구조화(LLM): `scripts/str01_batch_structurize.py` + `docs/struct_prompt_v4.md`
- 조사 루프: `scripts/inv02_03_investigation_loop.py` — **단, `scripts/cht01_chat_pipeline.py`와 인터페이스 불일치(모듈명·함수 시그니처 상이) 미해결 상태. 8장 "한계"에 반드시 기재.**
- 판정(Self-Consistency): `scripts/str03_consistency_analyze_v4.py` (결과: `data/processed/str03_consistency_v4_fixed_report.md`)
- Judge: **재조사 후 부분 확인** — `webapp/backend/llm/adapter.py`의 `MODEL_MAP`에 role별 provider 라우팅이 실재하며, `judge` role은 `structurize/investigate/answer`에 쓴 provider와 **다른** provider로 명시적으로 라우팅되도록 설계돼 있음(anthropic 답변 → openai judge, openai 답변 → anthropic judge) — "교차 벤더 Judge" 설계는 코드로 검증됨. 단, `webapp/backend/llm/mock_responses/judge/`는 빈 디렉터리이고 실제 judge 실행 결과 파일은 저장소에 없음 → 본문에서는 "설계됨/구현 예정"으로만 서술(수행 완료로 서술 금지)

## 5. 실험 (핵심 장)

### 5.1 B1 감지 baseline
| 수치 | 값 | 출처 |
|---|---|---|
| K12 포착 | **10/12** (A=4/5, B=3/4, C=3/3) | `data/processed/b1_eval_k12.csv` 실측 재계산 |
| 평균 선행일(포착 10건) | **215.7일** | 동일 파일 |
| 우연 포착 평균 확률 | **0.590** (실제 0.833과 대조) | `data/processed/b1_eval_validation.csv` 실측 |
| 정밀도(발화→12개월내 리콜) | **62.7%**(42/67, v1 원 모델명) → base_model 정규화 후 **74.6%**(50/67) → 관측기간 충족분만 **80.5%**(33/41) | `data/processed/precision_v2.csv` 실측 재계산 |
| 6개월 창 민감도 | **8/12** (12개월 창 10/12에서 하락) | `data/processed/b1_eval_validation.csv` 실측 |

### 5.2 구조화 미니테스트 (20건 strict 90% → 판정규칙 v2 → 20/20 교정)
**"strict 90%"는 [확인 필요]** — `data/samples/grading_sheet.csv`(v1, 20건)·`grading_sheet_v2.csv` 채점란 전부 공백(사람이 아직 채점하지 않음). 반면 "판정규칙 3종 주입 후 v1↔v2 무변화 검증"은 실재: **18/18건 무변화**(20건 중 경계 2건 제외) — CLAUDE.md Task 11, `data/processed/llm_struct_test_v2_regression.csv`. **"20/20"이 아니라 "18/18"이 정확한 수치.**

### 5.3 집중도 가설 (n=2 유망 → n=10 기각)
| 수치 | 값 | 출처 |
|---|---|---|
| 리콜연계 그룹 집중도 평균(재분류 후) | **0.637**(중앙값 0.700, n=7) | `data/processed/concentration_test_v2.csv` 실측 재계산 |
| 비리콜 그룹 집중도 평균 | **0.690**(중앙값 0.571, n=3) | 동일 |
| 결론 | 비리콜 그룹이 오히려 근소하게 높음 → 가설 기각 | CLAUDE.md Task 10 ③ |

### 5.4 한·미 매칭 오염
27건(kr_us_gap.csv) 중 검증된 것만 신뢰 — TUCSON 26V400000 +8일 사례가 실측 대조 성공 사례. **재조사로 정량 수치 확보**: `scripts/gap_v2_breakdown.py`가 KOTSA 기반 76건(`kr_us_gap_v2.csv`)에서 `|시차_일| > 365일`인 행을 "오매칭의심"으로 재분류 — 결과 **13/76건(17.1%)**이 오매칭의심, 매칭확신도 "중간" 69건/"낮음"(원문 오타 "낙음") 7건. | `data/processed/kr_us_gap_v2_breakdown.csv`, `scripts/gap_v2_breakdown.py` 실측

### 5.5 v4 전환·100건 검증
**instructions 원문("UNKNOWN 27건 중 26건 구제(형제 8+본문 18), insufficient 1")은 실측과 불일치 — 아래가 정확한 수치:**

| 수치 | instructions 원문 | 실측(재검증) | 출처 |
|---|---|---|---|
| UNKNOWN OR OTHER 건수 | 27건 | **45건** | `data/samples/sample_100_v4.csv`, `data/processed/str01_sample100_v4_fixed_report.md` |
| 형제 있어 구제 | 8건 | **11건** | 재계산(`scripts/str01_batch_structurize.py`의 `build_sibling_map`/`sibling_compdescs` 재사용) |
| 형제 없이 본문 판단 | 18건 | **25건** | 동일 |
| insufficient_info=true | 1건 | **9건**(UNKNOWN 중) / 전체 100건 기준 **14건** | 동일 |
| 총 구제(11+25) | 26건 | **36건** / 45건 (80%) | 동일 |
| 형식 위반 | 0/100 | **0/100 확인** | `str01_sample100_v4_fixed_report.md` STR-02 |
| 환각(evidence_quote 불일치) | 0/100 | **0/100 확인**(86건 실질 대조 대상, 14건은 빈 인용 예외) | 동일 |
| severity 분포 | — | CRITICAL 61/SERIOUS 23/MINOR 9/MODERATE 7 | 동일 |

### 5.6(추가, instructions에 없지만 실측 확보) — 20건 대조 세트
| 수치 | 값 | 출처 |
|---|---|---|
| 20건 형식위반/환각 | 0/20, 0/15(빈 인용 예외 5건 제외) | `data/processed/str01_sample20_v4_results.jsonl`, 이번 세션 재검증 |
| 20건 insufficient_info | 5/20(25.0%) | 동일 — 100건(14%)보다 높으나 원인은 표본 구성 차이(v4 층화 없는 구형 Task5 표본)로 규명됨 |

## 6. 평가 방법론
- Self-Consistency(v4, T=0.4, 3회): 안정 68% / 부분흔들림 20% / 불안정 12%; severity 3/3 일치 77%, driving_context 82%, insufficient_info 90% — `data/processed/str03_consistency_v4_fixed_report.md` 실측
- 골드라벨 교차 채점(5인): **미착수** — `grading_sheet*.csv` 전부 공백 확인. "진행 중"이 아니라 "착수 전"이 정확
- IAA(Judge 신뢰도): **재조사 후에도 미확인 → 본문 제외 권장** — kappa/Krippendorff/IAA 관련 스크립트·산출물이 저장소 전체(scripts/, docs/*.md)에 전혀 없음. 골드라벨 채점 자체가 미착수(위 항목)이므로 IAA는 애초에 계산 불가능한 상태 — 논리적으로 일관됨

## 7. 웹 서비스 구현
- 스크린샷 3장 확보: `docs/screenshots/{dashboard,chat,mycar}.png` (2026-07-08 Playwright 촬영)
- parts 테이블: 198행(rcl573_components_normalized.csv 기반), 76개 SW후보 캠페인 전체 커버 — CLAUDE.md 검증 기록과 파일 행수 일치 확인

## 8. 한계
- `cht01_chat_pipeline.py` ↔ `inv01_query_templates.py`/`inv02_03_investigation_loop.py` 인터페이스 불일치는 **미해결 상태로 실재**(직전 세션에서 진단만 하고 수정 보류) — 8장에 정직하게 기술 가능한 소재
- parts 테이블에 model 컬럼 없어 다부품 캠페인 모델별 구분 불가 — CLAUDE.md 기록

## 부록 — rcl573/공급사 정규화 수치 (5장·6장 보충 자료용)
| 수치 | 값 | 출처 |
|---|---|---|
| PDF URL 확보 | 71/76(93.4%) | `data/processed/rcl573_pdf_urls.csv` 실측 |
| 부품 지식 레코드(정규화 전) | 153행 | `data/processed/rcl573_components.csv` |
| 부품 지식 레코드(정규화·다중값 분해 후) | 198행 | `data/processed/rcl573_components_normalized.csv` |
| 공급사 alias(최종본) | 47행 전부 confidence=final | `data/processed/supplier_alias.csv` |

## [확인 필요] 재조사 최종 처리 목록 (Task 2 결과)

| 항목 | 재조사 결과 | 처리 |
|---|---|---|
| 미국 23%/한국 42~52%/자체 46% 삼각검증 | 근거 없음(재확인) | **본문 제외** — 서론에서 이 문장 삭제, "SW·전장 결함이 증가 추세"라는 정성적 서술만 유지 |
| UNKNOWN OR OTHER 1,702건 | 근거 없음(재확인), 실측 5,711건(33.7%)과 확정 불일치 | **수치 교체** — "1,702건" 대신 "5,711건(33.7%)" 사용 |
| NHTSA 원본 불만 "222만" | **확인됨** — 2,221,663행 | 채움, 본문에 그대로 사용 가능 |
| 좋은 Agent 6기준(2장 전체) | 노션 전용 프레임워크, code/data로 검증 불가능한 성격 | **부분 허용** — 기준 이름·정의는 노션 표현 참고 서술 가능(지시서 우선순위 규칙), 그러나 "본 프로젝트가 충족한다"는 대응표 각 셀은 반드시 5장 등 실측 수치로만 채움 |
| Judge(교차 벤더) | 코드 설계는 확인됨(`webapp/backend/llm/adapter.py`), 실행 산출물 없음 | **서술 톤 제한** — "설계/구현 예정"으로만 서술, "검증했다/수행했다" 금지 |
| IAA(Judge 신뢰도) | 근거 없음(재확인), 골드라벨 채점 자체가 미착수라 논리적으로도 불가능한 상태 | **본문 제외** — 6장에서 "예정" 서술만, 구체 수치 언급 없음 |
| 5.4 한·미 매칭 오염 정량화 | **확인됨** — 오매칭의심 13/76건(17.1%) | 채움, `data/processed/kr_us_gap_v2_breakdown.csv` 근거로 본문 사용 가능 |
| 5.2 "20건 strict 90%" | 채점 시트 전부 공백, 근거 없음(직전 턴에 이미 확인, 이번 턴 재확인 결과 동일) | **수치 교체** — "20건 strict 90%" 삭제, 대신 "판정규칙 v2 적용 후 18/18건 무변화"(실측)만 사용 |

**결론**: 본문(main.tex)에 `[확인 필요]` 문자열이 그대로 남는 항목은 없음 — 위 표대로 전부 "채움" 또는 "제외/교체" 처리 완료.
