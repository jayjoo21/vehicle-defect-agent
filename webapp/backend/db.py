"""SQLite 연결 헬퍼. 테이블 정의는 models.py, 데이터 적재는 seed.py."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: /api/chat의 SSE 스트리밍처럼 FastAPI가 동기 Depends를
    # 스레드풀에서 생성한 커넥션을 이후 이벤트루프 스레드에서 순차적으로(동시아님) 계속
    # 사용하는 경우가 있어 필요. 요청마다 커넥션을 새로 만들고 요청 종료 시 바로 닫으므로
    # (get_db) 커넥션이 여러 요청에 걸쳐 동시 공유되지는 않는다.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """FastAPI Depends용 요청 스코프 커넥션."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
