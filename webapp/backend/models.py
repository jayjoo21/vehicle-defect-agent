"""SQLite 테이블 DDL. 표준 SQL 문법만 사용 (추후 Postgres 전환 대비)."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS complaints (
    odino TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    year TEXT,
    date TEXT NOT NULL,
    text TEXT NOT NULL,
    part_category TEXT,
    symptom TEXT,
    severity TEXT
);

-- campaign은 PK가 아님: 같은 US 캠페인이 여러 차종에 공통 적용되는 실제 사례가 있어
-- (예: 24V204000이 IONIQ 5·IONIQ 6·Genesis GV60/GV70/G80에 공통 적용), campaign을
-- 유일키로 두면 첫 번째 매칭 차종을 제외한 나머지 차종의 리콜 보유 사실이 유실된다.
CREATE TABLE IF NOT EXISTS recalls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign TEXT NOT NULL,
    country TEXT NOT NULL,
    model TEXT NOT NULL,
    report_date TEXT NOT NULL,
    component TEXT,
    summary TEXT,
    kr_announce_date TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL,
    month TEXT NOT NULL,
    count INTEGER NOT NULL,
    baseline REAL,
    state TEXT NOT NULL,
    top_symptom TEXT,
    report_id INTEGER
);

CREATE TABLE IF NOT EXISTS signal_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL REFERENCES signals(id),
    state TEXT NOT NULL,
    changed_at TEXT NOT NULL
);

-- 6.6단계: 리포트 뷰 메타 헤더 카드(차종/캠페인/기준월/상태) + 핵심 수치 3칸 그리드를 위한 컬럼.
-- model/campaign/reference_month/state는 표시용 메타(지어낸 값 없음, seed.py가 실측/실쿼리로 채움),
-- metrics는 {complaint_count, concentration_pct, lead_days} JSON 문자열(해당 없는 값은 null).
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    title TEXT NOT NULL,
    markdown TEXT NOT NULL,
    created_at TEXT NOT NULL,
    model TEXT,
    campaign TEXT,
    reference_month TEXT,
    state TEXT,
    metrics TEXT
);

-- campaign은 PK가 아님: 같은 US 캠페인이 서로 다른 한국 보도자료 항목(부품별)에
-- 중복 매칭되는 실제 사례가 있어(예: 26V169000이 팰리세이드 보도자료 2건에 매칭),
-- campaign을 유일키로 두면 실측 행이 유실된다.
CREATE TABLE IF NOT EXISTS kr_us_gap (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign TEXT NOT NULL,
    model TEXT,
    defect_summary TEXT,
    date_basis TEXT,
    us_date TEXT,
    kr_date TEXT,
    kr_start_date TEXT,
    gap_days INTEGER,
    note TEXT
);
"""


def init_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()
