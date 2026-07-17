"""데모 인증 — 진짜 회원가입/세션 시스템이 아니다. 비밀번호 해싱·세션 보안은 범위 밖.

seed에 심는 test 계정 2개를 코드 상수로 둔다(택1: users 테이블 대신 코드 상수 — 데모용이라
단순하게, CLAUDE.md 작업 지시 원문 그대로). 계정 식별자(email)는 subscriptions 테이블의
account 컬럼 값으로 그대로 쓰인다.
"""

TEST_ACCOUNTS = {
    "user@test.com": {"password": "test", "role": "user"},
    "agent@test.com": {"password": "test", "role": "agent"},
}


def verify_login(email: str, password: str) -> dict | None:
    """일치하면 {"account": 정규화된 email, "role": ...}, 아니면 None."""
    key = email.strip().lower()
    account = TEST_ACCOUNTS.get(key)
    if account is None or account["password"] != password:
        return None
    return {"account": key, "role": account["role"]}
