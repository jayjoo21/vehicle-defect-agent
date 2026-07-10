# STR-03 자기일관성(Self-Consistency) 분석 리포트

## 개요
- 대상: 100건 (동일 100건을 v3 프롬프트, temperature=0.4로 3회 독립 실행)
- 목적: 다른 LLM·사람 라벨과 비교하는 게 아니라, 같은 모델이 스스로 얼마나 일관되게 판단하는지 측정 — 흔들리는 레코드 = 사람 검토 우선순위
- 산출물: `data/processed/str03_consistency_detail.csv` (전 건 상세), 이 리포트

## 필드별 3회 일치율 (정형값 5개)
| 필드 | 3/3 일치(안정) | 2/1 (부분흔들림) | 1/1/1 (완전분열) |
|---|---|---|---|
| 부품 분류 (part_category) | 85 (85.0%) | 14 (14.0%) | 1 (1.0%) |
| 심각도 (severity) | 87 (87.0%) | 11 (11.0%) | 2 (2.0%) |
| 주행 상황 (driving_context) | 89 (89.0%) | 11 (11.0%) | 0 (0.0%) |
| 정보부족 여부 (insufficient_info) | 99 (99.0%) | 1 (1.0%) | 0 (0.0%) |
| 기존리콜 언급 여부 (mentions_existing_recall) | 97 (97.0%) | 3 (3.0%) | 0 (0.0%) |

## 레코드별 불안정 점수 분포 (5개 필드 중 일치하지 않는 필드 수)
| 불안정 점수 | 건수 |
|---|---|
| 0 | 66 |
| 1 | 27 |
| 2 | 5 |
| 3 | 2 |
| 4 | 0 |
| 5 | 0 |

| 등급 | 건수 | 비율 |
|---|---|---|
| 안정 | 66 | 66.0% |
| 부분 흔들림 | 32 | 32.0% |
| 불안정 | 2 | 2.0% |

## 보조지표 — evidence_quote 위치 겹침(IoU) / symptoms 단어 자카드
- 안정 레코드(5필드 전부 일치, n=66) 평균 evidence 겹침(IoU): 0.791
- 불안정 레코드(1개 이상 필드 흔들림, n=34) 평균 evidence 겹침(IoU): 0.851
- 안정 레코드 평균 symptom 자카드: 0.567
- 불안정 레코드 평균 symptom 자카드: 0.571

- severity 3회 불일치 레코드(n=13) 평균 evidence 겹침(IoU): 0.882
- severity 3회 일치 레코드(n=87) 평균 evidence 겹침(IoU): 0.801

> 해석 가이드: evidence 겹침이 높은데도 판단이 갈렸다면 '같은 근거를 보고도 규칙 적용이 흔들린 것'(프롬프트 규칙이 모호할 가능성), 겹침이 낮다면 '애초에 다른 단서를 근거로 삼은 것'(원문 자체가 여러 단서를 담고 있어 모델이 어느 것을 볼지부터 흔들린 것)으로 구분해서 읽는다.

## temperature와 결과의 관계 — 해석상 반드시 짚어야 할 점
이 실험에서 관측된 흔들림(불안정 34건, 필드별 85~99% 일치)은 **전부 temperature=0.4로 일부러 올린 결과다.** 이건 숨은 결함이 아니라 self-consistency 진단 방법 자체의 설계 원리 — "살짝 흔들어서 어느 판단이 약한 다리인지 본다"는 것이라, 흔들림이 온도 때문에 발생하는 것 자체는 의도된 동작이다. 다만 이로 인해 이 데이터로 정당하게 주장할 수 있는 것과 없는 것이 갈린다.

- **정당한 주장 — 상대적 순위**: 66건이 T=0.4에서도 5필드 전부 그대로라면, 이 레코드들은 모델이 강하게 확신하는 케이스다. 반대로 상위 34건은 온도를 얼마로 잡든(0.2든 0.6이든) 상대적으로 더 흔들릴 가능성이 높은 후보군 — 이 순위를 "사람이 먼저 봐야 할 우선순위"로 쓰는 것은 타당하다.
- **부당한 주장 — 절대 수치**: "부품분류 85% 일치·심각도 87% 일치"를 "Gemini 운영(temperature=0) 판정이 이 정도로 불안정하다"고 읽으면 안 된다. T를 더 올렸으면 이 숫자는 더 나빠졌을 것이고, 이는 모델의 실제 신뢰도가 아니라 이번에 고른 T=0.4라는 진단 강도를 반영하는 수치다. 이 실험은 T=0(운영값) 3회 반복이라는 대조군 없이 진행됐다 — 즉 "T=0 대비 얼마나 더 흔들렸는가"는 이 리포트가 답할 수 없는 질문이며, 정확한 정량화가 필요하면 별도로 T=0 대조군 실행이 필요하다.
- **작은 표본 주의**: "severity 불일치 13건의 evidence 겹침(0.882)이 일치 87건(0.801)보다 오히려 높다"는 위 상관관계는 n=13이라는 작은 표본에서 나온 관찰이다. 이게 "심각도 판정 규칙이 실제로 모호하다"는 확정된 결론이 아니라, **추가 검증이 필요한 가설**로 취급해야 한다 — 반복 횟수를 늘리거나(3회→5회 이상) 여러 temperature 값에서 같은 방향의 패턴이 재현되는지 확인하기 전까지는.
- **결론**: 이번 실험의 확실한 산출물은 "이 100건 중 어디를 먼저 사람이 봐야 하는가"라는 우선순위 리스트(위 표)이고, 절대 수치나 필드 간 상관관계 해석은 참고 가설로만 취급한다.

## 검토 우선순위 상위 레코드 (불안정 점수 높은 순)
| ODINO | 점수 | 등급 | part_category(3회) | severity(3회) | driving_context(3회) | insufficient_info(3회) | mentions_existing_recall(3회) | evidence IoU | symptom 자카드 |
|---|---|---|---|---|---|---|---|---|---|
| 11689901 | 3 | 불안정 | NON_ELECTRICAL/NON_ELECTRICAL/NON_ELECTRICAL | MODERATE/SERIOUS/CRITICAL | 불명/불명/주행 중 | False/False/False | True/False/False | 0.333 | 0.487 |
| 11677788 | 3 | 불안정 | INSTRUMENT_CLUSTER/INSUFFICIENT_INFO/INSTRUMENT_CLUSTER | MODERATE/MODERATE/MODERATE | 정차·주차 중/불명/불명 | False/True/False | False/False/False | 1.0 | 0.194 |
| 11548885 | 2 | 부분 흔들림 | ELECTRICAL_SYSTEM/ELECTRICAL_SYSTEM/ELECTRICAL_SYSTEM | MODERATE/MODERATE/SERIOUS | 정차·주차 중/불명/불명 | False/False/False | False/False/False | 0.331 | 0.408 |
| 11544622 | 2 | 부분 흔들림 | POWERTRAIN_SW/ELECTRICAL_SYSTEM/ELECTRICAL_SYSTEM | SERIOUS/SERIOUS/CRITICAL | 정차·주차 중/정차·주차 중/정차·주차 중 | False/False/False | True/True/True | 0.796 | 0.406 |
| 11490756 | 2 | 부분 흔들림 | ELECTRICAL_SYSTEM/ELECTRICAL_SYSTEM/ELECTRICAL_SYSTEM | CRITICAL/SERIOUS/SERIOUS | 시동 시/시동 시/불명 | False/False/False | True/True/True | 1.0 | 0.451 |
| 11580773 | 2 | 부분 흔들림 | INSTRUMENT_CLUSTER/INSTRUMENT_CLUSTER/INSTRUMENT_CLUSTER | SERIOUS/CRITICAL/CRITICAL | 불명/주행 중/불명 | False/False/False | False/False/False | 1.0 | 0.493 |
| 11677493 | 2 | 부분 흔들림 | ELECTRICAL_SYSTEM/NON_ELECTRICAL/ELECTRICAL_SYSTEM | SERIOUS/CRITICAL/SERIOUS | 시동 시/시동 시/시동 시 | False/False/False | False/False/False | 1.0 | 0.667 |
| 11715018 | 1 | 부분 흔들림 | ELECTRICAL_SYSTEM/ELECTRICAL_SYSTEM/ELECTRICAL_SYSTEM | CRITICAL/CRITICAL/CRITICAL | 불명/주행 중/불명 | False/False/False | False/False/False | 0.194 | 0.576 |
| 11528536 | 1 | 부분 흔들림 | PROPULSION_BATTERY/PROPULSION_BATTERY/PROPULSION_BATTERY | CRITICAL/CRITICAL/CRITICAL | 주행 중/주행 중/주행 중 | False/False/False | True/True/False | 0.331 | 0.44 |
| 11542050 | 1 | 부분 흔들림 | ELECTRICAL_SYSTEM/ADAS/ADAS | CRITICAL/CRITICAL/CRITICAL | 주행 중/주행 중/주행 중 | False/False/False | False/False/False | 0.333 | 0.234 |
| 11723787 | 1 | 부분 흔들림 | POWERTRAIN_SW/POWERTRAIN_SW/NON_ELECTRICAL | CRITICAL/CRITICAL/CRITICAL | 주행 중/주행 중/주행 중 | False/False/False | False/False/False | 0.333 | 0.725 |
| 11446690 | 1 | 부분 흔들림 | POWERTRAIN_SW/NON_ELECTRICAL/NON_ELECTRICAL | CRITICAL/CRITICAL/CRITICAL | 주행 중/주행 중/주행 중 | False/False/False | False/False/False | 0.558 | 0.685 |
| 11668898 | 1 | 부분 흔들림 | POWERTRAIN_SW/POWERTRAIN_SW/POWERTRAIN_SW | CRITICAL/CRITICAL/CRITICAL | 주행 중/정차·주차 중/정차·주차 중 | False/False/False | False/False/False | 0.739 | 0.337 |
| 11476842 | 1 | 부분 흔들림 | POWERTRAIN_SW/ELECTRICAL_SYSTEM/POWERTRAIN_SW | CRITICAL/CRITICAL/CRITICAL | 주행 중/주행 중/주행 중 | False/False/False | False/False/False | 1.0 | 0.5 |
| 11501381 | 1 | 부분 흔들림 | NON_ELECTRICAL/NON_ELECTRICAL/NON_ELECTRICAL | CRITICAL/CRITICAL/CRITICAL | 정차·주차 중/정차·주차 중/주행 중 | False/False/False | False/False/False | 1.0 | 0.382 |

## 한계
- temperature=0.4는 운영 파이프라인(0)과 다른 진단 전용 설정 — 이 결과로 운영 출력 자체를 바꾸지 않는다. (자세한 해석 범위는 위 'temperature와 결과의 관계' 절 참조)
- symptom 자카드는 공백 기준 단어 집합 비교라 같은 뜻을 다른 단어로 쓴 경우(예: '제동 밀림' vs '브레이크 밀리는 느낌')는 실제보다 낮게 나올 수 있음 — 정답 판정이 아니라 참고 지표로만 사용.
- evidence_quote 위치를 못 찾은 건(원문 부분매칭 실패)은 겹침 계산에서 제외됨.
- 이 분석은 '어느 값이 정답인가'를 정하지 않는다 — 오직 '어디를 사람이 먼저 봐야 하는가'의 우선순위만 제공한다.
