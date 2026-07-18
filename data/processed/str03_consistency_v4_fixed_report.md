# STR-03 v4 자기일관성(Self-Consistency) 분석 리포트

## 개요
- 대상: 100건 (동일 100건을 v4 프롬프트, temperature=0.4로 3회 독립 실행, CMPLID 매칭)
- 비교 대상 정형필드 3개: severity·driving_context·insufficient_info (v3의 part_category는 v4엔 없음=compdesc1/compdesc2로 대체, 코드가 채우는 결정론적 필드라 비교 불필요. mentions_existing_recall도 v4 스키마엔 없음)
- 목적: 다른 LLM·사람 라벨과 비교하는 게 아니라, 같은 모델이 스스로 얼마나 일관되게 판단하는지 측정 — 흔들리는 레코드 = 사람 검토 우선순위
- 산출물: `data/processed/str03_consistency_v4_fixed_detail.csv` (전 건 상세), 이 리포트

## 필드별 3회 일치율 (정형값 3개)
| 필드 | 3/3 일치(안정) | 2/1 (부분흔들림) | 1/1/1 (완전분열) |
|---|---|---|---|
| 심각도 (severity) | 77 (77.0%) | 19 (19.0%) | 4 (4.0%) |
| 주행 상황 (driving_context) | 82 (82.0%) | 16 (16.0%) | 2 (2.0%) |
| 정보부족 여부 (insufficient_info) | 90 (90.0%) | 10 (10.0%) | 0 (0.0%) |

## 레코드별 불안정 점수 분포 (3개 필드 중 일치하지 않는 필드 수)
| 불안정 점수 | 건수 |
|---|---|
| 0 | 68 |
| 1 | 20 |
| 2 | 5 |
| 3 | 7 |

| 등급 | 건수 | 비율 |
|---|---|---|
| 안정 | 68 | 68.0% |
| 부분 흔들림 | 20 | 20.0% |
| 불안정 | 12 | 12.0% |

## 표본 그룹별 불안정 비율 (v4 고유 메커니즘 검증)
| 그룹 | 안정 | 부분 흔들림 | 불안정 | 총 | 불안정+부분흔들림 비율 |
|---|---|---|---|---|---|
| A_multi_cmplid | 20 | 4 | 3 | 27 | 25.9% |
| B_unknown_with_sibling | 6 | 4 | 3 | 13 | 53.8% |
| C_unknown_no_sibling | 11 | 2 | 0 | 13 | 15.4% |
| RANDOM | 31 | 10 | 6 | 47 | 34.0% |

> A_multi_cmplid(다중 CMPLID 앵커링)·B_unknown_with_sibling(형제 COMPDESC 조회) 그룹의 불안정 비율이 RANDOM보다 뚜렷이 높다면, 이 두 메커니즘 자체가 판단 흔들림을 더 유발한다는 뜻으로 해석 가능 — 다만 각 그룹 표본이 13~27건으로 작아 확정적 결론은 아니다.

## 보조지표 — evidence_quote 위치 겹침(IoU) / symptoms 단어 자카드
- 안정 레코드(3필드 전부 일치, n=68) 평균 evidence 겹침(IoU): 0.803
- 불안정 레코드(1개 이상 필드 흔들림, n=32) 평균 evidence 겹침(IoU): 0.758
- 안정 레코드 평균 symptom 자카드: 0.577
- 불안정 레코드 평균 symptom 자카드: 0.460

- severity 3회 불일치 레코드(n=23) 평균 evidence 겹침(IoU): 0.822
- severity 3회 일치 레코드(n=77) 평균 evidence 겹침(IoU): 0.782

> 해석 가이드: evidence 겹침이 높은데도 판단이 갈렸다면 '같은 근거를 보고도 규칙 적용이 흔들린 것'(프롬프트 규칙이 모호할 가능성), 겹침이 낮다면 '애초에 다른 단서를 근거로 삼은 것'(원문 자체가 여러 단서를 담고 있어 모델이 어느 것을 볼지부터 흔들린 것)으로 구분해서 읽는다.

## temperature와 결과의 관계 — 해석상 반드시 짚어야 할 점
이 실험에서 관측된 흔들림은 **전부 temperature=0.4로 일부러 올린 결과다.** 이건 숨은 결함이 아니라 self-consistency 진단 방법 자체의 설계 원리 — "살짝 흔들어서 어느 판단이 약한 다리인지 본다"는 것이라, 흔들림이 온도 때문에 발생하는 것 자체는 의도된 동작이다. 다만 이로 인해 이 데이터로 정당하게 주장할 수 있는 것과 없는 것이 갈린다.

- **정당한 주장 — 상대적 순위**: T=0.4에서도 3필드 전부 그대로인 레코드는 모델이 강하게 확신하는 케이스다. 반대로 흔들린 레코드는 온도를 얼마로 잡든 상대적으로 더 흔들릴 가능성이 높은 후보군 — 이 순위를 "사람이 먼저 봐야 할 우선순위"로 쓰는 것은 타당하다.
- **부당한 주장 — 절대 수치**: 위 필드별 일치율을 "Gemini 운영(temperature=0) 판정이 이 정도로 불안정하다"고 읽으면 안 된다. T를 더 올렸으면 이 숫자는 더 나빠졌을 것이고, 이는 모델의 실제 신뢰도가 아니라 이번에 고른 T=0.4라는 진단 강도를 반영하는 수치다. 이 실험은 T=0(운영값) 3회 반복이라는 대조군 없이 진행됐다.
- **표본 그룹별 비교도 참고 가설**: 위 '표본 그룹별 불안정 비율'은 각 그룹 13~27건 표본에서 나온 관찰이라, 확정된 결론이 아니라 추가 검증이 필요한 가설로 취급한다.
- **결론**: 이번 실험의 확실한 산출물은 "이 100건 중 어디를 먼저 사람이 봐야 하는가"라는 우선순위 리스트(상세 CSV)이고, 절대 수치나 그룹 간 비교 해석은 참고 가설로만 취급한다.

## 검토 우선순위 상위 레코드 (불안정 점수 높은 순)
| CMPLID | 그룹 | compdesc1 | 점수 | 등급 | severity(3회) | driving_context(3회) | insufficient_info(3회) | evidence IoU | symptom 자카드 |
|---|---|---|---|---|---|---|---|---|---|
| 1906724 | RANDOM | ELECTRICAL SYSTEM | 3 | 불안정 | CRITICAL/MINOR/CRITICAL | 주행 중/불명/주행 중 | False/True/False | 0.699 | 0.333 |
| 1824170 | B_unknown_with_sibling | UNKNOWN OR OTHER | 3 | 불안정 | SERIOUS/MINOR/MINOR | 정차·주차 중/불명/불명 | False/True/True |  | 0.333 |
| 1859971 | A_multi_cmplid | BACK OVER PREVENTION | 3 | 불안정 | SERIOUS/MINOR/MINOR | 정차·주차 중/불명/불명 | False/True/True |  | 0.333 |
| 1890746 | RANDOM | ELECTRICAL SYSTEM | 3 | 불안정 | SERIOUS/MODERATE/MINOR | 정차·주차 중/불명/불명 | False/True/True |  | 0.333 |
| 2087536 | A_multi_cmplid | UNKNOWN OR OTHER | 3 | 불안정 | SERIOUS/MINOR/MODERATE | 정차·주차 중/불명/불명 | False/True/True |  | 0.333 |
| 2091541 | A_multi_cmplid | FORWARD COLLISION AVOIDANCE | 3 | 불안정 | SERIOUS/MINOR/SERIOUS | 주행 중/불명/주행 중 | False/True/False | 1.0 | 0.172 |
| 2195083 | RANDOM | UNKNOWN OR OTHER | 3 | 불안정 | MINOR/MINOR/CRITICAL | 정차·주차 중/불명/정차·주차 중 | True/True/False |  | 0.333 |
| 2039389 | RANDOM | ELECTRICAL SYSTEM | 2 | 불안정 | MODERATE/SERIOUS/CRITICAL | 불명/정차·주차 중/주행 중 | False/False/False | 0.333 | 0.533 |
| 2220261 | B_unknown_with_sibling | UNKNOWN OR OTHER | 2 | 불안정 | MINOR/MINOR/CRITICAL | 불명/불명/주행 중 | False/False/False | 0.333 | 0.067 |
| 1975226 | RANDOM | ELECTRICAL SYSTEM | 2 | 불안정 | SERIOUS/CRITICAL/CRITICAL | 정차·주차 중/주행 중/정차·주차 중 | False/False/False | 1.0 | 0.833 |
| 2098867 | RANDOM | BACK OVER PREVENTION | 2 | 불안정 | SERIOUS/SERIOUS/MODERATE | 정차·주차 중/불명/불명 | False/False/False | 1.0 | 0.259 |
| 2179780 | B_unknown_with_sibling | UNKNOWN OR OTHER | 2 | 불안정 | CRITICAL/CRITICAL/MINOR | 불명/불명/불명 | False/False/True | 1.0 | 0.2 |
| 2175668 | RANDOM | ELECTRICAL SYSTEM | 1 | 부분 흔들림 | MODERATE/MODERATE/MODERATE | 불명/불명/불명 | True/False/True | 0.0 | 0.333 |
| 1862545 | A_multi_cmplid | ELECTRICAL SYSTEM | 1 | 부분 흔들림 | CRITICAL/CRITICAL/CRITICAL | 불명/불명/주행 중 | False/False/False | 0.182 | 0.503 |
| 1859970 | A_multi_cmplid | FORWARD COLLISION AVOIDANCE | 1 | 부분 흔들림 | SERIOUS/SERIOUS/SERIOUS | 주행 중/불명/주행 중 | False/False/False | 0.333 | 0.292 |

## 한계
- temperature=0.4는 운영 파이프라인(0)과 다른 진단 전용 설정 — 이 결과로 운영 출력 자체를 바꾸지 않는다. (자세한 해석 범위는 위 'temperature와 결과의 관계' 절 참조)
- symptom 자카드는 공백 기준 단어 집합 비교라 같은 뜻을 다른 단어로 쓴 경우는 실제보다 낮게 나올 수 있음 — 정답 판정이 아니라 참고 지표로만 사용.
- evidence_quote 위치를 못 찾은 건(원문 부분매칭 실패, 예: insufficient_info=true + 빈 인용)은 겹침 계산에서 제외됨.
- 이 분석은 '어느 값이 정답인가'를 정하지 않는다 — 오직 '어디를 사람이 먼저 봐야 하는가'의 우선순위만 제공한다.
