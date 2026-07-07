# Recall Radar — 웹 서비스 초안 v0

차량 결함 조사 Agent의 3화면(상황판 / 조사 채팅 / 내 차) 데모. 전체 명세는 `docs/13_초안v0_스펙.md` 참조.

## 사전 준비

- 백엔드는 conda 환경 `ogc2026`(pandas 2.2.3)을 사용한다. 없으면 새로 만들고 `pip install -r backend/requirements.txt`.
- 프론트는 Node.js + npm (frontend/에서 `npm install` 1회 필요, 이미 되어 있으면 생략).

## 1. DB 시드 (최초 1회, 또는 data/processed·data/recalls 원본이 바뀌었을 때)

```bash
cd webapp/backend
conda run -n ogc2026 python seed.py
```

`data/app.db`가 생성/갱신된다(gitignore 대상 — 지워도 위 명령으로 재생성 가능). 실행하면 콘솔에 적재 정합성 리포트(테이블별 행 수, signals 상태 분포, KPI 등)가 출력된다.

## 2. 백엔드 실행

```bash
cd webapp/backend
conda run -n ogc2026 python -m uvicorn main:app --port 8000 --host 127.0.0.1
```

- `http://127.0.0.1:8000/api/health` → `{"status":"ok"}`이면 정상.
- Windows에서 `--reload` 옵션은 `conda run`과 함께 쓰면 리로더 프로세스가 죽는 문제가 있어 쓰지 않는다. 코드를 고치면 서버를 껐다 다시 켤 것.

## 3. 프론트엔드 실행 (새 터미널)

```bash
cd webapp/frontend
npm run dev
```

- `http://localhost:5173` 접속. `vite.config.ts`의 프록시 설정으로 `/api/*` 요청이 자동으로 `http://127.0.0.1:8000`으로 전달된다 — 백엔드가 먼저 떠 있어야 한다.

## 목(mock) LLM 모드

- `.env.example`을 `webapp/.env`로 복사해서 사용. `LLM_PROVIDER=mock`(기본값)이면 실제 API 키 없이도 조사 채팅이 끝까지 동작한다 — 키가 없는 것은 에러가 아니라 정상 데모 모드다.
- mock 모드는 `backend/llm/mock_responses/{role}/{scenario}.json`의 답변 템플릿을 사용한다. 현재 지원하는 조사 채팅 시나리오 3종:
  1. **EV6 계기판** — 예: "내 차 EV6인데 계기판이 깜빡여요"
  2. **IONIQ 5 충전(ICCU)** — 예: "아이오닉5 충전 중에 12V 배터리 경고가 떠요"
  3. **범위 밖 질문** — 위 두 시나리오에 해당하지 않는 모든 질문(예: "브레이크 오일 언제 갈아요?")

## 실제 LLM 키를 꽂으려면

`webapp/.env`에 아래처럼 채우고 백엔드를 재시작한다.

```
LLM_PROVIDER=anthropic   # 또는 openai
ANTHROPIC_API_KEY=sk-...
OPENAI_API_KEY=sk-...    # judge가 반대 provider로 라우팅되므로 두 키 다 있으면 가장 안정적
```

> v0 현재 시점에는 `llm/adapter.py`의 실제 provider 연동 로직이 아직 구현되어 있지 않다(mock만 지원). 키를 넣어도 `NotImplementedError`가 발생한다 — 실제 연동은 이후 버전 작업.

## 디렉토리

```
webapp/
  frontend/   Vite + React + TypeScript
  backend/    FastAPI + SQLite
  .env.example
```
