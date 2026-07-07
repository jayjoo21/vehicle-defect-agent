"""POST /api/chat (SSE 스트림). 4단계에서 구현."""
from fastapi import APIRouter

router = APIRouter(tags=["chat"])


@router.post("/chat")
def post_chat():
    raise NotImplementedError("4단계에서 구현")
