"""DB 스키마 초기화 + 목데이터 적재. 실측 데이터 적재 로직은 2단계에서 채움."""
from db import get_connection
from models import init_schema


def seed():
    conn = get_connection()
    init_schema(conn)
    conn.close()
    print("schema initialized (data seeding: step 2)")


if __name__ == "__main__":
    seed()
