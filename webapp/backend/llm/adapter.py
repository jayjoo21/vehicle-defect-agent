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


class LLM:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "mock")

    def call(self, role: str, scenario: str, context: dict | None = None) -> dict:
        """role: structurize | investigate | judge | answer. scenario는 mock 모드에서만 사용."""
        if self.provider == "mock":
            return self._mock_call(role, scenario, context or {})
        raise NotImplementedError(f"provider={self.provider} 연동은 v0 이후 구현 (현재는 mock만 지원)")

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
