"""표시용 원문 텍스트 정리 유틸 (내용 변경 없음, 표시 정리만). chat.py/signals.py/vehicles.py가
공유 — 세 곳 모두 같은 complaints.text 원본을 인용하므로 정리 로직도 하나로 통일한다."""


def fix_mojibake(text: str) -> str:
    """UTF-8 원문이 latin-1로 잘못 디코딩되어 저장된 경우(예: 'it's' -> 'itâ€™s')를 복원한다.
    complaints.text 276건 확인(모두 스마트따옴표류 â€™/â€œ/â€ 패턴). latin1로 재인코딩 후
    utf-8로 재디코딩하는 왕복 변환이며, 순수 ASCII 텍스트는 두 인코딩에서 바이트가 동일해
    변화 없이 그대로 반환된다 — 내용을 새로 짓는 게 아니라 잘못된 디코딩을 되돌리는 것."""
    try:
        return text.encode("latin1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def clean_quote(text: str | None) -> str:
    """NHTSA 원문 인용의 개행·중복 공백 정리 + 인코딩 복원(내용 변경 없음, 표시용 정리만)."""
    return fix_mojibake(" ".join((text or "").split()))
