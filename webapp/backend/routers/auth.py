"""POST /api/auth/login — 데모 인증(auth.py의 test 계정 2개와 매칭). 진짜 세션·토큰 없음:
성공 시 {account, role}만 돌려주고 프론트가 localStorage에 저장해 이후 요청마다
account 문자열을 그대로 실어 보낸다(비밀번호 해싱·서버 세션은 범위 밖)."""
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auth import verify_login

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(request: Request):
    payload = await request.json()
    email = str(payload.get("email", ""))
    password = str(payload.get("password", ""))
    result = verify_login(email, password)
    if result is None:
        raise HTTPException(status_code=401, detail="계정을 확인하세요")
    return result
