"""EV6 조사 채팅 데모 시나리오용 수동 seed.

현재는 스텁입니다 — 스펙 9절의 "EV6 유사 신고(실제 확인한 2026-07-04 건 기반)"는
아직 이 세션에서 실제 ODINO/원문을 확인한 적이 없으므로, 검증되지 않은 값을
지어내지 않기 위해 비워둡니다. 4단계(조사 채팅) 작업 시 실제 EV6 불만 레코드를
NHTSA 데이터에서 확인한 뒤 아래 SEED_COMPLAINTS에 출처(ODINO)와 함께 채울 것.
"""

# 각 항목: (odino, model, year, date, text, part_category, symptom, severity) + 출처 주석 필수
SEED_COMPLAINTS: list[dict] = []


def seed(conn):
    if not SEED_COMPLAINTS:
        print("seed_manual: EV6 시나리오 레코드 없음 (4단계에서 실제 확인 후 채울 예정)")
        return
    conn.executemany(
        """INSERT OR IGNORE INTO complaints
           (odino, model, year, date, text, part_category, symptom, severity)
           VALUES (:odino, :model, :year, :date, :text, :part_category, :symptom, :severity)""",
        SEED_COMPLAINTS,
    )
    conn.commit()
