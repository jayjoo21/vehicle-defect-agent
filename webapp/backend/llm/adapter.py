"""LLM 어댑터. LLM_PROVIDER 환경변수가 없으면 자동 mock 모드 (에러 아님).
mock 시나리오 구현은 4단계(조사 채팅)에서 채움."""
import os

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


class LLM:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "mock")

    def call(self, role: str, messages: list, **kw):
        """role: structurize | investigate | judge | answer"""
        if self.provider == "mock":
            return self._mock_call(role, messages, **kw)
        raise NotImplementedError(f"provider={self.provider} 연동은 4단계 이후 구현")

    def _mock_call(self, role: str, messages: list, **kw):
        raise NotImplementedError("mock 시나리오는 4단계에서 구현")
