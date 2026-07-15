"""
MOBISCOPE STA-01 / STA-02 — 결함 상태 추적 SQLite DB
============================================================
목적
- LLM 구조화 결과와 원본 불만 CSV를 SQLite에 적재한다.
- 특정 ODINO/차종/부품 시그널이 신규(STA-01)인지,
  기존 리콜 후 재발(STA-02)인지 추적한다.
- 대시보드가 조회하기 쉬운 view CSV도 내보낸다.

담당 기능
- STA-01: 리콜 이력이 없는 신규 결함 후보 기록
- STA-02: 기존 리콜과 동일/유사 부품에서 리콜일 이후 재발 신고 기록

주의
- 이 모듈은 SQLite 수준의 상태 DB 뼈대다. 외부 API 호출은 기본 동작에 넣지 않았다.
- NHTSA/국내 리콜 데이터는 register_recall() 또는 import_recall_records()로 넣는다.
- VIN은 저장하지 않는다.
- 저장되는 내용은 미검증 소비자 신고와 분석 결과이며 결함 확정이 아니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import datetime
import json
import sqlite3

import pandas as pd

DEFAULT_CSV_PATH = Path("data/processed/hk_electrical_recent_full.csv")
DEFAULT_JSONL_PATH = Path("data/processed/llm_struct_test_results.jsonl")
DEFAULT_DB_PATH = Path("data/processed/defect_status_tracking.db")
DEFAULT_VIEW_CSV = Path("data/processed/defect_status_view.csv")
FALLBACKS = {
    "csv": [Path("/mnt/data/hk_electrical_recent_full.csv"), Path("hk_electrical_recent_full.csv")],
    "jsonl": [Path("/mnt/data/llm_struct_test_results.jsonl"), Path("/mnt/data/llm_struct_v2_18cases.jsonl"), Path("llm_struct_v2_18cases.jsonl")],
    "db": [Path("/mnt/data/defect_status_tracking_generated.db")],
    "view": [Path("/mnt/data/defect_status_view_generated.csv")],
}

STA_NEW = "STA-01"
STA_RECUR = "STA-02"
STA_LABEL = {
    STA_NEW: "신규 결함 후보",
    STA_RECUR: "기존 리콜 후 재발 후보",
}
VALID_RESOLUTION = {"OPEN", "IN_PROGRESS", "MONITORING", "RESOLVED", "DISMISSED"}
SEVERITY_RANK = {"CRITICAL": 4, "SERIOUS": 3, "MODERATE": 2, "MINOR": 1, "UNKNOWN": 0, None: 0}

# --- 차종×부품카테고리 단위 5단계 시그널 상태 -------------------------------
# defect_status_tracking(위 STA-01/02)은 "신고 1건"이 단위인 이진 판정이고,
# 그 의미는 바뀌지 않는다. 아래 SIGNAL_*은 그 위에 얹는 별도 집계 레이어
# (defect_signals 테이블)로, "이 차종 × 이 부품 카테고리" 그룹 전체의
# 생애주기를 5단계로 추적한다. 실제 판정 로직은 sta_signal_state.py.
SIGNAL_NEW = "NEW"
SIGNAL_RISING = "RISING"
SIGNAL_RECALLED = "RECALLED"
SIGNAL_DORMANT = "DORMANT"
SIGNAL_RECURRING = "RECURRING"
SIGNAL_STATES = (SIGNAL_NEW, SIGNAL_RISING, SIGNAL_RECALLED, SIGNAL_DORMANT, SIGNAL_RECURRING)
SIGNAL_LABEL_KO = {
    SIGNAL_NEW: "신규",
    SIGNAL_RISING: "증가",
    SIGNAL_RECALLED: "리콜",
    SIGNAL_DORMANT: "잠잠",
    SIGNAL_RECURRING: "재발",
}
# 대시보드/채팅 답변에서 우선 검토해야 할 순서(위험도 아님, 관심순).
SIGNAL_PRIORITY_ORDER = {
    SIGNAL_RECURRING: 1, SIGNAL_RISING: 2, SIGNAL_RECALLED: 3, SIGNAL_NEW: 4, SIGNAL_DORMANT: 5,
}

PART_RECALL_KEYWORDS = {
    "ELECTRICAL_SYSTEM": ["ELECTRICAL", "BATTERY", "WIRING", "INSTRUMENT", "CLUSTER", "DISPLAY", "SOFTWARE"],
    "ADAS": ["LANE", "COLLISION", "CAMERA", "RADAR", "SENSOR", "ELECTRONIC STABILITY", "FORWARD"],
    "POWERTRAIN_SW": ["ENGINE", "POWER TRAIN", "THROTTLE", "ECM", "ECU", "SOFTWARE", "FUEL"],
    # 아래 3종은 STR-04 v3 스키마(8종) 확정 시 추가됨(2026-07-13). 기존 3종만 있으면
    # 이 3개 카테고리는 _component_matches()가 항상 False를 반환해 리콜 매칭이
    # 전혀 안 되는 조용한 누락이 생긴다 — INV-01의 PART_CATEGORY_KEYWORDS에도
    # 동일한 갭이 있으나 그 파일은 STA 담당 범위가 아니라 별도로 전달함.
    "INSTRUMENT_CLUSTER": ["INSTRUMENT", "CLUSTER", "DASH", "DISPLAY", "SPEEDOMETER", "GAUGE"],
    "PROPULSION_BATTERY": ["BATTERY", "PROPULSION", "HIGH VOLTAGE", "HV BATTERY", "EV BATTERY", "ICCU", "CHARGING"],
    "BRAKES_ELECTRONIC": ["BRAKE", "BRAKES", "ABS", "ELECTRONIC STABILITY", "ESC"],
    "NON_ELECTRICAL": [],
    "INSUFFICIENT_INFO": [],
}


def _resolve(path: str | Path | None, default: Path, fallbacks: list[Path], *, create_parent: bool = False) -> Path:
    if path is not None:
        p = Path(path)
        if p.exists() or create_parent:
            if create_parent:
                p.parent.mkdir(parents=True, exist_ok=True)
            return p
        if str(p) != str(default):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {p}")
    if default.exists() or create_parent:
        if create_parent:
            default.parent.mkdir(parents=True, exist_ok=True)
        return default
    for fb in fallbacks:
        if fb.exists() or create_parent:
            if create_parent:
                fb.parent.mkdir(parents=True, exist_ok=True)
            return fb
    raise FileNotFoundError(f"파일을 찾을 수 없습니다: {default}")


def get_conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    db = _resolve(db_path, DEFAULT_DB_PATH, FALLBACKS["db"], create_parent=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    conn = get_conn(db_path)
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS vehicles (
            vehicle_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            make         TEXT NOT NULL,
            model        TEXT NOT NULL,
            year         INTEGER,
            created_at   TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(make, model, year)
        );
        CREATE INDEX IF NOT EXISTS idx_vehicles_make_model_year ON vehicles(make, model, year);

        CREATE TABLE IF NOT EXISTS complaint_reports (
            odino          TEXT PRIMARY KEY,
            cmplid         TEXT,
            vehicle_id     INTEGER REFERENCES vehicles(vehicle_id),
            fail_date      TEXT,
            ldate          TEXT,
            component_desc TEXT,
            complaint_text TEXT,
            crash          INTEGER DEFAULT 0,
            fire           INTEGER DEFAULT 0,
            injured        INTEGER DEFAULT 0,
            deaths         INTEGER DEFAULT 0,
            miles          REAL,
            state          TEXT,
            city           TEXT,
            created_at     TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_reports_vehicle ON complaint_reports(vehicle_id);
        CREATE INDEX IF NOT EXISTS idx_reports_fail_date ON complaint_reports(fail_date);
        CREATE INDEX IF NOT EXISTS idx_reports_component ON complaint_reports(component_desc);

        CREATE TABLE IF NOT EXISTS structured_results (
            odino             TEXT PRIMARY KEY REFERENCES complaint_reports(odino),
            part_category     TEXT,
            symptoms_json     TEXT,
            severity          TEXT,
            driving_context   TEXT,
            evidence_quote    TEXT,
            insufficient_info INTEGER DEFAULT 0,
            rule_notes        TEXT,
            created_at        TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_struct_part ON structured_results(part_category);
        CREATE INDEX IF NOT EXISTS idx_struct_severity ON structured_results(severity);

        CREATE TABLE IF NOT EXISTS recall_records (
            recall_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id      INTEGER NOT NULL REFERENCES vehicles(vehicle_id),
            campaign_no     TEXT,
            recall_date     TEXT,
            component       TEXT,
            summary         TEXT,
            source          TEXT DEFAULT 'MANUAL',
            status          TEXT DEFAULT 'OPEN' CHECK(status IN ('OPEN','CLOSED','PARTIAL','UNKNOWN')),
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(vehicle_id, campaign_no)
        );
        CREATE INDEX IF NOT EXISTS idx_recall_vehicle ON recall_records(vehicle_id);
        CREATE INDEX IF NOT EXISTS idx_recall_component ON recall_records(component);
        CREATE INDEX IF NOT EXISTS idx_recall_date ON recall_records(recall_date);

        CREATE TABLE IF NOT EXISTS defect_status_tracking (
            tracking_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            odino             TEXT NOT NULL UNIQUE REFERENCES complaint_reports(odino),
            vehicle_id        INTEGER REFERENCES vehicles(vehicle_id),
            recall_id         INTEGER REFERENCES recall_records(recall_id),
            status_code       TEXT NOT NULL CHECK(status_code IN ('STA-01','STA-02')),
            status_label      TEXT NOT NULL,
            part_category     TEXT,
            severity          TEXT,
            detection_date    TEXT,
            recurrence_basis  TEXT,
            resolution_status TEXT DEFAULT 'OPEN'
                              CHECK(resolution_status IN ('OPEN','IN_PROGRESS','MONITORING','RESOLVED','DISMISSED')),
            resolution_date   TEXT,
            notes             TEXT,
            created_at        TEXT DEFAULT (datetime('now','localtime')),
            updated_at        TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_tracking_status ON defect_status_tracking(status_code);
        CREATE INDEX IF NOT EXISTS idx_tracking_resolution ON defect_status_tracking(resolution_status);
        CREATE INDEX IF NOT EXISTS idx_tracking_severity ON defect_status_tracking(severity);

        CREATE TABLE IF NOT EXISTS status_change_log (
            log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_id  INTEGER NOT NULL REFERENCES defect_status_tracking(tracking_id),
            field_name   TEXT NOT NULL,
            old_value    TEXT,
            new_value    TEXT,
            changed_by   TEXT DEFAULT 'SYSTEM',
            changed_at   TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_log_tracking ON status_change_log(tracking_id);

        -- 차종×부품카테고리 단위 5단계 시그널(신규/증가/리콜/잠잠/재발).
        -- defect_status_tracking(신고 단위)과 별개 테이블 — 기존 의미를 안 건드리고
        -- 그 위에 얹는 집계 레이어. 계산 로직은 sta_signal_state.py.
        CREATE TABLE IF NOT EXISTS defect_signals (
            signal_id            INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id           INTEGER NOT NULL REFERENCES vehicles(vehicle_id),
            part_category        TEXT NOT NULL,
            signal_state         TEXT NOT NULL CHECK(signal_state IN
                                  ('NEW','RISING','RECALLED','DORMANT','RECURRING')),
            recall_id            INTEGER REFERENCES recall_records(recall_id),
            complaint_count      INTEGER NOT NULL DEFAULT 0,
            first_complaint_date TEXT,
            last_complaint_date  TEXT,
            recent_count         INTEGER,
            baseline_count       INTEGER,
            surge_ratio          REAL,
            surge_level          TEXT,
            quiet_months         REAL,
            state_reason         TEXT,
            computed_at          TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(vehicle_id, part_category)
        );
        CREATE INDEX IF NOT EXISTS idx_signals_state ON defect_signals(signal_state);
        CREATE INDEX IF NOT EXISTS idx_signals_vehicle ON defect_signals(vehicle_id);

        CREATE TABLE IF NOT EXISTS signal_state_log (
            log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id    INTEGER NOT NULL REFERENCES defect_signals(signal_id),
            old_state    TEXT,
            new_state    TEXT NOT NULL,
            reason       TEXT,
            changed_at   TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_signal_log_signal ON signal_state_log(signal_id);
        """
    )
    conn.commit()
    _ensure_column(conn, "recall_records", "part_number", "TEXT")
    _ensure_column(conn, "recall_records", "part_family", "TEXT")
    conn.commit()
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
    """이미 만들어져 있던 DB 파일에도 안전하게 컬럼을 추가한다(재실행해도 에러 없음).
    ALTER TABLE ADD COLUMN은 SQLite에서 기존 행을 안 건드리고 NULL로 채우는
    비파괴적 작업이라, 운영 중인 DB에 실행해도 안전하다."""
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def _date_to_iso(value: Any, *, dayfirst: bool = False) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        dt = pd.to_datetime(text, format="%Y%m%d", errors="coerce")
    else:
        dt = pd.to_datetime(text, dayfirst=dayfirst, errors="coerce")
    if pd.isna(dt):
        return None
    return dt.strftime("%Y-%m-%d")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or pd.isna(value):
            return default
        return int(float(value))
    except Exception:
        return default


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def upsert_vehicle(conn: sqlite3.Connection, make: str, model: str, year: int | str | None) -> int:
    make = str(make or "UNKNOWN").strip().upper()
    model = str(model or "UNKNOWN").strip().upper()
    year_int = _safe_int(year, default=None) if year not in (None, "") else None
    row = conn.execute(
        "SELECT vehicle_id FROM vehicles WHERE make=? AND model=? AND year IS ?",
        (make, model, year_int),
    ).fetchone()
    # SQLite의 IS ?가 환경에 따라 어색할 수 있어 보조 조회.
    if not row:
        row = conn.execute(
            "SELECT vehicle_id FROM vehicles WHERE make=? AND model=? AND COALESCE(year,-1)=COALESCE(?,-1)",
            (make, model, year_int),
        ).fetchone()
    if row:
        return int(row["vehicle_id"])
    cur = conn.execute("INSERT INTO vehicles(make, model, year) VALUES(?,?,?)", (make, model, year_int))
    conn.commit()
    return int(cur.lastrowid)


def load_complaints_csv(conn: sqlite3.Connection, csv_path: str | Path | None = None) -> int:
    csv = _resolve(csv_path, DEFAULT_CSV_PATH, FALLBACKS["csv"])
    df = pd.read_csv(csv, dtype=str, low_memory=False, encoding="utf-8-sig")
    df.columns = [str(c).strip().upper() for c in df.columns]
    if "VIN" in df.columns:
        df = df.drop(columns=["VIN"])
    before = len(df)
    if "ODINO" in df.columns:
        df = df.drop_duplicates(subset="ODINO", keep="first")

    inserted = updated = 0
    for _, row in df.iterrows():
        odino = str(row.get("ODINO") or "").strip()
        if not odino:
            continue
        vid = upsert_vehicle(conn, row.get("MAKETXT"), row.get("MODELTXT"), row.get("YEARTXT"))
        payload = (
            odino,
            str(row.get("CMPLID") or "").strip() or None,
            vid,
            _date_to_iso(row.get("FAILDATE")),
            _date_to_iso(row.get("LDATE")),
            str(row.get("COMPDESC") or "").strip() or None,
            str(row.get("CDESCR") or "").strip() or None,
            1 if str(row.get("CRASH") or "").strip().upper() == "Y" else 0,
            1 if str(row.get("FIRE") or "").strip().upper() == "Y" else 0,
            _safe_int(row.get("INJURED")),
            _safe_int(row.get("DEATHS")),
            _safe_float(row.get("MILES")),
            str(row.get("STATE") or "").strip() or None,
            str(row.get("CITY") or "").strip() or None,
        )
        exists = conn.execute("SELECT 1 FROM complaint_reports WHERE odino=?", (odino,)).fetchone()
        conn.execute(
            """
            INSERT INTO complaint_reports
            (odino, cmplid, vehicle_id, fail_date, ldate, component_desc, complaint_text,
             crash, fire, injured, deaths, miles, state, city)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(odino) DO UPDATE SET
                cmplid=excluded.cmplid,
                vehicle_id=excluded.vehicle_id,
                fail_date=excluded.fail_date,
                ldate=excluded.ldate,
                component_desc=excluded.component_desc,
                complaint_text=excluded.complaint_text,
                crash=excluded.crash,
                fire=excluded.fire,
                injured=excluded.injured,
                deaths=excluded.deaths,
                miles=excluded.miles,
                state=excluded.state,
                city=excluded.city
            """,
            payload,
        )
        inserted += 0 if exists else 1
        updated += 1 if exists else 0
    conn.commit()
    print(f"[STA LOAD CSV] source_rows={before:,} unique_odino={len(df):,} inserted={inserted:,} updated={updated:,}")
    return inserted + updated


def load_structured_jsonl(conn: sqlite3.Connection, jsonl_path: str | Path | None = None) -> int:
    path = _resolve(jsonl_path, DEFAULT_JSONL_PATH, FALLBACKS["jsonl"])
    count = 0
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            odino = str(rec.get("odino") or "").strip()
            if not odino:
                continue
            # 원본 CSV에 없는 ODINO도 구조화는 저장 가능하게 최소 complaint row 생성.
            if not conn.execute("SELECT 1 FROM complaint_reports WHERE odino=?", (odino,)).fetchone():
                conn.execute("INSERT OR IGNORE INTO complaint_reports(odino) VALUES(?)", (odino,))
            conn.execute(
                """
                INSERT INTO structured_results
                (odino, part_category, symptoms_json, severity, driving_context,
                 evidence_quote, insufficient_info, rule_notes)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(odino) DO UPDATE SET
                    part_category=excluded.part_category,
                    symptoms_json=excluded.symptoms_json,
                    severity=excluded.severity,
                    driving_context=excluded.driving_context,
                    evidence_quote=excluded.evidence_quote,
                    insufficient_info=excluded.insufficient_info,
                    rule_notes=excluded.rule_notes
                """,
                (
                    odino,
                    rec.get("part_category"),
                    json.dumps(rec.get("symptoms") or [], ensure_ascii=False),
                    rec.get("severity"),
                    rec.get("driving_context"),
                    rec.get("evidence_quote"),
                    1 if rec.get("insufficient_info") else 0,
                    rec.get("v2_rule_notes") or rec.get("rule_notes"),
                ),
            )
            count += 1
    conn.commit()
    print(f"[STA LOAD JSONL] records={count:,} path={path}")
    return count


def register_recall(
    conn: sqlite3.Connection,
    *,
    make: str,
    model: str,
    year: int | str | None,
    campaign_no: str,
    recall_date: str | None,
    component: str,
    summary: str = "",
    source: str = "MANUAL",
    status: str = "OPEN",
    part_number: str | None = None,
    part_family: str | None = None,
) -> int:
    """리콜 이력 수동/외부 적재. STA-02 판정 및 defect_signals 판정의 기준 데이터가 된다.

    part_number/part_family는 RCL573 파이프라인(sta_recall_loader.py)에서만 채워지는
    선택 필드다. recall_date는 None/빈 문자열이어도 안전하게 NULL로 저장된다 — RCL573
    산출물에 리콜일이 없는 경우가 있어(sta_recall_loader.py 문서 참고) 필수값으로 두지
    않았다.
    """
    vid = upsert_vehicle(conn, make, model, year)
    iso_date = _date_to_iso(recall_date, dayfirst=True) if recall_date else None
    cur = conn.execute(
        """
        INSERT INTO recall_records(vehicle_id, campaign_no, recall_date, component, summary, source, status,
                                    part_number, part_family)
        VALUES(?,?,?,?,?,?,?,?,?)
        ON CONFLICT(vehicle_id, campaign_no) DO UPDATE SET
            recall_date=COALESCE(excluded.recall_date, recall_records.recall_date),
            component=excluded.component,
            summary=excluded.summary,
            source=excluded.source,
            status=excluded.status,
            part_number=COALESCE(excluded.part_number, recall_records.part_number),
            part_family=COALESCE(excluded.part_family, recall_records.part_family)
        """,
        (vid, campaign_no, iso_date, component, summary, source, status, part_number, part_family),
    )
    conn.commit()
    row = conn.execute(
        "SELECT recall_id FROM recall_records WHERE vehicle_id=? AND campaign_no=?", (vid, campaign_no)
    ).fetchone()
    return int(row["recall_id"] if row else cur.lastrowid)


def import_recall_records(conn: sqlite3.Connection, recall_csv_path: str | Path) -> int:
    """
    선택 기능: 별도 리콜 CSV를 가져온다.
    필요한 컬럼: make, model, year, campaign_no, recall_date, component
    선택 컬럼: summary, source, status
    """
    df = pd.read_csv(recall_csv_path, dtype=str, encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]
    required = {"make", "model", "year", "campaign_no", "recall_date", "component"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"리콜 CSV 필수 컬럼 누락: {sorted(missing)}")
    n = 0
    for _, row in df.iterrows():
        register_recall(
            conn,
            make=row.get("make"),
            model=row.get("model"),
            year=row.get("year"),
            campaign_no=row.get("campaign_no"),
            recall_date=row.get("recall_date"),
            component=row.get("component"),
            summary=row.get("summary", ""),
            source=row.get("source", "CSV"),
            status=row.get("status", "OPEN") or "OPEN",
        )
        n += 1
    print(f"[STA LOAD RECALL] records={n:,}")
    return n


def _component_matches(part_category: str | None, component_text: str | None) -> bool:
    if not part_category or not component_text:
        return False
    keywords = PART_RECALL_KEYWORDS.get(str(part_category).upper(), [])
    if not keywords:
        return False
    comp = component_text.upper()
    return any(k.upper() in comp for k in keywords)


def find_matching_recall(
    conn: sqlite3.Connection,
    vehicle_id: int | None,
    part_category: str | None,
    detection_date: str | None,
) -> tuple[int | None, str]:
    """
    같은 차량 + 유사 부품 리콜이 있고, 리콜일이 신고일 이전이면 STA-02 후보로 본다.
    날짜가 없으면 같은 차량+부품 리콜 존재만으로 후보를 연결하되 basis에 날짜 불명 표시.
    """
    if not vehicle_id or not part_category:
        return None, "vehicle_id 또는 part_category 없음"
    rows = conn.execute(
        "SELECT * FROM recall_records WHERE vehicle_id=? ORDER BY recall_date DESC", (vehicle_id,)
    ).fetchall()
    for r in rows:
        if not _component_matches(part_category, r["component"]):
            continue
        recall_date = r["recall_date"]
        if detection_date and recall_date:
            if recall_date <= detection_date:
                return int(r["recall_id"]), f"동일 차량·유사 부품 리콜({r['campaign_no']}, {recall_date}) 이후 신고"
            # 리콜이 신고 뒤에 있으면 '재발'이 아니라 당시에는 신규 시그널로 둔다.
            continue
        return int(r["recall_id"]), f"동일 차량·유사 부품 리콜({r['campaign_no']}) 존재, 날짜 비교 불완전"
    return None, "동일 차량·유사 부품의 과거 리콜 이력 없음"


def find_all_matching_recalls(
    conn: sqlite3.Connection,
    vehicle_id: int | None,
    part_category: str | None,
) -> tuple[int | None, str, str | None]:
    """
    find_matching_recall()과의 차이: 그건 "신고 1건이 리콜 이후 재발인가"(날짜 선후 필수)를
    묻고, 이건 "이 차종×부품카테고리에 리콜이 존재하는가"(날짜 무관)만 묻는다.
    defect_signals 시그널 판정(sta_signal_state.py)에 쓰인다.

    반환: (recall_id 또는 None, 판정 근거 설명, recall_date 또는 None)
    recall_date가 있는 레코드를 우선하고, 그중 최신순으로 첫 매치를 반환한다.
    """
    if not vehicle_id or not part_category:
        return None, "vehicle_id 또는 part_category 없음", None
    rows = conn.execute(
        "SELECT * FROM recall_records WHERE vehicle_id=? "
        "ORDER BY (recall_date IS NULL) ASC, recall_date DESC",
        (vehicle_id,),
    ).fetchall()
    for r in rows:
        if _component_matches(part_category, r["component"]):
            return (
                int(r["recall_id"]),
                f"리콜({r['campaign_no']}) 매칭: {r['component']}",
                r["recall_date"],
            )
    return None, "동일 차량·유사 부품의 리콜 이력 없음", None


def classify_and_track(conn: sqlite3.Connection, odino: str, *, notes: str | None = None) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            cr.odino, cr.vehicle_id, cr.fail_date,
            sr.part_category, sr.severity, sr.insufficient_info
        FROM complaint_reports cr
        LEFT JOIN structured_results sr ON cr.odino = sr.odino
        WHERE cr.odino=?
        """,
        (str(odino),),
    ).fetchone()
    if not row:
        raise ValueError(f"ODINO {odino} 원본 신고 없음")

    recall_id, basis = find_matching_recall(
        conn,
        row["vehicle_id"],
        row["part_category"],
        row["fail_date"],
    )
    status_code = STA_RECUR if recall_id else STA_NEW
    status_label = STA_LABEL[status_code]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    existing = conn.execute(
        "SELECT tracking_id, status_code, resolution_status FROM defect_status_tracking WHERE odino=?",
        (odino,),
    ).fetchone()

    if existing:
        tid = int(existing["tracking_id"])
        old_code = existing["status_code"]
        conn.execute(
            """
            UPDATE defect_status_tracking
            SET vehicle_id=?, recall_id=?, status_code=?, status_label=?, part_category=?, severity=?,
                detection_date=?, recurrence_basis=?, notes=COALESCE(?, notes), updated_at=?
            WHERE tracking_id=?
            """,
            (
                row["vehicle_id"], recall_id, status_code, status_label, row["part_category"], row["severity"],
                row["fail_date"], basis, notes, now, tid,
            ),
        )
        if old_code != status_code:
            conn.execute(
                "INSERT INTO status_change_log(tracking_id, field_name, old_value, new_value) VALUES(?,?,?,?)",
                (tid, "status_code", old_code, status_code),
            )
        action = "UPDATE"
    else:
        cur = conn.execute(
            """
            INSERT INTO defect_status_tracking
            (odino, vehicle_id, recall_id, status_code, status_label, part_category, severity,
             detection_date, recurrence_basis, notes)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                odino, row["vehicle_id"], recall_id, status_code, status_label, row["part_category"], row["severity"],
                row["fail_date"], basis, notes,
            ),
        )
        tid = int(cur.lastrowid)
        action = "INSERT"
    conn.commit()
    return {
        "tracking_id": tid,
        "odino": odino,
        "status_code": status_code,
        "status_label": status_label,
        "part_category": row["part_category"],
        "severity": row["severity"],
        "recall_id": recall_id,
        "recurrence_basis": basis,
        "action": action,
    }


def classify_all(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT odino FROM structured_results ORDER BY odino").fetchall()
    results: list[dict[str, Any]] = []
    for r in rows:
        try:
            results.append(classify_and_track(conn, r["odino"]))
        except Exception as e:
            print(f"[STA CLASSIFY WARN] ODINO={r['odino']} {e}")
    counts = pd.Series([x["status_code"] for x in results]).value_counts().to_dict() if results else {}
    print(f"[STA CLASSIFY] total={len(results):,} counts={counts}")
    return results


def update_resolution(
    conn: sqlite3.Connection,
    odino: str,
    resolution_status: str,
    *,
    resolution_date: str | None = None,
    notes: str | None = None,
    changed_by: str = "SYSTEM",
) -> None:
    status = str(resolution_status).upper()
    if status not in VALID_RESOLUTION:
        raise ValueError(f"resolution_status는 {sorted(VALID_RESOLUTION)} 중 하나여야 합니다.")
    row = conn.execute(
        "SELECT tracking_id, resolution_status FROM defect_status_tracking WHERE odino=?", (odino,)
    ).fetchone()
    if not row:
        raise ValueError(f"ODINO {odino} 추적 레코드 없음")
    old = row["resolution_status"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        UPDATE defect_status_tracking
        SET resolution_status=?, resolution_date=COALESCE(?, resolution_date),
            notes=COALESCE(?, notes), updated_at=?
        WHERE odino=?
        """,
        (status, _date_to_iso(resolution_date) if resolution_date else None, notes, now, odino),
    )
    if old != status:
        conn.execute(
            """
            INSERT INTO status_change_log(tracking_id, field_name, old_value, new_value, changed_by)
            VALUES(?,?,?,?,?)
            """,
            (row["tracking_id"], "resolution_status", old, status, changed_by),
        )
    conn.commit()


def query_status_summary(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT
            dst.tracking_id,
            dst.odino,
            v.make, v.model, v.year,
            dst.status_code,
            dst.status_label,
            dst.part_category,
            dst.severity,
            dst.detection_date,
            dst.recurrence_basis,
            dst.resolution_status,
            r.campaign_no,
            r.recall_date,
            r.component AS recall_component,
            dst.updated_at
        FROM defect_status_tracking dst
        LEFT JOIN vehicles v ON dst.vehicle_id = v.vehicle_id
        LEFT JOIN recall_records r ON dst.recall_id = r.recall_id
        ORDER BY
            CASE dst.status_code WHEN 'STA-02' THEN 1 ELSE 2 END,
            CASE dst.severity WHEN 'CRITICAL' THEN 1 WHEN 'SERIOUS' THEN 2 WHEN 'MODERATE' THEN 3 WHEN 'MINOR' THEN 4 ELSE 5 END,
            dst.detection_date DESC
        """,
        conn,
    )


def export_status_view(conn: sqlite3.Connection, out_path: str | Path | None = None) -> Path:
    out = _resolve(out_path, DEFAULT_VIEW_CSV, FALLBACKS["view"], create_parent=True)
    df = query_status_summary(conn)
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[STA EXPORT] path={out} rows={len(df):,}")
    return out


def upsert_signal_state(conn: sqlite3.Connection, signal: dict[str, Any]) -> dict[str, Any]:
    """
    sta_signal_state.py가 계산한 판정 결과 dict 하나를 defect_signals에 INSERT/UPDATE하고,
    상태가 바뀐 경우에만 signal_state_log에 이력을 남긴다.

    이 함수는 순수 저장 담당이다 — "무엇이 신규/증가/리콜/잠잠/재발인지" 판단하는
    로직은 여기 없다(sta_signal_state.compute_signal_state가 담당). 스키마를 아는
    코드는 이 파일 하나로 모아 SQL이 여러 파일에 흩어지지 않게 했다.

    signal 필수 키: vehicle_id, part_category, signal_state, state_reason
    선택 키(없으면 None/0으로 저장): recall_id, complaint_count, first_complaint_date,
    last_complaint_date, recent_count, baseline_count, surge_ratio, surge_level, quiet_months
    """
    if signal["signal_state"] not in SIGNAL_STATES:
        raise ValueError(f"알 수 없는 signal_state: {signal['signal_state']!r} (허용: {SIGNAL_STATES})")

    existing = conn.execute(
        "SELECT signal_id, signal_state FROM defect_signals WHERE vehicle_id=? AND part_category=?",
        (signal["vehicle_id"], signal["part_category"]),
    ).fetchone()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    g = lambda k, default=None: signal.get(k, default)

    if existing:
        sid = int(existing["signal_id"])
        old_state = existing["signal_state"]
        conn.execute(
            """
            UPDATE defect_signals SET
                signal_state=?, recall_id=?, complaint_count=?, first_complaint_date=?,
                last_complaint_date=?, recent_count=?, baseline_count=?, surge_ratio=?,
                surge_level=?, quiet_months=?, state_reason=?, computed_at=?
            WHERE signal_id=?
            """,
            (signal["signal_state"], g("recall_id"), g("complaint_count", 0), g("first_complaint_date"),
             g("last_complaint_date"), g("recent_count"), g("baseline_count"), g("surge_ratio"),
             g("surge_level"), g("quiet_months"), signal["state_reason"], now, sid),
        )
        if old_state != signal["signal_state"]:
            conn.execute(
                "INSERT INTO signal_state_log(signal_id, old_state, new_state, reason) VALUES(?,?,?,?)",
                (sid, old_state, signal["signal_state"], signal["state_reason"]),
            )
    else:
        cur = conn.execute(
            """
            INSERT INTO defect_signals(
                vehicle_id, part_category, signal_state, recall_id, complaint_count,
                first_complaint_date, last_complaint_date, recent_count, baseline_count,
                surge_ratio, surge_level, quiet_months, state_reason
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (signal["vehicle_id"], signal["part_category"], signal["signal_state"], g("recall_id"),
             g("complaint_count", 0), g("first_complaint_date"), g("last_complaint_date"), g("recent_count"),
             g("baseline_count"), g("surge_ratio"), g("surge_level"), g("quiet_months"), signal["state_reason"]),
        )
        sid = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO signal_state_log(signal_id, old_state, new_state, reason) VALUES(?,?,?,?)",
            (sid, None, signal["signal_state"], signal["state_reason"]),
        )
    conn.commit()
    out = dict(signal)
    out["signal_id"] = sid
    return out


def query_signal_summary(conn: sqlite3.Connection) -> pd.DataFrame:
    """defect_signals를 차량/리콜 정보와 조인해 대시보드·CHT-01이 바로 쓰기 좋은 형태로 반환."""
    return pd.read_sql_query(
        """
        SELECT
            ds.signal_id, v.make, v.model, v.year,
            ds.part_category, ds.signal_state, ds.complaint_count,
            ds.first_complaint_date, ds.last_complaint_date,
            ds.recent_count, ds.baseline_count, ds.surge_ratio, ds.surge_level,
            ds.quiet_months, ds.state_reason,
            r.campaign_no, r.recall_date, r.source AS recall_source,
            ds.computed_at
        FROM defect_signals ds
        LEFT JOIN vehicles v ON ds.vehicle_id = v.vehicle_id
        LEFT JOIN recall_records r ON ds.recall_id = r.recall_id
        ORDER BY
            CASE ds.signal_state
                WHEN 'RECURRING' THEN 1 WHEN 'RISING' THEN 2 WHEN 'RECALLED' THEN 3
                WHEN 'NEW' THEN 4 WHEN 'DORMANT' THEN 5 ELSE 6
            END,
            ds.last_complaint_date DESC
        """,
        conn,
    )


def export_signal_view(conn: sqlite3.Connection, out_path: str | Path | None = None) -> Path:
    default = DEFAULT_VIEW_CSV.parent / "defect_signal_view.csv"
    out = _resolve(out_path, default, [p.parent / "defect_signal_view_generated.csv" for p in FALLBACKS["view"]], create_parent=True)
    df = query_signal_summary(conn)
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[STA EXPORT] path={out} rows={len(df):,}")
    return out


def run_status_tracking(
    *,
    csv_path: str | Path | None = None,
    jsonl_path: str | Path | None = None,
    db_path: str | Path | None = None,
    out_csv: str | Path | None = None,
) -> sqlite3.Connection:
    conn = init_db(db_path)
    load_complaints_csv(conn, csv_path)
    load_structured_jsonl(conn, jsonl_path)
    classify_all(conn)
    export_status_view(conn, out_csv)
    return conn


if __name__ == "__main__":
    conn0 = run_status_tracking()
    print(query_status_summary(conn0).head(20).to_string(index=False))
    conn0.close()
