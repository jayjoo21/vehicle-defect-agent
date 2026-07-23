# CHT(조사 채팅) 웹앱 답변 생성 프롬프트

- 위치: `webapp/backend/llm/adapter.py` (`SYSTEM_PROMPT`, `SCENARIO_BRIEF`, `SCENARIO_FACTS`, `_build_answer_prompt`, `ANSWER_JSON_SCHEMA`)
- 적용 대상: `LLM_PROVIDER=openai`일 때 `LLM.call("answer", scenario, context)` — 조사 채팅(`routers/chat.py`)과 사전 리포트 생성(`seed.py`, 단 seed는 `provider="mock"`으로 강제되어 실제로는 이 프롬프트를 타지 않음)
- 작성 배경: 이 CHT(웹앱 채팅) 역할용 시스템 프롬프트는 기존 팀 문서(`docs/13_초안v0_스펙.md`, STR/JDG 트랙 프롬프트)에 해당 항목이 없어 이번 작업에서 새로 작성함. STR/JDG 트랙의 기존 프롬프트(`docs/struct_prompt_v2/v3/v4.md`, `str04_judge_pipeline.py`)는 그대로 두고 손대지 않음.

## 설계 원칙

LLM이 실제로 만들어내는 것은 자연어 서술(`headline`/`chips`/`sections`/`confidence`)뿐이다. 인용 원문(`quotes`)·부품 정보(`parts`)·상담사 요약(`agent_summary`)·SSE 조사 단계(차종 인식·이력 조회·리콜 대조 등)는 전부 `routers/chat.py`가 DB에서 직접 조회해 채우며 LLM 출력과 무관하다 — 즉 인용·수치는 100% 실측값이고, LLM은 그 실측값을 문장으로 엮는 역할만 한다.

## 시스템 프롬프트 (verbatim, `adapter.py`의 `SYSTEM_PROMPT` 상수)

```
당신은 NHTSA(미국 도로교통안전국) 소비자 불만 신고와 리콜 기록을 근거로 현대·기아 차량의
전장·소프트웨어 결함 시그널을 조사하는 어시스턴트입니다.

반드시 지켜야 할 규칙:
1. 아래 "제공된 사실" 목록에 있는 정보만 근거로 답변하세요. 목록에 없는 리콜 캠페인 번호, ODINO 신고
   번호, 건수·비율 등 통계 수치를 새로 지어내지 마세요.
2. 신고는 NHTSA가 명시하듯 미검증 소비자 제보입니다. "결함 확정"이라는 표현을 쓰지 마세요.
3. 한국어로, 자연스러운 조사 요약 문체로 작성하세요.
4. 반드시 지정된 JSON 스키마에 맞춰 응답하세요. sections는 보통 2~4개, 각 섹션은 짧은 제목(title)과
   1~3문장의 본문(body)으로 구성합니다. badges에는 본문에서 실제로 언급한 리콜 캠페인 번호나 ODINO
   번호만 그대로 나열하세요(언급한 게 없으면 빈 배열).
5. confidence.level은 "높음"·"보통"·"낮음" 중 하나로, note에는 그 근거(표본 크기, 확정 리콜 여부 등)를
   간결히 적으세요.
```

**규칙 1** = 사실 기반 근거·지어내기 금지. **규칙 2** = "결함 확정" 표현 금지(CLAUDE.md 도메인 원칙과 동일). **규칙 3~5** = 출력 형식·스키마 고정.

## 사용자 프롬프트 구성 (시나리오별 사실 주입)

`_build_answer_prompt(scenario, context)`가 시나리오 브리핑(`SCENARIO_BRIEF`) + DB에서 조회된 사실 목록(`SCENARIO_FACTS[scenario](context)`)을 이어붙여 만든다. 사실 목록에 없는 값은 프롬프트에 아예 등장하지 않는다(예: 과거 사례가 1건뿐이면 2번째 항목 자체를 생략 — "-" sentinel을 감추는 것이 아니라 문장 자체를 안 만듦).

예시(EV6 시나리오, 실제 DB 조회값 대입 후):
```
사용자가 'EV6 계기판이 깜빡이다 꺼진다'는 취지로 문의했습니다. 아래 사실을 근거로 EV6 자체의 순수
계기판 리콜 여부, 이미 등록된 ICCU 리콜과의 관계, 과거 유사 사례, 권장 조치를 다루는 조사 요약을
작성하세요.

제공된 사실(이 목록 밖의 사실을 지어내지 마세요):
- 조사 대상 차종: EV6 (기아)
- 최근 90일(2026-04-01~2026-06-30) EV6 신고 건수: 53건
- EV6가 이미 보유한 ICCU(통합충전제어장치)/12V 배터리 관련 리콜 캠페인 번호: 24V200000·24V867000
- 전력손실·ICCU 언급 없이 순수 계기판 표시 이상만 보고된 과거 사례 1 — ODINO: 11630458 (접수일 2024-12-12)
- 동일 유형 과거 사례 2 — ODINO: 11670403 (접수일 2025-06-30)
- 참고(다른 차종 리콜): 투싼(TUCSON)의 계기판 소프트웨어 리콜 26V400000(2026-06-24 접수)이 증상 유형은 유사하나 EV6 리콜이 아님
```

범위 밖(`out_of_scope`) 시나리오는 사실 목록 자체가 비어 있어(context={}) 브리핑 문장만 전달되며, 브리핑에 "구체적인 리콜 번호나 통계는 절대 언급하지 마세요(근거 데이터가 없습니다)"를 명시해 환각을 방지한다.

## 출력 스키마 강제

OpenAI Structured Outputs(`response_format={"type":"json_schema","strict":true}`)로 `headline`/`chips`/`sections[].{title,body,badges}`/`confidence.{level,note}` 형태를 스키마 레벨에서 강제한다(`ANSWER_JSON_SCHEMA`). 모델이 이 스키마 밖의 필드를 만들어도 `_finalize_answer()`가 정확히 이 키만 추출해 사용한다.

## 고지문(disclaimer)

시스템 프롬프트 규칙 2("결함 확정 금지")와는 별개로, 실제 화면에 표시되는 법적 고지문(`DISCLAIMER`, "본 정보는 NHTSA·국토부 공개 신고 및 리콜 기록 기반이며, 개별 차량의 진단이 아닙니다. 신고는 미검증 소비자 제보를 포함합니다.")은 LLM 출력과 무관하게 `ChatAnswerCard.tsx`가 항상 하단에 고정 렌더링한다 — LLM이 실수로 고지문을 빠뜨리거나 다르게 표현해도 화면에는 항상 정확한 고지문이 뜬다.
