"""webapp/.env 로더. 지금까지 이 프로젝트엔 .env를 실제로 읽어들이는 코드가 없었다
(os.getenv는 진짜 OS 환경변수만 봄) — README가 ".env에 채우고 재시작" 이라 안내해도
실제로는 적용되지 않던 상태였다. python-dotenv를 새 의존성으로 추가하는 대신(CLAUDE.md:
새 의존성 추가 전 확인 요청) 수십 줄짜리 파서로 충분해 직접 구현한다.

이미 설정된 실제 OS 환경변수(예: Docker ENV, 배포 플랫폼의 환경변수)를 덮어쓰지 않는다 —
.env는 로컬 개발용 폴백일 뿐이다.
"""
import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env():
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value
