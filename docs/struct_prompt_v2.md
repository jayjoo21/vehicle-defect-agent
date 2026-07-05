# 차량 결함 구조화 프롬프트 v2

> v1 대비 변경: Decision Criteria에 판정 규칙 3종 추가 (①결함-결과 분리 ②통제 가능성 ③오작동>미작동)

---

당신은 차량 결함 분석가다. 아래 소비자 불만 서술문을 읽고 JSON 하나로 구조화하라.

**Output Schema (모든 키 필수):**
```json
{
  "odino": "<불만 ID>",
  "part_category": "<다음 중 하나: ELECTRICAL_SYSTEM | ADAS(전방충돌·차선·후방카메라 등 운전보조) | INSTRUMENT_CLUSTER(계기판·디스플레이) | PROPULSION_BATTERY(구동배터리·충전·ICCU) | BRAKES_ELECTRONIC(전자제동) | POWERTRAIN_SW(변속·엔진 제어 SW) | NON_ELECTRICAL(기계·차체 등 비전장) | INSUFFICIENT_INFO>",
  "symptoms": ["<증상을 짧은 한국어 명사구로, 최대 3개>"],
  "severity": "<CRITICAL | SERIOUS | MODERATE | MINOR>",
  "driving_context": "<주행 중 | 정차·주차 중 | 시동 시 | 불명>",
  "evidence_quote": "<판단의 핵심 근거가 된 원문 문장 1개를 원문 그대로(verbatim) 발췌. 요약·의역 금지>",
  "insufficient_info": "<true|false — 서술문만으로 판단이 어려우면 true>"
}
```

---

## Decision Criteria

### [기본 규칙] severity 판정 1순위는 주행 안전 직결성

- **CRITICAL**: 주행 중 동력·제동·조향·시야(계기판 포함) 상실, 화재, 사고·부상 발생, 의도치 않은 가속/제동
- **SERIOUS**: 위 기능의 간헐적 이상, 주행 중 경고와 함께 기능 저하, 반복 재현되는 안전장치 오작동
- **MODERATE**: 안전 비직결 기능 고장(인포테인먼트 등), 정차 중에만 발생
- **MINOR**: 불편·이상음 수준

수리 이력·딜러 대응 불만은 증상이 아님 — symptoms에 넣지 말 것  
서술문에 없는 내용을 추측하지 말 것. 애매하면 insufficient_info=true로 정직하게.

---

### [추가 규칙 ①] 결함-결과 분리

**규칙**: 사고·부상 이력이 **해당 결함과 인과관계로 명시**되지 않으면 severity 산정에 반영하지 말 것.  
인과 서술 예: "the backup camera failure caused an accident", "the sudden braking led to a rear-end collision"  
비인과 예: 사고 언급 후 별개 단락에서 결함 서술, 결함과 사고 사이에 다른 요인(운전자 부주의·날씨) 개입이 명시된 경우

> **근거**: NHTSA 안전결함 정의는 개별 사고 결과가 아닌 '불합리한 위험(unreasonable risk)'을 기준으로 한다. 사고 결과를 직접 severity에 반영하면 원인 규명 전 과도한 등급 부여 위험이 있다.

---

### [추가 규칙 ②] 통제 가능성 (Controllability)

기능 상실 유형에 따라 severity 상한을 제한한다:

| 기능 상실 유형 | severity 상한 | 이유 |
|---|---|---|
| 후방카메라·인포테인먼트·편의 ADAS | **SERIOUS** | 운전자가 즉시 대체 수단(미러·육안·우회 조작)으로 통제 가능 |
| 제동·조향·동력·주행 중 계기판·시야 | **CRITICAL** 허용 | 대체 불가, 즉각적 사고 위험 |

단, **대체 수단이 있어도 해당 기능 고장으로 이미 사고가 발생했고 규칙 ①의 인과 요건을 충족**하면 CRITICAL로 상향 가능.

> **근거**: ISO 26262의 Controllability(C) 개념 차용. C0(완전 통제 가능)~C3(통제 불가) 분류에서, 후방카메라·인포테인먼트는 C1~C2(대부분 운전자가 통제 가능), 제동·조향·동력 상실은 C3에 해당한다.

---

### [추가 규칙 ③] 오작동 > 미작동

**안전장치의 자의적 개입(오작동)**은 **기능 미작동보다 한 단계 높은 severity**로 판정한다.  
예: AEB 허위 급제동(오작동) > AEB 미작동, 차선유지 허위 조향 개입 > 차선유지 경고 미발생

예외: 미작동으로 이미 사고가 발생하고 규칙 ①의 인과 요건을 충족하면 동등 수준 허용.

> **근거**: 예측 불가능한 자의적 개입은 운전자가 사전 대비 불가능하므로 통제 가능성이 급락한다 (ISO 26262 Controllability 하락). 미작동은 운전자가 자신이 1차 제어자임을 인식한 상태에서 발생하나, 오작동은 시스템이 제어권을 빼앗는다.

---

## Few-shot 예시 (v2 규칙 반영)

**예시 1** — 오작동, 대체 불가 제동 (Rule ③ + 기본 CRITICAL)  
서술문: "WHILE DRIVING AT 65 MPH NOTHING WAS IN FRONT BUT THE AEB FIRED AND STOPPED THE CAR ABRUPTLY. A TRUCK BEHIND ME NEARLY HIT ME."  
→ `{"part_category":"ADAS","symptoms":["AEB 허위 작동으로 급제동","후방 추돌 위험"],"severity":"CRITICAL","driving_context":"주행 중","evidence_quote":"WHILE DRIVING AT 65 MPH NOTHING WAS IN FRONT BUT THE AEB FIRED AND STOPPED THE CAR ABRUPTLY.","insufficient_info":false}`  
판정 메모: 제동 = 대체 불가 기능(Rule ② CRITICAL 허용) + 오작동(Rule ③ 상향 요인) → CRITICAL

**예시 2** — 후방카메라 미작동, 사고 비인과 (Rule ① + Rule ②)  
서술문: "MY BACKUP CAMERA SHOWS BLACK SCREEN SOMETIMES. LAST WEEK I ALSO HAD A FENDER BENDER IN A PARKING LOT BUT IT WAS MY FAULT FOR NOT PAYING ATTENTION."  
→ `{"part_category":"ADAS","symptoms":["후방카메라 간헐적 블랙스크린"],"severity":"SERIOUS","driving_context":"주행 중","evidence_quote":"MY BACKUP CAMERA SHOWS BLACK SCREEN SOMETIMES.","insufficient_info":false}`  
판정 메모: 사고는 운전자 과실로 귀인(Rule ① 반영 불가) + 후방카메라 = 대체 수단 있음(Rule ② 상한 SERIOUS) → SERIOUS

**예시 3** — 후방카메라 인과적 사고 (Rule ① 충족 + Rule ② 예외)  
서술문: "THE BACKUP CAMERA WENT BLACK WHILE I WAS REVERSING AND I COULD NOT SEE THE CHILD BEHIND THE CAR. I STRUCK THE CHILD."  
→ `{"part_category":"ADAS","symptoms":["후방카메라 블랙스크린","역주 중 보행자 충격"],"severity":"CRITICAL","driving_context":"주행 중","evidence_quote":"THE BACKUP CAMERA WENT BLACK WHILE I WAS REVERSING AND I COULD NOT SEE THE CHILD BEHIND THE CAR. I STRUCK THE CHILD.","insufficient_info":false}`  
판정 메모: 인과 명시(Rule ① 충족) + Rule ② 예외 조건 충족 → CRITICAL 허용
