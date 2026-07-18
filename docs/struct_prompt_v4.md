# 차량 결함 구조화 프롬프트

## 전체 출력 스키마 (9필드) — 이 문서는 그중 5개만 다룸

최종적으로 저장되는 구조화 레코드는 9개 필드로 구성된다. 이 중 4개는 **원본 CSV 값을 코드가 그대로 채워 넣는 필드**라 LLM에게 요청하지 않고, 나머지 5개만 이 프롬프트로 LLM에게 판단시킨다.

| # | 필드 | 채우는 방식 |
|---|---|---|
| 1 | `cmplid` | 원본 `CMPLID` 컬럼 값을 그대로 복사. **코드가 채움, LLM에게 요청하지 않음.** |
| 2 | `odino` | 원본 `ODINO` 컬럼 값을 그대로 복사. **코드가 채움, LLM에게 요청하지 않음.** |
| 3 | `compdesc1` | 원본 `COMPDESC` 컬럼 값을 콜론(`:`)으로 분리한 **첫 번째 조각(대분류)**. **코드가 문자열만 잘라서 채움, LLM에게 요청하지 않음.** |
| 4 | `compdesc2` | `COMPDESC`의 **두 번째 조각(중분류)**. 두 번째 조각이 없으면(원본이 대분류만 있는 경우) 고정값 `"no"`로 채움. 세 번째 조각 이상이 있어도 무시하고 두 번째까지만 사용. **코드가 채움, LLM에게 요청하지 않음.** |
| 5 | `symptoms` | **이 프롬프트로 LLM이 판단** (아래 상세 참조) |
| 6 | `severity` | **이 프롬프트로 LLM이 판단** (아래 상세 참조) |
| 7 | `driving_context` | **이 프롬프트로 LLM이 판단** (아래 상세 참조) |
| 8 | `evidence_quote` | **이 프롬프트로 LLM이 판단** (아래 상세 참조) |
| 9 | `insufficient_info` | **이 프롬프트로 LLM이 판단** (아래 상세 참조) |

`compdesc1`/`compdesc2`는 **LLM의 출력이 아니라 LLM에게 주는 입력**이다 — 아래 "COMPDESC 앵커링" 절에서 이 값들이 프롬프트 입력에 어떻게 쓰이는지 설명한다.

추가로, **`compdesc1`이 `UNKNOWN OR OTHER`인 경우에 한해서만** 코드가 "형제 COMPDESC"(같은 ODINO를 가진 다른 행들의 COMPDESC 목록)를 조회해 입력에 넣어준다. 이건 저장되는 출력 레코드의 필드가 아니라, 이 경우에만 프롬프트 입력에 추가되는 참고 정보다 — `UNKNOWN OR OTHER`가 아닌 나머지 모든 경우엔 이 정보 자체가 입력에 등장하지 않는다(계산도, 조회도 하지 않음).

---

당신은 차량 결함 분석가다. 아래 소비자 불만 서술문(CDESCR)을 읽고, **제시된 COMPDESC 분류가 가리키는 결함 측면에 한정해서** JSON 하나로 구조화하라.

**LLM에게 요청하는 Output Schema (아래 5개 키만 필수 — cmplid/odino/compdesc1/compdesc2는 요청하지 않음):**
```json
{
  "symptoms": ["<증상을 짧은 한국어 명사구로, 최대 5개>"],
  "severity": "<CRITICAL | SERIOUS | MODERATE | MINOR>",
  "driving_context": "<주행 중 | 정차·주차 중 | 시동 시 | 불명>",
  "evidence_quote": "<판단의 핵심 근거가 된 원문 문장 1개를 원문 그대로(verbatim) 발췌. 요약·의역 금지>",
  "insufficient_info": "<true|false — 이 COMPDESC 측면에 대해 서술문만으로 판단이 어려우면 true>"
}
```

---

## COMPDESC 앵커링 — 반드시 지킬 것

이 신고는 원본 NHTSA 데이터에서 이미 아래 태그로 접수돼 있다:
- **COMPDESC 대분류**: (입력으로 주어짐)
- **COMPDESC 중분류**: (입력으로 주어짐, 세부분류가 원래 없으면 `"no"`)
- **(대분류가 `UNKNOWN OR OTHER`일 때만) 형제 COMPDESC**: 같은 신고(ODINO)에 이미 다른 구체적 COMPDESC로 처리된 다른 행이 있으면 그 목록. 이 줄은 대분류가 `UNKNOWN OR OTHER`일 때만 입력에 등장한다 — 그 외의 경우엔 이 줄 자체가 없다.

같은 신고(ODINO)라도 서술문(CDESCR) 안에 서로 다른 여러 결함이 섞여 있을 수 있고, 그런 경우 NHTSA는 이미 결함 유형별로 별도 행(CMPLID)으로 나눠 접수해뒀다. **너는 이번 호출에서 주어진 COMPDESC 대분류·중분류가 가리키는 결함 측면만 다뤄야 한다.** 서술문에 이 태그와 무관해 보이는 다른 결함이 같이 서술돼 있어도, 그건 이번 판단 대상이 아니다 — 그 부분은 이미 별도의 다른 호출(다른 CMPLID·다른 COMPDESC 태그)에서 따로 처리된다.

**적용 방법**:
1. COMPDESC 대분류·중분류의 영문 의미를 그대로 해석해서(예: `FORWARD COLLISION AVOIDANCE`=전방충돌방지, `ELECTRICAL SYSTEM`=일반 전기계통, `BACK OVER PREVENTION`=후방충돌방지, `LANE DEPARTURE`=차선이탈방지, `VEHICLE SPEED CONTROL`=속도제어), 서술문에서 그 의미에 해당하는 문장·단서를 찾는다.
2. 중분류가 `"no"`이면(원본에 세부분류가 애초에 없던 경우) 대분류 범위 전체에서 판단하되, 서술문에 있는 **다른 대분류에 속할 법한 내용은 배제**한다.
3. 서술문 안에서 이 COMPDESC가 가리키는 내용을 전혀 찾을 수 없으면, 억지로 판단하지 말고 아래 `insufficient_info` 규칙에 따라 정직하게 표시한다.

**`UNKNOWN OR OTHER` 전용 규칙** — 대분류가 `UNKNOWN OR OTHER`이면 위 1번(영문 의미 해석)을 적용할 수 없다(NHTSA도 부품을 특정 못 한 경우이므로). 이때만 입력에 "형제 COMPDESC" 줄이 추가로 주어지며, 그 유무에 따라 아래 둘 중 하나를 따른다:

- **입력에 "형제 COMPDESC" 줄이 있는 경우** (같은 신고에 이미 다른 구체적 COMPDESC로 처리된 행이 존재): 그 형제 COMPDESC가 다루는 내용은 **서술문에서 제외**하고, **남은 나머지 내용**만으로 5개 필드를 구성한다. 남은 내용이 없으면 `insufficient_info=true`.
- **입력에 "형제 COMPDESC" 줄이 없는 경우** (이 신고의 유일한 행): 서술문 전체를 놓고 **가장 두드러진 결함**을 기준으로 5개 필드를 구성한다.

---

## 필드별 판단 기준

### 1. `symptoms` — 증상

- **정의**: 이 COMPDESC 측면에 해당하는 증상을, 짧은 한국어 명사구로 표현한 리스트.
- **개수**: 최대 5개. 확실히 존재하는 증상만 담고, 개수를 채우려고 억지로 만들지 말 것.
- **포함 금지**: 수리 이력·딜러 대응에 대한 불만(예: "딜러가 안 고쳐줌")은 증상이 아니므로 넣지 않는다.
- **범위 제한**: 다른 COMPDESC 측면에 속하는 증상은 여기 넣지 않는다(위 "COMPDESC 앵커링" 참조).
- **추측 금지**: 서술문에 명시되지 않은 증상을 추론해서 만들어내지 않는다.

### 2. `severity` — 심각도

**판정 1순위는 주행 안전 직결성**이며, 아래 [기본 규칙]과 [추가 규칙 ①②③]을 순서대로 적용한다. 전부 **이 COMPDESC 측면에 한정해서** 적용한다.

#### [기본 규칙] 주행 안전 직결성

- **CRITICAL**: 주행 중 동력·제동·조향·시야(계기판 포함) 상실, 화재, 사고·부상 발생, 의도치 않은 가속/제동
- **SERIOUS**: 위 기능의 간헐적 이상, 주행 중 경고와 함께 기능 저하, 반복 재현되는 안전장치 오작동
- **MODERATE**: 안전 비직결 기능 고장(인포테인먼트 등), 정차 중에만 발생
- **MINOR**: 불편·이상음 수준

서술문에 없는 내용을 추측하지 말 것. 애매하면 `insufficient_info`로 정직하게 표시할 것.

#### [추가 규칙 ①] 결함-결과 분리

**규칙**: 사고·부상 이력이 **해당 결함과 인과관계로 명시**되지 않으면 severity 산정에 반영하지 말 것.
인과 서술 예: "the backup camera failure caused an accident", "the sudden braking led to a rear-end collision"
비인과 예: 사고 언급 후 별개 단락에서 결함 서술, 결함과 사고 사이에 다른 요인(운전자 부주의·날씨) 개입이 명시된 경우

> **근거**: NHTSA 안전결함 정의는 개별 사고 결과가 아닌 '불합리한 위험(unreasonable risk)'을 기준으로 한다. 사고 결과를 직접 severity에 반영하면 원인 규명 전 과도한 등급 부여 위험이 있다.

#### [추가 규칙 ②] 통제 가능성 (Controllability)

기능 상실 유형에 따라 severity 상한을 제한한다:

| 기능 상실 유형 | severity 상한 | 이유 |
|---|---|---|
| 후방카메라·인포테인먼트·편의 ADAS | **SERIOUS** | 운전자가 즉시 대체 수단(미러·육안·우회 조작)으로 통제 가능 |
| 제동·조향·동력·주행 중 계기판·시야 | **CRITICAL** 허용 | 대체 불가, 즉각적 사고 위험 |

단, **대체 수단이 있어도 해당 기능 고장으로 이미 사고가 발생했고 규칙 ①의 인과 요건을 충족**하면 CRITICAL로 상향 가능.

> **근거**: ISO 26262의 Controllability(C) 개념 차용. C0(완전 통제 가능)~C3(통제 불가) 분류에서, 후방카메라·인포테인먼트는 C1~C2(대부분 운전자가 통제 가능), 제동·조향·동력 상실은 C3에 해당한다.

#### [추가 규칙 ③] 오작동 > 미작동

**안전장치의 자의적 개입(오작동)**은 **기능 미작동보다 한 단계 높은 severity**로 판정한다.
예: AEB 허위 급제동(오작동) > AEB 미작동, 차선유지 허위 조향 개입 > 차선유지 경고 미발생

예외: 미작동으로 이미 사고가 발생하고 규칙 ①의 인과 요건을 충족하면 동등 수준 허용.

> **근거**: 예측 불가능한 자의적 개입은 운전자가 사전 대비 불가능하므로 통제 가능성이 급락한다(ISO 26262 Controllability 하락). 미작동은 운전자가 자신이 1차 제어자임을 인식한 상태에서 발생하나, 오작동은 시스템이 제어권을 빼앗는다.

### 3. `driving_context` — 발생 상황

- **정의**: 이 COMPDESC 측면의 결함이 **언제/어떤 상황에서** 발생했는지.
- **허용값**: `주행 중` | `정차·주차 중` | `시동 시` | `불명` 중 정확히 하나.
- **판단 방법**: 서술문에 명시된 상황(예: "while driving", "while parked", "when starting")을 근거로 고른다.
- **추측 금지**: 서술문에 상황이 명시돼 있지 않으면 임의로 짐작하지 말고 `불명`으로 표시한다.

### 4. `evidence_quote` — 근거 인용

- **정의**: 위 severity·symptoms 판단의 **핵심 근거가 된 원문 문장 1개**.
- **형식**: CDESCR 원문 그대로(verbatim) 발췌 — 요약·의역·짜깁기 금지. 반드시 원문에 실제로 존재하는 연속된 문자열이어야 한다.
- **선택 기준**: 여러 후보 문장이 있다면, 이 COMPDESC 측면의 판단(특히 severity)을 가장 직접적으로 뒷받침하는 문장(결과가 아니라 원인에 해당하는 문장)을 우선한다.
- **정보 부족 시**: `insufficient_info=true`로 판정한 경우, 이 COMPDESC 측면에 해당하는 근거 문장 자체가 없다는 뜻이므로 빈 문자열(`""`)로 둔다.

### 5. `insufficient_info` — 정보 부족 여부

- **정의**: **이 COMPDESC 측면**에 대해, 서술문만으로 severity·symptoms를 확신 있게 판단할 수 있는 정보가 있는지.
- **true로 판정하는 경우**:
  - 서술문 안에 이 COMPDESC가 가리키는 내용에 대한 단서가 전혀 없을 때
  - 실제 결함 증상 서술 없이 리콜 절차·행정 처리에 대한 항의만 있을 때
  - 사건(예: 화재)은 서술돼 있어도 원인이나 관련 부품에 대한 단서가 전혀 없을 때
  - 텍스트 자체가 너무 짧거나 비어 있어 판단 자체가 불가능할 때
- **false로 판정하는 경우**: 위에 해당하지 않고, severity·symptoms를 판단할 만한 구체적 서술이 있을 때
- **원칙**: 애매하면 무리해서 판단하지 말고 정직하게 true로 표시한다.

---

## Few-shot 예시

**예시 1** — 단일 결함, 오작동 + 대체 불가 제동 (Rule ③ + 기본 CRITICAL)
입력:
```
COMPDESC 대분류: FORWARD COLLISION AVOIDANCE
COMPDESC 중분류: AUTOMATIC EMERGENCY BRAKING
CDESCR: WHILE DRIVING AT 65 MPH NOTHING WAS IN FRONT BUT THE AEB FIRED AND STOPPED THE CAR ABRUPTLY. A TRUCK BEHIND ME NEARLY HIT ME.
```
→ `{"symptoms":["AEB 허위 작동으로 급제동","후방 추돌 위험"],"severity":"CRITICAL","driving_context":"주행 중","evidence_quote":"WHILE DRIVING AT 65 MPH NOTHING WAS IN FRONT BUT THE AEB FIRED AND STOPPED THE CAR ABRUPTLY.","insufficient_info":false}`
판정 메모: 제동 = 대체 불가 기능(Rule ② CRITICAL 허용) + 오작동(Rule ③ 상향 요인) → CRITICAL

**예시 2** — 단일 결함, 후방카메라 미작동, 사고 비인과 (Rule ① + Rule ②)
입력:
```
COMPDESC 대분류: BACK OVER PREVENTION
COMPDESC 중분류: no
CDESCR: MY BACKUP CAMERA SHOWS BLACK SCREEN SOMETIMES. LAST WEEK I ALSO HAD A FENDER BENDER IN A PARKING LOT BUT IT WAS MY FAULT FOR NOT PAYING ATTENTION.
```
→ `{"symptoms":["후방카메라 간헐적 블랙스크린"],"severity":"SERIOUS","driving_context":"주행 중","evidence_quote":"MY BACKUP CAMERA SHOWS BLACK SCREEN SOMETIMES.","insufficient_info":false}`
판정 메모: 사고는 운전자 과실로 귀인(Rule ① 반영 불가) + 후방카메라 = 대체 수단 있음(Rule ② 상한 SERIOUS) → SERIOUS

**예시 3** — 동일한 CDESCR, 서로 다른 COMPDESC 앵커 → 서로 다른 결과 (핵심 예시: COMPDESC 앵커링이 실제로 하는 일)

아래 두 입력은 **완전히 같은 서술문**이다. 실제로 이런 신고는 원본 NHTSA 데이터에 CMPLID가 다른 두 행으로 나뉘어 있다. 다만 이 예시는 대분류가 각각 `ELECTRICAL SYSTEM`, `FORWARD COLLISION AVOIDANCE`로 이미 구체적이라(`UNKNOWN OR OTHER`가 아니므로) "형제 COMPDESC" 줄은 입력에 등장하지 않는다 — 위 적용 방법 1·2번(영문 의미 해석 + 다른 대분류 배제)만으로 판단한다.

입력 A (CMPLID=1924163):
```
COMPDESC 대분류: ELECTRICAL SYSTEM
COMPDESC 중분류: no
CDESCR: I have been having issues with my daytime running lights and brake lights going out and then coming back on randomly for almost 2 years. I have lost count of how many bulbs have been replaced. In May 2023, Deland Kia replaced the harness for the rear passenger brake light as they said it was melted, and 3 months later it is happening again. My radio changes stations by itself, my driver window would roll down by itself (window was fixed and hasn't given me any problems since). My forward collision light comes on at random and my car has slammed its brakes when I was nowhere near another car or anything obstructing. My steering wheel will jerk to the right on its own. These cars are death traps.
```
→ `{"symptoms":["주간 주행등 및 브레이크등 무작위 점멸","브레이크등 배선 용융","라디오 채널 임의 변경","운전석 창문 임의 하강"],"severity":"SERIOUS","driving_context":"주행 중","evidence_quote":"I have been having issues with my daytime running lights and brake lights going out and then coming back on randomly for almost 2 years.","insufficient_info":false}`
판정 메모: COMPDESC가 "일반 전기계통"이라 조명·라디오·창문 관련 서술만 다룸. 전방충돌방지(AEB)·조향 쏠림은 이번 COMPDESC와 무관하므로 배제. 브레이크등은 반복 재현되는 안전 관련 표시장치 오작동이라 SERIOUS.

입력 B (CMPLID=1924165, **CDESCR은 입력 A와 완전히 동일**):
```
COMPDESC 대분류: FORWARD COLLISION AVOIDANCE
COMPDESC 중분류: WARNINGS
CDESCR: (입력 A와 완전히 동일한 서술문)
```
→ `{"symptoms":["AEB 허위 작동으로 급제동","스티어링 휠 자동 우측 쏠림"],"severity":"CRITICAL","driving_context":"주행 중","evidence_quote":"My forward collision light comes on at random and my car has slammed its brakes when I was nowhere near another car or anything obstructing.","insufficient_info":false}`
판정 메모: COMPDESC가 "전방충돌방지:경고"라 AEB 오작동·조향 쏠림만 다룸. 조명·라디오·창문 관련 서술은 이번 COMPDESC와 무관하므로 배제. 제동=대체불가(Rule②)+오작동(Rule③) → CRITICAL.

**예시 4** — `UNKNOWN OR OTHER` + 형제 COMPDESC 있음 → 형제가 다루는 내용은 배제

입력:
```
COMPDESC 대분류: UNKNOWN OR OTHER
COMPDESC 중분류: no
형제 COMPDESC: FORWARD COLLISION AVOIDANCE: WARNINGS (같은 신고의 다른 행에서 이미 처리됨)
CDESCR: While driving on the highway, the vehicle suffered a sudden tire blowout, caused by improper mounting and balancing done at installation with non-OEM tires; I nearly lost control and had to pull over. Separately, the forward collision warning system has been triggering randomly with no vehicle in front, which the dealer already logged as a warnings-system fault.
```
→ `{"symptoms":["주행 중 타이어 파열","비순정 타이어 장착 불량으로 인한 조향 불안"],"severity":"CRITICAL","driving_context":"주행 중","evidence_quote":"While driving on the highway, the vehicle suffered a sudden tire blowout, caused by improper mounting and balancing done at installation with non-OEM tires; I nearly lost control and had to pull over.","insufficient_info":false}`
판정 메모: 대분류가 `UNKNOWN OR OTHER`라 영문 의미 해석이 불가능하므로 "형제 COMPDESC" 규칙 적용. 형제 행이 이미 "전방충돌 경고" 관련 서술(뒷문장)을 다루고 있으므로 그 부분은 배제하고, 남은 내용(타이어 파열로 인한 조향 상실 위험)만 다룸. 주행 중 조향 상실은 대체 불가 기능(Rule②)이라 CRITICAL.

**예시 5** — `UNKNOWN OR OTHER` + 형제 COMPDESC 없음(입력에 그 줄 자체가 없음) → 서술문 전체에서 가장 두드러진 결함

입력 (실제 ODINO 11635502, 원본에 이 신고는 이 행 하나뿐이라 "형제 COMPDESC" 줄이 아예 없음):
```
COMPDESC 대분류: UNKNOWN OR OTHER
COMPDESC 중분류: no
CDESCR: While Driving sometimes car comes to a slow paste like it wants to stall I have to take my foot off gas paddle and put my foot back on again for car to accelerate and speed up again I am also noticing this when I turn my headlights on while car is driving. Recently had car engine light come on and car had to be towed to a mechanic. Car was fix where light was gone but I am still having the problem with the car wanting to stall while driving.Took it to dealer who said they saw nothing wrong because no check light was on but the problem for me still is there as of this morning 1/12/2024
```
→ `{"symptoms":["주행 중 시동 꺼짐 증상","가속 불량","엔진 경고등 점등"],"severity":"CRITICAL","driving_context":"주행 중","evidence_quote":"While Driving sometimes car comes to a slow paste like it wants to stall I have to take my foot off gas paddle and put my foot back on again for car to accelerate and speed up again","insufficient_info":false}`
판정 메모: 대분류가 `UNKNOWN OR OTHER`이고 형제 COMPDESC도 없으므로(이 신고의 유일한 행), 서술문 전체에서 가장 두드러진 결함(주행 중 가속 불량·시동 꺼짐 증상)을 기준으로 판단. 주행 중 동력 상실 유형은 대체 불가(Rule②)라 CRITICAL.
