import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from routers import chat, reports, signals, vehicles

app = FastAPI(title="MOBISCOPE API")

# 배포 환경(Docker)은 프론트를 이 서버가 같은 오리진에서 직접 서빙하므로 CORS가 필요 없다.
# 로컬 개발(Vite :5173 → 이 서버 :8000)만 origin이 갈리므로 그때만 명시 허용.
_allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(signals.router, prefix="/api")
app.include_router(vehicles.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(chat.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# 빌드된 프론트(webapp/frontend/dist)가 있으면(Docker 이미지) 같은 서버에서 정적 파일로
# 서빙한다. 로컬 개발 중엔 이 디렉터리가 없어(Vite가 따로 서빙) 아래 라우트는 등록되지 않는다.
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        """SPA fallback: 정적 자산은 그대로, 그 외 경로(/chat, /my-car 등)는 index.html로
        돌려 클라이언트 라우터(react-router)가 처리하게 한다. /api/*는 위에서 이미 매칭되어
        이 catch-all까지 오지 않는다."""
        if full_path.startswith("api/"):
            # 등록된 API 라우터에 없는 /api/* 경로 — SPA 셸을 돌려주지 않고 진짜 404를 낸다.
            raise HTTPException(status_code=404)
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
