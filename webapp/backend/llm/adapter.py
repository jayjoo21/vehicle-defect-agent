"""LLM 어댑터. LLM_PROVIDER 환경변수가 없으면 자동 mock 모드 (에러 아님).

role: structurize | investigate | judge | answer
mock 모드는 llm/mock_responses/{role}/{scenario}.json의 markdown_template에
context 딕셔너리를 .format()으로 대입해 반환한다 — 실측 수치(신고 건수 등)는
전부 chat.py가 DB에서 직접 조회해 context로 넘기므로, 템플릿에는 지어낸 값이 없다.
"""
import json
import os
from pathlib import Path

MOCK_DIR = Path(__file__).resolve().parent / "mock_responses"

# provider별 role->모델 매핑. 하드코딩 금지, 설정에서만 관리.
MODEL_MAP = {
    "anthropic": {
        "structurize": "claude-haiku-4-5-20251001",
        "investigate": "claude-sonnet-5",
        "answer": "claude-sonnet-5",
        "judge": "openai",  # 다른 provider로 라우팅
    },
    "openai": {
        "structurize": "gpt-5-mini",
        "investigate": "gpt-5",
        "answer": "gpt-5",
        "judge": "anthropic",  # 다른 provider로 라우팅
    },
}


def _fmt(value: str, context: dict) -> str:
    return value.format(**context)


def _format_section(section: dict, context: dict) -> dict:
    badges = []
    for b in section.get("badges", []):
        text = _fmt(b, context).strip()
        # "-"는 이 프로젝트 전역에서 값 없음 sentinel(예: cluster_odino_2 없으면 "-")로
        # 쓰이므로, 뱃지로 formatting했을 때 그 sentinel만 남는 경우는 표시하지 않는다.
        if text and not text.endswith("-"):
            badges.append(text)
    return {
        "title": _fmt(section["title"], context),
        "body": _fmt(section["body"], context),
        "badges": badges,
    }


def _format_structured(template: dict, context: dict) -> dict:
    return {
        "headline": _fmt(template["headline"], context),
        "chips": [_fmt(c, context) for c in template.get("chips", [])],
        "sections": [_format_section(s, context) for s in template.get("sections", [])],
    }


def _structured_to_markdown(structured: dict, confidence: dict | None) -> str:
    """structured(headline+sections)로부터 리포트 저장용 markdown을 파생시킨다 — chat.py의 SSE
    답변과 seed.py의 사전 리포트가 항상 같은 함수를 거치므로 두 markdown이 바이트 단위로 일치한다."""
    parts = [structured["headline"]]
    for s in structured["sections"]:
        parts.append(f"**{s['title']}** — {s['body']}")
    if confidence:
        parts.append(f"## 확신도와 한계\n\n**확신도: {confidence['level']}.** {confidence['note']}")
    return "\n\n".join(parts)


# --- 실제 provider 연동 (v0 이후) ---
#
# role="answer"만 구현한다 — chat.py가 이 어댑터에 실제로 요청하는 유일한 role이고,
# structurize/investigate/judge는 별도 오프라인 스크립트(scripts/str01_batch_structurize.py 등)가
# 이미 자체 구현을 갖고 있어 이 웹앱 어댑터가 대신할 필요가 없다(CLAUDE.md: 요구한 것만 구현).
#
# LLM이 만들어내는 것은 "headline/chips/sections/confidence" 뿐이다. 출처(sources)·인용
# (quotes)·부품 정보(parts)·상담사 요약(agent_summary)은 전부 chat.py가 DB에서 직접 조회해
# 채우므로 LLM 응답과 무관하게 항상 100% 실측값이다 — 이 스키마 밖의 필드를 LLM이 만들어내도
# chat.py가 반환값을 덮어써서 무시한다.
ANSWER_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "chips": {"type": "array", "items": {"type": "string"}},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "badges": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "body", "badges"],
                "additionalProperties": False,
            },
        },
        "confidence": {
            "type": "object",
            "properties": {
                "level": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["level", "note"],
            "additionalProperties": False,
        },
    },
    "required": ["headline", "chips", "sections", "confidence"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """당신은 NHTSA(미국 도로교통안전국) 소비자 불만 신고와 리콜 기록을 근거로 현대·기아 차량의
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
   간결히 적으세요."""


def _fact_or_skip(context: dict, key: str, label: str) -> str | None:
    value = context.get(key, "-")
    if value == "-" or value is None:
        return None
    return f"{label}: {value}"


def _ev6_facts(context: dict) -> list[str]:
    facts = [
        "조사 대상 차종: EV6 (기아)",
        f"최근 90일(2026-04-01~2026-06-30) EV6 신고 건수: {context['recent_count']}건",
        f"EV6가 이미 보유한 ICCU(통합충전제어장치)/12V 배터리 관련 리콜 캠페인 번호: {context['iccu_campaigns']}",
    ]
    f1 = _fact_or_skip(context, "cluster_odino_1", "전력손실·ICCU 언급 없이 순수 계기판 표시 이상만 보고된 과거 사례 1 — ODINO")
    if f1:
        facts.append(f"{f1} (접수일 {context['cluster_date_1']})")
    f2 = _fact_or_skip(context, "cluster_odino_2", "동일 유형 과거 사례 2 — ODINO")
    if f2:
        facts.append(f"{f2} (접수일 {context['cluster_date_2']})")
    facts.append(
        "참고(다른 차종 리콜): 투싼(TUCSON)의 계기판 소프트웨어 리콜 26V400000(2026-06-24 접수)이 "
        "증상 유형은 유사하나 EV6 리콜이 아님"
    )
    return facts


def _ioniq5_facts(context: dict) -> list[str]:
    facts = [
        "조사 대상 차종: IONIQ 5 (현대)",
        f"최근 90일 IONIQ 5 신고 건수: {context['recent_count']}건",
        f"IONIQ 5가 이미 보유한 ICCU/충전 관련 리콜 캠페인 번호: {context['iccu_campaigns']}",
        f"최근 90일 신고 중 ICCU·12V 배터리 증상과 일치하는 건수: {context['iccu_hit_count']}건 ({context['iccu_ratio']}%)",
    ]
    f1 = _fact_or_skip(context, "odino_1", "대표 사례 1 — ODINO")
    if f1:
        facts.append(f"{f1} (접수일 {context['date_1']})")
    f2 = _fact_or_skip(context, "odino_2", "대표 사례 2 — ODINO")
    if f2:
        facts.append(f"{f2} (접수일 {context['date_2']})")
    fr = _fact_or_skip(context, "odino_recur", "기존 리콜 재발/언급 사례 — ODINO")
    if fr:
        facts.append(f"{fr} (접수일 {context['date_recur']})")
    return facts


SCENARIO_FACTS = {
    "ev6_cluster": _ev6_facts,
    "ioniq5_charging": _ioniq5_facts,
}

SCENARIO_BRIEF = {
    "ev6_cluster": (
        "사용자가 'EV6 계기판이 깜빡이다 꺼진다'는 취지로 문의했습니다. 아래 사실을 근거로 EV6 자체의 순수 "
        "계기판 리콜 여부, 이미 등록된 ICCU 리콜과의 관계, 과거 유사 사례, 권장 조치를 다루는 조사 요약을 "
        "작성하세요."
    ),
    "ioniq5_charging": (
        "사용자가 'IONIQ 5 충전 중 12V 배터리 경고'라는 취지로 문의했습니다. 아래 사실을 근거로 ICCU/충전 "
        "리콜 현황, 최근 신고의 증상 집중도, 대표 사례, 권장 조치를 다루는 조사 요약을 작성하세요."
    ),
    "out_of_scope": (
        "사용자의 질문이 이 서비스(NHTSA 소비자 불만·리콜 기반 전장/SW 결함 조사)의 범위 밖입니다. 서비스 "
        "범위를 안내하고, 차종명과 증상을 함께 입력하면 조사할 수 있다고 안내하세요. 구체적인 리콜 번호나 "
        "통계는 절대 언급하지 마세요(근거 데이터가 없습니다)."
    ),
}


def _build_answer_prompt(scenario: str, context: dict) -> str:
    brief = SCENARIO_BRIEF.get(scenario, SCENARIO_BRIEF["out_of_scope"])
    facts_fn = SCENARIO_FACTS.get(scenario)
    facts = facts_fn(context) if facts_fn else []
    if not facts:
        return brief
    fact_lines = "\n".join(f"- {f}" for f in facts)
    return f"{brief}\n\n제공된 사실(이 목록 밖의 사실을 지어내지 마세요):\n{fact_lines}"


def _finalize_answer(data: dict) -> dict:
    structured = {
        "headline": data["headline"],
        "chips": list(data.get("chips", [])),
        "sections": [
            {"title": s["title"], "body": s["body"], "badges": list(s.get("badges", []))}
            for s in data.get("sections", [])
        ],
    }
    confidence = data.get("confidence")
    markdown = _structured_to_markdown(structured, confidence)
    return {"markdown": markdown, "structured": structured}


class LLM:
    def __init__(self, provider: str | None = None):
        # provider 인자로 명시 override 가능 — seed.py가 사전 리포트를 생성할 때 ambient
        # LLM_PROVIDER(.env, 실배포에서는 openai)와 무관하게 항상 mock을 강제하기 위해 필요하다.
        # (시드는 결정적이어야 하고 Docker 빌드 시 실행되므로 실LLM 호출·비용·실패 위험이 없어야 함.)
        self.provider = provider or os.getenv("LLM_PROVIDER", "mock")

    def call(self, role: str, scenario: str, context: dict | None = None) -> dict:
        """role: structurize | investigate | judge | answer. scenario는 mock 모드에서만 사용."""
        context = context or {}
        if self.provider == "mock":
            return self._mock_call(role, scenario, context)
        if role != "answer":
            # chat.py는 role="answer"만 호출한다 — 다른 role은 이 웹앱 범위 밖(오프라인 스크립트가 별도 구현).
            raise NotImplementedError(f"role={role}는 real provider에서 미구현 (mock만 지원)")
        if self.provider == "openai":
            return self._openai_answer(scenario, context)
        raise NotImplementedError(f"provider={self.provider} 연동 미구현 (MODEL_MAP: openai, anthropic만 정의됨. 현재 openai만 실구현)")

    def _openai_answer(self, scenario: str, context: dict) -> dict:
        from openai import OpenAI

        # timeout=45: 실측 결과 gpt-5(JSON 스키마 강제) 응답은 정상 성공 시에도 15~43초가
        # 걸린다(이 세션에서 반복 관측) — 30초는 정상 응답까지 끊어버려 오히려 오류를 유발했다.
        # max_retries=1(기본값 2 대신): 기본 재시도 2회 + 매 시도 타임아웃이 겹치면 최악의 경우
        # 90초 이상 걸려 프론트/프록시가 먼저 끊어버릴 수 있어 재시도를 1회로 제한해 상한을 둔다.
        client = OpenAI(timeout=45, max_retries=1)
        model = MODEL_MAP["openai"]["answer"]
        print(f"[LLM] provider=openai role=answer model={model} scenario={scenario}", flush=True)
        prompt = _build_answer_prompt(scenario, context)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "chat_answer", "schema": ANSWER_JSON_SCHEMA, "strict": True},
            },
        )
        data = json.loads(resp.choices[0].message.content)
        return _finalize_answer(data)

    def _mock_call(self, role: str, scenario: str, context: dict) -> dict:
        path = MOCK_DIR / role / f"{scenario}.json"
        if not path.exists():
            raise FileNotFoundError(f"mock response 없음: {path}")
        template = json.loads(path.read_text(encoding="utf-8"))
        if role == "answer" and "headline" in template:
            structured = _format_structured(template, context)
            confidence = None
            if "confidence" in template:
                confidence = {
                    "level": _fmt(template["confidence"]["level"], context),
                    "note": _fmt(template["confidence"]["note"], context),
                }
            markdown = _structured_to_markdown(structured, confidence)
            return {"markdown": markdown, "structured": structured}
        markdown = template["markdown_template"].format(**context)
        return {"markdown": markdown}
