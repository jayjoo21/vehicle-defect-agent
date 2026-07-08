# 빌드 컨텍스트는 반드시 저장소 루트여야 한다 (scripts/, data/processed, data/recalls를
# 참조하기 때문). 저장소 루트에서 다음과 같이 빌드한다:
#   docker build -f webapp/Dockerfile -t precall .
#   docker run -p 8000:8000 precall

# ---- 1단계: 프론트엔드 빌드 ----
FROM node:20-slim AS frontend-build
WORKDIR /app/webapp/frontend
COPY webapp/frontend/package.json webapp/frontend/package-lock.json ./
RUN npm ci
COPY webapp/frontend/ ./
RUN npm run build

# ---- 2단계: 백엔드 + DB 시드 + 정적 파일 ----
FROM python:3.11-slim AS final
WORKDIR /app

# engine/normalize.py가 REPO_ROOT/scripts/precision_v2.py를 import (차종명 정규화 재사용)
COPY scripts/precision_v2.py scripts/precision_v2.py

# seed.py/seed_manual.py가 읽는 실측 산출물만 포함 (data/raw는 1.46GB 원본이라 절대 포함 금지)
COPY data/processed data/processed
COPY data/recalls data/recalls

COPY webapp/backend webapp/backend
RUN pip install --no-cache-dir -r webapp/backend/requirements.txt

# 목(mock) 모드 DB를 빌드 시점에 미리 구워 이미지에 포함 (API 키 불필요)
RUN cd webapp/backend && python seed.py

COPY --from=frontend-build /app/webapp/frontend/dist webapp/frontend/dist

ENV LLM_PROVIDER=mock
ENV PORT=8000
WORKDIR /app/webapp/backend
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
