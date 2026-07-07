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

CREATE TABLE IF NOT EXISTS recalls (
    campaign TEXT PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    title TEXT NOT NULL,
    markdown TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kr_us_gap (
    campaign TEXT PRIMARY KEY,
    us_date TEXT NOT NULL,
    kr_date TEXT,
    gap_days INTEGER,
    note TEXT
);
"""


def init_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()
