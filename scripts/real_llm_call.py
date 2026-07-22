"""Gemini adapter for the INV investigation loop."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from google import genai
from google.genai import types


MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MAX_ATTEMPTS = 3
_client: genai.Client | None = None

SYSTEM_PROMPTS = {
    "generate_hypothesis": """당신은 자동차 결함 조사관입니다.
정찰 쿼리의 실제 수치만 근거로 차종·연식·증상 가설을 한 문장으로 세우세요.
명확한 패턴이 없으면 데이터가 부족하다고 답하세요.
JSON만 반환하세요: {\"hypothesis\": \"...\"}""",
    "select_query_or_conclude": """가설과 조사 결과를 보고 추가 검증 여부를 판단하세요.
available_tools 안의 도구만 선택하고, 특정 차종 질문은 모델별 도구로 교차 검증하세요.
JSON만 반환하세요: {\"action\": \"query\", \"query_name\": \"...\", \"params\": {...}}
또는 {\"action\": \"conclude\"}""",
    "judge_hypothesis": """가설과 all_results를 종합해 판정하세요.
true는 명확한 지지, false는 반박, null은 근거 부족입니다. 실제 숫자만 인용하세요.
JSON만 반환하세요: {\"is_retained\": true, \"reason\": \"...\"}""",
}


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
        _client = genai.Client(api_key=api_key)
    return _client


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```json\s*|\s*```$", "", text.strip(), flags=re.MULTILINE).strip()
    if not cleaned.startswith("{"):
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            cleaned = match.group(0)
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise TypeError("Gemini 응답의 최상위 값은 JSON 객체여야 합니다.")
    return value


def _is_retryable(exc: Exception) -> bool:
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    text = str(exc).upper()
    return code in {429, 500, 502, 503, 504} or any(
        marker in text for marker in ("UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE_EXCEEDED")
    )


def real_llm_call(prompt_type: str, context: dict[str, Any]) -> dict[str, Any]:
    if prompt_type not in SYSTEM_PROMPTS:
        raise ValueError(f"알 수 없는 prompt_type: {prompt_type!r}")

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = _get_client().models.generate_content(
                model=MODEL_NAME,
                contents=json.dumps(context, ensure_ascii=False, default=str),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPTS[prompt_type],
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            return _extract_json(response.text)
        except Exception as exc:
            if attempt == MAX_ATTEMPTS or not _is_retryable(exc):
                raise
            time.sleep(2 ** (attempt - 1))

    raise RuntimeError("Gemini 호출 재시도 상태가 올바르지 않습니다.")


if __name__ == "__main__":
    print(real_llm_call("generate_hypothesis", {"scouting_results": {}}))
